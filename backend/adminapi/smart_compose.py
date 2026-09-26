"""智能组卷 V2 —— 三阶段定向组卷系统。

重新设计的组卷流程，解决旧方案"遍历全题库 + LLM 选题"的性能瓶颈：

    Phase 1  知识点掌握度分析
        聚合所有用户的答题历史（historys），计算每个知识点的掌握率，
        识别薄弱环节 → 确定考试重点方向

    Phase 2  考试蓝图生成
        根据考试类型（月考/期中/期末）+ 掌握度分析 + 用户配置，
        生成知识板块权重分配方案（可选 LLM 辅助，payload 极小）

    Phase 3  定向题目检索
        通过知识点索引（kp_question_index）O(1) 查找题目 ID 列表，
        按难度 + 题型筛选后随机抽样 → 组装试卷
        不遍历题库，不依赖 LLM，支持数十万题规模

性能特征：
    - Phase 1: O(H×A)  H=答题记录数, A=平均每份答题数（内存计算）
    - Phase 2: O(K)    K=知识点数量（规则计算或小 payload LLM 调用）
    - Phase 3: O(S×Q)  S=知识板块数(3-15), Q=每板块查询数（索引查找）
    - 不随题库总题量增长 → 支持 10 万+ 题目规模

作者：WorkBuddy AI
"""
import hashlib
import json
import logging
import random
from collections import defaultdict

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from core.models import Document
from .ai_jobs import AIJobManager

logger = logging.getLogger(__name__)

# ---- 考试类型配置 ----
EXAM_TYPE_CONFIG = {
    'monthly': {
        'label': '月考',
        'kp_count_range': (3, 6),       # 聚焦 3-6 个知识点
        'weakness_weight': 0.7,         # 70% 权重给薄弱知识点
        'coverage_weight': 0.3,         # 30% 权重给覆盖面
        'difficulty_bias': {'easy': -5, 'medium': 0, 'hard': 5},  # 月考偏难
    },
    'midterm': {
        'label': '期中考试',
        'kp_count_range': (6, 10),
        'weakness_weight': 0.4,
        'coverage_weight': 0.6,
        'difficulty_bias': {},
    },
    'final': {
        'label': '期末考试',
        'kp_count_range': (10, 20),
        'weakness_weight': 0.25,
        'coverage_weight': 0.75,
        'difficulty_bias': {'easy': 5, 'medium': 0, 'hard': -5},  # 期末偏基础
    },
    'mock': {
        'label': '模拟考试',
        'kp_count_range': (8, 15),
        'weakness_weight': 0.3,
        'coverage_weight': 0.7,
        'difficulty_bias': {},
    },
    'custom': {
        'label': '自定义',
        'kp_count_range': (3, 25),
        'weakness_weight': 0.5,
        'coverage_weight': 0.5,
        'difficulty_bias': {},
    },
}

KP_INDEX_COLLECTION = 'kp_question_index'
KP_INDEX_TTL_HOURS = 6  # 索引有效期，超时自动重建


# ===========================================================================
# Phase 0: 知识点索引（预处理，为 Phase 3 提供快速查找能力）
# ===========================================================================

class KnowledgePointIndex:
    """知识点 → 题目索引，支持 O(1) 定向检索。

    索引结构（存储在 Document collection='kp_question_index'）::

        {
            examid: "subject_001",
            kp_name: "函数与导数",
            total_questions: 45,
            by_qtype_difficulty: {
                "single": {"easy": ["q1","q3"], "medium": ["q2"], "hard": ["q5"]},
                "judge":  {"easy": ["q7"], ...},
                ...
            },
            question_ids: ["q1","q2","q3",...],  # 全量 ID（用于无过滤时快速取全部）
            updated_at: "2026-09-24T20:00:00"
        }

    查找流程：
        1. 计算索引 key = f"{examid}_{md5(kp_name)[:8]}"
        2. 从 Document 读取索引文档
        3. 按 qtype + difficulty 从 by_qtype_difficulty 取题目 ID 列表
        4. random.sample 抽样
        5. 按 ID 批量取题目详情

    复杂度：O(1) 索引查找 + O(k) 取 k 道题目详情，与题库总量无关。
    """

    COLLECTION = KP_INDEX_COLLECTION

    @staticmethod
    def _index_key(examid, kp_name):
        """生成索引文档 ID。"""
        h = hashlib.md5(kp_name.encode('utf-8')).hexdigest()[:8]
        return f"{examid}_{h}"

    # ---- 索引构建 ----

    @classmethod
    def build_index(cls, examid, force=False):
        """为指定科目构建知识点索引。

        Args:
            examid: 科目 ID
            force: True 强制重建（忽略 TTL）

        Returns:
            (kp_count, total_questions) 知识点数量和总题目数

        流程：
            1. 检查索引是否已存在且未过期（除非 force=True）
            2. 加载该科目所有题目（仅读取 id + qtype + difficulty + knowledge_points）
            3. 按 kp_name → qtype → difficulty 分组
            4. 存储为索引文档（每个知识点一个文档）
        """
        # 检查是否需要重建
        if not force:
            existing = Document.objects.filter(
                collection=cls.COLLECTION,
                data__examid=str(examid),
            ).first()
            if existing:
                updated_at = existing.data.get('updated_at', '')
                if updated_at:
                    from django.utils.dateparse import parse_datetime
                    try:
                        dt = parse_datetime(updated_at)
                        if dt and (timezone.now() - dt).total_seconds() < KP_INDEX_TTL_HOURS * 3600:
                            logger.info('KP index for %s is fresh (age < %dh), skip rebuild',
                                        examid, KP_INDEX_TTL_HOURS)
                            # 返回现有索引统计
                            all_docs = Document.objects.filter(
                                collection=cls.COLLECTION, data__examid=str(examid))
                            total = sum(d.data.get('total_questions', 0) for d in all_docs)
                            return all_docs.count(), total
                    except (ValueError, TypeError):
                        pass  # 解析失败，继续重建

        logger.info('Building KP index for subject %s ...', examid)

        # 加载该科目所有题目
        qs = Document.objects.filter(collection='questions')
        if examid:
            qs = qs.filter(Q(data__examid=str(examid)) | Q(data__examid=examid))

        # 构建索引：kp_name → qtype → difficulty → [question_ids]
        kp_index = {}  # kp_name → {qtype: {difficulty: [ids]}}

        for doc in qs:
            d = doc.data or {}
            ai_analysis = d.get('ai_analysis') or {}
            qtype = d.get('qtype', '')
            difficulty = ai_analysis.get('difficulty') or d.get('difficulty') or 'medium'
            doc_id = doc.doc_id or str(doc.pk)

            for kp in (ai_analysis.get('knowledge_points') or []):
                if isinstance(kp, dict) and kp.get('name'):
                    kp_name = kp['name']
                    if kp_name not in kp_index:
                        kp_index[kp_name] = {}
                    if qtype not in kp_index[kp_name]:
                        kp_index[kp_name][qtype] = defaultdict(list)
                    kp_index[kp_name][qtype][difficulty].append(doc_id)

        # 存储索引文档
        now = timezone.now().isoformat()
        total_questions = 0

        for kp_name, qtype_map in kp_index.items():
            index_key = cls._index_key(examid, kp_name)
            # 统计该 KP 的总题目数
            kp_total = sum(len(ids) for qt_map in qtype_map.values() for ids in qt_map.values())
            total_questions += kp_total

            # 扁平化所有题目 ID（用于无过滤时快速取全部）
            all_ids = []
            for qt_map in qtype_map.values():
                for ids in qt_map.values():
                    all_ids.extend(ids)

            index_data = {
                'examid': str(examid),
                'kp_name': kp_name,
                'total_questions': kp_total,
                'by_qtype_difficulty': {
                    qt: dict(diff_map) for qt, diff_map in qtype_map.items()
                },
                'question_ids': all_ids,
                'updated_at': now,
            }

            # Upsert
            try:
                doc = Document.objects.get(collection=cls.COLLECTION, doc_id=index_key)
                doc.data = index_data
                doc.save(update_fields=['data'])
            except Document.DoesNotExist:
                Document.objects.create(
                    collection=cls.COLLECTION,
                    doc_id=index_key,
                    data=index_data,
                )

        logger.info('KP index built: %d knowledge points, %d questions for subject %s',
                     len(kp_index), total_questions, examid)
        return len(kp_index), total_questions

    # ---- 索引查询 ----

    @classmethod
    def get_question_ids(cls, examid, kp_name, qtype=None, difficulty=None):
        """按知识点 + 题型 + 难度检索题目 ID 列表。

        Returns:
            list[str] 题目 ID 列表（未抽样，调用方按需 random.sample）
        """
        index_key = cls._index_key(examid, kp_name)
        try:
            doc = Document.objects.get(collection=cls.COLLECTION, doc_id=index_key)
        except Document.DoesNotExist:
            return []

        data = doc.data or {}
        by_qt_diff = data.get('by_qtype_difficulty', {})

        if qtype and difficulty:
            return by_qt_diff.get(qtype, {}).get(difficulty, [])
        elif qtype:
            result = []
            for diff_ids in by_qt_diff.get(qtype, {}).values():
                result.extend(diff_ids)
            return result
        elif difficulty:
            result = []
            for qt_map in by_qt_diff.values():
                result.extend(qt_map.get(difficulty, []))
            return result
        else:
            return data.get('question_ids', [])

    @classmethod
    def list_knowledge_points(cls, examid):
        """列出某科目所有已索引的知识点。

        Returns:
            list[{name, total_questions}]
        """
        qs = Document.objects.filter(
            collection=cls.COLLECTION, data__examid=str(examid))
        return [
            {
                'name': d.data.get('kp_name', ''),
                'total_questions': d.data.get('total_questions', 0),
            }
            for d in qs
        ]

    @classmethod
    def get_index_stats(cls, examid):
        """获取索引统计信息。"""
        qs = Document.objects.filter(
            collection=cls.COLLECTION, data__examid=str(examid))
        kp_list = []
        total = 0
        for d in qs:
            data = d.data or {}
            kp_total = data.get('total_questions', 0)
            total += kp_total
            kp_list.append({
                'name': data.get('kp_name', ''),
                'total_questions': kp_total,
                'updated_at': data.get('updated_at', ''),
            })
        return {
            'examid': str(examid),
            'kp_count': len(kp_list),
            'total_questions': total,
            'knowledge_points': sorted(kp_list, key=lambda x: x['total_questions'], reverse=True),
        }


# ===========================================================================
# Phase 1: 知识点掌握度分析
# ===========================================================================

class KnowledgeMasteryAnalyzer:
    """跨用户知识点掌握度分析器。

    从答题历史（historys）聚合每个知识点的掌握情况，
    为考试蓝图生成提供数据支撑。

    数据来源：
        - historys 集合：所有用户的考试/练习记录
        - questions 集合：题目知识点标注（ai_analysis.knowledge_points）

    分析流程：
        1. 加载该科目所有题目，构建 question_id → [kp_names] 映射
        2. 加载该科目所有答题历史
        3. 逐题统计：对每道已答题目，查其知识点 → 更新该 KP 的 correct/total
        4. 计算掌握率 = correct / total
        5. 按薄弱程度排序（掌握率低 → 薄弱 → 排前面）

    复杂度：O(Q + H×A)
        Q = 科目题目数, H = 答题记录数, A = 平均每份答题数
        全程内存计算，不随题库总量增长。
    """

    @staticmethod
    def _extract_subject_id(h_data):
        """从答题历史中提取科目 ID。

        historys 的 subject 字段可能是完整对象 {_id, code, name} 或字符串。
        """
        subject = h_data.get('subject')
        if isinstance(subject, dict):
            return str(subject.get('_id') or subject.get('code') or '')
        if isinstance(subject, str):
            return subject
        return ''

    @classmethod
    def analyze(cls, examid):
        """分析指定科目的知识点掌握情况。

        Args:
            examid: 科目 ID

        Returns:
            list[dict] 知识点掌握报告，按薄弱程度降序排列::

                [{
                    'knowledge_point': '函数与导数',
                    'total_answered': 120,   # 总作答人次
                    'correct_count': 54,     # 正确人次
                    'mastery_rate': 0.45,    # 掌握率
                    'weakness_score': 0.55,  # 薄弱分（1 - mastery_rate）
                }, ...]
        """
        from .ai_services import normalize_history_items, make_question_lookup

        examid_str = str(examid)

        # 1. 加载题目，构建 question_id → [kp_names] 映射
        qs = Document.objects.filter(
            collection='questions'
        ).filter(Q(data__examid=examid_str) | Q(data__examid=examid))

        qid_to_kps = {}
        for q in qs:
            doc_id = q.doc_id or str(q.pk)
            ai = (q.data or {}).get('ai_analysis') or {}
            kps = []
            for kp in (ai.get('knowledge_points') or []):
                if isinstance(kp, dict) and kp.get('name'):
                    kps.append(kp['name'])
            if kps:
                qid_to_kps[doc_id] = kps

        if not qid_to_kps:
            logger.warning('No questions with knowledge points found for subject %s', examid)
            return []

        # 2. 加载答题历史（按科目过滤）
        all_historys = Document.objects.filter(collection='historys')
        # historys 的 subject 字段是对象，SQLite JSON 查询不可靠，内存过滤
        subject_historys = []
        for h in all_historys:
            h_subj = cls._extract_subject_id(h.data or {})
            if h_subj == examid_str or h_subj == str(examid):
                subject_historys.append(h)

        if not subject_historys:
            logger.info('No exam history found for subject %s', examid)
            return []

        # 3. 逐题统计知识点掌握情况
        question_lookup = make_question_lookup()
        kp_stats = defaultdict(lambda: {'total': 0, 'correct': 0})

        for h in subject_historys:
            h_data = h.data or {}
            items = normalize_history_items(h_data, question_lookup)
            for item in items:
                qid = item.get('questionId', '')
                is_correct = item.get('is_correct')
                if is_correct is None:
                    continue  # 无法判定对错，跳过
                for kp_name in qid_to_kps.get(qid, []):
                    kp_stats[kp_name]['total'] += 1
                    if is_correct:
                        kp_stats[kp_name]['correct'] += 1

        # 4. 计算掌握率
        report = []
        for kp_name, stats in kp_stats.items():
            total = stats['total']
            correct = stats['correct']
            rate = correct / total if total > 0 else 0
            report.append({
                'knowledge_point': kp_name,
                'total_answered': total,
                'correct_count': correct,
                'mastery_rate': round(rate, 3),
                'weakness_score': round(1 - rate, 3),
            })

        # 按薄弱程度降序（最薄弱的排最前）
        report.sort(key=lambda x: (-x['weakness_score'], -x['total_answered']))
        return report


# ===========================================================================
# Phase 2: 考试蓝图生成
# ===========================================================================

class ExamBlueprintGenerator:
    """考试蓝图生成器。

    根据考试类型 + 知识点掌握分析 + 用户配置，
    生成知识板块权重分配方案。

    考试类型策略：
        - 月考: 聚焦 3-6 个薄弱知识点，70% 权重给薄弱环节
        - 期中: 6-10 个知识点，40% 薄弱 + 60% 覆盖
        - 期末: 10-20 个知识点，25% 薄弱 + 75% 覆盖，偏基础
        - 模拟: 8-15 个知识点，30% 薄弱 + 70% 覆盖
        - 自定义: 用户指定，均衡分配

    蓝图结构::

        {
            exam_type: "final",
            sections: [{
                knowledge_point: "函数与导数",
                weight: 0.15,
                question_count: 3,
                total_score: 15,
                questions: [{
                    qtype: "single",
                    count: 2,
                    score_per_question: 5,
                    difficulty_dist: {"easy": 1, "medium": 1, "hard": 0}
                }]
            }],
            total_count: 20,
            total_score: 100
        }
    """

    @classmethod
    def generate(cls, exam_type, examid, mastery_report, user_config, use_llm=True):
        """生成考试蓝图。

        Args:
            exam_type: 考试类型 (monthly/midterm/final/mock/custom)
            examid: 科目 ID
            mastery_report: KnowledgeMasteryAnalyzer.analyze() 的返回值
            user_config: 用户配置 {qtype_dist, difficulty_dist, total_score, count, knowledge_points}
            use_llm: 是否尝试 LLM 辅助生成（失败自动回退规则）

        Returns:
            dict 考试蓝图
        """
        type_config = EXAM_TYPE_CONFIG.get(exam_type, EXAM_TYPE_CONFIG['final'])

        # 尝试 LLM 辅助
        if use_llm and mastery_report and exam_type != 'custom':
            try:
                blueprint = cls._generate_with_llm(exam_type, mastery_report, user_config, type_config)
                if blueprint:
                    return blueprint
            except Exception as e:
                logger.warning('LLM blueprint generation failed, falling back to rules: %s', e)

        # 规则引擎生成
        return cls._generate_rule_based(exam_type, examid, mastery_report, user_config, type_config)

    @classmethod
    def _generate_rule_based(cls, exam_type, examid, mastery_report, user_config, type_config):
        """规则引擎生成蓝图。"""
        min_kp, max_kp = type_config['kp_count_range']
        weakness_w = type_config['weakness_weight']
        coverage_w = type_config['coverage_weight']

        # 确定要考查的知识点
        manual_kps = user_config.get('knowledge_points') or []
        if manual_kps:
            selected_kps = list(manual_kps[:max_kp])
        elif mastery_report:
            # 混合选取：薄弱 + 覆盖
            weak_kps = [r for r in mastery_report if r['weakness_score'] >= 0.3]
            strong_kps = [r for r in mastery_report if r['weakness_score'] < 0.3]

            n_weak = min(len(weak_kps), max(min_kp, int(max_kp * weakness_w)))
            n_strong = min(len(strong_kps), max_kp - n_weak)

            # 如果薄弱知识点不够，从强的补
            if n_weak + n_strong < min_kp and len(mastery_report) >= min_kp:
                n_strong = min_kp - n_weak
                n_strong = min(n_strong, len(strong_kps))

            selected_kps = [r['knowledge_point'] for r in weak_kps[:n_weak]]
            selected_kps += [r['knowledge_point'] for r in strong_kps[:n_strong]]
        else:
            # 无掌握数据 → 从索引获取所有知识点
            kp_list = KnowledgePointIndex.list_knowledge_points(examid)
            if kp_list:
                # 按题量降序取前 max_kp 个
                kp_list.sort(key=lambda x: x['total_questions'], reverse=True)
                selected_kps = [kp['name'] for kp in kp_list[:max_kp]]
            else:
                selected_kps = []

        if not selected_kps:
            return {
                'exam_type': exam_type,
                'sections': [],
                'total_count': user_config.get('count', 20),
                'total_score': user_config.get('total_score', 100),
                'qtype_dist': user_config.get('qtype_dist', {}),
                'difficulty_dist': user_config.get('difficulty_dist', {}),
                'warning': '未能确定考查知识点，请先进行 AI 题目解析或手动指定知识点',
            }

        # 计算权重
        kp_map = {r['knowledge_point']: r for r in mastery_report} if mastery_report else {}
        weights = {}
        for kp in selected_kps:
            r = kp_map.get(kp)
            if r:
                weakness = r['weakness_score']
                w = weakness_w * weakness + coverage_w * (1 - weakness)
            else:
                w = coverage_w  # 无掌握数据的 KP 给覆盖权重
            weights[kp] = w

        # 归一化
        total_w = sum(weights.values())
        if total_w > 0:
            weights = {k: v / total_w for k, v in weights.items()}
        else:
            n = len(selected_kps)
            weights = {k: 1.0 / n for k in selected_kps}

        # 构建蓝图板块
        total_count = int(user_config.get('count', 20))
        total_score = int(user_config.get('total_score', 100))
        qtype_dist = user_config.get('qtype_dist', {})
        difficulty_dist = user_config.get('difficulty_dist', {})
        diff_bias = type_config.get('difficulty_bias', {})

        # 应用难度偏移（如月考偏难）
        adjusted_diff = dict(difficulty_dist)
        if diff_bias:
            for d in ('easy', 'medium', 'hard'):
                if d in adjusted_diff and d in diff_bias:
                    adjusted_diff[d] = max(0, int(adjusted_diff[d]) + diff_bias[d])
            # 归一化到 100
            diff_sum = sum(adjusted_diff.values())
            if diff_sum > 0:
                adjusted_diff = {k: round(v * 100 / diff_sum) for k, v in adjusted_diff.items()}

        sections = []
        for kp in selected_kps:
            kp_weight = weights[kp]
            kp_count = max(1, round(total_count * kp_weight))
            kp_score = round(total_score * kp_weight)

            # 按 qtype_dist 分配
            questions_spec = []
            qt_total = sum(int(v) for v in qtype_dist.values() if v)
            for qt, qt_cnt in qtype_dist.items():
                if not qt_cnt or int(qt_cnt) <= 0:
                    continue
                qt_ratio = int(qt_cnt) / qt_total if qt_total else 0
                qt_target = max(1, round(kp_count * qt_ratio))
                qt_score = round(kp_score * qt_ratio)
                score_per = max(1, round(qt_score / qt_target)) if qt_target else 1

                # 按难度分配
                diff_spec = {}
                diff_total = sum(int(v) for v in adjusted_diff.values() if v)
                diff_keys = list(adjusted_diff.keys())
                for i, (diff, pct) in enumerate(adjusted_diff.items()):
                    if not pct or int(pct) <= 0:
                        continue
                    if i == len(diff_keys) - 1:
                        diff_count = qt_target - sum(diff_spec.values())
                    else:
                        diff_count = max(0, round(qt_target * int(pct) / 100)) if diff_total else 0
                    diff_spec[diff] = max(0, diff_count)

                questions_spec.append({
                    'qtype': qt,
                    'count': qt_target,
                    'score_per_question': score_per,
                    'difficulty_dist': diff_spec,
                })

            sections.append({
                'knowledge_point': kp,
                'weight': round(kp_weight, 3),
                'question_count': kp_count,
                'total_score': kp_score,
                'questions': questions_spec,
            })

        return {
            'exam_type': exam_type,
            'exam_type_label': type_config['label'],
            'sections': sections,
            'total_count': total_count,
            'total_score': total_score,
            'qtype_dist': qtype_dist,
            'difficulty_dist': difficulty_dist,
            'adjusted_difficulty_dist': adjusted_diff,
        }

    @classmethod
    def _generate_with_llm(cls, exam_type, mastery_report, user_config, type_config):
        """LLM 辅助蓝图生成（小 payload，不会超时）。"""
        from .ai_services import AIServiceBase
        from .ai_prompts import PromptBuilder

        # 构建 LLM prompt（只传统计数据，不传题目）
        type_label = type_config['label']
        total_count = user_config.get('count', 20)
        total_score = user_config.get('total_score', 100)

        # 精简掌握数据（最多 15 个 KP，只传名称+掌握率+作答人次）
        top_kps = mastery_report[:15]
        kp_lines = []
        for i, r in enumerate(top_kps, 1):
            kp_lines.append(
                f"{i}. {r['knowledge_point']} - 掌握率 {r['mastery_rate']*100:.0f}%"
                f"（{r['total_answered']} 人次作答）"
            )

        system_prompt = (
            '你是一位资深的考试命题专家。根据学生群体的知识点掌握数据，'
            '为考试设计知识板块权重分配方案。返回严格的 JSON 格式，不要包含任何其他文字。'
        )
        user_prompt = (
            f'考试类型：{type_label}\n'
            f'题目总数：{total_count}\n'
            f'总分：{total_score}\n\n'
            f'学生知识点掌握数据（按薄弱程度排序）：\n'
            f'{chr(10).join(kp_lines)}\n\n'
            f'请为本次{type_label}设计考试蓝图，选择 {type_config["kp_count_range"][0]}-'
            f'{type_config["kp_count_range"][1]} 个知识点。\n'
            f'薄弱知识点应给予更高权重，但也要保证覆盖面。\n\n'
            f'返回 JSON 格式：\n'
            f'{{\n'
            f'  "sections": [\n'
            f'    {{"knowledge_point": "知识点名", "weight": 0.15, "reason": "选择理由"}}\n'
            f'  ]\n'
            f'}}\n'
            f'weights 总和应为 1.0。'
        )

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        content, err = AIServiceBase.call_llm_with_fallback(
            messages, model_tier='lite',  # 蓝图生成用轻量模型即可
            func_name='exam_compose')

        if err or not content:
            return None

        llm_result = PromptBuilder.parse_json_response(content)
        if not llm_result or 'sections' not in llm_result:
            return None

        # 将 LLM 的权重方案融入完整蓝图
        llm_sections = llm_result['sections']
        kp_weights = {}
        for s in llm_sections:
            kp = s.get('knowledge_point', '')
            w = float(s.get('weight', 0))
            if kp and w > 0:
                kp_weights[kp] = w

        # 用 LLM 权重重新构建蓝图
        selected_kps = list(kp_weights.keys())
        total_w = sum(kp_weights.values())
        if total_w > 0:
            kp_weights = {k: v / total_w for k, v in kp_weights.items()}

        # 复用规则引擎的分配逻辑
        total_count = int(user_config.get('count', 20))
        total_score = int(user_config.get('total_score', 100))
        qtype_dist = user_config.get('qtype_dist', {})
        difficulty_dist = user_config.get('difficulty_dist', {})

        sections = []
        for kp in selected_kps:
            kp_weight = kp_weights[kp]
            kp_count = max(1, round(total_count * kp_weight))
            kp_score = round(total_score * kp_weight)

            questions_spec = []
            qt_total = sum(int(v) for v in qtype_dist.values() if v)
            for qt, qt_cnt in qtype_dist.items():
                if not qt_cnt or int(qt_cnt) <= 0:
                    continue
                qt_ratio = int(qt_cnt) / qt_total if qt_total else 0
                qt_target = max(1, round(kp_count * qt_ratio))
                score_per = max(1, round(kp_score * qt_ratio / qt_target)) if qt_target else 1

                diff_spec = {}
                diff_keys = list(difficulty_dist.keys())
                for i, (diff, pct) in enumerate(difficulty_dist.items()):
                    if not pct or int(pct) <= 0:
                        continue
                    if i == len(diff_keys) - 1:
                        diff_spec[diff] = qt_target - sum(diff_spec.values())
                    else:
                        diff_spec[diff] = max(0, round(qt_target * int(pct) / 100))

                questions_spec.append({
                    'qtype': qt,
                    'count': qt_target,
                    'score_per_question': score_per,
                    'difficulty_dist': diff_spec,
                })

            llm_reason = ''
            for s in llm_sections:
                if s.get('knowledge_point') == kp:
                    llm_reason = s.get('reason', '')
                    break

            sections.append({
                'knowledge_point': kp,
                'weight': round(kp_weight, 3),
                'question_count': kp_count,
                'total_score': kp_score,
                'questions': questions_spec,
                'reason': llm_reason,
            })

        return {
            'exam_type': exam_type,
            'exam_type_label': type_config['label'],
            'sections': sections,
            'total_count': total_count,
            'total_score': total_score,
            'qtype_dist': qtype_dist,
            'difficulty_dist': difficulty_dist,
            'blueprint_source': 'llm',
        }


# ===========================================================================
# Phase 3: 定向题目检索
# ===========================================================================

class TargetedQuestionRetriever:
    """定向题目检索器。

    通过知识点索引 O(1) 查找题目，按难度 + 题型筛选后随机抽样。

    检索流程（每个知识板块）：
        1. 从 KP 索引获取该知识点 + 题型 + 难度的题目 ID 列表
        2. random.sample 抽取所需数量
        3. 按 ID 批量取题目详情
        4. 若数量不足 → 放宽难度过滤 → 放宽题型过滤 → 放宽知识点过滤

    复杂度：O(S × D)  S=板块数(3-15), D=每板块查询数(1-5)
        不随题库总量增长。
    """

    @classmethod
    def retrieve(cls, examid, blueprint):
        """按考试蓝图定向检索题目。

        Args:
            examid: 科目 ID
            blueprint: ExamBlueprintGenerator.generate() 的返回值

        Returns:
            (selected_questions, section_results)
            selected_questions: list[{id, qtype, difficulty, score, knowledge_point, title}]
            section_results: list[{knowledge_point, requested, retrieved, fallback_used}]
        """
        sections = blueprint.get('sections', [])
        selected_questions = []
        used_ids = set()  # 防止跨板块重复选题
        section_results = []

        for section in sections:
            kp_name = section['knowledge_point']
            requested = section.get('question_count', 0)
            section_questions = []
            fallback_used = False

            for q_spec in section.get('questions', []):
                qtype = q_spec['qtype']
                count = q_spec['count']
                score_per = q_spec['score_per_question']
                diff_dist = q_spec.get('difficulty_dist', {})

                # 按难度逐层检索
                for diff, diff_count in diff_dist.items():
                    if diff_count <= 0:
                        continue
                    fetched = cls._fetch_questions(
                        examid, kp_name, qtype, diff, diff_count, score_per, used_ids)
                    section_questions.extend(fetched)
                    for q in fetched:
                        used_ids.add(q['id'])

                # 数量不足 → 放宽难度（该题型所有难度）
                if len([q for q in section_questions if q['qtype'] == qtype]) < count:
                    needed = count - len([q for q in section_questions if q['qtype'] == qtype])
                    all_ids = KnowledgePointIndex.get_question_ids(examid, kp_name, qtype=qtype)
                    available = [qid for qid in all_ids if qid not in used_ids]
                    if available:
                        extra = random.sample(available, min(needed, len(available)))
                        for qid in extra:
                            q_detail = cls._fetch_question_detail(qid, qtype, score_per, kp_name)
                            if q_detail:
                                section_questions.append(q_detail)
                                used_ids.add(qid)
                        fallback_used = True

            # 整个板块数量不足 → 放宽知识点（从该科目随机补题）
            if len(section_questions) < requested:
                needed = requested - len(section_questions)
                extra = cls._fetch_fallback_questions(examid, needed, used_ids, score_per)
                section_questions.extend(extra)
                for q in extra:
                    used_ids.add(q['id'])
                fallback_used = True

            selected_questions.extend(section_questions)
            section_results.append({
                'knowledge_point': kp_name,
                'requested': requested,
                'retrieved': len(section_questions),
                'fallback_used': fallback_used,
                'weight': section.get('weight', 0),
            })

            logger.info('Section "%s": requested %d, retrieved %d, fallback=%s',
                        kp_name, requested, len(section_questions), fallback_used)

        return selected_questions, section_results

    @classmethod
    def _fetch_questions(cls, examid, kp_name, qtype, difficulty, count, score_per, used_ids):
        """从索引检索指定数量的题目。"""
        q_ids = KnowledgePointIndex.get_question_ids(
            examid, kp_name, qtype=qtype, difficulty=difficulty)
        # 排除已选
        available = [qid for qid in q_ids if qid not in used_ids]
        if not available:
            return []

        actual = min(count, len(available))
        sampled_ids = random.sample(available, actual)

        results = []
        for qid in sampled_ids:
            q_detail = cls._fetch_question_detail(qid, qtype, score_per, kp_name)
            if q_detail:
                q_detail['difficulty'] = difficulty
                results.append(q_detail)
        return results

    @staticmethod
    def _fetch_question_detail(qid, qtype, score, kp_name):
        """按 ID 取单题详情（仅取必要字段）。"""
        try:
            doc = Document.objects.get(collection='questions', doc_id=qid)
            d = doc.data or {}
            return {
                'id': qid,
                'qtype': d.get('qtype', qtype),
                'difficulty': (d.get('ai_analysis') or {}).get('difficulty',
                            d.get('difficulty', 'medium')),
                'score': score,
                'knowledge_point': kp_name,
                'title': (d.get('title') or d.get('content_md', '') or '')[:80],
            }
        except Document.DoesNotExist:
            return None

    @staticmethod
    def _fetch_fallback_questions(examid, count, used_ids, default_score):
        """板块题量不足时，从该科目随机补题。"""
        qs = Document.objects.filter(
            collection='questions'
        ).filter(Q(data__examid=str(examid)) | Q(data__examid=examid))

        available = []
        for doc in qs:
            doc_id = doc.doc_id or str(doc.pk)
            if doc_id not in used_ids:
                available.append(doc_id)
                if len(available) >= count * 3:  # 取 3 倍备用
                    break

        if not available:
            return []

        sampled = random.sample(available, min(count, len(available)))
        results = []
        for qid in sampled:
            try:
                doc = Document.objects.get(collection='questions', doc_id=qid)
                d = doc.data or {}
                results.append({
                    'id': qid,
                    'qtype': d.get('qtype', ''),
                    'difficulty': (d.get('ai_analysis') or {}).get('difficulty',
                                d.get('difficulty', 'medium')),
                    'score': default_score,
                    'knowledge_point': '(补充题)',
                    'title': (d.get('title') or d.get('content_md', '') or '')[:80],
                })
            except Document.DoesNotExist:
                continue
        return results


# ===========================================================================
# 智能组卷服务（三阶段编排）
# ===========================================================================

class SmartComposeService:
    """智能组卷服务 —— 三阶段定向组卷。

    编排流程：
        Phase 1  KnowledgeMasteryAnalyzer.analyze()  → 掌握度报告
        Phase 2  ExamBlueprintGenerator.generate()   → 考试蓝图
        Phase 3  TargetedQuestionRetriever.retrieve() → 选题组卷

    与旧 ExamCompositionService 的区别：
        - 不将题目发给 LLM 做选题（Phase 3 纯算法检索）
        - LLM 仅在 Phase 2 可选使用（payload 极小，不会超时）
        - 通过 KP 索引定向检索，不遍历全题库
        - 支持数十万题规模

    用法::

        job_id = AIJobManager.create('smart_compose', config)
        AIJobManager.start(job_id, lambda jid: SmartComposeService.compose(config, jid))
    """

    SERVICE_NAME = 'smart_compose'

    @classmethod
    def compose(cls, config, job_id):
        """三阶段智能组卷主流程。

        Args:
            config: 组卷配置::

                {
                    exam_type: "final",         # monthly/midterm/final/mock/custom
                    examid / subject_id: "subj_001",  # 科目ID（兼容两种命名）
                    qtype_dist: {"single": 10, "multiple": 5, "judge": 5},
                    difficulty_dist: {"easy": 30, "medium": 50, "hard": 20},
                    total_score: 100,
                    count: 20,
                    knowledge_points: [],       # 可选：手动指定知识点（覆盖自动分析）
                    use_llm_blueprint: true     # 可选：是否用 LLM 辅助蓝图
                }

            job_id: AI 任务 ID
        """
        AIJobManager.update(job_id, progress=0, progress_text='开始智能组卷',
                            status=AIJobManager.STATUS_RUNNING)

        # 兼容字段命名
        examid = config.get('examid') or config.get('subject_id') or ''
        exam_type = config.get('exam_type', 'final')
        use_llm = config.get('use_llm_blueprint', True)

        if not examid:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='科目 ID 不能为空', progress_text='参数错误')
            return

        # ---- Phase 1: 知识点掌握度分析 ----
        AIJobManager.update(job_id, progress=10, progress_text='正在分析知识点掌握数据...')

        manual_kps = config.get('knowledge_points') or []
        if manual_kps:
            # 用户手动指定知识点，跳过掌握度分析
            mastery_report = []
            AIJobManager.update(job_id, progress=25,
                                progress_text='使用手动指定的知识点（跳过掌握度分析）')
        else:
            mastery_report = KnowledgeMasteryAnalyzer.analyze(examid)
            weak_count = len([r for r in mastery_report if r['weakness_score'] >= 0.3])
            AIJobManager.update(job_id, progress=25,
                                progress_text='知识点分析完成：%d 个知识点，%d 个薄弱' % (
                                    len(mastery_report), weak_count))

        # ---- Phase 2: 生成考试蓝图 ----
        AIJobManager.update(job_id, progress=35, progress_text='正在生成考试蓝图...')

        blueprint = ExamBlueprintGenerator.generate(
            exam_type, examid, mastery_report, config, use_llm=use_llm)

        sections = blueprint.get('sections', [])
        if not sections:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='无法生成考试蓝图：未找到足够的知识点。'
                                      '请先对题目进行 AI 解析以标注知识点，或手动指定知识点。',
                                progress_text='蓝图生成失败')
            return

        AIJobManager.update(job_id, progress=45,
                            progress_text='考试蓝图已生成：%d 个知识板块（%s）' % (
                                len(sections), blueprint.get('exam_type_label', exam_type)))

        # ---- 确保知识点索引存在 ----
        AIJobManager.update(job_id, progress=50, progress_text='正在检查知识点索引...')

        index_kp_count, index_q_count = KnowledgePointIndex.build_index(examid)

        AIJobManager.update(job_id, progress=55,
                            progress_text='知识点索引就绪：%d 个知识点，%d 道题目已索引' % (
                                index_kp_count, index_q_count))

        # ---- Phase 3: 定向题目检索 ----
        AIJobManager.update(job_id, progress=60, progress_text='正在定向检索题目...')

        selected_questions, section_results = TargetedQuestionRetriever.retrieve(
            examid, blueprint)

        if not selected_questions:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='未能检索到足够的题目。请检查题库是否包含相关知识点标注。',
                                progress_text='题目检索失败')
            return

        AIJobManager.update(job_id, progress=85,
                            progress_text='已检索 %d 道题目，正在组装试卷...' % len(selected_questions))

        # ---- 组装最终结果 ----
        result = {
            'question_ids': [q['id'] for q in selected_questions],
            'questions': selected_questions,
            'sections': section_results,
            'blueprint': blueprint,
            'mastery_summary': {
                'total_kps_analyzed': len(mastery_report),
                'weak_kps': len([r for r in mastery_report if r['weakness_score'] >= 0.3]),
                'top_weak_kps': [
                    {'name': r['knowledge_point'], 'mastery_rate': r['mastery_rate'],
                     'total_answered': r['total_answered']}
                    for r in mastery_report[:5]
                ],
            } if mastery_report else None,
            'index_stats': {
                'indexed_kps': index_kp_count,
                'indexed_questions': index_q_count,
            },
            'candidate_count': len(selected_questions),
            'selected_count': len(selected_questions),
            'total_score': blueprint.get('total_score', 100),
            'total_count': blueprint.get('total_count', len(selected_questions)),
        }

        AIJobManager.update(job_id, progress=100, progress_text='智能组卷完成',
                            status=AIJobManager.STATUS_SUCCESS, result=result)

        logger.info('Smart compose completed: job=%s, %d questions, %d sections, type=%s',
                     job_id, len(selected_questions), len(sections), exam_type)

    @classmethod
    def confirm_draft(cls, job_id, exam_name):
        """确认组卷结果，创建考试草稿文档。

        与 ExamCompositionService.confirm_draft 同构，
        读取 ai_jobs result → 创建 exam Document(status=draft) → 返回 exam_id。

        Args:
            job_id: AI 任务 ID（必须为 success 状态）
            exam_name: 考试名称

        Returns:
            exam_id（字符串）或 None（任务不存在或未成功）
        """
        import uuid as uuid_lib
        job_data = AIJobManager.get(job_id)
        if not job_data:
            return None
        if job_data.get('status') != AIJobManager.STATUS_SUCCESS:
            return None

        result = job_data.get('result') or {}
        question_ids = result.get('question_ids', [])
        if not question_ids:
            return None

        exam_id = uuid_lib.uuid4().hex[:16]
        exam_data = {
            'name': exam_name or 'AI智能组卷-%s' % exam_id[:8],
            'status': 'draft',
            'questionCount': len(question_ids),
            'totalScore': result.get('total_score', 100),
            'questions': question_ids,
            'composition_result': result,
            'compose_method': 'smart_compose_v2',
            'exam_type': result.get('blueprint', {}).get('exam_type', ''),
            'createdBy': 'smart_compose',
            'createTime': timezone.now().strftime('%Y/%m/%d %H:%M'),
        }

        Document.objects.create(
            collection='exam',
            doc_id=exam_id,
            data=exam_data,
        )
        return exam_id
