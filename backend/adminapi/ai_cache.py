"""AI 结果缓存管理 —— 基于内容哈希的缓存命中与失效。

缓存数据存储在 Document 的 data JSON 字段中，以 field_name 为 key。
缓存条目即 AI 返回的结构化结果本身，额外追加 content_hash 和 cached_at 字段：

{
    ...AI结果字段...,           # 如 knowledge_points, difficulty 等
    "content_hash": "abcdef0123456789",
    "cached_at": "2024-01-01T00:00:00Z"
}

缓存命中条件：content_hash 匹配且缓存非 None 且未过期。
"""
import hashlib
import json
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import Document


class AICacheManager:
    """AI 结果缓存读写管理器。

    所有缓存操作通过 Document(collection, doc_id) 定位目标文档，
    在文档 data 中以 field_name 为 key 存储缓存对象。
    缓存对象即 AI 结果本身（直接合并 content_hash 和 cached_at），
    前端读取 doc.data[field_name] 即可获得完整结果。
    """

    # 缓存有效期（秒），默认 7 天
    CACHE_TTL_SECONDS = 7 * 24 * 3600

    @staticmethod
    def compute_hash(*fields) -> str:
        """将关键字段 JSON 序列化后取 SHA-256 前 16 位。

        相同输入必定返回相同 hash，用于缓存命中判断。
        None 值统一转为空字符串以保证稳定性。
        """
        parts = []
        for field in fields:
            if field is None:
                parts.append('')
            elif isinstance(field, str):
                parts.append(field)
            else:
                parts.append(json.dumps(field, sort_keys=True, ensure_ascii=False))
        raw = '|'.join(parts)
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]

    @staticmethod
    def _get_doc(collection, doc_id):
        """获取目标 Document，支持 doc_id 和 pk 双模式查找。"""
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

    @classmethod
    def get(cls, collection, doc_id, field_name):
        """从 Document 中读取缓存字段，命中且未过期时返回结果 dict，否则 None。

        返回的 dict 即 AI 结果本身（包含 content_hash, cached_at 等元数据）。
        """
        doc = cls._get_doc(collection, doc_id)
        if not doc:
            return None
        cache = doc.data.get(field_name)
        if not isinstance(cache, dict):
            return None
        # 检查过期
        cached_at = cache.get('cached_at')
        if cached_at:
            try:
                dt = parse_datetime(cached_at)
                if dt and timezone.now() - dt > timedelta(seconds=cls.CACHE_TTL_SECONDS):
                    return None
            except (ValueError, TypeError):
                pass
        return cache

    @classmethod
    def get_stale(cls, collection, doc_id, field_name):
        """允许返回过期缓存（用于降级场景，如 LLM 调用失败时）。

        返回的 dict 即 AI 结果本身（包含 content_hash 等元数据）。
        """
        doc = cls._get_doc(collection, doc_id)
        if not doc:
            return None
        cache = doc.data.get(field_name)
        if not isinstance(cache, dict):
            return None
        return cache

    @classmethod
    def set(cls, collection, doc_id, field_name, result, content_hash):
        """写入缓存到 Document 的 data[field_name]。

        将 result（dict）与 content_hash、cached_at 合并后直接存储，
        确保前端读取 doc.data[field_name] 即可获得完整结果。
        """
        doc = cls._get_doc(collection, doc_id)
        if not doc:
            return
        data = dict(doc.data)
        # 合并 result + 缓存元数据，避免包装层
        stored = dict(result) if isinstance(result, dict) else {'result': result}
        stored['content_hash'] = content_hash
        stored['cached_at'] = timezone.now().isoformat()
        data[field_name] = stored
        doc.data = data
        doc.save(update_fields=['data'])

    @classmethod
    def invalidate(cls, collection, doc_id, field_name):
        """清除缓存（置为 None）。"""
        doc = cls._get_doc(collection, doc_id)
        if not doc:
            return
        data = dict(doc.data)
        if field_name in data:
            data[field_name] = None
            doc.data = data
            doc.save(update_fields=['data'])

    @classmethod
    def invalidate_batch(cls, collection, doc_ids, field_name):
        """批量清除缓存。"""
        for doc_id in doc_ids:
            cls.invalidate(collection, doc_id, field_name)
