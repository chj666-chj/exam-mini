"""数据统计看板接口。

- GET /api/admin/dashboard/overview/   核心指标概览
- GET /api/admin/dashboard/trend/      趋势数据（?days=30）
- GET /api/admin/dashboard/ranking/    活跃用户榜 / 科目分布
"""
from collections import Counter, defaultdict
from datetime import timedelta

from django.utils import timezone

from . import data_utils as du
from . import permissions as perm
from .responses import ErrorCode, fail, ok, paginate, parse_page
from core.models import Document

# 答题时长字段形如 "0:40"（分:秒）
def _duration_seconds(value):
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


def _collect_sources():
    """一次性汇总看板所需的轻量数据集。"""
    profiles = {}
    for item in du.iter_docs('profiles'):
        data = item['data']
        openid = data.get('_openid')
        if not openid:
            continue
        info = du.as_obj(data.get('userInfo')) or {}
        profiles[openid] = {
            'nickname': du.to_text(info.get('nickName')) if isinstance(info, dict) else '',
            'avatar': du.to_text(info.get('avatarUrl')) if isinstance(info, dict) else '',
        }

    records = []
    for item in du.iter_docs('historys'):
        data = item['data']
        records.append({
            'openid': data.get('_openid') or '',
            'date': du.doc_date(item),
            'subject': du.subject_name(data),
            'accuracy': du.accuracy_of(data),
            'duration': _duration_seconds(data.get('time')),
        })

    notes = []
    for item in du.iter_docs('notes'):
        data = item['data']
        notes.append({'openid': data.get('_openid') or '', 'date': du.doc_date(item)})

    return profiles, records, notes


def _anchor_date(records, notes):
    dates = [r['date'] for r in records if r['date']]
    dates += [n['date'] for n in notes if n['date']]
    return max(dates) if dates else timezone.localdate()


def _window_stats(records, notes, anchor, days):
    """统计以 anchor 为终点、向前 days 天的窗口指标。"""
    start = anchor - timedelta(days=days - 1)
    rec_in = [r for r in records if r['date'] and start <= r['date'] <= anchor]
    note_in = [n for n in notes if n['date'] and start <= n['date'] <= anchor]
    active = {r['openid'] for r in rec_in if r['openid']}
    new_users = _new_user_count(records, anchor, days)
    acc = [r['accuracy'] for r in rec_in if r['accuracy'] is not None]
    return {
        'records': len(rec_in),
        'notes': len(note_in),
        'active_users': len(active),
        'new_users': new_users,
        'avg_accuracy': round(sum(acc) / len(acc), 4) if acc else 0,
    }


def _new_user_count(records, anchor, days):
    """窗口内首次产生答题记录的用户数（以全量首次活跃日判断）。"""
    first = {}
    for r in records:
        if r['openid'] and r['date']:
            if r['openid'] not in first or r['date'] < first[r['openid']]:
                first[r['openid']] = r['date']
    start = anchor - timedelta(days=days - 1)
    return sum(1 for d in first.values() if start <= d <= anchor)


@perm.require_perms('dashboard.view')
def overview(request):
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)

    profiles, records, notes = _collect_sources()
    anchor = _anchor_date(records, notes)
    openids = set(profiles.keys()) | {r['openid'] for r in records if r['openid']} | {n['openid'] for n in notes if n['openid']}
    acc = [r['accuracy'] for r in records if r['accuracy'] is not None]
    durations = [r['duration'] for r in records if r['duration']]

    data = {
        'totals': {
            'users': len(openids),
            'exams': Document.objects.filter(collection='exam').count(),
            'subjects': Document.objects.filter(collection='subjects').count(),
            'questions': Document.objects.filter(collection='questions').count(),
            'records': len(records),
            'notes': len(notes),
        },
        'base_date': anchor.strftime('%Y-%m-%d'),
        'today': _window_stats(records, notes, anchor, 1),
        'last7': _window_stats(records, notes, anchor, 7),
        'last30': _window_stats(records, notes, anchor, 30),
        'avg_accuracy': round(sum(acc) / len(acc), 4) if acc else 0,
        'avg_duration': round(sum(durations) / len(durations), 1) if durations else 0,
        'updated_at': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    return ok(data)


@perm.require_perms('dashboard.view')
def trend(request):
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)

    try:
        days = int(request.GET.get('days', 30))
    except (TypeError, ValueError):
        days = 30
    days = max(7, min(days, 180))

    profiles, records, notes = _collect_sources()
    anchor = _anchor_date(records, notes)
    first = {}
    for r in records:
        if r['openid'] and r['date']:
            if r['openid'] not in first or r['date'] < first[r['openid']]:
                first[r['openid']] = r['date']

    rec_counter = Counter(r['date'] for r in records if r['date'])
    note_counter = Counter(n['date'] for n in notes if n['date'])
    new_counter = Counter(first.values())
    active_map = defaultdict(set)
    for r in records:
        if r['date'] and r['openid']:
            active_map[r['date']].add(r['openid'])

    series = []
    for offset in range(days - 1, -1, -1):
        day = anchor - timedelta(days=offset)
        series.append({
            'date': day.strftime('%Y-%m-%d'),
            'records': rec_counter.get(day, 0),
            'notes': note_counter.get(day, 0),
            'active_users': len(active_map.get(day, ())),
            'new_users': new_counter.get(day, 0),
        })
    return ok({'base_date': anchor.strftime('%Y-%m-%d'), 'days': days, 'series': series})


@perm.require_perms('dashboard.view')
def ranking(request):
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)

    profiles, records, notes = _collect_sources()

    user_stat = defaultdict(lambda: {'records': 0, 'notes': 0, 'last': None, 'acc_sum': 0.0, 'acc_n': 0})
    for r in records:
        if not r['openid']:
            continue
        s = user_stat[r['openid']]
        s['records'] += 1
        if r['date'] and (s['last'] is None or r['date'] > s['last']):
            s['last'] = r['date']
        if r['accuracy'] is not None:
            s['acc_sum'] += r['accuracy']
            s['acc_n'] += 1
    for n in notes:
        if n['openid']:
            user_stat[n['openid']]['notes'] += 1

    top_users = []
    for openid, s in sorted(user_stat.items(), key=lambda kv: (-kv[1]['records'], -kv[1]['notes']))[:10]:
        profile = profiles.get(openid, {})
        top_users.append({
            'openid': openid,
            'nickname': profile.get('nickname') or '（未授权资料）',
            'records': s['records'],
            'notes': s['notes'],
            'accuracy': round(s['acc_sum'] / s['acc_n'], 4) if s['acc_n'] else 0,
            'last_active': s['last'].strftime('%Y-%m-%d') if s['last'] else '',
        })

    subject_counter = Counter(r['subject'] or '未知科目' for r in records)
    accuracy_by_subject = defaultdict(lambda: [0.0, 0])
    for r in records:
        if r['accuracy'] is not None:
            bucket = accuracy_by_subject[r['subject'] or '未知科目']
            bucket[0] += r['accuracy']
            bucket[1] += 1
    subjects = [
        {
            'name': name,
            'records': count,
            'accuracy': round(accuracy_by_subject[name][0] / accuracy_by_subject[name][1], 4)
            if accuracy_by_subject.get(name) and accuracy_by_subject[name][1] else 0,
        }
        for name, count in subject_counter.most_common(10)
    ]

    return ok({'top_users': top_users, 'subjects': subjects})


@perm.require_perms('admin.view')
def operation_logs(request):
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)

    """GET /api/admin/dashboard/logs/ 操作审计日志"""
    from .models import OperationLog
    page, page_size = parse_page(request)
    qs = OperationLog.objects.all()
    username = request.GET.get('username', '').strip()
    action = request.GET.get('action', '').strip()
    if username:
        qs = qs.filter(username__icontains=username)
    if action:
        qs = qs.filter(action__icontains=action)
    total = qs.count()
    items = [x.to_client() for x in qs[(page - 1) * page_size: page * page_size]]
    return ok(paginate(items, total, page, page_size))
