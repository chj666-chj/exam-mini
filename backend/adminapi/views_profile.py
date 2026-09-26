"""用户画像聚合接口。

GET /api/admin/users/<openid>/profile/

从 historys（答题记录）、notes（错题）、questions（题库）集合中
聚合用户的综合画像数据，包含四个模块：
1. 题目作答情况：作答总数、正确率、作答趋势
2. 考试情况：考试记录、成绩、排名及变化趋势
3. 知识点掌握情况：各知识点掌握度评级
4. 薄弱情况：薄弱知识点及高错误率题型
"""
from collections import Counter, defaultdict
from datetime import timedelta

from django.utils import timezone

from . import data_utils as du
from . import permissions as perm
from .responses import ErrorCode, fail, ok
from core.models import Document


# ---- 工具函数 ----

def _duration_seconds(value):
    """解析答题时长字段（形如 '0:40' 分:秒）。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if ':' in text:
            parts = text.split(':')
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(float(parts[1]))
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _typename_normalize(raw):
    """题型名称归一化。"""
    text = du.to_text(raw).strip()
    mapping = {
        '单选': '单选题', 'single': '单选题', '单选题': '单选题',
        '多选': '多选题', 'multiple': '多选题', '多选题': '多选题',
        '判断': '判断题', 'judge': '判断题', '判断题': '判断题',
        '填空': '填空题', 'fill': '填空题', '填空题': '填空题',
        '问答': '问答题', 'qa': '问答题', '简答': '问答题', '问答题': '问答题',
    }
    return mapping.get(text, text or '未知题型')


def _knowledge_point(title, comments):
    """从题目标题/解析中粗略提取知识点关键词。

    由于历史数据没有显式标签字段，这里基于科目+题型维度做知识点归类。
    如果题目有 tag_ids 则优先用标签名，否则用科目名+题型作为知识点维度。
    """
    return None  # 由调用方根据实际数据构建


# ---- 核心聚合 ----

def _collect_user_data(openid):
    """一次性收集指定用户的所有相关数据。"""
    # 1. 用户资料
    profile = {}
    for item in du.iter_docs('profiles'):
        if item['data'].get('_openid') == openid:
            data = item['data']
            info = du.as_obj(data.get('userInfo')) or {}
            profile = {
                'nickname': du.to_text(info.get('nickName')) if isinstance(info, dict) else '',
                'avatar': du.to_text(info.get('avatarUrl')) if isinstance(info, dict) else '',
                'city': du.to_text(info.get('city')) if isinstance(info, dict) else '',
                'status': data.get('status') or 'active',
            }
            break

    # 2. 答题记录（historys 集合）
    records = []
    for item in du.iter_docs('historys'):
        data = item['data']
        if data.get('_openid') != openid:
            continue
        items_list = du.as_obj(data.get('items')) or []
        questions_list = du.as_obj(data.get('questions')) or []
        q_list = questions_list if questions_list else items_list
        total = len(q_list)
        right_num = du.to_number(data.get('rightNum'), 0)
        acc = du.accuracy_of(data)
        records.append({
            '_id': item['doc_id'] or str(item['pk']),
            'date': du.doc_date(item),
            'date_str': du.to_text(data.get('createTime')),
            'subject': du.subject_name(data),
            'examid': du.to_text(data.get('examid')),
            'rightNum': right_num,
            'total': total,
            'accuracy': acc,
            'duration': _duration_seconds(data.get('time')),
            'time_str': du.to_text(data.get('time')),
            'questions': q_list,
            'score_arr': du.as_obj(data.get('score_arr')) or [],
        })

    # 3. 错题（notes 集合）
    notes = []
    for item in du.iter_docs('notes'):
        data = item['data']
        if data.get('_openid') != openid:
            continue
        question = du.as_obj(data.get('question')) or {}
        notes.append({
            '_id': item['doc_id'] or str(item['pk']),
            'ordernum': du.to_text(data.get('ordernum')),
            'date': du.doc_date(item),
            'question_title': du.to_text(question.get('title')) if isinstance(question, dict) else '',
            'typename': _typename_normalize(question.get('typename')) if isinstance(question, dict) else '',
            'examid': du.to_text(question.get('examid')) if isinstance(question, dict) else '',
        })

    # 4. 科目信息
    subjects_map = {}
    for item in du.iter_docs('subjects'):
        data = item['data']
        code = du.to_text(data.get('code')) or du.to_text(data.get('_id'))
        if code:
            subjects_map[code] = du.to_text(data.get('name')) or code

    # 5. 考试信息
    exams_map = {}
    for item in du.iter_docs('exam'):
        data = item['data']
        code = du.to_text(data.get('code')) or du.to_text(data.get('_id'))
        if code:
            exams_map[code] = du.to_text(data.get('name')) or code

    return profile, records, notes, subjects_map, exams_map


def _build_answer_stats(records):
    """模块1：题目作答情况统计。"""
    total_records = len(records)
    total_questions = sum(r['total'] for r in records if r['total'])
    total_right = sum(r['rightNum'] for r in records if r['rightNum'])
    accs = [r['accuracy'] for r in records if r['accuracy'] is not None]
    avg_acc = round(sum(accs) / len(accs), 4) if accs else 0
    durations = [r['duration'] for r in records if r['duration']]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0

    # 作答趋势（按日期聚合）
    daily_map = defaultdict(lambda: {'count': 0, 'right': 0, 'total_q': 0, 'acc_sum': 0.0, 'acc_n': 0})
    for r in records:
        if r['date']:
            key = r['date'].strftime('%Y-%m-%d')
            slot = daily_map[key]
            slot['count'] += 1
            slot['right'] += r['rightNum']
            slot['total_q'] += r['total']
            if r['accuracy'] is not None:
                slot['acc_sum'] += r['accuracy']
                slot['acc_n'] += 1

    trend_series = []
    if daily_map:
        dates = sorted(daily_map.keys())
        for d in dates:
            slot = daily_map[d]
            trend_series.append({
                'date': d,
                'records': slot['count'],
                'questions': slot['total_q'],
                'right': slot['right'],
                'accuracy': round(slot['acc_sum'] / slot['acc_n'], 4) if slot['acc_n'] else 0,
            })

    # 最近作答
    recent = sorted(records, key=lambda x: x['date'] or timezone.now().date(), reverse=True)[:10]
    recent_list = [{
        '_id': r['_id'],
        'date': r['date'].strftime('%Y-%m-%d') if r['date'] else r['date_str'],
        'subject': r['subject'] or '未知科目',
        'right': r['rightNum'],
        'total': r['total'],
        'accuracy': round(r['accuracy'], 4) if r['accuracy'] is not None else 0,
        'time': r['time_str'],
    } for r in recent]

    return {
        'total_records': total_records,
        'total_questions': total_questions,
        'total_right': total_right,
        'avg_accuracy': avg_acc,
        'avg_duration': avg_duration,
        'trend': trend_series,
        'recent': recent_list,
    }


def _build_exam_stats(records, notes, all_user_records):
    """模块2：考试情况统计。

    all_user_records: 其他用户的答题记录列表（用于排名计算）。
    """
    if not records:
        return {
            'total_exams': 0,
            'avg_score': 0,
            'best_score': 0,
            'rank': 0,
            'total_users': 0,
            'records': [],
            'score_trend': [],
        }

    # 按科目分组，计算每次成绩
    exam_records = []
    for r in records:
        if r['total'] == 0:
            continue
        score_pct = round(r['rightNum'] / r['total'], 4) if r['total'] else 0
        exam_records.append({
            '_id': r['_id'],
            'date': r['date'].strftime('%Y-%m-%d') if r['date'] else r['date_str'],
            'subject': r['subject'] or '未知科目',
            'examid': r['examid'] or '',
            'right': r['rightNum'],
            'total': r['total'],
            'score_pct': score_pct,
            'accuracy': round(r['accuracy'], 4) if r['accuracy'] is not None else score_pct,
            'time': r['time_str'],
        })

    # 成绩趋势（按时间排序）
    score_trend = sorted(exam_records, key=lambda x: x['date'])
    scores = [e['score_pct'] for e in score_trend if e['score_pct'] > 0]

    # 排名计算：统计所有用户的平均正确率，排名当前用户
    user_avg_acc = {}
    for rec_list in all_user_records:
        for r in rec_list:
            oid = r.get('_openid', '')
            if not oid:
                continue
            acc = r.get('accuracy')
            if acc is not None:
                slot = user_avg_acc.setdefault(oid, {'sum': 0.0, 'n': 0})
                slot['sum'] += acc
                slot['n'] += 1

    user_scores = []
    for oid, s in user_avg_acc.items():
        avg = round(s['sum'] / s['n'], 4) if s['n'] else 0
        user_scores.append((oid, avg))
    user_scores.sort(key=lambda x: -x[1])

    rank = 0
    total_users = len(user_scores)
    for idx, (oid, _) in enumerate(user_scores, 1):
        if oid == records[0].get('_openid') if records else False:
            rank = idx
            break
    # 如果上面没匹配到，用 openid 查
    target_openid = None
    for r in records:
        if r.get('_openid'):
            target_openid = r['_openid']
            break
    if rank == 0 and target_openid:
        for idx, (oid, _) in enumerate(user_scores, 1):
            if oid == target_openid:
                rank = idx
                break

    return {
        'total_exams': len(exam_records),
        'avg_score': round(sum(scores) / len(scores), 4) if scores else 0,
        'best_score': max(scores) if scores else 0,
        'rank': rank,
        'total_users': total_users,
        'records': sorted(exam_records, key=lambda x: x['date'], reverse=True)[:20],
        'score_trend': [{'date': e['date'], 'score': e['score_pct'], 'subject': e['subject']} for e in score_trend],
    }


def _build_knowledge_stats(records, notes, subjects_map):
    """模块3：知识点掌握情况。

    由于历史数据没有显式知识点标签，这里基于科目维度做掌握度评估。
    掌握度 = 该科目下的平均正确率，评级标准：
    >=0.85 精通, >=0.70 熟练, >=0.60 一般, >=0.40 薄弱, <0.40 未掌握
    """
    # 按科目聚合答题正确率
    subject_acc = defaultdict(lambda: {'sum': 0.0, 'n': 0, 'total_q': 0, 'right': 0, 'records': 0})
    for r in records:
        subject_name = r['subject'] or '未知科目'
        slot = subject_acc[subject_name]
        slot['records'] += 1
        slot['total_q'] += r['total']
        slot['right'] += r['rightNum']
        if r['accuracy'] is not None:
            slot['sum'] += r['accuracy']
            slot['n'] += 1

    # 按科目聚合错题数
    subject_notes = defaultdict(int)
    for n in notes:
        subject_name = n.get('subject') or '未知科目'
        # notes 没有直接科目字段，用 examid 关联
        subject_notes[subject_name] += 1

    knowledge_list = []
    for subject_name, s in sorted(subject_acc.items(), key=lambda x: -x[1]['records']):
        avg_acc = round(s['sum'] / s['n'], 4) if s['n'] else 0
        mastery_level = _mastery_level(avg_acc)
        knowledge_list.append({
            'name': subject_name,
            'accuracy': avg_acc,
            'mastery': mastery_level['level'],
            'mastery_label': mastery_level['label'],
            'mastery_color': mastery_level['color'],
            'mastery_pct': round(avg_acc * 100),
            'total_questions': s['total_q'],
            'right_questions': s['right'],
            'records': s['records'],
            'notes_count': subject_notes.get(subject_name, 0),
        })

    return knowledge_list


def _mastery_level(accuracy):
    """根据正确率返回掌握度评级。"""
    if accuracy >= 0.85:
        return {'level': 5, 'label': '精通', 'color': '#67c23a'}
    if accuracy >= 0.70:
        return {'level': 4, 'label': '熟练', 'color': '#409eff'}
    if accuracy >= 0.60:
        return {'level': 3, 'label': '一般', 'color': '#e6a23c'}
    if accuracy >= 0.40:
        return {'level': 2, 'label': '薄弱', 'color': '#f56c6c'}
    return {'level': 1, 'label': '未掌握', 'color': '#909399'}


def _build_weakness_stats(records, notes):
    """模块4：薄弱情况分析。

    - 薄弱知识点：正确率低于 60% 的科目
    - 高错误率题型：按题型统计错误率
    - 高频错题：反复出错的具体题目
    """

    def _is_question_right(q_data, user_answer):
        """比较用户答案与题目正确选项，返回 True 表示答对。"""
        if not isinstance(q_data, dict) or not isinstance(user_answer, list):
            return True  # 无法判断时默认正确，不计入错误率
        options = q_data.get('options') or []
        if not isinstance(options, list) or len(options) == 0:
            return True  # 非选项题（填空/问答）暂不判分，默认正确
        correct_codes = [str(opt.get('code', '')) for opt in options
                         if isinstance(opt, dict) and str(opt.get('value', '')) in ('1', 'True', 'true')]
        if not correct_codes:
            return True
        if len(user_answer) != len(correct_codes):
            return False
        return all(str(a) in correct_codes for a in user_answer)

    # 4.1 薄弱科目（正确率 < 60%）
    subject_acc = defaultdict(lambda: {'sum': 0.0, 'n': 0, 'total_q': 0, 'right': 0})
    for r in records:
        subject_name = r['subject'] or '未知科目'
        slot = subject_acc[subject_name]
        slot['total_q'] += r['total']
        slot['right'] += r['rightNum']
        if r['accuracy'] is not None:
            slot['sum'] += r['accuracy']
            slot['n'] += 1

    weak_subjects = []
    for subject_name, s in subject_acc.items():
        avg_acc = round(s['sum'] / s['n'], 4) if s['n'] else 0
        if avg_acc < 0.60:
            weak_subjects.append({
                'name': subject_name,
                'accuracy': avg_acc,
                'error_rate': round(1 - avg_acc, 4),
                'total_questions': s['total_q'],
                'wrong_questions': s['total_q'] - s['right'],
            })
    weak_subjects.sort(key=lambda x: x['accuracy'])

    # 4.2 按题型统计错误率
    # P0-4 修复：questions 存的是题目 ID 字符串列表，需批量获取题目对象
    all_qids = set()
    for r in records:
        for qid in r.get('questions', []):
            all_qids.add(str(qid))
    question_map = {}
    if all_qids:
        for item in du.iter_docs('questions'):
            qid = str(item['doc_id'] or item['pk'] or '')
            if qid in all_qids:
                question_map[qid] = item['data']

    type_stats = defaultdict(lambda: {'total': 0, 'wrong': 0})
    for r in records:
        score_arr = r.get('score_arr') or []
        questions = r.get('questions', [])
        for i, qid in enumerate(questions):
            qid_str = str(qid)
            q_data = question_map.get(qid_str)
            if not q_data:
                continue
            typename = _typename_normalize(q_data.get('typename'))
            type_stats[typename]['total'] += 1
            # 用 score_arr 中的用户答案判断对错
            user_ans = score_arr[i] if i < len(score_arr) else None
            if user_ans is not None and not _is_question_right(q_data, user_ans):
                type_stats[typename]['wrong'] += 1

    type_weakness = []
    for typename, s in type_stats.items():
        if s['total'] == 0:
            continue
        error_rate = round(s['wrong'] / s['total'], 4)
        type_weakness.append({
            'typename': typename,
            'total': s['total'],
            'wrong': s['wrong'],
            'error_rate': error_rate,
        })
    type_weakness.sort(key=lambda x: -x['error_rate'])

    # 4.3 高频错题（从 notes 中找反复出错的题目）
    note_title_counter = Counter(n['question_title'] for n in notes if n['question_title'])
    frequent_errors = []
    for title, count in note_title_counter.most_common(10):
        if count >= 1 and title:
            # 找该题的题型
            typename = ''
            for n in notes:
                if n['question_title'] == title:
                    typename = n['typename']
                    break
            frequent_errors.append({
                'title': title[:80],
                'typename': typename,
                'error_count': count,
            })

    return {
        'weak_subjects': weak_subjects,
        'type_weakness': type_weakness,
        'frequent_errors': frequent_errors,
        'total_notes': len(notes),
    }


# ---- 接口 ----

@perm.require_perms('user.view')
def user_profile(request, openid):
    """GET /api/admin/users/<openid>/profile/  用户综合画像。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)

    # 收集目标用户数据
    profile, records, notes, subjects_map, exams_map = _collect_user_data(openid)

    if not profile and not records and not notes:
        return fail(ErrorCode.NOT_FOUND, '用户不存在或无答题数据')

    # 收集所有用户答题记录（用于排名计算）
    all_records_raw = []
    for item in du.iter_docs('historys'):
        data = item['data']
        oid = data.get('_openid', '')
        if not oid:
            continue
        all_records_raw.append({
            '_openid': oid,
            'accuracy': du.accuracy_of(data),
        })

    # 给 records 补上 _openid 字段（排名用）
    for r in records:
        r['_openid'] = openid

    # 构建各模块数据
    answer_stats = _build_answer_stats(records)
    exam_stats = _build_exam_stats(records, notes, [all_records_raw])
    knowledge_stats = _build_knowledge_stats(records, notes, subjects_map)
    weakness_stats = _build_weakness_stats(records, notes)

    # 用户基础信息
    user_base = {
        'openid': openid,
        'nickname': profile.get('nickname') or '（未授权资料）',
        'avatar': profile.get('avatar') or '',
        'city': profile.get('city') or '',
        'status': profile.get('status') or 'active',
        'last_active': max((r['date'] for r in records if r['date']), default=None),
    }
    if user_base['last_active']:
        user_base['last_active'] = user_base['last_active'].strftime('%Y-%m-%d')

    return ok({
        'user': user_base,
        'answer': answer_stats,
        'exam': exam_stats,
        'knowledge': knowledge_stats,
        'weakness': weakness_stats,
    })
