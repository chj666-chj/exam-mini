"""题库批量导入 / 图片上传 / AI 判卷预留接口。

批量导入：
- POST /api/admin/questions/import/            {items, async, on_duplicate, default_examid, tags}
- GET  /api/admin/questions/import/            任务列表
- GET  /api/admin/questions/import/<job_id>/   任务详情与逐题结果

异步说明：本地开发无 Celery，采用守护线程执行导入任务，
任务状态/进度实时落库，前端轮询 GET 接口获取进度与结果。
"""
import threading
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from core.models import Document
from . import data_utils as du
from . import excel_import as xl
from . import permissions as perm
from .models import ImportJob, QuestionTag, Tag
from .question_schema import QTYPES, duplicate_key, normalize_question
from .responses import ErrorCode, fail, ok, paginate, parse_page

MAX_IMPORT_ITEMS = 500
DUPLICATE_MODES = ('skip', 'overwrite', 'error')

# 运行中的线程句柄（便于观察，进程重启后任务会按中断状态恢复显示）
_RUNNING = {}


# ---------------------------------------------------------------- 导入处理
def _existing_questions():
    """现有题目的 (doc, dup_key) 列表。"""
    rows = []
    for item in Document.objects.filter(collection='questions').values_list('pk', 'doc_id', 'data'):
        pk, doc_id, data = item
        key = duplicate_key({
            'examid': data.get('examid', ''),
            'content_md': data.get('content_md') or data.get('title') or '',
        })
        rows.append({'pk': pk, 'doc_id': doc_id or str(pk), 'key': key, 'data': data})
    return rows


def _bind_tags(question_doc, tag_ids):
    """给题目绑定标签（QuestionTag 表 + 文档 tag_ids 镜像）。"""
    if not tag_ids:
        return
    tags = Tag.objects.filter(pk__in=tag_ids)
    for tag in tags:
        QuestionTag.objects.get_or_create(question=question_doc, tag=tag)
    synced = sorted(question_doc.tag_bindings.values_list('tag_id', flat=True))
    if synced != question_doc.data.get('tag_ids'):
        question_doc.data = {**question_doc.data, 'tag_ids': synced}
        question_doc.save(update_fields=['data'])


def _save_question(data, explicit_id):
    obj = Document(collection='questions', doc_id=explicit_id, data=data)
    obj.save()
    return obj


def _process_items(job, items, on_duplicate, default_examid, batch_tags):
    """执行导入，逐题落库并更新任务进度。"""
    existing = _existing_questions()
    by_id = {r['doc_id']: r for r in existing}
    by_key = {r['key']: r for r in existing}
    results = []

    for index, item in enumerate(items):
        title_hint = ''
        entry = {'index': index, 'status': 'failed', '_id': '', 'errors': []}
        try:
            data, errors = normalize_question(item, default_examid=default_examid)
            if errors:
                entry['errors'] = errors
                entry['title'] = du.to_text(item.get('title') if isinstance(item, dict) else '')[:60]
                results.append(entry)
                job.failed += 1
                continue

            title_hint = data['title']
            entry['title'] = title_hint
            entry['qtype'] = data['qtype']
            explicit_id = du.to_text(item.get('_id')).strip() if isinstance(item, dict) else ''
            key = duplicate_key(data)
            dup = None
            if explicit_id and explicit_id in by_id:
                dup = by_id[explicit_id]
                entry['duplicate_of'] = '_id'
            elif key in by_key:
                dup = by_key[key]
                entry['duplicate_of'] = 'title'

            if dup and on_duplicate == 'error':
                entry['status'] = 'failed'
                entry['errors'] = [f'题目重复（{entry["duplicate_of"]} 与现有题目 {dup["doc_id"]} 冲突）']
                results.append(entry)
                job.failed += 1
                continue

            if dup and on_duplicate == 'skip':
                entry['status'] = 'skipped'
                entry['_id'] = dup['doc_id']
                entry['errors'] = [f'已存在相同题目（{entry["duplicate_of"]}），按规则跳过']
                results.append(entry)
                job.skipped += 1
                continue

            tag_ids = list(set(batch_tags + data.pop('tag_ids', [])))

            if dup and on_duplicate == 'overwrite':
                obj = Document.objects.get(pk=dup['pk'])
                merged = dict(obj.data)
                merged.update(data)
                obj.data = merged
                obj.save()
            else:
                obj = _save_question(data, explicit_id or None)

            _bind_tags(obj, tag_ids)
            entry['status'] = 'success' if not dup else 'overwritten'
            entry['_id'] = obj.doc_id or str(obj.pk)
            results.append(entry)
            job.succeeded += 1

            # 记录到新映射，防止本批次内部重复
            by_key[key] = {'pk': obj.pk, 'doc_id': obj.doc_id or str(obj.pk)}
            if explicit_id:
                by_id[explicit_id] = by_key[key]
        except Exception as e:  # 单题异常不影响整批
            entry['title'] = title_hint or du.to_text(item.get('title') if isinstance(item, dict) else '')[:60]
            entry['errors'] = [f'写入失败：{e}']
            results.append(entry)
            job.failed += 1

        job.results = results
        if (index + 1) % 10 == 0 or index == len(items) - 1:
            job.save(update_fields=['succeeded', 'failed', 'skipped', 'results'])

    return results


def _finish_job(job):
    if job.failed == 0 and job.status != 'failed':
        job.status = 'success'
    elif job.succeeded > 0 or job.skipped > 0:
        job.status = 'partial'
    else:
        job.status = 'failed'
    job.finished_at = timezone.now()
    job.save()
    _RUNNING.pop(job.pk, None)


def _maybe_auto_analyze(job):
    """导入成功后自动触发 AI 题目解析（通过配置控制是否启用）。

    仅当 ai_config.feature_config.question_analyze.auto_analyze_on_import 为 True 时触发。
    收集新导入成功的题目 ID，异步启动批量解析任务。
    """
    if job.status not in ('success', 'partial'):
        return

    # 检查是否启用自动解析
    from .views_ai import _get_ai_config
    config, _ = _get_ai_config()
    if not config.get('enabled'):
        return

    feature_config = config.get('feature_config') or {}
    analyze_config = feature_config.get('question_analyze') or {}
    if not analyze_config.get('auto_analyze_on_import', False):
        return

    # 收集新导入成功的题目 ID
    question_ids = []
    for r in (job.results or []):
        if r.get('status') in ('success', 'overwritten') and r.get('_id'):
            question_ids.append(r['_id'])

    if not question_ids:
        return

    # 异步触发批量解析
    from .ai_jobs import AIJobManager
    from .ai_services import QuestionAnalysisService

    def _analyze_task(jid):
        QuestionAnalysisService.analyze_batch(question_ids, jid)

    analyze_job_id = AIJobManager.create('question_analyze', {
        'source': 'import',
        'import_job_id': job.pk,
        'question_ids': question_ids,
    })
    AIJobManager.start(analyze_job_id, _analyze_task)


def _run_import(job_id):
    job = ImportJob.objects.get(pk=job_id)
    job.status = 'processing'
    job.started_at = timezone.now()
    job.save(update_fields=['status', 'started_at'])
    payload = job.payload or {}
    try:
        with transaction.atomic():
            _process_items(
                job,
                payload.get('items') or [],
                payload.get('on_duplicate') or 'skip',
                payload.get('default_examid') or '',
                payload.get('tags') or [],
            )
    except Exception as e:
        job.error = str(e)[:500]
    _finish_job(job)
    _maybe_auto_analyze(job)


# ---------------------------------------------------------------- 接口
@csrf_exempt
@perm.require_perms('question.import')
def import_create(request):
    """POST /api/admin/questions/import/"""
    if request.method == 'GET':
        page, page_size = parse_page(request)
        qs = ImportJob.objects.all()
        total = qs.count()
        items = [j.to_client() for j in qs[(page - 1) * page_size: page * page_size]]
        return ok(paginate(items, total, page, page_size))

    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET / POST', http_status=405)

    body, err = perm.json_body(request)
    if err:
        return err
    items = body.get('items')
    if not isinstance(items, list) or not items:
        return fail(ErrorCode.PARAM_ERROR, 'items 不能为空数组')
    if len(items) > MAX_IMPORT_ITEMS:
        return fail(ErrorCode.PARAM_ERROR, f'单次最多导入 {MAX_IMPORT_ITEMS} 道题目')
    on_duplicate = du.to_text(body.get('on_duplicate')) or 'skip'
    if on_duplicate not in DUPLICATE_MODES:
        return fail(ErrorCode.PARAM_ERROR, f'on_duplicate 必须是：{", ".join(DUPLICATE_MODES)}')
    is_async = bool(body.get('async'))
    batch_tags = [int(t) for t in (body.get('tags') or []) if isinstance(t, int) or str(t).isdigit()]
    if batch_tags:
        found = Tag.objects.filter(pk__in=batch_tags).count()
        if found != len(set(batch_tags)):
            return fail(ErrorCode.PARAM_ERROR, '部分标签不存在')

    job = ImportJob.objects.create(
        created_by=request.admin_user,
        mode='async' if is_async else 'sync',
        status='pending',
        total=len(items),
        payload={
            'items': items,
            'on_duplicate': on_duplicate,
            'default_examid': du.to_text(body.get('default_examid')),
            'tags': batch_tags,
        },
    )
    perm.log_action(
        request.admin_user, 'question.import', target=f'任务#{job.pk}',
        detail=f'{len(items)} 题 / {job.mode} / {on_duplicate}', ip=perm.client_ip(request),
    )

    if is_async:
        thread = threading.Thread(target=_run_import, args=(job.pk,), daemon=True, name=f'import-{job.pk}')
        _RUNNING[job.pk] = thread
        thread.start()
        return ok(job.to_client(), '导入任务已创建，正在后台处理', )

    _run_import(job.pk)
    job.refresh_from_db()
    return ok(job.to_client(with_results=True), '导入完成')


@perm.require_perms('question.import', 'question.view', methods=['GET'])
def import_detail(request, job_id):
    """GET /api/admin/questions/import/<job_id>/"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    try:
        job = ImportJob.objects.get(pk=job_id)
    except ImportJob.DoesNotExist:
        return fail(ErrorCode.NOT_FOUND, '导入任务不存在')
    with_results = request.GET.get('with_results', '1') != '0'
    return ok(job.to_client(with_results=with_results))


# ---------------------------------------------------------------- Excel 模板下载与导入

@perm.require_perms('question.import')
def import_templates(request):
    """GET /api/admin/questions/import/templates/    获取可用模板列表。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    return ok({'templates': xl.available_templates()}, '可用模板列表')


@perm.require_perms('question.import')
def import_template_download(request, qtype):
    """GET /api/admin/questions/import/templates/<qtype>/    下载指定题型的 Excel 模板。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)

    if qtype not in xl.EXCEL_TEMPLATES:
        return fail(ErrorCode.PARAM_ERROR, f'不支持的题型：{qtype}，支持：{", ".join(xl.EXCEL_TEMPLATES.keys())}')

    content, filename = xl.template_to_bytes(qtype)
    if not content:
        return fail(ErrorCode.PARAM_ERROR, '模板生成失败')

    response = HttpResponse(
        content,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    from urllib.parse import quote
    response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return response


@csrf_exempt
@perm.require_perms('question.import')
def import_excel(request):
    """POST /api/admin/questions/import/excel/    上传 Excel 文件并导入。

    请求参数（multipart/form-data）：
        file          —— Excel 文件（.xlsx）
        qtype         —— 题型代码（single/multiple/judge/fill/qa）
        on_duplicate  —— 重复处理策略（skip/overwrite/error），默认 skip
        default_examid — 默认科目编号
        tags          —— 批量标签 ID（逗号分隔字符串）
        async         —— 是否异步处理（true/false），默认 false
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    file_obj = request.FILES.get('file')
    if not file_obj:
        return fail(ErrorCode.PARAM_ERROR, '缺少文件字段 file')

    # 校验文件类型
    ext = Path(file_obj.name).suffix.lower()
    if ext not in ('.xlsx', '.xls'):
        return fail(ErrorCode.PARAM_ERROR, '仅支持 .xlsx 格式文件')

    qtype = du.to_text(request.POST.get('qtype')).strip()
    if not qtype:
        return fail(ErrorCode.PARAM_ERROR, '请指定题型 qtype')
    if qtype not in xl.EXCEL_TEMPLATES:
        return fail(ErrorCode.PARAM_ERROR, f'不支持的题型：{qtype}，支持：{", ".join(xl.EXCEL_TEMPLATES.keys())}')

    on_duplicate = du.to_text(request.POST.get('on_duplicate')) or 'skip'
    if on_duplicate not in DUPLICATE_MODES:
        return fail(ErrorCode.PARAM_ERROR, f'on_duplicate 必须是：{", ".join(DUPLICATE_MODES)}')

    default_examid = du.to_text(request.POST.get('default_examid')).strip()
    is_async = du.to_text(request.POST.get('async')).lower() in ('true', '1', 'yes')

    # 批量标签
    batch_tags_str = du.to_text(request.POST.get('tags')).strip()
    batch_tags = []
    if batch_tags_str:
        batch_tags = [int(t) for t in batch_tags_str.split(',') if t.strip().isdigit()]
    if batch_tags:
        found = Tag.objects.filter(pk__in=batch_tags).count()
        if found != len(set(batch_tags)):
            return fail(ErrorCode.PARAM_ERROR, '部分标签不存在')

    # 读取所有已有标签（用于名称匹配）
    existing_tags = list(Tag.objects.all())

    # 解析 Excel
    try:
        parsed = xl.parse_excel(file_obj, qtype, default_examid=default_examid, existing_tags=existing_tags)
    except Exception as e:
        return fail(ErrorCode.PARAM_ERROR, f'Excel 文件解析失败：{e}')

    # 如果没有有效数据且没有错误，说明文件为空
    if parsed['total_rows'] == 0:
        return fail(ErrorCode.PARAM_ERROR, 'Excel 文件中没有数据行（请检查是否只填了表头或示例行未修改）')

    # 如果全部校验失败，直接返回校验结果（不入库）
    if not parsed['items'] and parsed['errors']:
        return ok({
            'status': 'validation_failed',
            'total_rows': parsed['total_rows'],
            'valid_count': 0,
            'invalid_count': parsed['total_rows'],
            'errors': parsed['errors'],
            'warnings': parsed.get('warnings', []),
            'succeeded': 0,
            'failed': parsed['total_rows'],
            'skipped': 0,
            'results': [],
        }, f'校验失败：{len(parsed["errors"])} 处错误，请修正后重新上传')

    # 创建导入任务
    job = ImportJob.objects.create(
        created_by=request.admin_user,
        mode='async' if is_async else 'sync',
        status='pending',
        total=len(parsed['items']),
        payload={
            'items': parsed['items'],
            'on_duplicate': on_duplicate,
            'default_examid': default_examid,
            'tags': batch_tags,
            'source': 'excel',
            'qtype': qtype,
            'excel_errors': parsed['errors'],
            'excel_warnings': parsed.get('warnings', []),
            'excel_total_rows': parsed['total_rows'],
        },
    )
    perm.log_action(
        request.admin_user, 'question.import', target=f'Excel导入任务#{job.pk}',
        detail=f'{qtype} / {parsed["total_rows"]} 行 / 有效 {parsed["valid_count"]} / 错误 {len(parsed["errors"])}',
        ip=perm.client_ip(request),
    )

    if is_async:
        thread = threading.Thread(target=_run_import, args=(job.pk,), daemon=True, name=f'excel-import-{job.pk}')
        _RUNNING[job.pk] = thread
        thread.start()
        return ok(_excel_job_client(job, parsed), 'Excel 导入任务已创建，正在后台处理')

    # 同步执行
    _run_import(job.pk)
    job.refresh_from_db()
    return ok(_excel_job_client(job, parsed), '导入完成')


def _excel_job_client(job, parsed):
    """组装 Excel 导入任务的客户端返回数据。"""
    data = job.to_client(with_results=True)
    data['source'] = 'excel'
    data['qtype'] = parsed.get('qtype', '')
    data['total_rows'] = parsed['total_rows']
    data['valid_count'] = parsed['valid_count']
    data['invalid_count'] = parsed['total_rows'] - parsed['valid_count']
    data['excel_errors'] = parsed['errors']
    data['excel_warnings'] = parsed.get('warnings', [])
    return data


@perm.require_perms('question.manage')
def ai_grade(request, doc_id):
    """POST /api/admin/questions/<id>/ai-grade/  AI 判卷（预留接口）。

    请求：{answer_text: "考生作答", rubric?: "覆盖题面默认评分要点"}
    当前返回未接入状态；接入判卷服务后在此编排模型调用并回写成绩。
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '请使用 POST 提交', http_status=405)
    question = Document.objects.filter(collection='questions', doc_id=str(doc_id)).first()
    if question is None and str(doc_id).isdigit():
        question = Document.objects.filter(collection='questions', pk=int(doc_id), doc_id=None).first()
    if question is None:
        return fail(ErrorCode.NOT_FOUND, '题目不存在')

    body, err = perm.json_body(request)
    if err:
        return err
    answer_text = du.to_text(body.get('answer_text'))
    if not answer_text.strip():
        return fail(ErrorCode.PARAM_ERROR, 'answer_text 不能为空')

    data = question.data or {}
    qtype = data.get('qtype') or data.get('typename')
    gradable = qtype in ('qa', 'fill', '问答题', '填空题') or bool(data.get('sub_questions'))
    if not gradable:
        return fail(ErrorCode.PARAM_ERROR, f'该题型（{qtype}）为客观题，无需 AI 判卷')

    grading = data.get('ai_grading') or {}
    if not grading.get('enabled'):
        return ok({
            'graded': False,
            'supported': False,
            'reason': 'ai_grading_disabled',
            'message': '该题未启用 AI 判卷（ai_grading.enabled=false）',
            'score': None,
            'max_score': grading.get('max_score') or data.get('score') or 0,
        }, 'AI 判卷未启用')

    # ---- AI 判卷服务接入 ----
    rubric = du.to_text(body.get('rubric')) or grading.get('rubric', '')
    max_score = grading.get('max_score') or data.get('score') or 0

    from .ai_services import GradingService
    grading_result = GradingService.grade_single(question, answer_text, rubric=rubric or None)

    if 'error' in grading_result:
        return fail(ErrorCode.SERVER_ERROR, grading_result['error'])

    return ok({
        'graded': True,
        'supported': True,
        'score': grading_result.get('score'),
        'max_score': grading_result.get('max_score', max_score),
        'feedback_md': grading_result.get('feedback_md', ''),
        'confidence': grading_result.get('confidence', 0),
        'model': grading_result.get('model', ''),
        'graded_at': grading_result.get('graded_at', ''),
        'needs_human_review': grading_result.get('needs_human_review', False),
        'human_review': grading_result.get('human_review'),
    }, 'AI 判卷完成')


# ---------------------------------------------------------------- 图片上传
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'}
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB


@csrf_exempt
@perm.require_perms('question.manage')
def upload_image(request):
    """POST /api/admin/upload/  multipart 表单字段 file"""
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '请使用 POST 提交', http_status=405)
    file_obj = request.FILES.get('file')
    if not file_obj:
        return fail(ErrorCode.PARAM_ERROR, '缺少文件字段 file')
    ext = Path(file_obj.name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return fail(ErrorCode.PARAM_ERROR, f'仅支持图片格式：{", ".join(sorted(ALLOWED_EXTENSIONS))}')
    if file_obj.size > MAX_UPLOAD_SIZE:
        return fail(ErrorCode.PARAM_ERROR, '图片大小不能超过 5MB')

    month = timezone.now().strftime('%Y%m')
    upload_dir = Path(settings.MEDIA_ROOT) / 'uploads' / month
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid.uuid4().hex[:16]}{ext}'
    target = upload_dir / filename
    with open(target, 'wb') as f:
        for chunk in file_obj.chunks():
            f.write(chunk)

    url = f'{settings.MEDIA_URL}uploads/{month}/{filename}'
    perm.log_action(request.admin_user, 'upload.image', target=url, ip=perm.client_ip(request))
    return ok({'url': url, 'name': file_obj.name, 'size': file_obj.size}, '上传成功')
