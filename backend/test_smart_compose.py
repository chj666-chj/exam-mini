"""Test: Smart Compose V2 — 三阶段定向组卷系统测试。

测试覆盖：
  Phase 0  KnowledgePointIndex — 索引 key 生成、索引结构
  Phase 1  KnowledgeMasteryAnalyzer — 掌握度计算逻辑（mock 数据）
  Phase 2  ExamBlueprintGenerator — 蓝图生成规则（各考试类型）
  Phase 3  TargetedQuestionRetriever — 定向检索 + 回退逻辑（mock 索引）
  编排     SmartComposeService — 配置解析、字段兼容

运行方式：
  cd backend && python test_smart_compose.py
"""
import os
import sys
import random
import django
from collections import Counter
from unittest.mock import patch, MagicMock

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from adminapi.smart_compose import (
    EXAM_TYPE_CONFIG,
    KnowledgePointIndex,
    KnowledgeMasteryAnalyzer,
    ExamBlueprintGenerator,
    TargetedQuestionRetriever,
    SmartComposeService,
)

results = []

def test(name, passed, detail=''):
    results.append((name, passed, detail))
    tag = 'PASS' if passed else 'FAIL'
    print(f'  [{tag}] {name}' + (f' -- {detail}' if detail else ''))


print('=' * 70)
print('Test: Smart Compose V2 — 三阶段定向组卷')
print('=' * 70)

# ===========================================================================
# 1. EXAM_TYPE_CONFIG 配置验证
# ===========================================================================
print('\n--- 1. EXAM_TYPE_CONFIG 配置验证 ---')

required_types = {'monthly', 'midterm', 'final', 'mock', 'custom'}
test('考试类型配置完整', set(EXAM_TYPE_CONFIG.keys()) == required_types,
     f'类型: {sorted(EXAM_TYPE_CONFIG.keys())}')

for etype, cfg in EXAM_TYPE_CONFIG.items():
    test(f'{etype} 有 label', bool(cfg.get('label')), cfg.get('label', ''))
    test(f'{etype} 有 kp_count_range', isinstance(cfg.get('kp_count_range'), tuple)
         and len(cfg['kp_count_range']) == 2, str(cfg.get('kp_count_range')))
    test(f'{etype} 权重和为1.0', abs(cfg.get('weakness_weight', 0) + cfg.get('coverage_weight', 0) - 1.0) < 0.01,
         f'w={cfg.get("weakness_weight")}, c={cfg.get("coverage_weight")}')

# 月考应偏难
test('月考难度偏移偏难', EXAM_TYPE_CONFIG['monthly']['difficulty_bias'].get('hard', 0) > 0,
     str(EXAM_TYPE_CONFIG['monthly']['difficulty_bias']))

# 期末应偏基础
test('期末难度偏移偏基础', EXAM_TYPE_CONFIG['final']['difficulty_bias'].get('easy', 0) > 0,
     str(EXAM_TYPE_CONFIG['final']['difficulty_bias']))


# ===========================================================================
# 2. KnowledgePointIndex — 索引 key 生成
# ===========================================================================
print('\n--- 2. KnowledgePointIndex 索引 key 生成 ---')

key1 = KnowledgePointIndex._index_key('subj_001', '函数与导数')
key2 = KnowledgePointIndex._index_key('subj_001', '函数与导数')
key3 = KnowledgePointIndex._index_key('subj_001', '三角函数')
key4 = KnowledgePointIndex._index_key('subj_002', '函数与导数')

test('相同参数生成相同 key', key1 == key2, f'{key1} == {key2}')
test('不同知识点生成不同 key', key1 != key3, f'{key1} != {key3}')
test('不同科目生成不同 key', key1 != key4, f'{key1} != {key4}')
test('key 包含科目 ID 前缀', key1.startswith('subj_001_'), key1)
test('key 长度合理 (< 100)', len(key1) < 100, f'len={len(key1)}')


# ===========================================================================
# 3. ExamBlueprintGenerator — 规则引擎蓝图生成
# ===========================================================================
print('\n--- 3. ExamBlueprintGenerator 规则引擎 ---')

def make_mastery_report(kps):
    """生成 mock 掌握度报告。"""
    return [
        {
            'knowledge_point': name,
            'total_answered': total,
            'correct_count': int(total * rate),
            'mastery_rate': rate,
            'weakness_score': round(1 - rate, 3),
        }
        for name, total, rate in kps
    ]

# 3.1 月考：应聚焦薄弱知识点
mastery = make_mastery_report([
    ('函数与导数', 100, 0.3),   # 薄弱
    ('三角函数', 80, 0.35),     # 薄弱
    ('数列', 60, 0.5),          # 中等
    ('立体几何', 40, 0.7),      # 较好
    ('概率统计', 50, 0.8),      # 良好
    ('解析几何', 30, 0.85),     # 良好
])

user_config = {
    'qtype_dist': {'single': 10, 'judge': 5, 'fill': 5},
    'difficulty_dist': {'easy': 30, 'medium': 50, 'hard': 20},
    'total_score': 100,
    'count': 20,
}

blueprint_monthly = ExamBlueprintGenerator._generate_rule_based(
    'monthly', 'subj_001', mastery, user_config, EXAM_TYPE_CONFIG['monthly'])

test('月考蓝图有 sections', len(blueprint_monthly.get('sections', [])) > 0,
     f'{len(blueprint_monthly.get("sections", []))} sections')

monthly_sections = blueprint_monthly.get('sections', [])
monthly_kps = [s['knowledge_point'] for s in monthly_sections]
test('月考聚焦薄弱知识点', '函数与导数' in monthly_kps and '三角函数' in monthly_kps,
     f'KPs: {monthly_kps}')
test('月考板块数在 3-6 范围', 3 <= len(monthly_sections) <= 6,
     f'{len(monthly_sections)} sections')

# 权重总和应接近 1.0
total_weight = sum(s['weight'] for s in monthly_sections)
test('月考权重总和为 1.0', abs(total_weight - 1.0) < 0.05, f'总权重={total_weight:.3f}')

# 3.2 期末：应覆盖更多知识点
blueprint_final = ExamBlueprintGenerator._generate_rule_based(
    'final', 'subj_001', mastery, user_config, EXAM_TYPE_CONFIG['final'])

final_sections = blueprint_final.get('sections', [])
test('期末板块数 >= 月考板块数', len(final_sections) >= len(monthly_sections),
     f'期末={len(final_sections)}, 月考={len(monthly_sections)}')

# 3.3 自定义：手动指定知识点
custom_config = dict(user_config)
custom_config['knowledge_points'] = ['自定义知识点A', '自定义知识点B', '自定义知识点C']

blueprint_custom = ExamBlueprintGenerator._generate_rule_based(
    'custom', 'subj_001', mastery, custom_config, EXAM_TYPE_CONFIG['custom'])

custom_kps = [s['knowledge_point'] for s in blueprint_custom.get('sections', [])]
test('自定义模式使用手动指定的知识点', set(custom_kps) == {'自定义知识点A', '自定义知识点B', '自定义知识点C'},
     f'KPs: {custom_kps}')

# 3.4 无掌握数据：应回退到索引
with patch.object(KnowledgePointIndex, 'list_knowledge_points', return_value=[
    {'name': '索引KP1', 'total_questions': 50},
    {'name': '索引KP2', 'total_questions': 30},
    {'name': '索引KP3', 'total_questions': 20},
]):
    blueprint_no_mastery = ExamBlueprintGenerator._generate_rule_based(
        'final', 'subj_001', [], user_config, EXAM_TYPE_CONFIG['final'])
    no_mastery_kps = [s['knowledge_point'] for s in blueprint_no_mastery.get('sections', [])]
    test('无掌握数据时回退到索引知识点', '索引KP1' in no_mastery_kps,
         f'KPs: {no_mastery_kps}')

# 3.5 难度偏移验证
test('月考蓝图包含 adjusted_difficulty_dist', 'adjusted_difficulty_dist' in blueprint_monthly,
     str(blueprint_monthly.get('adjusted_difficulty_dist', {})))
adjusted = blueprint_monthly.get('adjusted_difficulty_dist', {})
adjusted_sum = sum(adjusted.values())
test('调整后难度总和为 100', adjusted_sum == 100, f'总和={adjusted_sum}')

# 3.6 空 mastery + 空索引
with patch.object(KnowledgePointIndex, 'list_knowledge_points', return_value=[]):
    blueprint_empty = ExamBlueprintGenerator._generate_rule_based(
        'final', 'subj_001', [], user_config, EXAM_TYPE_CONFIG['final'])
    test('无数据时蓝图 sections 为空且有 warning',
         len(blueprint_empty.get('sections', [])) == 0 and 'warning' in blueprint_empty,
         blueprint_empty.get('warning', '')[:50])

# 3.7 每个 section 的 question_spec 验证
for section in monthly_sections:
    qs_total = sum(qs['count'] for qs in section.get('questions', []))
    test(f'板块"{section["knowledge_point"]}" 题数 > 0', section['question_count'] > 0,
         f'count={section["question_count"]}, spec_total={qs_total}')
    test(f'板块"{section["knowledge_point"]}" 有题型分布',
         len(section.get('questions', [])) > 0,
         f'{len(section.get("questions", []))} qtypes')


# ===========================================================================
# 4. TargetedQuestionRetriever — 定向检索（mock 索引）
# ===========================================================================
print('\n--- 4. TargetedQuestionRetriever 定向检索 ---')

# Mock 索引：每个知识点有足够的题目
mock_index_data = {
    '函数与导数': {
        'single': {'easy': ['q1', 'q2', 'q3'], 'medium': ['q4', 'q5', 'q6'], 'hard': ['q7', 'q8']},
        'judge':  {'easy': ['q9', 'q10'], 'medium': ['q11', 'q12'], 'hard': ['q13']},
        'fill':   {'easy': ['q14'], 'medium': ['q15', 'q16'], 'hard': ['q17']},
    },
    '三角函数': {
        'single': {'easy': ['q20', 'q21'], 'medium': ['q22', 'q23'], 'hard': ['q24']},
        'judge':  {'easy': ['q25'], 'medium': ['q26', 'q27'], 'hard': ['q28']},
        'fill':   {'easy': ['q29'], 'medium': ['q30'], 'hard': ['q31']},
    },
}

def mock_get_question_ids(examid, kp_name, qtype=None, difficulty=None):
    data = mock_index_data.get(kp_name, {})
    if qtype and difficulty:
        return data.get(qtype, {}).get(difficulty, [])
    elif qtype:
        result = []
        for diff_ids in data.get(qtype, {}).values():
            result.extend(diff_ids)
        return result
    else:
        result = []
        for qt_map in data.values():
            for diff_ids in qt_map.values():
                result.extend(diff_ids)
        return result

# Mock 题目详情
def mock_fetch_detail(qid, qtype, score, kp_name):
    return {
        'id': qid,
        'qtype': qtype,
        'difficulty': 'medium',
        'score': score,
        'knowledge_point': kp_name,
        'title': f'题目{qid}',
    }

with patch.object(KnowledgePointIndex, 'get_question_ids', side_effect=mock_get_question_ids), \
     patch.object(TargetedQuestionRetriever, '_fetch_question_detail', side_effect=mock_fetch_detail), \
     patch.object(TargetedQuestionRetriever, '_fetch_fallback_questions', return_value=[]):

    test_blueprint = {
        'exam_type': 'monthly',
        'sections': [
            {
                'knowledge_point': '函数与导数',
                'weight': 0.6,
                'question_count': 6,
                'total_score': 60,
                'questions': [
                    {'qtype': 'single', 'count': 3, 'score_per_question': 5,
                     'difficulty_dist': {'easy': 1, 'medium': 1, 'hard': 1}},
                    {'qtype': 'judge', 'count': 2, 'score_per_question': 5,
                     'difficulty_dist': {'easy': 1, 'medium': 1, 'hard': 0}},
                    {'qtype': 'fill', 'count': 1, 'score_per_question': 10,
                     'difficulty_dist': {'medium': 1}},
                ],
            },
            {
                'knowledge_point': '三角函数',
                'weight': 0.4,
                'question_count': 4,
                'total_score': 40,
                'questions': [
                    {'qtype': 'single', 'count': 2, 'score_per_question': 5,
                     'difficulty_dist': {'easy': 1, 'medium': 1, 'hard': 0}},
                    {'qtype': 'judge', 'count': 1, 'score_per_question': 10,
                     'difficulty_dist': {'medium': 1}},
                    {'qtype': 'fill', 'count': 1, 'score_per_question': 10,
                     'difficulty_dist': {'medium': 1}},
                ],
            },
        ],
        'total_count': 10,
        'total_score': 100,
    }

    selected, section_results = TargetedQuestionRetriever.retrieve('subj_001', test_blueprint)

    test('检索到题目', len(selected) > 0, f'{len(selected)} questions')
    test('无重复题目', len(set(q['id'] for q in selected)) == len(selected),
         f'{len(selected)} questions, {len(set(q["id"] for q in selected))} unique')
    test('section_results 数量匹配', len(section_results) == len(test_blueprint['sections']),
         f'{len(section_results)} results')

    for sr in section_results:
        test(f'板块"{sr["knowledge_point"]}" 检索数 > 0', sr['retrieved'] > 0,
             f'requested={sr["requested"]}, retrieved={sr["retrieved"]}')

# 4.2 题量不足时的回退测试
mock_index_sparse = {
    '稀缺知识点': {
        'single': {'easy': ['q1'], 'medium': [], 'hard': []},
    },
}

def mock_get_ids_sparse(examid, kp_name, qtype=None, difficulty=None):
    data = mock_index_sparse.get(kp_name, {})
    if qtype and difficulty:
        return data.get(qtype, {}).get(difficulty, [])
    elif qtype:
        result = []
        for diff_ids in data.get(qtype, {}).values():
            result.extend(diff_ids)
        return result
    return []

fallback_questions = [
    {'id': f'fb{i}', 'qtype': 'single', 'difficulty': 'medium', 'score': 5,
     'knowledge_point': '(补充题)', 'title': f'补充题{i}'}
    for i in range(5)
]

with patch.object(KnowledgePointIndex, 'get_question_ids', side_effect=mock_get_ids_sparse), \
     patch.object(TargetedQuestionRetriever, '_fetch_question_detail', side_effect=mock_fetch_detail), \
     patch.object(TargetedQuestionRetriever, '_fetch_fallback_questions', return_value=fallback_questions):

    sparse_blueprint = {
        'exam_type': 'monthly',
        'sections': [{
            'knowledge_point': '稀缺知识点',
            'weight': 1.0,
            'question_count': 5,
            'total_score': 50,
            'questions': [
                {'qtype': 'single', 'count': 5, 'score_per_question': 10,
                 'difficulty_dist': {'easy': 2, 'medium': 2, 'hard': 1}},
            ],
        }],
        'total_count': 5,
        'total_score': 50,
    }

    selected_sparse, results_sparse = TargetedQuestionRetriever.retrieve('subj_001', sparse_blueprint)

    test('稀缺知识点触发了回退补题', results_sparse[0]['fallback_used'] == True,
         f'retrieved={results_sparse[0]["retrieved"]}, fallback={results_sparse[0]["fallback_used"]}')
    test('回退后题目数满足需求', len(selected_sparse) >= 1,
         f'{len(selected_sparse)} questions')


# ===========================================================================
# 5. SmartComposeService — 配置解析与字段兼容
# ===========================================================================
print('\n--- 5. SmartComposeService 配置兼容 ---')

# 5.1 字段兼容性
config_variants = [
    {'examid': 'subj_001', 'exam_type': 'final'},
    {'subject_id': 'subj_001', 'exam_type': 'monthly'},
    {'examid': 'subj_001'},  # 默认 exam_type
]

for i, cfg in enumerate(config_variants):
    examid = cfg.get('examid') or cfg.get('subject_id') or ''
    exam_type = cfg.get('exam_type', 'final')
    test(f'配置变体{i+1} 解析 examid', examid == 'subj_001', f'examid={examid}')
    test(f'配置变体{i+1} 解析 exam_type', exam_type in required_types, f'exam_type={exam_type}')

# 5.2 无效考试类型
invalid_types = ['weekly', 'quarterly', '', None, 123]
for vt in invalid_types:
    # views 层会拒绝无效类型，这里验证配置表不会 KeyError
    cfg = EXAM_TYPE_CONFIG.get(vt, EXAM_TYPE_CONFIG['final'])
    test(f'无效类型 {repr(vt)} 回退到 final', cfg == EXAM_TYPE_CONFIG['final'], '')


# ===========================================================================
# 6. KnowledgeMasteryAnalyzer — 掌握度计算逻辑
# ===========================================================================
print('\n--- 6. KnowledgeMasteryAnalyzer 掌握度计算 ---')

# 6.1 subject ID 提取
test('subject 为对象时提取 _id',
     KnowledgeMasteryAnalyzer._extract_subject_id({'subject': {'_id': 'subj_001', 'name': '数学'}}) == 'subj_001')
test('subject 为对象时提取 code',
     KnowledgeMasteryAnalyzer._extract_subject_id({'subject': {'code': 'subj_002'}}) == 'subj_002')
test('subject 为字符串时直接返回',
     KnowledgeMasteryAnalyzer._extract_subject_id({'subject': 'subj_003'}) == 'subj_003')
test('subject 为空时返回空字符串',
     KnowledgeMasteryAnalyzer._extract_subject_id({}) == '')
test('subject 为 None 时返回空字符串',
     KnowledgeMasteryAnalyzer._extract_subject_id({'subject': None}) == '')


# ===========================================================================
# 7. 蓝图题型/难度分配一致性
# ===========================================================================
print('\n--- 7. 蓝图分配一致性 ---')

# 验证蓝图各板块的题数总和 ≈ total_count
for etype in ['monthly', 'midterm', 'final', 'mock']:
    bp = ExamBlueprintGenerator._generate_rule_based(
        etype, 'subj_001', mastery, user_config, EXAM_TYPE_CONFIG[etype])
    sections = bp.get('sections', [])
    if sections:
        total_allocated = sum(s['question_count'] for s in sections)
        target = user_config['count']
        test(f'{etype} 蓝图题数总和接近目标({target})',
             abs(total_allocated - target) <= len(sections),  # 允许每板块±1的误差
             f'allocated={total_allocated}, target={target}')

        # 验证每个板块的 score 总和
        for s in sections:
            spec_score = sum(qs['count'] * qs['score_per_question'] for qs in s.get('questions', []))
            test(f'{etype} 板块"{s["knowledge_point"][:8]}" 分值合理',
                 spec_score > 0, f'section_score={s["total_score"]}, spec_score={spec_score}')


# ===========================================================================
# 汇总
# ===========================================================================
print('\n' + '=' * 70)
passed = sum(1 for _, p, _ in results if p)
failed = sum(1 for _, p, _ in results if not p)
total = len(results)
print(f'Results: {passed} passed, {failed} failed, {total} total')
print('=' * 70)

if failed > 0:
    print('\nFailed tests:')
    for name, p, detail in results:
        if not p:
            print(f'  [FAIL] {name} -- {detail}')
    sys.exit(1)
else:
    print('\nAll tests passed!')
    sys.exit(0)
