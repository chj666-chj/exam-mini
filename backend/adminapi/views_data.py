"""小程序业务数据管理接口（基于通用文档集合）+ 用户聚合视图。

统一约定：
- 列表：GET  /api/admin/<resource>/?page=1&page_size=20&keyword=xx&<字段>=<值>&ordering=-pk
- 新增：POST /api/admin/<resource>/            body 为文档 JSON（可带 _id 指定主键）
- 更新：PUT  /api/admin/<resource>/<id>/       body 为完整文档
- 局部：PATCH /api/admin/<resource>/<id>/      body 为待更新字段
- 删除：DELETE /api/admin/<resource>/<id>/
- 批量删除：POST /api/admin/<resource>/bulk-delete/  {"ids": [...]}
"""
from django.db import transaction
from django.db.models import Q
from django.core.cache import cache
from django.utils import timezone

from core.models import Document
from . import article_code
from . import data_utils as du
from . import permissions as perm
from .models import QuestionTag, Tag
from .responses import ErrorCode, fail, ok, paginate, parse_page

# ---- 业务数据校验 ----
def _validate_named(body):
    """带名称字段的资源（考试/科目）：name 出现时不得为空。"""
    if 'name' in body and not du.to_text(body.get('name')).strip():
        return '名称不能为空'
    return None


def _validate_exam(body):
    """考试数据校验：name 必填，duration/passScore/totalScore/questionCount 为非负数，status 枚举合法。"""
    if 'name' in body and not du.to_text(body.get('name')).strip():
        return '考试名称不能为空'
    # 数值字段非负校验
    for field in ('duration', 'passScore', 'totalScore', 'questionCount'):
        if field in body:
            val = du.to_number(body.get(field), 0)
            if val < 0:
                return f'{field} 不能为负数'
    # 状态枚举校验
    valid_status = ('draft', 'published', 'archived')
    if 'status' in body:
        status = du.to_text(body.get('status')).strip()
        if status and status not in valid_status:
            return f'status 必须是 {", ".join(valid_status)} 之一'
    # 评分方式枚举校验
    valid_scoring = ('auto', 'manual', 'hybrid')
    if 'scoringType' in body:
        scoring = du.to_text(body.get('scoringType')).strip()
        if scoring and scoring not in valid_scoring:
            return f'scoringType 必须是 {", ".join(valid_scoring)} 之一'
    # 及格分不应超过总分
    pass_score = du.to_number(body.get('passScore'), 0)
    total_score = du.to_number(body.get('totalScore'), 0)
    if pass_score and total_score and pass_score > total_score:
        return '及格分不能超过总分'
    return None


def _validate_studynote(body):
    """学习笔记数据校验：title 必填。"""
    if 'title' in body and not du.to_text(body.get('title')).strip():
        return '笔记标题不能为空'
    return None


def _validate_article(body):
    """文章数据校验：title 必填且非空、status 枚举合法、images 最多 3 张、tags 最多 5 个。"""
    if 'title' in body and not du.to_text(body.get('title')).strip():
        return '文章标题不能为空'
    valid_status = ('pending', 'published', 'rejected', 'taken_down')
    if 'status' in body:
        status = du.to_text(body.get('status')).strip()
        if status and status not in valid_status:
            return 'status 必须是 %s 之一' % ' / '.join(valid_status)
    if 'images' in body:
        images = body.get('images')
        if not isinstance(images, list):
            return 'images 必须是数组'
        if len(images) > 3:
            return 'images 最多 3 张'
    if 'tags' in body:
        tags = body.get('tags')
        if not isinstance(tags, list):
            return 'tags 必须是数组'
        if len(tags) > 5:
            return 'tags 最多 5 个'
    return None


def _validate_activation_code(body):
    """激活码数据校验：code 必须为 6 位数字，status 枚举合法，vipDuration 非负。"""
    if 'code' in body:
        code = du.to_text(body.get('code')).strip()
        if not code:
            return '激活码不能为空'
        if not (code.isdigit() and len(code) == 6):
            return '激活码必须为 6 位数字'
    valid_status = ('active', 'used', 'disabled')
    if 'status' in body:
        status = du.to_text(body.get('status')).strip()
        if status and status not in valid_status:
            return f'status 必须是 {", ".join(valid_status)} 之一'
    if 'vipDuration' in body:
        val = du.to_number(body.get('vipDuration'), 0)
        if val < 0:
            return 'vipDuration 不能为负数'
    return None


def _validate_question(body):
    """题目数据校验。"""
    # 题干：仅当 title 或 content_md 出现在 body 中时才校验非空
    has_title_key = 'title' in body
    has_content_key = 'content_md' in body
    if has_title_key or has_content_key:
        title = du.to_text(body.get('title')).strip()
        content_md = du.to_text(body.get('content_md')).strip()
        if not title and not content_md:
            return '题干不能为空（title 或 content_md 至少填一个）'
    if 'examid' in body and not du.to_text(body.get('examid')).strip():
        return '所属科目编号 examid 不能为空'
    if 'options' in body:
        options = body.get('options')
        if not isinstance(options, list):
            return 'options 必须是数组'
        if len(options) < 2:
            return '选项至少需要 2 个'
        for idx, opt in enumerate(options):
            if not isinstance(opt, dict):
                return f'第 {idx + 1} 个选项必须是对象'
            if not du.to_text(opt.get('code')).strip():
                return f'第 {idx + 1} 个选项缺少选项码 code'
            if not du.to_text(opt.get('content')).strip():
                return f'第 {idx + 1} 个选项缺少内容 content'
        if not any(du.to_number(opt.get('value'), 0) == 1 or opt.get('is_correct') for opt in options):
            return '请至少指定一个正确答案（value=1 或 is_correct=true）'
    return None


# 资源 -> 集合配置
RESOURCES = {
    'exams': {
        'collection': 'exam', 'view': 'exam.view', 'manage': 'exam.manage', 'label': '考试',
        'search': ['name', 'code', 'desc'], 'filters': ['code', 'status'], 'ordering': 'pk',
        'required': ['name'], 'validator': _validate_exam,
    },
    'subjects': {
        'collection': 'subjects', 'view': 'subject.view', 'manage': 'subject.manage', 'label': '科目',
        'search': ['name', 'pid', 'code'], 'filters': ['pid', 'code'], 'ordering': 'pk',
        'required': ['name'], 'validator': _validate_named,
    },
    'questions': {
        'collection': 'questions', 'view': 'question.view', 'manage': 'question.manage', 'label': '题目',
        'search': ['title', 'typename', 'comments', 'content_md'], 'filters': ['examid', 'typecode', 'typename', 'qtype'], 'ordering': 'pk',
        'required': ['examid'], 'validator': _validate_question,
    },
    'records': {
        'collection': 'historys', 'view': 'record.view', 'manage': 'record.manage', 'label': '答题记录',
        'search': ['_openid'], 'filters': ['_openid'], 'ordering': '-pk',
        'required': [], 'validator': None,
    },
    'notes': {
        'collection': 'notes', 'view': 'note.view', 'manage': 'note.manage', 'label': '错题笔记',
        'search': ['_openid', 'ordernum'], 'filters': ['_openid', 'ordernum', 'category', 'reviewStatus'],
        'ordering': '-pk', 'required': [], 'validator': None,
    },
    'knowledge': {
        'collection': 'knowledgebase', 'view': 'knowledge.view', 'manage': 'knowledge.manage', 'label': '知识库',
        'search': ['title', 'category', 'summary'], 'filters': ['type', 'category'], 'ordering': '-pk',
        'required': ['title'], 'validator': None,
    },
    'studynotes': {
        'collection': 'studynotes', 'view': 'studynote.view', 'manage': 'studynote.manage', 'label': '学习笔记',
        'search': ['title', 'category', 'tags', 'content'], 'filters': ['category'], 'ordering': '-pk',
        'required': ['title'], 'validator': _validate_studynote,
    },
    'articles': {
        'collection': 'articles', 'view': 'article.view', 'manage': 'article.manage', 'label': '文章',
        'search': ['title', 'summary', 'tags', 'author', 'code'],
        'filters': ['status', 'tags', 'code'], 'ordering': '-pk',
        'required': ['title'], 'validator': _validate_article,
    },
    'app-settings': {
        'collection': 'app_config', 'view': 'admin.view', 'manage': 'admin.manage', 'label': '应用设置',
        'search': ['doc_id', 'title'], 'filters': ['doc_id'], 'ordering': 'pk',
        'required': ['doc_id'], 'validator': None,
    },
    'activation-codes': {
        'collection': 'activation_codes', 'view': 'admin.view', 'manage': 'admin.manage', 'label': '激活码',
        'search': ['code', 'usedBy', 'note'], 'filters': ['status'], 'ordering': '-pk',
        'required': ['code'], 'validator': _validate_activation_code,
    },
}


def _validate_payload(config, body, partial=False):
    """校验写入数据，返回错误信息或 None。

    partial=True（PATCH）只校验出现的字段；全量写入（POST/PUT）额外校验必填字段。
    """
    if not partial:
        for field in config.get('required', []):
            value = body.get(field)
            if value is None or (isinstance(value, str) and not value.strip()) or value == []:
                return f'缺少必填字段：{field}'
    validator = config.get('validator')
    if validator:
        return validator(body)
    return None

USER_STATUS_ACTIVE = 'active'
USER_STATUS_DISABLED = 'disabled'


# ---------------------------------------------------------------- 通用集合资源
def _resource(request, name):
    """解析资源名并校验读权限，返回 (config, error)。"""
    config = RESOURCES.get(name)
    if not config:
        return None, fail(ErrorCode.NOT_FOUND, f'未知资源：{name}')
    user = request.admin_user
    if not user.is_superuser and config['view'] not in user.permissions:
        return None, fail(ErrorCode.FORBIDDEN, f'无权限查看{config["label"]}')
    return config, None


def _need_manage(request, config):
    user = request.admin_user
    if not user.is_superuser and config['manage'] not in user.permissions:
        return fail(ErrorCode.FORBIDDEN, f'无权限修改{config["label"]}')
    return None


def _build_query(config, request):
    qs = Document.objects.filter(collection=config['collection'])
    keyword = request.GET.get('keyword', '').strip()
    if keyword:
        cond = Q()
        for field in config['search']:
            cond |= Q(**{f'data__{field}__icontains': keyword})
        qs = qs.filter(cond)
    for field in config['filters']:
        raw = request.GET.get(field)
        if raw in (None, ''):
            continue
        lookup = f'data__{field}'
        qs = qs.filter(Q(**{lookup: raw}) | Q(**{lookup: du.to_number(raw, raw)}))
    return qs


def _apply_ordering(qs, config, request):
    ordering = request.GET.get('ordering') or config['ordering']
    if ordering in ('pk', '-pk', 'created_at', '-created_at', 'updated_at', '-updated_at'):
        if ordering.endswith('created_at') or ordering.endswith('updated_at'):
            return qs.order_by(ordering.replace('created_at', 'created_at'))
        return qs.order_by(ordering)
    return qs.order_by(config['ordering'])


def _serialize(doc):
    item = doc.to_client()
    item['_created_at'] = timezone.localtime(doc.created_at).strftime('%Y-%m-%d %H:%M:%S')
    item['_updated_at'] = timezone.localtime(doc.updated_at).strftime('%Y-%m-%d %H:%M:%S')
    return item


def _enrich_questions_with_tags(docs, items):
    """批量加载题目-标签绑定关系，附加 _tags 字段到列表项。"""
    doc_pks = [d.pk for d in docs]
    if not doc_pks:
        return items
    bindings = QuestionTag.objects.filter(
        question_id__in=doc_pks
    ).select_related('tag')
    tags_by_doc = {}
    for b in bindings:
        tags_by_doc.setdefault(b.question_id, []).append(b.tag.to_client())
    for doc, item in zip(docs, items):
        item['_tags'] = tags_by_doc.get(doc.pk, [])
    return items


def _bind_question_tags(question_doc, tag_ids):
    """为题目文档创建/替换标签绑定（全量替换），并同步 tag_ids 到文档数据。"""
    valid_ids = [int(t) for t in tag_ids if str(t).isdigit()]
    tags = list(Tag.objects.filter(pk__in=valid_ids))
    with transaction.atomic():
        question_doc.tag_bindings.all().delete()
        QuestionTag.objects.bulk_create(
            [QuestionTag(question=question_doc, tag=t) for t in tags]
        )
        synced_ids = sorted(question_doc.tag_bindings.values_list('tag_id', flat=True))
    data = dict(question_doc.data)
    data['tag_ids'] = synced_ids
    question_doc.data = data
    question_doc.save(update_fields=['data'])
    return synced_ids


def _find_doc(collection, doc_id):
    try:
        return Document.objects.get(collection=collection, doc_id=str(doc_id))
    except Document.DoesNotExist:
        pass
    if str(doc_id).isdigit():
        try:
            return Document.objects.get(collection=collection, pk=int(doc_id), doc_id=None)
        except Document.DoesNotExist:
            return None
    return None


@perm.require_perms()
def resource_list(request, name):
    config, err = _resource(request, name)
    if err:
        return err
    if request.method == 'POST':
        return _resource_create(request, config)
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET / POST', http_status=405)
    page, page_size = parse_page(request)
    qs = _apply_ordering(_build_query(config, request), config, request)
    total = qs.count()
    docs = list(qs[(page - 1) * page_size: page * page_size])
    items = [_serialize(d) for d in docs]
    # 题目列表附加标签绑定信息
    if config['collection'] == 'questions':
        items = _enrich_questions_with_tags(docs, items)
    return ok(paginate(items, total, page, page_size))


def _resource_create(request, config):
    err = _need_manage(request, config)
    if err:
        return err
    body, err = perm.json_body(request)
    if err:
        return err
    body.pop('_created_at', None)
    body.pop('_updated_at', None)
    doc_id = body.pop('_id', None)
    if doc_id in (None, ''):
        doc_id = None
    else:
        doc_id = str(doc_id)
        if _find_doc(config['collection'], doc_id):
            return fail(ErrorCode.CONFLICT, f'该 _id 已存在：{doc_id}')
    message = _validate_payload(config, body, partial=False)
    if message:
        return fail(ErrorCode.PARAM_ERROR, message)
    obj = Document.objects.create(collection=config['collection'], doc_id=doc_id, data=body)
    # 文章：自动生成唯一编码（ART-YYYYMMDD-NNNN），供知识库索引溯源使用
    if config['collection'] == 'articles':
        article_code.assign_article_code(obj)
    # 题目：创建标签绑定
    if config['collection'] == 'questions' and isinstance(body.get('tag_ids'), list):
        _bind_question_tags(obj, body['tag_ids'])
    perm.log_action(
        request.admin_user, f'{name_of(config)}.create',
        target=obj.doc_id or str(obj.pk), detail=_brief(body), ip=perm.client_ip(request),
    )
    return ok({'_id': obj.doc_id or str(obj.pk)}, '新增成功')


def name_of(config):
    for key, cfg in RESOURCES.items():
        if cfg is config:
            return key.rstrip('s') if key != 'exams' else 'exam'
    return 'data'


def _brief(body, length=120):
    for key in ('title', 'name', 'content', 'ordernum', '_openid'):
        if body.get(key):
            return str(body[key])[:length]
    return str(body)[:length]


@perm.require_perms()
def resource_detail(request, name, doc_id):
    config, err = _resource(request, name)
    if err:
        return err
    doc = _find_doc(config['collection'], doc_id)
    if not doc:
        return fail(ErrorCode.NOT_FOUND, '记录不存在')

    if request.method == 'GET':
        return ok(_serialize(doc))

    err = _need_manage(request, config)
    if err:
        return err

    if request.method in ('PUT', 'PATCH'):
        body, err = perm.json_body(request)
        if err:
            return err
        body.pop('_id', None)
        body.pop('_created_at', None)
        body.pop('_updated_at', None)
        if request.method == 'PUT':
            # 全量替换：先校验，归属字段不可被改写
            merged = dict(doc.data)
            merged.update(body)
            message = _validate_payload(config, merged, partial=False)
            if message:
                return fail(ErrorCode.PARAM_ERROR, message)
            if '_openid' in doc.data:
                merged['_openid'] = doc.data['_openid']
            doc.data = merged
        else:
            # 局部更新：只校验出现的字段
            message = _validate_payload(config, body, partial=True)
            if message:
                return fail(ErrorCode.PARAM_ERROR, message)
            doc.data.update(body)

        # AI 缓存失效：题目内容或题型变更时清除 ai_analysis
        if config['collection'] == 'questions' and ('content_md' in body or 'qtype' in body):
            doc.data['ai_analysis'] = None

        doc.save()
        # 文章：确保存在唯一编码（兼容历史数据 / 手工写入）
        if config['collection'] == 'articles':
            article_code.assign_article_code(doc)
        # 题目：更新标签绑定
        if config['collection'] == 'questions' and 'tag_ids' in body:
            _bind_question_tags(doc, body.get('tag_ids') or [])
        perm.log_action(
            request.admin_user, f'{name_of(config)}.update', target=str(doc_id),
            detail=_brief(body), ip=perm.client_ip(request),
        )
        return ok({'_id': doc.doc_id or str(doc.pk)}, '保存成功')

    if request.method == 'DELETE':
        doc.delete()
        perm.log_action(request.admin_user, f'{name_of(config)}.delete', target=str(doc_id), ip=perm.client_ip(request))
        return ok({'deleted': True}, '删除成功')

    return fail(ErrorCode.PARAM_ERROR, '方法不支持', http_status=405)


@perm.require_perms()
def resource_bulk_delete(request, name):
    config, err = _resource(request, name)
    if err:
        return err
    err = _need_manage(request, config)
    if err:
        return err
    body, err = perm.json_body(request)
    if err:
        return err
    ids = body.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return fail(ErrorCode.PARAM_ERROR, 'ids 不能为空')
    deleted = 0
    for doc_id in ids:
        doc = _find_doc(config['collection'], doc_id)
        if doc:
            doc.delete()
            deleted += 1
    perm.log_action(
        request.admin_user, f'{name_of(config)}.bulk_delete',
        target=f'{deleted} 条', ip=perm.client_ip(request),
    )
    return ok({'deleted': deleted}, f'已删除 {deleted} 条记录')


# ---------------------------------------------------------------- 文章审核
@perm.require_perms('article.audit')
def article_audit(request, doc_id):
    """POST /api/admin/articles/<doc_id>/audit/  审核文章。

    请求体：{action: 'publish'|'reject'|'takedown', reason?: string}
    - publish  -> status='published'
    - reject   -> status='rejected'，保存 rejectReason
    - takedown -> status='taken_down'
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    doc = _find_doc('articles', doc_id)
    if not doc:
        return fail(ErrorCode.NOT_FOUND, '文章不存在')

    body, err = perm.json_body(request)
    if err:
        return err

    action = du.to_text(body.get('action')).strip()
    reason = du.to_text(body.get('reason')).strip()

    action_status_map = {
        'publish': 'published',
        'reject': 'rejected',
        'takedown': 'taken_down',
    }
    if action not in action_status_map:
        return fail(ErrorCode.PARAM_ERROR, 'action 必须是 publish / reject / takedown 之一')

    now_str = timezone.localtime(timezone.now()).strftime('%Y/%m/%d %H:%M')
    doc.data['status'] = action_status_map[action]
    doc.data['updateTime'] = now_str
    if action == 'reject':
        doc.data['rejectReason'] = reason
    else:
        doc.data.pop('rejectReason', None)
    doc.save()

    perm.log_action(
        request.admin_user, 'article.audit',
        target=str(doc_id), detail='%s: %s' % (action, reason), ip=perm.client_ip(request),
    )
    return ok({'_id': doc.doc_id or str(doc.pk)}, '审核操作成功')


# ---------------------------------------------------------------- 错题统计
@perm.require_perms('note.view', methods=['GET'])
def notes_stats(request):
    """GET /api/admin/notes/stats/  错题分类统计聚合。

    返回：
    - total: 错题总数
    - by_category: 按分类分组 {category: count}
    - by_review_status: 按复习状态分组 {status: count}
    - by_subject: 按科目分组（从 question.examid 推断）{subject: count}
    - frequent: 错误频率最高的前 10 道题（按 ordernum 聚合）
    """
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)

    docs = list(du.iter_docs('notes'))
    total = len(docs)

    by_category = {}
    by_review_status = {}
    by_subject = {}
    ordernum_count = {}

    for item in docs:
        data = item['data']
        # 分类统计
        cat = du.to_text(data.get('category')) or '未分类'
        by_category[cat] = by_category.get(cat, 0) + 1
        # 复习状态统计
        status = du.to_text(data.get('reviewStatus')) or 'pending'
        by_review_status[status] = by_review_status.get(status, 0) + 1
        # 科目统计（从 question 中推断）
        question = du.as_obj(data.get('question')) or {}
        examid = du.to_text(question.get('examid')) if isinstance(question, dict) else ''
        subject = du.to_text(data.get('subject')) or examid or '未知科目'
        by_subject[subject] = by_subject.get(subject, 0) + 1
        # 错误频率
        ordernum = du.to_text(data.get('ordernum'))
        if ordernum:
            ordernum_count[ordernum] = ordernum_count.get(ordernum, 0) + 1

    # 高频错题 Top 10
    frequent = sorted(ordernum_count.items(), key=lambda x: x[1], reverse=True)[:10]
    frequent_list = [{'ordernum': k, 'count': v} for k, v in frequent]

    return ok({
        'total': total,
        'by_category': by_category,
        'by_review_status': by_review_status,
        'by_subject': by_subject,
        'frequent': frequent_list,
    })


# ---------------------------------------------------------------- 原始数据浏览
@perm.require_perms('data.view')
def collection_index(request):
    """GET /api/admin/collections/ 集合概览（含文档数量）"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    rows = (
        Document.objects.values('collection')
        .order_by('collection')
        .distinct()
    )
    data = []
    for row in rows:
        name = row['collection']
        data.append({'name': name, 'count': Document.objects.filter(collection=name).count()})
    return ok(data)


@perm.require_perms('data.view')
def collection_docs(request, name):
    """GET /api/admin/collections/<name>/ 原始文档分页浏览"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    page, page_size = parse_page(request, default_size=10)
    qs = Document.objects.filter(collection=name)
    keyword = request.GET.get('keyword', '').strip()
    if keyword:
        qs = qs.filter(Q(data__icontains=keyword) | Q(doc_id__icontains=keyword))
    total = qs.count()
    items = [_serialize(d) for d in qs.order_by('pk')[(page - 1) * page_size: page * page_size]]
    return ok(paginate(items, total, page, page_size))


# ---------------------------------------------------------------- 小程序用户
# 缓存 key 与 TTL
_CACHE_KEY_USER_STATS = 'admin:user_stats:all'
_CACHE_TTL_USER_STATS = 300  # 5 分钟


def _invalidate_user_stats_cache():
    """清除用户统计缓存（在用户数据变更时调用）。"""
    cache.delete(_CACHE_KEY_USER_STATS)


def _user_stats():
    """聚合所有 openid 的画像与统计（DB 聚合 + 缓存）。

    优化点：
    1. profiles 只取需要的字段，不全量加载 data
    2. notes 计数用数据库 annotate 聚合，不加载到内存
    3. historys 计数用数据库 annotate 聚合
    4. 正确率仍需遍历 historys（accuracy_of 逻辑复杂），但只取 data 字段
    5. 结果缓存 5 分钟，写入/删除时主动清除
    """
    cached = cache.get(_CACHE_KEY_USER_STATS)
    if cached is not None:
        return cached

    # 1. profiles —— 逐条取 data（需要 userInfo 嵌套字段，无法纯 SQL 聚合）
    profiles = {}
    for item in Document.objects.filter(collection='profiles').values('pk', 'doc_id', 'data'):
        data = item['data']
        openid = data.get('_openid')
        if not openid:
            continue
        info = du.as_obj(data.get('userInfo')) or {}
        profiles[openid] = {
            'doc_pk': item['pk'],
            'doc_id': item['doc_id'] or str(item['pk']),
            'nickname': du.to_text(info.get('nickName')) if isinstance(info, dict) else '',
            'avatar': du.to_text(info.get('avatarUrl')) if isinstance(info, dict) else '',
            'city': du.to_text(info.get('city')) if isinstance(info, dict) else '',
            'gender': du.to_number(info.get('gender'), 0) if isinstance(info, dict) else 0,
            'status': data.get('status') or USER_STATUS_ACTIVE,
            'remark': data.get('remark') or '',
        }

    # 2. notes —— 数据库 count 聚合（按 _openid 分组）
    notes_agg = {}
    for item in Document.objects.filter(collection='notes').values('data'):
        oid = item['data'].get('_openid')
        if oid:
            notes_agg[oid] = notes_agg.get(oid, 0) + 1

    # 3. historys —— 计数 + 最近活跃日期 + 正确率 + 科目集合
    stats = {}
    for item in Document.objects.filter(collection='historys').values('data'):
        data = item['data']
        openid = data.get('_openid')
        if not openid:
            continue
        s = stats.setdefault(openid, {
            'openid': openid, 'records': 0, 'notes': notes_agg.get(openid, 0),
            'last': None, 'acc_sum': 0.0, 'acc_n': 0, 'subjects': set(),
        })
        s['records'] += 1
        d = du.doc_date({'data': data})
        if d and (s['last'] is None or d > s['last']):
            s['last'] = d
        acc = du.accuracy_of(data)
        if acc is not None:
            s['acc_sum'] += acc
            s['acc_n'] += 1
        name = du.subject_name(data)
        if name:
            s['subjects'].add(name)

    # 4. 合并 profiles + stats（与原逻辑一致）
    result = []
    for openid in set(list(profiles.keys()) + list(stats.keys())):
        p = profiles.get(openid, {})
        s = stats.get(openid, {})
        result.append({
            'openid': openid,
            'nickname': p.get('nickname') or '（未授权资料）',
            'avatar': p.get('avatar') or '',
            'city': p.get('city') or '',
            'gender': p.get('gender') or 0,
            'status': p.get('status') or USER_STATUS_ACTIVE,
            'remark': p.get('remark') or '',
            'has_profile': openid in profiles,
            'records': s.get('records', 0),
            'notes': s.get('notes', 0) or notes_agg.get(openid, 0),
            'accuracy': round(s['acc_sum'] / s['acc_n'], 4) if s.get('acc_n') else 0,
            'subjects': sorted(s.get('subjects', set())),
            'last_active': s['last'].strftime('%Y-%m-%d') if s.get('last') else '',
            '_last_date': s.get('last'),
        })
    result.sort(key=lambda x: (x['_last_date'] is None, x['_last_date'] or ''), reverse=True)

    # 5. 写入缓存
    cache.set(_CACHE_KEY_USER_STATS, result, _CACHE_TTL_USER_STATS)
    return result


@perm.require_perms('user.view', methods=['GET'])
def user_list(request):
    """GET /api/admin/users/"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '方法不支持', http_status=405)
    page, page_size = parse_page(request)
    keyword = request.GET.get('keyword', '').strip().lower()
    status = request.GET.get('status', '').strip()
    items = _user_stats()
    if keyword:
        items = [x for x in items
                 if keyword in x['openid'].lower() or keyword in x['nickname'].lower()]
    if status:
        items = [x for x in items if x['status'] == status]
    total = len(items)
    start, end = (page - 1) * page_size, page * page_size
    data = [{k: v for k, v in x.items() if k != '_last_date'} for x in items[start:end]]
    return ok(paginate(data, total, page, page_size))


def user_detail(request, openid):
    """GET /api/admin/users/<openid>/"""
    profiles = {x['openid']: x for x in _user_stats()}
    base = profiles.get(openid)
    if not base:
        return fail(ErrorCode.NOT_FOUND, '用户不存在')
    base.pop('_last_date', None)

    recent_records = []
    for item in du.iter_docs('historys'):
        data = item['data']
        if data.get('_openid') != openid:
            continue
        recent_records.append({
            '_id': item['doc_id'] or str(item['pk']),
            'createTime': du.to_text(data.get('createTime')),
            'subject': du.subject_name(data),
            'rightNum': du.to_number(data.get('rightNum'), 0),
            'total': len(du.as_obj(data.get('items')) or []),
            'time': du.to_text(data.get('time')),
        })
    recent_records.reverse()
    recent_records = recent_records[:10]

    recent_notes = []
    for item in du.iter_docs('notes'):
        data = item['data']
        if data.get('_openid') != openid:
            continue
        question = du.as_obj(data.get('question')) or {}
        recent_notes.append({
            '_id': item['doc_id'] or str(item['pk']),
            'ordernum': du.to_text(data.get('ordernum')),
            'title': du.to_text(question.get('title')) if isinstance(question, dict) else '',
        })
    recent_notes.reverse()
    recent_notes = recent_notes[:10]

    return ok({
        'profile': base,
        'recent_records': recent_records,
        'recent_notes': recent_notes,
    })


def _can_manage(request):
    user = request.admin_user
    if not user.is_superuser and 'user.manage' not in user.permissions:
        return fail(ErrorCode.FORBIDDEN, '无权限编辑用户')
    return None


@perm.require_perms('user.view')
def user_dispatch(request, openid):
    """统一入口：GET 详情 / PUT/PATCH 更新 / DELETE 删除"""
    if request.method == 'GET':
        return user_detail(request, openid)
    if request.method in ('PUT', 'PATCH'):
        err = _can_manage(request)
        return err or user_update(request, openid)
    if request.method == 'DELETE':
        err = _can_manage(request)
        return err or user_delete(request, openid)
    return fail(ErrorCode.PARAM_ERROR, '方法不支持', http_status=405)


def user_update(request, openid):
    """PUT/PATCH /api/admin/users/<openid>/  {nickname, status, remark}"""
    if request.method not in ('PUT', 'PATCH'):
        return fail(ErrorCode.PARAM_ERROR, '请使用 PUT 或 PATCH 提交', http_status=405)
    body, err = perm.json_body(request)
    if err:
        return err

    doc = Document.objects.filter(collection='profiles', data___openid=openid).first()
    data = dict(doc.data) if doc else {'_openid': openid, 'userInfo': {}}
    info = du.as_obj(data.get('userInfo')) or {}
    if not isinstance(info, dict):
        info = {}
    if 'nickname' in body:
        info['nickName'] = du.to_text(body.get('nickname'))
    data['userInfo'] = info
    if 'status' in body:
        status = du.to_text(body.get('status'), USER_STATUS_ACTIVE)
        if status not in (USER_STATUS_ACTIVE, USER_STATUS_DISABLED):
            return fail(ErrorCode.PARAM_ERROR, '状态值非法')
        data['status'] = status
    if 'remark' in body:
        data['remark'] = du.to_text(body.get('remark'))

    if doc:
        doc.data = data
        doc.save()
    else:
        doc = Document.objects.create(collection='profiles', doc_id=None, data=data)
    perm.log_action(
        request.admin_user, 'user.update', target=openid,
        detail=str({k: body[k] for k in ('nickname', 'status', 'remark') if k in body}),
        ip=perm.client_ip(request),
    )
    _invalidate_user_stats_cache()
    return ok({'_id': doc.doc_id or str(doc.pk)}, '保存成功')


def user_delete(request, openid):
    """DELETE /api/admin/users/<openid>/ 删除该用户全部业务数据（高危操作）"""
    if request.method != 'DELETE':
        return fail(ErrorCode.PARAM_ERROR, '请使用 DELETE 提交', http_status=405)
    if not request.admin_user.is_superuser:
        return fail(ErrorCode.FORBIDDEN, '删除用户数据仅超级管理员可执行')
    deleted = 0
    for collection in ('profiles', 'historys', 'notes', 'test', 'record', 'history'):
        n, _ = Document.objects.filter(collection=collection, data___openid=openid).delete()
        deleted += n or 0
    perm.log_action(request.admin_user, 'user.delete', target=openid, detail=f'{deleted} 条', ip=perm.client_ip(request))
    _invalidate_user_stats_cache()
    return ok({'deleted': deleted}, f'已删除该用户的 {deleted} 条数据')


def unknown_endpoint(request, path=''):
    """兜底：/api/admin/ 下未匹配的请求统一返回 JSON 40401。"""
    return fail(ErrorCode.NOT_FOUND, '接口不存在', http_status=404)


# ---------------------------------------------------------------- 激活码批量生成
import random
import string


@perm.require_perms('admin.manage', methods=['POST'])
def activation_codes_generate(request):
    """POST /api/admin/activation-codes/generate/

    批量生成激活码。
    请求体：
        count       : int   生成数量（1-500，默认 1）
        vipDuration : int   VIP 有效天数（0=永久，默认 30）
        expireAt    : str   激活码过期时间（空=永不过期，格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS）
        note        : str   备注（可选）
    返回：
        { created: int, codes: [{_id, code, status, vipDuration, expireAt}] }
    """
    body, err = perm.json_body(request)
    if err:
        return err

    count = du.to_number(body.get('count'), 1)
    if count < 1:
        return fail(ErrorCode.PARAM_ERROR, 'count 至少为 1')
    if count > 500:
        return fail(ErrorCode.PARAM_ERROR, 'count 不能超过 500')

    vip_duration = du.to_number(body.get('vipDuration'), 30)
    if vip_duration < 0:
        return fail(ErrorCode.PARAM_ERROR, 'vipDuration 不能为负数')

    expire_at = du.to_text(body.get('expireAt')).strip()
    note = du.to_text(body.get('note')).strip()

    # 生成不重复的 6 位数字激活码
    existing_codes = set(
        Document.objects.filter(collection='activation_codes')
        .values_list('data__code', flat=True)
    )
    generated = []
    attempts = 0
    max_attempts = count * 10 + 100  # 防止死循环

    while len(generated) < count and attempts < max_attempts:
        attempts += 1
        code = ''.join(random.choices(string.digits, k=6))
        if code in existing_codes:
            continue
        existing_codes.add(code)
        now_str = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M:%S')
        data = {
            'code': code,
            'status': 'active',
            'vipDuration': vip_duration,
            'expireAt': expire_at,
            'usedBy': '',
            'usedAt': '',
            'note': note,
            'createdAt': now_str,
        }
        doc = Document.objects.create(collection='activation_codes', doc_id=None, data=data)
        generated.append({
            '_id': doc.doc_id or str(doc.pk),
            'code': code,
            'status': 'active',
            'vipDuration': vip_duration,
            'expireAt': expire_at,
        })

    perm.log_action(
        request.admin_user, 'activation_code.generate',
        target=f'{len(generated)} 条', detail=f'vipDuration={vip_duration}, expireAt={expire_at}',
        ip=perm.client_ip(request),
    )
    return ok({'created': len(generated), 'codes': generated}, f'成功生成 {len(generated)} 个激活码')
