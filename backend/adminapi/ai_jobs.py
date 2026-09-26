"""AI 异步任务管理 —— 与 ImportJob 同构的守护线程任务系统。

任务状态机：pending -> running -> success/failed/cancelled
任务文档存储在 ai_jobs collection（core.Document）。

与 adminapi/models.py 中的 ImportJob（Django Model）不同，
AI 任务使用通用文档存储（core.Document collection='ai_jobs'），
便于灵活扩展任务配置与结果结构。
"""
import threading
import uuid
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import Document

_AI_JOBS_COLLECTION = 'ai_jobs'

# 运行中的线程句柄（便于观察，进程重启后任务会按中断状态恢复显示）
_RUNNING = {}
_LOCK = threading.Lock()


class AIJobManager:
    """AI 异步任务管理器。

    任务文档结构（存储在 Document.data 中）：
    {
        job_type: str,           # 任务类型（question_analyze / exam_compose / ai_grade）
        status: str,             # pending / running / success / failed / cancelled
        config: dict,            # 任务配置参数
        result: dict | None,     # 任务结果（成功时填充）
        progress: int,           # 0-100
        progress_text: str,      # 进度描述
        error: str,              # 失败原因
        openid: str | None,      # 发起人 openid
        created_at: str,         # ISO 时间
        updated_at: str,         # ISO 时间
    }
    """

    COLLECTION = _AI_JOBS_COLLECTION

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'

    VALID_STATUSES = (STATUS_PENDING, STATUS_RUNNING, STATUS_SUCCESS, STATUS_FAILED, STATUS_CANCELLED)

    @classmethod
    def create(cls, job_type, config, openid=None):
        """在 ai_jobs collection 创建任务文档，返回 job_id。"""
        job_id = uuid.uuid4().hex[:16]
        now = timezone.now().isoformat()
        doc_data = {
            'job_type': job_type,
            'status': cls.STATUS_PENDING,
            'config': config or {},
            'result': None,
            'progress': 0,
            'progress_text': '排队中',
            'error': '',
            'openid': openid or '',
            'created_at': now,
            'updated_at': now,
        }
        Document.objects.create(
            collection=cls.COLLECTION,
            doc_id=job_id,
            data=doc_data,
        )
        return job_id

    @classmethod
    def start(cls, job_id, target_func):
        """启动守护线程执行 target_func(job_id)。

        target_func 接收 job_id 作为唯一参数，内部应通过 update() 更新进度。
        异常会被捕获并标记任务为 failed。

        任务完成后自动记录 AI 使用日志（token 用量从线程局部读取）。
        """
        def _wrapper():
            _job_ok = False
            _job_err = ''
            try:
                cls.update(job_id, status=cls.STATUS_RUNNING, progress=0,
                           progress_text='开始执行')
                target_func(job_id)
                _job_ok = True
            except Exception as e:
                _job_err = str(e)[:500]
                cls.update(job_id, status=cls.STATUS_FAILED,
                           error=_job_err, progress_text='任务执行异常')
            finally:
                _RUNNING.pop(job_id, None)
                # 记录 AI 使用日志（异步任务完成）
                try:
                    from .ai_usage_logger import AIUsageLogger
                    job_data = cls.get(job_id) or {}
                    func_name = job_data.get('job_type', '')
                    openid = job_data.get('openid', '')
                    source = 'mp' if openid else 'admin'
                    if _job_ok:
                        # 尝试从线程局部读取最后一次 LLM 调用的 token 用量
                        usage = {}
                        try:
                            from .views_ai import _get_last_call_usage
                            usage = _get_last_call_usage() or {}
                        except Exception:
                            pass
                        AIUsageLogger.log(
                            func_name=func_name, source=source, openid=openid,
                            status=AIUsageLogger.STATUS_SUCCESS,
                            tokens_prompt=usage.get('prompt_tokens', 0),
                            tokens_completion=usage.get('completion_tokens', 0),
                            tokens_total=usage.get('total_tokens', 0),
                            job_id=job_id,
                        )
                    else:
                        AIUsageLogger.log(
                            func_name=func_name, source=source, openid=openid,
                            status=AIUsageLogger.STATUS_FAILED,
                            error=_job_err, job_id=job_id,
                        )
                except Exception:
                    pass  # 日志失败不影响任务流程

        thread = threading.Thread(target=_wrapper, daemon=True, name='ai-job-%s' % job_id)
        with _LOCK:
            _RUNNING[job_id] = thread
        thread.start()

    @classmethod
    def update(cls, job_id, **fields):
        """线程安全更新任务状态。

        可更新字段：status, progress, progress_text, result, error, config。
        自动更新 updated_at 时间戳。
        """
        try:
            doc = Document.objects.get(collection=cls.COLLECTION, doc_id=job_id)
        except Document.DoesNotExist:
            return
        data = dict(doc.data)
        # 过滤合法字段
        allowed = ('job_type', 'status', 'config', 'result', 'progress',
                   'progress_text', 'error', 'openid')
        for key, value in fields.items():
            if key in allowed:
                data[key] = value
        data['updated_at'] = timezone.now().isoformat()
        # 如果状态变为成功，确保 progress=100
        if data.get('status') == cls.STATUS_SUCCESS and data.get('progress', 0) < 100:
            data['progress'] = 100
        doc.data = data
        doc.save(update_fields=['data'])

    @classmethod
    def get(cls, job_id):
        """查询任务状态，返回任务文档 dict 或 None。"""
        try:
            doc = Document.objects.get(collection=cls.COLLECTION, doc_id=job_id)
        except Document.DoesNotExist:
            return None
        data = dict(doc.data)
        data['job_id'] = job_id
        return data

    @classmethod
    def list(cls, status=None, job_type=None, page=1, page_size=20):
        """分页列表。

        返回 {list, total, page, page_size}。
        """
        qs = Document.objects.filter(collection=cls.COLLECTION)
        if status:
            qs = qs.filter(data__status=status)
        if job_type:
            qs = qs.filter(data__job_type=job_type)
        total = qs.count()
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))
        docs = list(qs.order_by('-pk')[(page - 1) * page_size: page * page_size])
        items = []
        for doc in docs:
            item = dict(doc.data)
            item['job_id'] = doc.doc_id
            items.append(item)
        return {
            'list': items,
            'total': total,
            'page': page,
            'page_size': page_size,
        }

    @classmethod
    def cancel(cls, job_id):
        """取消任务。

        仅对 pending/running 状态有效；已结束的任务不受影响。
        """
        job_data = cls.get(job_id)
        if not job_data:
            return
        if job_data.get('status') in (cls.STATUS_PENDING, cls.STATUS_RUNNING):
            cls.update(job_id, status=cls.STATUS_CANCELLED,
                       progress_text='已取消')
        _RUNNING.pop(job_id, None)

    @classmethod
    def cleanup_stale(cls, timeout_minutes=30):
        """清理超时任务（>timeout_minutes 的 running 任务标记为 failed）。"""
        threshold = timezone.now() - timedelta(minutes=timeout_minutes)
        qs = Document.objects.filter(collection=cls.COLLECTION, data__status=cls.STATUS_RUNNING)
        for doc in qs:
            updated_at = doc.data.get('updated_at')
            if not updated_at:
                continue
            try:
                dt = parse_datetime(updated_at)
                if dt and dt < threshold:
                    data = dict(doc.data)
                    data['status'] = cls.STATUS_FAILED
                    data['error'] = '任务超时未完成（>%d分钟）' % timeout_minutes
                    data['updated_at'] = timezone.now().isoformat()
                    doc.data = data
                    doc.save(update_fields=['data'])
            except (ValueError, TypeError):
                pass
