"""标签管理与题目-标签绑定接口。

- GET    /api/admin/tags/                       标签列表（?category=&keyword=）
- POST   /api/admin/tags/                       新增标签
- GET    /api/admin/tags/<id>/                  标签详情（含绑定题目数）
- PUT    /api/admin/tags/<id>/                  更新标签
- DELETE /api/admin/tags/<id>/                  删除标签（自动解除绑定）
- GET    /api/admin/tags/<id>/stats/            标签使用统计（按学科/题型/难度维度）
- GET    /api/admin/questions/<id>/tags/        题目已绑定标签
- PUT    /api/admin/questions/<id>/tags/        全量替换绑定 {tag_ids: []}
- POST   /api/admin/tags/bind/                  批量绑定 {question_ids:[], tag_ids:[], mode: add|replace|remove}
"""
from collections import defaultdict

from django.db import transaction

from core.models import Document
from . import data_utils as du
from . import permissions as perm
from .models import QuestionTag, Tag
from .responses import ErrorCode, fail, ok, paginate, parse_page

WRITE_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']
TAG_CATEGORIES = [c for c, _ in Tag.CATEGORY_CHOICES]


def _get_question(doc_id):
    """按 _id 或 pk 定位 questions 集合文档。"""
    try:
        return Document.objects.get(collection='questions', doc_id=str(doc_id))
    except Document.DoesNotExist:
        pass
    if str(doc_id).isdigit():
        try:
            return Document.objects.get(collection='questions', pk=int(doc_id), doc_id=None)
        except Document.DoesNotExist:
            return None
    return None


def _sync_tag_ids(question_doc):
    """把 QuestionTag 绑定关系镜像到文档 tag_ids 字段。"""
    ids = sorted(question_doc.tag_bindings.values_list('tag_id', flat=True))
    data = dict(question_doc.data)
    data['tag_ids'] = ids
    question_doc.data = data
    question_doc.save(update_fields=['data'])
    return ids


@perm.require_perms('tag.view', 'tag.manage', methods=WRITE_METHODS)
def tag_list(request):
    if request.method == 'GET':
        page, page_size = parse_page(request, default_size=50)
        qs = Tag.objects.all()
        category = request.GET.get('category', '').strip()
        keyword = request.GET.get('keyword', '').strip()
        if category:
            qs = qs.filter(category=category)
        if keyword:
            qs = qs.filter(name__icontains=keyword)
        total = qs.count()
        items = [t.to_client() for t in qs[(page - 1) * page_size: page * page_size]]
        return ok(paginate(items, total, page, page_size))

    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET / POST', http_status=405)

    body, err = perm.json_body(request)
    if err:
        return err
    name = du.to_text(body.get('name')).strip()
    category = du.to_text(body.get('category')).strip()
    if not name:
        return fail(ErrorCode.PARAM_ERROR, '标签名不能为空')
    if category not in TAG_CATEGORIES:
        return fail(ErrorCode.PARAM_ERROR, f'分类必须是：{", ".join(TAG_CATEGORIES)}')
    if Tag.objects.filter(name=name, category=category).exists():
        return fail(ErrorCode.CONFLICT, f'该分类下已存在同名标签：{name}')
    tag = Tag.objects.create(
        name=name,
        category=category,
        description=du.to_text(body.get('description')),
        color=du.to_text(body.get('color')),
    )
    perm.log_action(request.admin_user, 'tag.create', target=f'{category}:{name}', ip=perm.client_ip(request))
    return ok(tag.to_client(), '标签创建成功')


@perm.require_perms('tag.view', 'tag.manage', methods=WRITE_METHODS)
def tag_detail(request, pk):
    try:
        tag = Tag.objects.get(pk=pk)
    except Tag.DoesNotExist:
        return fail(ErrorCode.NOT_FOUND, '标签不存在')

    if request.method == 'GET':
        return ok(tag.to_client())

    if request.method in ('PUT', 'PATCH'):
        body, err = perm.json_body(request)
        if err:
            return err
        if 'name' in body:
            name = du.to_text(body.get('name')).strip()
            if not name:
                return fail(ErrorCode.PARAM_ERROR, '标签名不能为空')
            if Tag.objects.filter(name=name, category=tag.category).exclude(pk=pk).exists():
                return fail(ErrorCode.CONFLICT, f'该分类下已存在同名标签：{name}')
            tag.name = name
        if 'description' in body:
            tag.description = du.to_text(body.get('description'))
        if 'color' in body:
            tag.color = du.to_text(body.get('color'))
        if 'category' in body:
            category = du.to_text(body.get('category')).strip()
            if category not in TAG_CATEGORIES:
                return fail(ErrorCode.PARAM_ERROR, f'分类必须是：{", ".join(TAG_CATEGORIES)}')
            if Tag.objects.filter(name=tag.name, category=category).exclude(pk=pk).exists():
                return fail(ErrorCode.CONFLICT, '目标分类下已存在同名标签')
            tag.category = category
        tag.save()
        perm.log_action(request.admin_user, 'tag.update', target=f'{tag.category}:{tag.name}', ip=perm.client_ip(request))
        return ok(tag.to_client(), '保存成功')

    if request.method == 'DELETE':
        usage = tag.bindings.count()
        tag.delete()
        perm.log_action(request.admin_user, 'tag.delete', target=f'{tag.category}:{tag.name}',
                        detail=f'解除 {usage} 处绑定', ip=perm.client_ip(request))
        return ok({'deleted': True, 'unbound': usage}, '已删除标签并解除绑定')

    return fail(ErrorCode.PARAM_ERROR, '方法不支持', http_status=405)


@perm.require_perms('tag.view')
def question_tags(request, doc_id):
    """GET /api/admin/questions/<id>/tags/"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    question = _get_question(doc_id)
    if not question:
        return fail(ErrorCode.NOT_FOUND, '题目不存在')
    tags = [b.tag.to_client() for b in question.tag_bindings.select_related('tag')]
    return ok(tags)


@perm.require_perms('tag.manage')
def question_tags_bind(request, doc_id):
    """PUT/POST /api/admin/questions/<id>/tags/  {tag_ids: [...]} 全量替换"""
    if request.method not in ('PUT', 'POST'):
        return fail(ErrorCode.PARAM_ERROR, '请使用 PUT 或 POST 提交', http_status=405)
    question = _get_question(doc_id)
    if not question:
        return fail(ErrorCode.NOT_FOUND, '题目不存在')
    body, err = perm.json_body(request)
    if err:
        return err
    tag_ids = body.get('tag_ids') or []
    if not isinstance(tag_ids, list):
        return fail(ErrorCode.PARAM_ERROR, 'tag_ids 必须是数组')
    tags = list(Tag.objects.filter(pk__in=[t for t in tag_ids if isinstance(t, int)]))
    found = {t.pk for t in tags}
    missing = [t for t in tag_ids if isinstance(t, int) and t not in found]
    if missing:
        return fail(ErrorCode.PARAM_ERROR, f'标签不存在：{missing}')
    with transaction.atomic():
        question.tag_bindings.all().delete()
        QuestionTag.objects.bulk_create([QuestionTag(question=question, tag=t) for t in tags])
        synced = _sync_tag_ids(question)
    perm.log_action(request.admin_user, 'question.bind_tags', target=str(doc_id),
                    detail=f'tags={synced}', ip=perm.client_ip(request))
    return ok({'tag_ids': synced}, '标签已更新')


@perm.require_perms('tag.manage')
def tags_batch_bind(request):
    """POST /api/admin/tags/bind/  {question_ids:[], tag_ids:[], mode:add|replace|remove}"""
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '请使用 POST 提交', http_status=405)
    body, err = perm.json_body(request)
    if err:
        return err
    question_ids = body.get('question_ids') or []
    tag_ids = body.get('tag_ids') or []
    mode = du.to_text(body.get('mode')) or 'add'
    if not question_ids or not isinstance(question_ids, list):
        return fail(ErrorCode.PARAM_ERROR, 'question_ids 不能为空')
    if not tag_ids or not isinstance(tag_ids, list):
        return fail(ErrorCode.PARAM_ERROR, 'tag_ids 不能为空')
    if mode not in ('add', 'replace', 'remove'):
        return fail(ErrorCode.PARAM_ERROR, 'mode 必须是 add / replace / remove')
    tags = list(Tag.objects.filter(pk__in=tag_ids))
    if len(tags) != len(set(tag_ids)):
        return fail(ErrorCode.PARAM_ERROR, '部分标签不存在')

    affected, not_found = 0, []
    with transaction.atomic():
        for doc_id in question_ids:
            question = _get_question(doc_id)
            if not question:
                not_found.append(str(doc_id))
                continue
            if mode == 'replace':
                question.tag_bindings.all().delete()
            if mode in ('add', 'replace'):
                for tag in tags:
                    QuestionTag.objects.get_or_create(question=question, tag=tag)
            elif mode == 'remove':
                question.tag_bindings.filter(tag_id__in=tag_ids).delete()
            _sync_tag_ids(question)
            affected += 1
    perm.log_action(request.admin_user, 'tag.batch_bind', target=f'{affected} 题',
                    detail=f'mode={mode} tags={tag_ids}', ip=perm.client_ip(request))
    return ok({'affected': affected, 'not_found': not_found}, f'已处理 {affected} 道题目')


@perm.require_perms('tag.view')
def tag_stats(request, pk):
    """GET /api/admin/tags/<pk>/stats/  标签使用统计（按学科/题型/难度维度）。

    返回：
    - total_count: 使用该标签的题目总数
    - by_subject: 按学科（examid/subject）分组 {学科名: 题目数}
    - by_qtype: 按题型分组 {题型: 题目数}
    - by_difficulty: 按难度分组 {难度: 题目数}（来自 AI 解析）
    - by_examid: 按科目编号分组 {科目编号: 题目数}
    - recent_questions: 最近绑定的题目摘要（最多 10 条）
    """
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    try:
        tag = Tag.objects.get(pk=pk)
    except Tag.DoesNotExist:
        return fail(ErrorCode.NOT_FOUND, '标签不存在')

    # 获取所有绑定该标签的题目文档
    bindings = tag.bindings.select_related('question').all()
    question_docs = [b.question for b in bindings if b.question_id]

    total_count = len(question_docs)

    by_subject = defaultdict(int)
    by_qtype = defaultdict(int)
    by_difficulty = defaultdict(int)
    by_examid = defaultdict(int)
    recent_questions = []

    for qdoc in question_docs:
        data = qdoc.data or {}
        # 学科维度
        examid = du.to_text(data.get('examid')) or '未分类'
        subject = du.to_text(data.get('subject')) or examid
        if not subject:
            subject = '未分类'
        by_subject[subject] += 1
        by_examid[examid] += 1

        # 题型维度
        qtype = du.to_text(data.get('qtype')) or '未知'
        by_qtype[qtype] += 1

        # 难度维度（来自 AI 解析）
        ai_analysis = data.get('ai_analysis') or {}
        difficulty = du.to_text(ai_analysis.get('difficulty')) if isinstance(ai_analysis, dict) else ''
        if not difficulty:
            difficulty = du.to_text(data.get('difficulty')) or '未标注'
        by_difficulty[difficulty] += 1

        # 收集最近题目摘要
        title = du.to_text(data.get('title')) or du.to_text(data.get('content_md')) or ''
        recent_questions.append({
            'question_id': qdoc.doc_id or str(qdoc.pk),
            'title': title[:80] if title else '-',
            'examid': examid,
            'qtype': qtype,
        })

    # 最近 10 条（按 pk 倒序，即最近创建/绑定的在前）
    recent_questions = sorted(recent_questions, key=lambda x: x['question_id'], reverse=True)[:10]

    # 排序辅助
    def _sorted_dict(d):
        return dict(sorted(d.items(), key=lambda x: x[1], reverse=True))

    return ok({
        'tag_id': tag.pk,
        'tag_name': tag.name,
        'tag_category': tag.category,
        'total_count': total_count,
        'by_subject': _sorted_dict(by_subject),
        'by_qtype': _sorted_dict(by_qtype),
        'by_difficulty': _sorted_dict(by_difficulty),
        'by_examid': _sorted_dict(by_examid),
        'recent_questions': recent_questions,
    })
