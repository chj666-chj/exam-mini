"""通用数据处理工具：把通用文档模型里的业务数据规整为看板/列表可用结构。

小程序端的数据以「集合 + JSON 文档」形式存放（core.Document），
管理端在此统一做类型归一、时间解析与字段抽取，避免各视图重复实现。
"""
import ast
from datetime import date, datetime

from django.utils import timezone

from core.models import Document


def iter_docs(collection, only_ids=False):
    """惰性遍历集合内文档数据（dict）。"""
    qs = Document.objects.filter(collection=collection).order_by('pk')
    if only_ids:
        return qs.values_list('pk', flat=True)
    for data, pk, doc_id, created in qs.values_list('data', 'pk', 'doc_id', 'created_at'):
        yield {'data': data, 'pk': pk, 'doc_id': doc_id, 'created_at': created}


def to_text(value, default=''):
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ('name', 'title', 'nickName', 'content'):
            if key in value:
                return to_text(value[key], default)
        return default
    return default


def to_number(value, default=0):
    """把 '3.0' / 3.0 / '3' / True 等转为数字。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    try:
        text = str(value).strip()
        if not text:
            return default
        return float(text) if '.' in text else int(text)
    except (TypeError, ValueError):
        return default


def as_obj(value):
    """兼容字段被存成 Python repr 字符串的情况（历史数据）。"""
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in '[{':
            try:
                return ast.literal_eval(text)
            except (ValueError, SyntaxError):
                return None
    return None


def parse_datetime(value):
    """解析多种时间格式：

    - '2020/03/22 17:47' / '2020-03-22 17:47:00'
    - '20200322174708'（14 位时间戳）
    - 10/13 位 unix 时间戳
    - datetime / date 对象
    """
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    if isinstance(value, date):
        return timezone.make_aware(datetime.combine(value, datetime.min.time()))
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        try:
            return timezone.make_aware(datetime.fromtimestamp(ts))
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        if len(text) == 14:
            try:
                return timezone.make_aware(datetime.strptime(text, '%Y%m%d%H%M%S'))
            except ValueError:
                return None
        if len(text) == 8:
            try:
                return timezone.make_aware(datetime.strptime(text, '%Y%m%d'))
            except ValueError:
                return None
    for fmt in (
        '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M', '%Y/%m/%d',
        '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
        '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f',
    ):
        try:
            dt = datetime.strptime(text[:len(fmt) + 8] if fmt.endswith('%f') else text, fmt)
            return timezone.make_aware(dt)
        except ValueError:
            continue
    return None


def doc_time(doc, include_created=False):
    """取文档业务时间。

    依次尝试：createTime -> ordernum（交卷批次号，14 位时间戳）-> _id 时间戳 -> time。
    include_created=True 时才回退到数据落库时间（导入时间），
    看板统计默认关闭该回退，避免"导入时间"污染业务趋势。
    """
    data = doc['data'] if isinstance(doc, dict) and 'data' in doc else doc
    for key in ('createTime', 'ordernum', '_id', 'time'):
        dt = parse_datetime(data.get(key))
        if dt:
            return dt
    if include_created and isinstance(doc, dict):
        return doc.get('created_at')
    return None


def doc_date(doc):
    dt = doc_time(doc)
    return dt.date() if dt else None


def collect_openids():
    """汇总所有出现过的 openid 及其来源集合。"""
    result = {}
    for collection in ('profiles', 'historys', 'notes', 'test', 'record', 'history'):
        for item in iter_docs(collection):
            openid = item['data'].get('_openid')
            if not openid:
                continue
            info = result.setdefault(openid, {'openid': openid, 'collections': set()})
            info['collections'].add(collection)
    return result


def subject_name(doc_data):
    subj = as_obj(doc_data.get('subject')) or {}
    if isinstance(subj, dict):
        return to_text(subj.get('name'))
    return to_text(subj)


def accuracy_of(doc_data):
    """答题记录正确率（0~1），无法计算时返回 None。"""
    right = to_number(doc_data.get('rightNum'), None) if doc_data.get('rightNum') is not None else None
    items = as_obj(doc_data.get('items')) or []
    questions = as_obj(doc_data.get('questions')) or []
    total = len(items) or len(questions) or 0
    if right is None or not total:
        return None
    return max(0.0, min(1.0, right / float(total)))
