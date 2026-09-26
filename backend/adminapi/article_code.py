"""文章唯一编码工具。

编码规则（全平台统一）：``ART-YYYYMMDD-NNNN``

- ``ART``     固定前缀，标识「文章」域，与题目（RK_*）、知识库（KB_*）区分
- ``YYYYMMDD`` 文章入库日期（本地时区），保证编码按天重置、可读可排序
- ``NNNN``     当日流水号，4 位零填充，从 0001 开始

唯一性保证：生成时扫描同前缀已用编码，取最大流水号 +1；不依赖数据库自增，
因此在 SQLite 单库、多进程并发下也能通过「生成 → 落库」前的重复检查兜底。
写入路径统一走 :func:`assign_article_code`，保证任何入口（管理端新建、
小程序投稿、种子数据、回填命令）都使用同一套规则。

可追溯性：文章进入知识库索引时，派生的知识库文档 ``_id`` 固定为
``KB_ART_<编码>``（见 :func:`kb_doc_id_for_code`）。于是：

- 由知识库条目 ``KB_ART_ART-20260912-0001`` 可反查文章编码 ``ART-20260912-0001``
- 由文章编码可正查它在索引中的条目 ``KB_ART_<编码>``
"""
import re

from django.utils import timezone

from core.models import Document

from . import data_utils as du

ARTICLE_COLLECTION = 'articles'
KB_COLLECTION = 'knowledgebase'

CODE_PREFIX = 'ART'
KB_DOC_PREFIX = 'KB_ART_'
MAX_SEQ_PER_DAY = 9999

#: 文章编码校验正则（严格格式）
CODE_RE = re.compile(r'^ART-(\d{8})-(\d{4})$')
#: 知识库中由文章派生的文档 _id 校验正则（前缀为 KB_ART_，下划线分隔）
KB_ART_DOC_ID_RE = re.compile(r'^KB_ART_(ART-\d{8}-\d{4})$')


# --------------------------------------------------------------------------
# 解析 / 校验
# --------------------------------------------------------------------------

def parse_article_code(code):
    """解析文章编码。

    Args:
        code: 待解析编码字符串

    Returns:
        ``{'code','date','seq'}`` 或 ``None``（格式非法）
    """
    if not isinstance(code, str):
        return None
    text = code.strip()
    match = CODE_RE.match(text)
    if not match:
        return None
    return {'code': text, 'date': match.group(1), 'seq': int(match.group(2))}


def is_valid_article_code(code):
    """判断是否为合法文章编码。"""
    return parse_article_code(code) is not None


def article_code_of(doc):
    """读取文章 Document 上的编码（无则返回 None）。"""
    if doc is None:
        return None
    data = getattr(doc, 'data', None) or {}
    code = data.get('code')
    if isinstance(code, str) and code.strip():
        return code.strip()
    return None


# --------------------------------------------------------------------------
# 可追溯关联：文章编码 <-> 知识库文档 _id
# --------------------------------------------------------------------------

def kb_doc_id_for_code(code):
    """文章编码 → 知识库文档 _id。"""
    if not is_valid_article_code(code):
        return None
    return '%s%s' % (KB_DOC_PREFIX, code.strip())


def kb_doc_id_for_article(doc):
    """文章 Document → 知识库文档 _id（无编码时返回 None）。"""
    return kb_doc_id_for_code(article_code_of(doc))


def parse_kb_art_doc_id(doc_id):
    """知识库文档 _id → 文章编码（非文章派生条目返回 None）。"""
    if not isinstance(doc_id, str):
        return None
    match = KB_ART_DOC_ID_RE.match(doc_id.strip())
    return match.group(1) if match else None


# --------------------------------------------------------------------------
# 生成 / 分配
# --------------------------------------------------------------------------

def _existing_codes(date_part):
    """收集某日期下已使用的文章编码集合。"""
    prefix = '%s-%s-' % (CODE_PREFIX, date_part)
    codes = set()
    qs = Document.objects.filter(collection=ARTICLE_COLLECTION).only('doc_id', 'data')
    for doc in qs:
        data = doc.data or {}
        code = data.get('code')
        if isinstance(code, str) and code.startswith(prefix):
            codes.add(code.strip())
    return codes


def _next_code(date_part):
    """在同日期已用编码基础上取下一个可用流水号。"""
    base = '%s-%s-' % (CODE_PREFIX, date_part)
    used = _existing_codes(date_part)
    for seq in range(1, MAX_SEQ_PER_DAY + 1):
        candidate = '%s%04d' % (base, seq)
        if candidate not in used:
            return candidate
    raise ValueError('当日文章编码已用尽（上限 %d 条）' % MAX_SEQ_PER_DAY)


def generate_article_code(now=None):
    """生成一个新的文章编码（仅生成，不落库）。

    Args:
        now: 可选的 datetime（用于测试注入）

    Returns:
        形如 ``ART-20260912-0001`` 的编码
    """
    moment = now or timezone.localtime(timezone.now())
    if timezone.is_naive(moment):
        moment = timezone.localtime(timezone.make_aware(moment))
    return _next_code(moment.strftime('%Y%m%d'))


def assign_article_code(doc, now=None, save=True):
    """为文章补编码（幂等）。

    已有合法编码时直接返回原编码；否则生成并写入 ``data['code']``。

    Args:
        doc:  core.Document（collection='articles'）
        now:  可选 datetime（测试注入）
        save: 是否立即保存

    Returns:
        编码字符串
    """
    if doc is None:
        return None
    existing = article_code_of(doc)
    if existing and is_valid_article_code(existing):
        return existing

    code = generate_article_code(now)
    data = dict(doc.data or {})
    data['code'] = code
    doc.data = data
    if save:
        doc.save()
    return code


def _date_part_of(doc, fallback=None):
    """取文章入库日期（优先 createTime，其次 updateTime，最后当前日期）。"""
    data = doc.data or {}
    for key in ('createTime', 'updateTime'):
        moment = du.parse_datetime(data.get(key))
        if moment:
            return timezone.localtime(moment).strftime('%Y%m%d')
    if fallback:
        return fallback
    return timezone.localtime(timezone.now()).strftime('%Y%m%d')


def backfill_article_codes():
    """为缺少编码的历史文章补编码（幂等）。

    按文章 ``createTime`` 归属日期分组，组内按 pk 升序分配当日流水号，
    结果稳定可复现；已存在合法编码的文章保持不变。

    Returns:
        ``{'total': 文章总数, 'assigned': 本次补码数, 'skipped': 已有编码数}``
    """
    docs = list(Document.objects.filter(collection=ARTICLE_COLLECTION).order_by('pk'))
    used = {}
    pending = []

    for doc in docs:
        code = article_code_of(doc)
        if code and is_valid_article_code(code):
            used.setdefault(code.split('-')[1], set()).add(code)
        else:
            pending.append(doc)

    for doc in pending:
        date_part = _date_part_of(doc)
        bucket = used.setdefault(date_part, set())
        chosen = None
        for seq in range(1, MAX_SEQ_PER_DAY + 1):
            candidate = '%s-%s-%04d' % (CODE_PREFIX, date_part, seq)
            if candidate not in bucket:
                chosen = candidate
                break
        if not chosen:
            continue
        bucket.add(chosen)
        data = dict(doc.data or {})
        data['code'] = chosen
        doc.data = data
        doc.save()

    assigned = len(pending)
    return {
        'total': len(docs),
        'assigned': assigned,
        'skipped': len(docs) - assigned,
    }
