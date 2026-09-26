"""AI 业务服务层 —— P0 级 AI 功能的核心实现。

包含：
- AIServiceBase：基类，提供模型配置、缓存、降级调用、脱敏等通用能力
- QuestionAnalysisService：AI 题目解析（单题 + 批量）
- ExamCompositionService：AI 智能组卷（候选池筛选 → LLM 选题 → 确认草稿）
- GradingService：AI 智能判卷（单题 + 批量 + 人工复核判定）

所有服务类继承 AIServiceBase，通过 self.call_llm_with_fallback() 调用 LLM。
复用 views_ai._call_llm() 和 views_ai._get_ai_config()，不重写 LLM 调用逻辑。
"""
import json
import logging
import math
import random
import re
import uuid as uuid_lib
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from core.models import Document
from . import article_code as ac
from .ai_cache import AICacheManager
from .ai_jobs import AIJobManager
from .ai_prompts import PromptBuilder
from . import data_utils as du

logger = logging.getLogger(__name__)

# ---- 模型分级配置 ----
MODEL_TIERS = {
    'lite':     {'model': 'gpt-4o-mini', 'max_tokens': 1000, 'temperature': 0.3},
    'standard': {'model': 'gpt-4o-mini', 'max_tokens': 2000, 'temperature': 0.5},
    'complex':  {'model': 'gpt-4o',      'max_tokens': 4000, 'temperature': 0.7},
}


# --------------------------------------------------------------------------
# 超时检查工具
# --------------------------------------------------------------------------

class JobTimeoutGuard:
    """批量操作的耗时守卫，防止后台线程长时间卡死。

    用法::

        guard = JobTimeoutGuard(job_id, timeout=600)
        for item in items:
            if guard.exceeded():
                AIJobManager.update(job_id, status='failed', error='批量操作超时')
                return
            ...  # 处理 item
            guard.tick()
    """

    def __init__(self, job_id=None, timeout=None):
        self.job_id = job_id
        if timeout is not None:
            self.timeout = timeout
        else:
            self.timeout = getattr(settings, 'AI_JOB_TIMEOUT_SECONDS', 600)
        self._start = timezone.now()
        self._tick_count = 0

    def elapsed(self):
        """返回已耗时（秒）。"""
        return (timezone.now() - self._start).total_seconds()

    def exceeded(self):
        """是否已超时。"""
        return self.elapsed() > self.timeout

    def remaining(self):
        """剩余时间（秒）。"""
        return max(0, self.timeout - self.elapsed())

    def tick(self):
        """记录一次处理，返回是否仍可继续。"""
        self._tick_count += 1
        return not self.exceeded()

# 功能 -> 模型分级映射
FUNCTION_MODEL_MAP = {
    'question_analyze': 'standard',
    'exam_compose': 'complex',       # 组卷需处理大候选池+推理，与判卷/试卷分析同级
    'ai_grade': 'complex',
    'exam_analyze': 'complex',
    'learning_profile': 'complex',
    'review_recommend': 'lite',
    'article_enhance': 'standard',
    # ---- P2 级功能 ----
    'kb_qa': 'standard',
    'auto_tag': 'standard',
    'excel_validate': 'complex',
    'learning_report': 'complex',
    'cs_chat': 'standard',
}

# PII 字段列表，脱敏时递归移除
_PII_FIELDS = (
    '_openid', 'nickName', 'avatarUrl', 'phone', 'email', 'city', 'userInfo',
)


# --------------------------------------------------------------------------
# historys 数据归一化
#
# 答题记录在同一集合里存在两种形态：
#   1) 小程序答题页写入：items = ['RK_..._Q01', ...]（题目 ID 字符串数组），
#      配套 score_arr = [['C'], ['A','B']]（用户作答）与 rightNum（答对数）；
#   2) 导入 / AI 路径写入：items = [{questionId, isCorrect, usedTime, ...}]。
#
# 下游 AI 服务（试卷分析 / 答题分析 / 学习报告）需要逐题的对错与题型，
# 因此统一在此归一化，避免每个服务各写一套解析逻辑。
# --------------------------------------------------------------------------

def _question_correct_codes(question_doc):
    """从题目文档解析正确答案选项码集合（无则返回 None）。"""
    if question_doc is None:
        return None
    data = getattr(question_doc, 'data', None) or {}
    codes = set()
    options = data.get('options')
    if isinstance(options, list):
        for opt in options:
            if not isinstance(opt, dict):
                continue
            value = opt.get('value')
            if du.to_number(value, 0) == 1 or opt.get('is_correct'):
                code = du.to_text(opt.get('code')) or du.to_text(opt.get('key'))
                if code:
                    codes.add(code.strip().upper())
    if not codes:
        answer = du.to_text(data.get('answer'))
        if answer:
            codes = {ch.upper() for ch in re.findall(r'[A-Za-z]', answer)}
    return codes or None


def _normalize_answer(user_answer):
    """把用户作答归一化为选项码集合。"""
    if isinstance(user_answer, str):
        return {ch.upper() for ch in re.findall(r'[A-Za-z]', user_answer)}
    if isinstance(user_answer, (list, tuple, set)):
        return {str(x).strip().upper() for x in user_answer if str(x).strip()}
    return set()


def item_is_correct(item, question_doc=None):
    """判断单条作答是否正确。

    优先读取对象形态里的显式判定字段；字符串形态则用 ``user_answer``
    与该题的正确答案比对。无法判定时返回 None。

    Args:
        item:         归一化后的作答项（dict）
        question_doc: 可选题目文档，字符串形态判定对错时必需

    Returns:
        True / False / None
    """
    if not isinstance(item, dict):
        return None
    if item.get('isCorrect') is not None:
        return bool(item.get('isCorrect'))
    if item.get('right') is not None:
        return du.to_number(item.get('right'), 0) >= 1
    if item.get('status') is not None:
        return bool(item.get('status'))
    if item.get('result') is not None:
        return item.get('result') == 'correct'
    ai_grading = item.get('ai_grading')
    if isinstance(ai_grading, dict):
        max_score = du.to_number(ai_grading.get('max_score', 0))
        score = du.to_number(ai_grading.get('score', 0))
        return score >= max_score * 0.6 if max_score > 0 else score > 0
    if item.get('user_answer') is not None:
        correct_codes = _question_correct_codes(question_doc)
        if correct_codes:
            return _normalize_answer(item.get('user_answer')) == correct_codes
    return None


def normalize_history_items(h_data, question_lookup=None):
    """归一化一条 historys 记录的 items 为作答项列表。

    每个作答项至少包含 ``questionId``；对象形态的原始字段原样保留，
    字符串形态附带 ``user_answer`` 与 ``item_index``。

    Args:
        h_data:          historys 的 data 字典
        question_lookup: 可选 ``callable(qid) -> question Document``，
                         用于字符串形态下判定对错；缺省则不判定

    Returns:
        list[dict]，每项含 ``questionId``、``item_index``、``is_correct``
    """
    if not isinstance(h_data, dict):
        return []

    raw_items = h_data.get('items')
    if not isinstance(raw_items, list):
        raw_items = h_data.get('questions')
    if not isinstance(raw_items, list):
        raw_items = []

    score_arr = h_data.get('score_arr')
    if not isinstance(score_arr, list):
        score_arr = []

    normalized = []
    for idx, raw in enumerate(raw_items):
        if isinstance(raw, dict):
            qid = raw.get('questionId') or raw.get('qid') or raw.get('_id') or ''
            if not du.to_text(qid):
                continue
            item = dict(raw)
            item['questionId'] = str(qid)
            item['item_index'] = idx
        elif isinstance(raw, str) and raw.strip():
            item = {
                'questionId': raw.strip(),
                'item_index': idx,
                'user_answer': score_arr[idx] if idx < len(score_arr) else None,
            }
            # 字符串形态下，score_arr 可能是 1/0 整数（小程序运行时）或答案列表（导入路径）
            # 仅当 score_arr 值是 int/float 时直接作为对错判定；列表/字符串则留给 lookup 比对
            if idx < len(score_arr):
                sa_val = score_arr[idx]
                if isinstance(sa_val, (int, float)) and not isinstance(sa_val, bool):
                    item['isCorrect'] = bool(sa_val)
        else:
            continue

        question_doc = None
        if question_lookup is not None and 'is_correct' not in item:
            try:
                question_doc = question_lookup(item['questionId'])
            except Exception:  # pragma: no cover - 查询失败不应中断聚合
                question_doc = None
        item['is_correct'] = item_is_correct(item, question_doc)
        normalized.append(item)
    return normalized


def make_question_lookup():
    """构造带进程内缓存的题目查询函数（供按记录聚合时复用）。"""
    cache = {}

    def _lookup(qid):
        key = str(qid)
        if key not in cache:
            cache[key] = AIServiceBase._find_question_doc(key)
        return cache[key]

    return _lookup


class AIServiceBase:
    """AI 服务基类，提供通用能力。

    子类通过继承获得：模型配置读取、LLM 降级调用、缓存读写、
    PII 脱敏、内容哈希计算、Prompt 构建等能力。
    """

    SERVICE_NAME = 'base'

    @classmethod
    def get_model_config(cls, func_name):
        """根据 FUNCTION_MODEL_MAP 获取模型配置，支持 ai_config.feature_config 覆盖。

        返回 dict 包含：model, max_tokens, temperature, tier, enabled。
        feature_config 中对应功能的配置会覆盖默认模型参数。
        """
        tier = FUNCTION_MODEL_MAP.get(func_name, 'standard')
        config = dict(MODEL_TIERS.get(tier, MODEL_TIERS['standard']))

        # 从 ai_config.feature_config 读取覆盖配置（延迟导入避免循环依赖）
        from .views_ai import _get_ai_config
        ai_config, _ = _get_ai_config()
        feature_config = ai_config.get('feature_config') or {}
        func_config = feature_config.get(func_name) or {}

        # 检查功能是否启用
        config['enabled'] = func_config.get('enabled', True)

        # 覆盖模型参数（非空值才覆盖）
        if func_config.get('model'):
            config['model'] = func_config['model']
        if func_config.get('temperature') is not None:
            try:
                config['temperature'] = float(func_config['temperature'])
            except (ValueError, TypeError):
                pass
        if func_config.get('max_tokens'):
            try:
                config['max_tokens'] = int(func_config['max_tokens'])
            except (ValueError, TypeError):
                pass

        config['tier'] = tier
        return config

    @classmethod
    def call_llm_with_fallback(cls, messages, model_tier='standard', cache_key=None, fallback=None,
                               model_id=None, openid=None, func_name=None,
                               retry_callback=None):
        """三级降级调用 LLM（带渐进超时重试 + 指数退避）。

        模型解析优先级（详见 ``ai_models.resolve_model``）：
          显式 model_id → 功能级配置指定模型 → 当前线程生效模型 →
          用户默认 → 全局默认 → 旧版单配置。

        超时与重试策略：
          - 超时按 model_tier 从 settings.AI_LLM_TIMEOUTS 读取
          - 第一次失败后指数退避等待（2s → 4s → 8s）
          - 超时错误重试时递增超时（×1.5 → ×2.0），给 LLM 更多时间
          - 4xx HTTP 错误不重试（配置错误重试无意义）
          - retry_callback(err, attempt) 在重试前回调，可用于缩减 payload

        Args:
            retry_callback: 可选回调 fn(err_str, attempt_num) -> new_messages，
                            返回缩减后的 messages 用于重试（如减少候选题数量）。

        Returns:
            (content, error) —— content 为 LLM 返回文本，error 为错误信息。
        """
        from .views_ai import _call_llm, _get_ai_config
        from . import ai_models
        import time as _time

        # 功能名：优先显式传入，否则用服务自身的 SERVICE_NAME
        func_name = func_name or getattr(cls, 'SERVICE_NAME', None)

        ai_config, _ = _get_ai_config()
        if not ai_config.get('enabled'):
            return None, 'AI 功能未启用，请先在配置中开启'

        # 优先复用线程内已解析的模型；否则按优先级解析
        resolved = ai_models.get_active_model()
        if resolved is None:
            resolved, err = ai_models.resolve_model(
                model_id=model_id, openid=openid, func_name=func_name)
            if err or not resolved:
                return None, err or '模型解析失败'

        explicit = bool((model_id or '').strip()) or resolved.get('source') == 'explicit'
        call_config, err = ai_models.build_call_config(
            resolved, func_name=func_name, explicit=explicit)
        if err:
            return None, err

        # 旧版单配置：保留按分级覆盖模型参数的既有行为
        if resolved.get('source') == 'legacy':
            tier_config = MODEL_TIERS.get(model_tier, MODEL_TIERS['standard'])
            call_config['model'] = tier_config['model']
            call_config['maxTokens'] = tier_config['max_tokens']
            call_config['temperature'] = tier_config['temperature']
        else:
            # 非旧版模型：确保 tier 级别 max_tokens 作为下限
            # 模型条目可能 maxTokens=2000，但 complex 功能（试卷分析/组卷）需要 4000
            tier_config = MODEL_TIERS.get(model_tier, MODEL_TIERS['standard'])
            tier_max = int(tier_config.get('max_tokens', 2000))
            current_max = int(call_config.get('maxTokens') or 2000)
            if current_max < tier_max:
                logger.info('maxTokens raised from %d to %d (tier=%s requires minimum)',
                            current_max, tier_max, model_tier)
                call_config['maxTokens'] = tier_max

        # 注入分级超时到 call_config，_call_llm 会读取
        call_config['tier'] = model_tier

        # 读取基础超时和重试配置
        base_timeouts = getattr(settings, 'AI_LLM_TIMEOUTS', {})
        base_timeout = base_timeouts.get(model_tier, base_timeouts.get('default', 45))
        max_retries = getattr(settings, 'AI_LLM_MAX_RETRIES', 2)
        retry_delay_base = getattr(settings, 'AI_LLM_RETRY_DELAY', 2)

        # 超时递增系数：第1次重试 ×1.5，第2次重试 ×2.0
        timeout_multipliers = [1.5, 2.0]

        current_messages = messages

        # 最多尝试 1 + max_retries 次
        for attempt in range(1 + max_retries):
            # 渐进超时：第0次用原始值，后续递增
            if attempt == 0:
                call_config['_timeout'] = None  # 使用 tier 默认
            else:
                mult = timeout_multipliers[min(attempt - 1, len(timeout_multipliers) - 1)]
                call_config['_timeout'] = int(base_timeout * mult)
                logger.info('LLM retry attempt %d: timeout increased to %ds (×%.1f)',
                            attempt, call_config['_timeout'], mult)

            content, err = _call_llm(call_config, current_messages)
            if content:
                if attempt > 0:
                    logger.info('LLM retry attempt %d succeeded', attempt)
                return content, None

            # content 为空：确保 err 有值，避免日志打印 "None"
            if not err:
                err = 'LLM 返回空内容（HTTP 200 但 content 为空）'

            # 判断是否值得重试：4xx 客户端错误 / 配置错误 / 内容过滤不重试
            if ('HTTP 4' in err or 'API Key 未配置' in err or 'API 地址' in err
                    or 'content_filter' in err or 'function_call' in err):
                logger.warning('LLM call failed with non-retryable error: %s', err)
                break

            # finish_reason=length 是 max_tokens 不足，重试可能有效（下次超时更长）
            # 但如果是空内容且非超时，重试大概率拿同样结果 → 限制重试
            if 'finish_reason=length' not in err and '超时' not in err and 'timed out' not in err:
                # 非超时类空内容：仅重试一次，避免浪费
                if attempt >= 1:
                    logger.warning('LLM returned empty content (non-timeout), skipping further retries: %s', err)
                    break

            if attempt < max_retries:
                # 指数退避：2s → 4s → 8s
                delay = retry_delay_base * (2 ** attempt)
                logger.warning('LLM attempt %d failed: %s, retrying after %ds...',
                               attempt + 1, err, delay)
                _time.sleep(delay)

                # 回调：允许调用方缩减 payload（如减少候选题数量）
                if retry_callback:
                    new_messages = retry_callback(err or '', attempt + 1)
                    if new_messages:
                        current_messages = new_messages
                        logger.info('LLM retry payload reduced by callback')

        # 降级：返回 fallback（缓存值）
        if fallback is not None:
            logger.warning('LLM all retries failed: %s, falling back to cached result', err)
            return fallback, None

        return None, err or 'LLM 调用失败'

    @staticmethod
    def sanitize_for_llm(data):
        """移除 PII 字段，保护用户隐私。

        递归处理嵌套 dict 和 list，移除 _PII_FIELDS 中列出的字段。
        """
        if not isinstance(data, dict):
            return {}
        result = {}
        for key, value in data.items():
            if key in _PII_FIELDS:
                continue
            if isinstance(value, dict):
                result[key] = AIServiceBase.sanitize_for_llm(value)
            elif isinstance(value, list):
                result[key] = [
                    AIServiceBase.sanitize_for_llm(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    @staticmethod
    def compute_content_hash(*fields):
        """调用 AICacheManager.compute_hash 计算内容哈希。

        自动纳入「当前生效模型」签名（见 ai_models.get_active_signature），
        使同一内容在不同模型下的缓存彼此隔离 —— 切换模型后不会命中旧模型结果。
        """
        from . import ai_models
        signature = ai_models.get_active_signature()
        if signature:
            return AICacheManager.compute_hash(*(tuple(fields) + ('model:' + signature,)))
        return AICacheManager.compute_hash(*fields)

    @staticmethod
    def get_cache(collection, doc_id, field_name):
        """读取缓存。"""
        return AICacheManager.get(collection, doc_id, field_name)

    @staticmethod
    def set_cache(collection, doc_id, field_name, result, content_hash):
        """写入缓存。"""
        AICacheManager.set(collection, doc_id, field_name, result, content_hash)

    @staticmethod
    def build_prompt(template_name, **params):
        """调用 PromptBuilder 构建 prompt。

        根据 template_name 动态调用 PromptBuilder.build_<template_name>_prompt。
        """
        builder_method = getattr(PromptBuilder, 'build_%s_prompt' % template_name, None)
        if builder_method:
            return builder_method(**params)
        return PromptBuilder.build_system_prompt(template_name)

    # ---- 辅助方法 ----
    @staticmethod
    def _find_question_doc(doc_id):
        """按 doc_id 或 pk 查找题目文档。"""
        doc = Document.objects.filter(collection='questions', doc_id=str(doc_id)).first()
        if not doc and str(doc_id).isdigit():
            doc = Document.objects.filter(collection='questions', pk=int(doc_id), doc_id=None).first()
        return doc

    @staticmethod
    def _find_history_doc(history_id):
        """按 doc_id 或 pk 查找答题记录文档。"""
        doc = Document.objects.filter(collection='historys', doc_id=str(history_id)).first()
        if not doc and str(history_id).isdigit():
            doc = Document.objects.filter(collection='historys', pk=int(history_id), doc_id=None).first()
        return doc


class QuestionAnalysisService(AIServiceBase):
    """AI 题目解析服务。

    分析题目内容，返回：知识点、难度、题型识别、答案解析、推荐标签、核心概念、常见错误。
    结果存入 question_doc.data['ai_analysis']。
    """

    SERVICE_NAME = 'question_analyze'
    BATCH_SIZE = 10

    @classmethod
    def analyze_single(cls, question_doc):
        """单题 AI 解析（同步）。

        流程：
        1. 检查缓存（content_hash = hash(content_md + qtype + options)）
        2. 调用 LLM
        3. 解析 JSON
        4. 存入 question_doc.data['ai_analysis']
        5. 返回结果

        Args:
            question_doc: core.Document (collection='questions')

        Returns:
            分析结果 dict，包含 version, content_hash, model, analyzed_at 等元数据。
        """
        data = question_doc.data or {}
        content_md = du.to_text(data.get('content_md')) or du.to_text(data.get('title'))
        qtype = du.to_text(data.get('qtype'))
        options = data.get('options', [])

        # 计算内容哈希
        content_hash = cls.compute_content_hash(
            content_md, qtype,
            json.dumps(options, sort_keys=True, ensure_ascii=False)
        )

        # 检查缓存
        doc_id = question_doc.doc_id or str(question_doc.pk)
        cached = cls.get_cache('questions', doc_id, 'ai_analysis')
        if cached and isinstance(cached, dict) and cached.get('content_hash') == content_hash:
            return cached

        # 获取模型配置
        model_config = cls.get_model_config('question_analyze')
        if not model_config.get('enabled', True):
            return {'error': '题目解析功能未启用'}

        # 构建 prompt
        system_prompt = PromptBuilder.build_system_prompt('question_analyze')
        user_prompt = PromptBuilder.build_question_analyze_prompt(content_md, qtype, options)

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        # 调用 LLM（带降级：失败时返回缓存）
        content, err = cls.call_llm_with_fallback(
            messages, model_tier=model_config.get('tier', 'standard'),
            cache_key=content_hash, fallback=cached
        )
        if err and not content:
            return {'error': 'AI 解析失败：%s' % err}

        # 解析 JSON
        result = PromptBuilder.parse_json_response(content)
        if not result or not isinstance(result, dict):
            if cached:
                return cached
            return {'error': 'AI 返回结果解析失败'}

        # 补充元数据
        result['version'] = 1
        result['content_hash'] = content_hash
        result['model'] = model_config.get('model', '')
        result['analyzed_at'] = timezone.now().isoformat()

        # 写入缓存（同时存储到 doc.data['ai_analysis']，含 content_hash + cached_at）
        cls.set_cache('questions', doc_id, 'ai_analysis', result, content_hash)

        return result

    @classmethod
    def analyze_batch(cls, question_ids, job_id):
        """批量解析（异步，在守护线程中执行）。

        分批 BATCH_SIZE(10) 题/次合并 prompt -> 逐批调用 LLM -> 更新进度 -> 批量存储。

        Args:
            question_ids: 题目 ID 列表（doc_id 或 pk 字符串）
            job_id: AI 任务 ID，用于更新进度
        """
        total = len(question_ids)
        AIJobManager.update(job_id, progress=0, progress_text='开始批量解析',
                            status=AIJobManager.STATUS_RUNNING)

        if total == 0:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS,
                                progress=100, progress_text='无题目需要解析',
                                result={'total': 0, 'processed': 0})
            return

        processed = 0
        model_config = cls.get_model_config('question_analyze')
        guard = JobTimeoutGuard(job_id)

        for batch_start in range(0, total, cls.BATCH_SIZE):
            # 超时检查
            if guard.exceeded():
                logger.warning('Batch analyze timeout after %ds, processed %d/%d',
                               int(guard.elapsed()), processed, total)
                AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                    error='批量解析超时（%ds），已完成 %d/%d 题'
                                          % (int(guard.elapsed()), processed, total),
                                    progress_text='解析超时',
                                    result={'total': total, 'processed': processed, 'timed_out': True})
                return

            batch_ids = question_ids[batch_start:batch_start + cls.BATCH_SIZE]

            # 获取题目文档
            docs = []
            for qid in batch_ids:
                doc = cls._find_question_doc(qid)
                if doc:
                    docs.append(doc)

            if not docs:
                processed += len(batch_ids)
                continue

            # 构建批量 prompt
            questions_text = []
            for i, doc in enumerate(docs):
                d = doc.data or {}
                cm = du.to_text(d.get('content_md')) or du.to_text(d.get('title'))
                qt = du.to_text(d.get('qtype'))
                doc_identifier = doc.doc_id or str(doc.pk)
                questions_text.append(
                    '--- 题目 %d (ID: %s) ---\n题型: %s\n内容: %s' % (i + 1, doc_identifier, qt, cm)
                )

            system_prompt = PromptBuilder.build_system_prompt('question_analyze')
            user_prompt = (
                '请分析以下 %d 道题目，返回 JSON 格式结果：\n'
                '格式为 {"results": [{...分析结果1...}, {...分析结果2...}, ...]}，\n'
                'results 数组中每个元素对应一道题目，顺序与输入一致。\n\n%s\n\n'
                '每个分析结果包含：knowledge_points, difficulty, difficulty_score, '
                'qtype_detected, answer_analysis_md, suggested_tags, key_concepts, common_mistakes。'
            ) % (len(docs), '\n\n'.join(questions_text))

            messages = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ]

            # 调用 LLM
            content, err = cls.call_llm_with_fallback(
                messages, model_tier=model_config.get('tier', 'standard'))

            if content:
                result = PromptBuilder.parse_json_response(content)
                # 提取结果列表
                results_list = []
                if isinstance(result, dict):
                    results_list = result.get('results', [])
                elif isinstance(result, list):
                    results_list = result

                # 存储结果
                for i, doc in enumerate(docs):
                    analysis = results_list[i] if i < len(results_list) else None
                    if not analysis or not isinstance(analysis, dict):
                        # 批量解析中个别题失败，降级为单题解析
                        try:
                            cls.analyze_single(doc)
                        except Exception as e:
                            logger.error('Fallback single analyze failed for doc %s: %s', doc.pk, e)
                        processed += 1
                        continue

                    d = doc.data or {}
                    cm = du.to_text(d.get('content_md')) or du.to_text(d.get('title'))
                    qt = du.to_text(d.get('qtype'))
                    opts = d.get('options', [])
                    ch = cls.compute_content_hash(
                        cm, qt, json.dumps(opts, sort_keys=True, ensure_ascii=False))

                    analysis['version'] = 1
                    analysis['content_hash'] = ch
                    analysis['model'] = model_config.get('model', '')
                    analysis['analyzed_at'] = timezone.now().isoformat()

                    doc_identifier = doc.doc_id or str(doc.pk)
                    # 写入缓存（同时存储到 doc.data['ai_analysis']）
                    cls.set_cache('questions', doc_identifier, 'ai_analysis', analysis, ch)
            else:
                # 批量失败，降级为逐题解析
                logger.warning('Batch analyze failed (%s), falling back to single', err)
                for doc in docs:
                    try:
                        cls.analyze_single(doc)
                    except Exception as e:
                        logger.error('Single analyze failed for doc %s: %s', doc.pk, e)

            processed += len(docs)
            progress = int(processed / total * 100) if total else 100
            AIJobManager.update(job_id, progress=progress,
                                progress_text='已解析 %d/%d 题' % (processed, total))

        AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS,
                            progress=100, progress_text='批量解析完成',
                            result={'total': total, 'processed': processed})


class ExamCompositionService(AIServiceBase):
    """AI 智能组卷服务。

    从候选题池中智能选题，生成满足题型分布、难度分布和总分要求的试卷。
    """

    SERVICE_NAME = 'exam_compose'

    # ---- 候选题采样策略 ----

    @staticmethod
    def _load_question_pool(examid, max_load=600):
        """从题库加载原始候选题池（按科目过滤，去重）。

        加载上限 max_load 条记录，提取 id/qtype/difficulty/knowledge_summary/score，
        返回 (candidates_list, seen_ids_set)。

        与采样逻辑分离，便于重试时复用已加载的数据。
        """
        qs = Document.objects.filter(collection='questions')
        if examid:
            qs = qs.filter(Q(data__examid=str(examid)) | Q(data__examid=examid))

        candidates = []
        seen_ids = set()
        for doc in qs[:max_load]:
            doc_id = doc.doc_id or str(doc.pk)
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)

            d = doc.data or {}
            ai_analysis = d.get('ai_analysis') or {}
            difficulty = ai_analysis.get('difficulty') or d.get('difficulty') or 'medium'
            kp_names = []
            for kp in (ai_analysis.get('knowledge_points') or []):
                if isinstance(kp, dict) and kp.get('name'):
                    kp_names.append(kp['name'])

            candidates.append({
                'id': doc_id,
                'qtype': d.get('qtype', ''),
                'difficulty': difficulty,
                'knowledge_summary': '、'.join(kp_names) if kp_names else '未标注',
                'knowledge_tags': kp_names,  # 保留原始知识点列表用于匹配
                'score': d.get('score', 0),
            })

        return candidates, seen_ids

    @staticmethod
    def _stratified_sample(candidates, config, sample_ratio=None, max_per_qtype=None,
                           min_per_qtype=None):
        """按题型分层随机采样候选题，确保每种题型有足够的候选。

        策略：
        1. 按 qtype 将候选题分组
        2. 对每种用户需要的题型（qtype_dist 中数量 > 0 的）：
           - 计算该题型需要的题数 needed_count
           - 采样数 = needed_count × sample_ratio，但不低于 min_per_qtype
           - 如果该题型可用题数 < 采样数，全部纳入
        3. 对不需要的题型：不采样（用户没要求的题型不会出现在最终试卷中）
        4. 如果指定了 knowledge_points，优先采样匹配知识点的题目
        5. 在每个题型组内，按 difficulty_dist 比例进一步分层采样
        6. 使用 random.sample 保证随机性（每次组卷候选不同）

        Args:
            candidates: 完整候选题列表 [{id, qtype, difficulty, ...}]
            config: 组卷配置 {qtype_dist, difficulty_dist, count, knowledge_points, ...}
            sample_ratio: 每种题型采样数 = 需要数 × 此比率（默认从 settings 读取）
            max_per_qtype: 每种题型采样上限（默认从 settings 读取）
            min_per_qtype: 每种题型采样下限（默认从 settings 读取）

        Returns:
            采样后的候选题列表（已随机打乱顺序）
        """
        if sample_ratio is None:
            sample_ratio = getattr(settings, 'AI_COMPOSE_SAMPLE_RATIO', 5)
        if max_per_qtype is None:
            max_per_qtype = getattr(settings, 'AI_COMPOSE_SAMPLE_MAX_PER_QTYPE', 60)
        if min_per_qtype is None:
            min_per_qtype = getattr(settings, 'AI_COMPOSE_SAMPLE_MIN_PER_QTYPE', 10)

        qtype_dist = config.get('qtype_dist', {})
        difficulty_dist = config.get('difficulty_dist', {})
        knowledge_points = config.get('knowledge_points', [])

        # 用户需要的题型（数量 > 0）
        needed_qtypes = {qt: int(cnt) for qt, cnt in qtype_dist.items()
                         if cnt and int(cnt) > 0}

        if not needed_qtypes:
            # 没有指定题型分布，从全部候选题中随机采样
            total_count = int(config.get('count', 0)) or len(candidates)
            sample_total = min(total_count * sample_ratio, len(candidates), max_per_qtype * 5)
            sampled = random.sample(candidates, min(sample_total, len(candidates)))
            logger.info('Stratified sample (no qtype_dist): %d → %d', len(candidates), len(sampled))
            random.shuffle(sampled)
            return sampled

        # 按 qtype 分组
        qtype_groups = {}
        for c in candidates:
            qt = c.get('qtype', '')
            qtype_groups.setdefault(qt, []).append(c)

        # 需要的难度（比例 > 0）
        needed_difficulties = set(d for d, pct in difficulty_dist.items()
                                  if pct and int(pct) > 0)

        sampled = []

        for qt, needed_count in needed_qtypes.items():
            group = qtype_groups.get(qt, [])
            if not group:
                logger.warning('Stratified sample: qtype "%s" has 0 candidates in pool', qt)
                continue

            # 计算该题型的采样数
            sample_size = needed_count * sample_ratio
            sample_size = max(sample_size, min_per_qtype)
            sample_size = min(sample_size, max_per_qtype, len(group))

            # 如果指定了知识点，优先采样匹配知识点的题目
            if knowledge_points:
                kp_matched = []
                kp_unmatched = []
                for c in group:
                    c_tags = set(t.lower() for t in c.get('knowledge_tags', []))
                    kp_set = set(str(kp).lower() for kp in knowledge_points)
                    if c_tags & kp_set:
                        kp_matched.append(c)
                    else:
                        kp_unmatched.append(c)

                # 优先从匹配的题目中采样
                if len(kp_matched) >= sample_size:
                    # 在匹配题目中按难度分层
                    sampled_qt = ExamCompositionService._sample_by_difficulty(
                        kp_matched, difficulty_dist, sample_size)
                else:
                    # 匹配不够，从未匹配中补
                    sampled_qt = random.sample(kp_matched, len(kp_matched))
                    remaining = sample_size - len(sampled_qt)
                    if remaining > 0 and kp_unmatched:
                        extra = random.sample(kp_unmatched, min(remaining, len(kp_unmatched)))
                        sampled_qt.extend(extra)
            else:
                # 无知识点要求，直接按难度分层采样
                sampled_qt = ExamCompositionService._sample_by_difficulty(
                    group, difficulty_dist, sample_size)

            sampled.extend(sampled_qt)
            logger.info('Stratified sample qtype "%s": %d available → %d sampled (need %d, ratio %dx)',
                        qt, len(group), len(sampled_qt), needed_count, sample_ratio)

        # 加入未标注题型的题目（可能有用户未指定的题型）
        # 限制数量，避免过多无关题目
        unlabeled = qtype_groups.get('', [])
        if unlabeled and len(sampled) < max_per_qtype * len(needed_qtypes):
            extra = random.sample(unlabeled, min(len(unlabeled), min_per_qtype))
            sampled.extend(extra)

        # 随机打乱最终顺序，避免 LLM 依赖排列顺序
        random.shuffle(sampled)

        logger.info('Stratified sample total: %d → %d (qtypes=%s)',
                     len(candidates), len(sampled), list(needed_qtypes.keys()))
        return sampled

    @staticmethod
    def _sample_by_difficulty(group, difficulty_dist, sample_size):
        """在题型组内按难度分布分层随机采样。

        如果 difficulty_dist 指定了 easy:30/medium:50/hard:20，
        则采样时大致按此比例从各难度中抽取。

        Args:
            group: 同一题型的候选题列表
            difficulty_dist: 难度分布 {"easy": 30, "medium": 50, "hard": 20}
            sample_size: 总采样数

        Returns:
            采样后的题目列表
        """
        if not difficulty_dist or not group:
            return random.sample(group, min(sample_size, len(group)))

        # 按难度分组
        diff_groups = {}
        for c in group:
            d = c.get('difficulty', 'medium')
            diff_groups.setdefault(d, []).append(c)

        # 计算各难度的采样数
        total_pct = sum(int(v) for v in difficulty_dist.values() if v)
        if total_pct == 0:
            return random.sample(group, min(sample_size, len(group)))

        sampled = []
        remaining = sample_size

        # 按比例分配
        difficulties = list(difficulty_dist.keys())
        for i, (diff, pct) in enumerate(difficulty_dist.items()):
            if not pct or int(pct) <= 0:
                continue
            if i == len(difficulty_dist) - 1:
                # 最后一个难度取剩余全部，避免除法误差
                diff_sample = remaining
            else:
                diff_sample = int(sample_size * int(pct) / total_pct)
            diff_sample = max(diff_sample, 0)
            diff_sample = min(diff_sample, remaining)

            pool = diff_groups.get(diff, [])
            if pool:
                take = min(diff_sample, len(pool))
                sampled.extend(random.sample(pool, take))
                remaining -= take

        # 如果按比例分配后仍有剩余（某些难度题不够），从未用完的难度中补
        if remaining > 0:
            used_ids = set(c['id'] for c in sampled)
            leftover = [c for c in group if c['id'] not in used_ids]
            if leftover:
                extra = random.sample(leftover, min(remaining, len(leftover)))
                sampled.extend(extra)

        return sampled

    # ---- 组卷主流程 ----

    @classmethod
    def compose(cls, config, job_id):
        """智能组卷（异步，在守护线程中执行）。

        流程：
        1. 从题库加载候选题池（按 examid 过滤，去重）
        2. 按题型分层随机采样（根据 qtype_dist + difficulty_dist + knowledge_points）
           → 大幅缩减候选池，确保每种题型有足够候选
        3. 构建 prompt（题号+难度+知识点摘要+分值）
        4. 调用 LLM（超时重试时自动缩减候选池）
        5. 校验选中题目 ID（必须在候选池中）
        6. 确保锁定题目包含在内
        7. 存入 ai_jobs result

        Args:
            config: 组卷配置 {examid, qtype_dist, difficulty_dist, total_score, count,
                              knowledge_points, locked_questions}
            job_id: AI 任务 ID
        """
        AIJobManager.update(job_id, progress=0, progress_text='开始组卷',
                            status=AIJobManager.STATUS_RUNNING)

        examid = config.get('examid', '')
        locked_questions = config.get('locked_questions', [])

        # ---- 1. 加载候选题池 ----
        AIJobManager.update(job_id, progress=5, progress_text='正在从题库加载候选题...')
        max_load = getattr(settings, 'AI_COMPOSE_MAX_CANDIDATES', 200) * 3
        all_candidates, seen_ids = cls._load_question_pool(examid, max_load=max_load)

        if not all_candidates:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='候选题池为空（该科目下没有题目）', progress_text='候选题池为空')
            return

        AIJobManager.update(job_id, progress=15,
                            progress_text='题库共 %d 题，正在进行分层采样...' % len(all_candidates))

        # ---- 2. 分层随机采样 ----
        candidates = cls._stratified_sample(all_candidates, config)

        if not candidates:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='采样后候选题为空（请检查题型分布配置是否与题库匹配）',
                                progress_text='采样后候选题为空')
            return

        AIJobManager.update(job_id, progress=25,
                            progress_text='采样完成，候选 %d 题，正在生成组卷方案' % len(candidates))

        # ---- 3. 构建组卷 prompt ----
        system_prompt = PromptBuilder.build_system_prompt('exam_compose')
        user_prompt = PromptBuilder.build_exam_compose_prompt(candidates, config)

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        model_config = cls.get_model_config('exam_compose')

        # ---- 4. 调用 LLM（带渐进超时重试 + payload 缩减） ----
        _retry_state = {
            'all_candidates': all_candidates,
            'candidates': candidates,
            'config': config,
            'system_prompt': system_prompt,
            'seen_ids': seen_ids,
        }

        def _reduce_payload_on_retry(err_str, attempt):
            """超时重试时缩减候选池：重新采样更小的候选集。"""
            if '超时' not in err_str and 'timeout' not in err_str.lower():
                return None  # 非超时错误不缩减

            current = _retry_state['candidates']
            # 缩减目标：当前数量的 60%，但不低于 30
            target = max(int(len(current) * 0.6), 30)
            if target >= len(current):
                return None

            # 从当前候选池中随机采样缩减（而非截取前 N 个，保持多样性）
            reduced = random.sample(current, target)
            _retry_state['candidates'] = reduced
            logger.info('Compose retry %d: reduced candidates %d → %d (re-sampled)',
                        attempt, len(current), len(reduced))
            AIJobManager.update(job_id, progress_text='重试中（候选池缩减至 %d 题）' % target)

            new_prompt = PromptBuilder.build_exam_compose_prompt(reduced, _retry_state['config'])
            return [
                {'role': 'system', 'content': _retry_state['system_prompt']},
                {'role': 'user', 'content': new_prompt},
            ]

        AIJobManager.update(job_id, progress=40, progress_text='正在调用 AI 生成组卷方案...')

        content, err = cls.call_llm_with_fallback(
            messages, model_tier=model_config.get('tier', 'standard'),
            retry_callback=_reduce_payload_on_retry)

        if err and not content:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='AI 组卷失败：%s' % err, progress_text='组卷失败')
            return

        # ---- 5. 解析 LLM 返回结果 ----
        result = PromptBuilder.parse_json_response(content)
        if not result or not result.get('question_ids'):
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='AI 组卷结果解析失败', progress_text='结果解析失败')
            return

        # ---- 6. 校验选中题目 ID（必须在候选池中） ----
        selected_ids = result.get('question_ids', [])
        valid_ids = []
        for qid in selected_ids:
            qid_str = str(qid)
            if qid_str in seen_ids and qid_str not in valid_ids:
                valid_ids.append(qid_str)

        # 确保锁定题目包含在内
        for locked_id in locked_questions:
            locked_str = str(locked_id)
            if locked_str in seen_ids and locked_str not in valid_ids:
                valid_ids.insert(0, locked_str)

        result['question_ids'] = valid_ids
        result['candidate_count'] = len(candidates)
        result['pool_count'] = len(all_candidates)
        result['selected_count'] = len(valid_ids)

        AIJobManager.update(job_id, progress=100, progress_text='组卷完成',
                            status=AIJobManager.STATUS_SUCCESS, result=result)

    @classmethod
    def confirm_draft(cls, job_id, exam_name):
        """确认组卷结果，创建考试草稿文档。

        读取 ai_jobs result -> 创建 exam Document(status=draft) -> 返回 exam_id。

        Args:
            job_id: AI 任务 ID（必须为 success 状态）
            exam_name: 考试名称

        Returns:
            exam_id（字符串）或 None（任务不存在或未成功）
        """
        job_data = AIJobManager.get(job_id)
        if not job_data:
            return None
        if job_data.get('status') != AIJobManager.STATUS_SUCCESS:
            return None

        result = job_data.get('result') or {}
        question_ids = result.get('question_ids', [])

        exam_id = uuid_lib.uuid4().hex[:16]
        exam_data = {
            'name': exam_name or 'AI组卷-%s' % exam_id[:8],
            'status': 'draft',
            'questionCount': len(question_ids),
            'totalScore': result.get('total_score', 100),
            'questions': question_ids,
            'composition_result': result,
            'createdBy': 'ai_compose',
            'createTime': timezone.now().strftime('%Y/%m/%d %H:%M'),
        }

        Document.objects.create(
            collection='exam',
            doc_id=exam_id,
            data=exam_data,
        )
        return exam_id


class GradingService(AIServiceBase):
    """AI 智能判卷服务。

    对主观题作答进行 AI 评分，返回分数、反馈和置信度。
    支持 single/batch 两种模式，batch 模式更新答题记录中的逐题判卷结果。
    """

    SERVICE_NAME = 'ai_grade'

    @classmethod
    def grade_single(cls, question_doc, answer_text, rubric=None):
        """单题 AI 判卷（同步）。

        流程：
        1. 检查缓存（content_hash = hash(question_md + answer_text + rubric)）
        2. 脱敏题目数据
        3. 调用 LLM（complex 模型）
        4. 解析 {score, feedback_md, confidence}
        5. 判断 needs_human_review
        6. 返回结果

        Args:
            question_doc: core.Document (collection='questions')
            answer_text: 考生作答文本
            rubric: 评分标准（覆盖题面默认 rubric，可为 None）

        Returns:
            判卷结果 dict，包含 score, max_score, feedback_md, confidence, model,
            graded_at, content_hash, human_review, needs_human_review。
        """
        data = question_doc.data or {}
        content_md = du.to_text(data.get('content_md')) or du.to_text(data.get('title'))

        # 获取满分
        ai_grading = data.get('ai_grading') or {}
        max_score = ai_grading.get('max_score') or data.get('score') or 0

        # 计算内容哈希
        content_hash = cls.compute_content_hash(content_md, answer_text, rubric or '')

        # 检查缓存
        doc_id = question_doc.doc_id or str(question_doc.pk)
        cached = cls.get_cache('questions', doc_id, 'ai_grading_result')
        if cached and isinstance(cached, dict) and cached.get('content_hash') == content_hash:
            return cached

        # 获取模型配置
        model_config = cls.get_model_config('ai_grade')
        if not model_config.get('enabled', True):
            return {'error': 'AI 判卷功能未启用'}

        # 脱敏题目数据
        sanitized_question = cls.sanitize_for_llm(data)

        # 获取有效 rubric
        effective_rubric = rubric or ai_grading.get('rubric', '')

        # 构建 prompt
        system_prompt = PromptBuilder.build_system_prompt('ai_grade')
        user_prompt = PromptBuilder.build_grading_prompt(
            sanitized_question, answer_text, effective_rubric, max_score)

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        # 调用 LLM（complex 模型，带降级）
        content, err = cls.call_llm_with_fallback(
            messages, model_tier=model_config.get('tier', 'complex'),
            cache_key=content_hash, fallback=cached)

        if err and not content:
            return {'error': 'AI 判卷失败：%s' % err}

        # 解析 JSON
        result = PromptBuilder.parse_json_response(content)
        if not result or not isinstance(result, dict):
            if cached:
                return cached
            return {'error': 'AI 返回结果解析失败'}

        # 规范化分数（限制在 0 ~ max_score 范围内）
        try:
            score = float(result.get('score', 0))
        except (ValueError, TypeError):
            score = 0.0
        if max_score > 0:
            score = max(0.0, min(score, float(max_score)))
        else:
            score = max(0.0, score)
        result['score'] = score

        # 补充元数据
        result['max_score'] = max_score
        result['model'] = model_config.get('model', '')
        result['graded_at'] = timezone.now().isoformat()
        result['content_hash'] = content_hash
        result['human_review'] = {
            'reviewed': False,
            'adjusted_score': None,
            'reviewer': None,
            'reviewed_at': None,
        }
        result['needs_human_review'] = cls.needs_human_review(result)

        # 写入缓存
        cls.set_cache('questions', doc_id, 'ai_grading_result', result, content_hash)

        return result

    @classmethod
    def grade_batch(cls, history_id, job_id):
        """批量判卷（异步，在守护线程中执行）。

        读取 historys 中所有主观题作答 -> 逐题 grade_single ->
        更新 historys.items[n].ai_grading -> 更新进度。

        Args:
            history_id: 答题记录文档 ID
            job_id: AI 任务 ID
        """
        AIJobManager.update(job_id, progress=0, progress_text='开始批量判卷',
                            status=AIJobManager.STATUS_RUNNING)

        history_doc = cls._find_history_doc(history_id)
        if not history_doc:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='答题记录不存在', progress_text='记录不存在')
            return

        history_data = dict(history_doc.data)
        items = history_data.get('items', [])
        if not isinstance(items, list):
            items = []

        # 找出需要 AI 判卷的主观题
        subjective_items = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            qid = item.get('questionId') or item.get('qid') or item.get('_id')
            if not qid:
                continue
            question_doc = cls._find_question_doc(qid)
            if not question_doc:
                continue

            qd = question_doc.data or {}
            qtype = qd.get('qtype', '')
            is_subjective = qtype in ('qa', 'fill', 'multi_part') or \
                bool(qd.get('ai_grading', {}).get('enabled'))
            if is_subjective:
                subjective_items.append((i, question_doc))

        total = len(subjective_items)
        if total == 0:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS,
                                progress=100, progress_text='无主观题需要判卷',
                                result={'graded': 0, 'total': 0})
            return

        graded = 0
        guard = JobTimeoutGuard(job_id)
        for idx, question_doc in subjective_items:
            # 超时检查：防止批量判卷长时间卡死
            if guard.exceeded():
                logger.warning('Grade batch timeout after %ds, graded %d/%d',
                               int(guard.elapsed()), graded, total)
                AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                    error='批量判卷超时（%ds），已完成 %d/%d 题'
                                          % (int(guard.elapsed()), graded, total),
                                    progress_text='判卷超时')
                break

            item = items[idx]
            answer_text = du.to_text(item.get('answer')) or \
                du.to_text(item.get('answer_text')) or \
                du.to_text(item.get('userAnswer'))

            try:
                grading_result = cls.grade_single(question_doc, answer_text)
                if 'error' not in grading_result:
                    items[idx]['ai_grading'] = grading_result
                    graded += 1
            except Exception as e:
                logger.error('Failed to grade question at index %d: %s', idx, e)

            progress = int((graded + 1) / total * 100)
            AIJobManager.update(job_id, progress=progress,
                                progress_text='已判卷 %d/%d 题' % (graded, total))

        # 更新 historys 文档（即使超时也保存已完成的部分）
        history_data['items'] = items
        history_doc.data = history_data
        history_doc.save(update_fields=['data'])

        # 判断最终状态
        if guard.exceeded():
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                progress=progress,
                                progress_text='判卷超时，已保存 %d/%d 题' % (graded, total),
                                result={'graded': graded, 'total': total, 'timed_out': True})
        else:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS,
                                progress=100, progress_text='批量判卷完成',
                                result={'graded': graded, 'total': total})

    @staticmethod
    def needs_human_review(grading_result):
        """判断是否需要人工复核。

        规则：
        - confidence < 0.7 -> 需要复核
        - score == 0 -> 需要复核（零分可能是误判）
        - max_score > 0 且 score == max_score -> 需要复核（满分也可能是误判）

        Args:
            grading_result: 判卷结果 dict

        Returns:
            bool —— True 表示需要人工复核
        """
        confidence = grading_result.get('confidence', 0)
        try:
            confidence = float(confidence)
        except (ValueError, TypeError):
            confidence = 0.0

        score = grading_result.get('score', 0)
        try:
            score = float(score)
        except (ValueError, TypeError):
            score = 0.0

        max_score = grading_result.get('max_score', 0)
        try:
            max_score = float(max_score)
        except (ValueError, TypeError):
            max_score = 0.0

        if confidence < 0.7:
            return True
        if score == 0:
            return True
        if max_score > 0 and score == max_score:
            return True
        return False


# ====================================================================
# P1 级 AI 服务
# ====================================================================

class ExamAnalysisService(AIServiceBase):
    """AI 试卷分析服务。

    预聚合试卷答题统计（各题正确率、得分分布、难度分布），
    调用 LLM 生成分析报告，存入 exam.data['ai_analysis']。
    需要 ≥10 份答题记录才执行分析。
    """

    SERVICE_NAME = 'exam_analyze'
    MIN_RECORDS = 10
    REANALYZE_RECORD_GROWTH_THRESHOLD = 0.10  # 10% 增长触发重新分析
    REANALYZE_DAYS_THRESHOLD = 7  # 超过 7 天触发重新分析

    @classmethod
    def analyze(cls, examid, job_id):
        """AI 试卷分析（异步，在守护线程中执行）。

        流程：
        1. aggregate_stats(examid) 后端预聚合各题正确率/用时/难度分布
        2. 调用 LLM（complex 模型）生成分析报告
        3. 存入 exam.data['ai_analysis']
        4. 更新 AIJobManager 状态

        Args:
            examid: 考试文档 ID
            job_id: AI 任务 ID
        """
        AIJobManager.update(job_id, progress=0, progress_text='开始试卷分析',
                            status=AIJobManager.STATUS_RUNNING)

        # 1. 预聚合统计数据
        AIJobManager.update(job_id, progress=20, progress_text='正在聚合答题统计')
        stats = cls.aggregate_stats(examid)

        if not stats:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='试卷不存在或无答题记录', progress_text='分析失败')
            return

        total_records = stats.get('total_records', 0)
        if total_records < cls.MIN_RECORDS:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='答题记录不足 %d 份，当前 %d 份' % (cls.MIN_RECORDS, total_records),
                                progress_text='记录不足')
            return

        # 2. 构建缓存 key
        question_ids = [qs.get('question_id', '') for qs in stats.get('question_stats', [])]
        content_hash = cls.compute_content_hash(
            str(examid),
            json.dumps(question_ids, sort_keys=True, ensure_ascii=False),
            str(total_records),
            stats.get('latest_record_time', ''),
        )

        # 检查缓存
        cached = cls.get_cache('exam', str(examid), 'ai_analysis')
        if cached and isinstance(cached, dict) and cached.get('content_hash') == content_hash:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS,
                                progress=100, progress_text='分析完成（命中缓存）',
                                result=cached)
            return

        # 3. 脱敏后调用 LLM
        AIJobManager.update(job_id, progress=50, progress_text='正在生成分析报告')
        sanitized_stats = cls.sanitize_for_llm(stats)

        model_config = cls.get_model_config('exam_analyze')
        if not model_config.get('enabled', True):
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='试卷分析功能未启用', progress_text='功能未启用')
            return

        system_prompt = PromptBuilder.build_system_prompt('exam_analyze')
        user_prompt = PromptBuilder.build_exam_analyze_prompt(sanitized_stats)

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        content, err = cls.call_llm_with_fallback(
            messages, model_tier=model_config.get('tier', 'complex'),
            cache_key=content_hash, fallback=cached)

        if err and not content:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='AI 试卷分析失败：%s' % err, progress_text='分析失败')
            return

        # 4. 解析 JSON
        result = PromptBuilder.parse_json_response(content)
        if not result or not isinstance(result, dict):
            if cached:
                AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS,
                                    progress=100, progress_text='分析完成（降级缓存）',
                                    result=cached)
                return
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='AI 分析结果解析失败', progress_text='解析失败')
            return

        # 5. 补充元数据
        result['examid'] = str(examid)
        result['total_records'] = total_records
        result['content_hash'] = content_hash
        result['model'] = model_config.get('model', '')
        result['analyzed_at'] = timezone.now().isoformat()

        # 6. 存入 exam 文档
        AIJobManager.update(job_id, progress=80, progress_text='正在保存分析结果')
        cls.set_cache('exam', str(examid), 'ai_analysis', result, content_hash)

        AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS,
                            progress=100, progress_text='试卷分析完成',
                            result=result)

    @classmethod
    def aggregate_stats(cls, examid):
        """后端预聚合试卷统计数据。

        - 读取 exam 文档获取题目列表
        - 查询 historys 集合中该考试的答题记录
        - 计算各题正确率、平均用时、难度分布、得分分布
        - 返回统计摘要 dict（不送全量记录到 LLM，只送摘要）

        Args:
            examid: 考试文档 ID

        Returns:
            统计摘要 dict 或 None（试卷不存在）
        """
        # 查找 exam 文档
        exam_doc = Document.objects.filter(
            collection='exam', doc_id=str(examid)
        ).first()
        if not exam_doc and str(examid).isdigit():
            exam_doc = Document.objects.filter(
                collection='exam', pk=int(examid), doc_id=None
            ).first()

        if not exam_doc:
            return None

        exam_data = exam_doc.data or {}
        question_ids = exam_data.get('questions', [])
        if not isinstance(question_ids, list):
            question_ids = []
        # 统一转为字符串
        question_ids = [str(qid) for qid in question_ids]
        exam_name = exam_data.get('name', '未知考试')
        total_score = du.to_number(exam_data.get('totalScore', 100))

        # 查找该考试的答题记录
        # 优先通过 examid 字段匹配
        history_qs = Document.objects.filter(
            Q(data__examid=str(examid)) | Q(data__examid=examid),
            collection='historys',
        )

        histories = list(history_qs.order_by('-pk')[:200])  # 限制最多 200 条

        # 如果通过 examid 匹配为空但有题目列表，用 SQL 级过滤代替全表扫描
        if not histories and question_ids:
            question_id_set = set(question_ids)
            # 先尝试用 data__items__contains 索引查询（SQLite JSON 查询）
            # 退化方案：限制扫描量，最多扫 500 条
            scan_qs = Document.objects.filter(collection='historys').order_by('-pk')[:500]
            for h in scan_qs:
                h_items = normalize_history_items(h.data or {})
                # 只检查第一个匹配即可（判断是否属于该考试）
                for item in h_items:
                    if item['questionId'] in question_id_set:
                        histories.append(h)
                        break
                if len(histories) >= 200:
                    break

        total_records = len(histories)
        if total_records == 0:
            return {
                'exam_name': exam_name,
                'total_records': 0,
                'question_stats': [],
                'score_distribution': {'high': 0, 'medium': 0, 'low': 0},
                'avg_score': 0,
                'avg_accuracy': 0,
                'latest_record_time': '',
            }

        # 预聚合各题统计
        question_stats_map = {}  # question_id -> {correct, total, times}
        scores = []
        latest_record_time = ''
        # 题目查询带缓存，避免同一条记录内重复查库
        question_lookup = make_question_lookup()

        for h in histories:
            h_data = h.data or {}
            h_create = du.to_text(h_data.get('createTime', ''))
            if h_create and h_create > latest_record_time:
                latest_record_time = h_create

            # items 可能是题目 ID 字符串数组（小程序写入）或对象数组（导入路径）
            items = normalize_history_items(h_data, question_lookup)

            # 计算该份记录的得分率
            h_score = du.to_number(h_data.get('score', 0))
            h_right = du.to_number(h_data.get('rightNum', 0))
            h_total_q = len(items)
            if h_total_q > 0:
                score_rate = h_score / total_score if total_score > 0 else h_right / h_total_q
                scores.append(score_rate)

            # 逐题统计
            for item in items:
                qid = item['questionId']
                # 如果有题目列表且该题不在列表中，跳过
                if question_ids and qid not in question_ids:
                    continue

                if qid not in question_stats_map:
                    question_stats_map[qid] = {
                        'question_id': qid,
                        'correct': 0,
                        'total': 0,
                        'times': [],
                    }

                stat = question_stats_map[qid]
                stat['total'] += 1

                if item.get('is_correct'):
                    stat['correct'] += 1

                # 用时
                used_time = item.get('usedTime') or item.get('time') or 0
                try:
                    stat['times'].append(float(used_time))
                except (ValueError, TypeError):
                    pass

        # 构建各题统计列表
        question_stats = []
        for qid in (question_ids if question_ids else list(question_stats_map.keys())):
            stat = question_stats_map.get(qid)
            if not stat or stat['total'] == 0:
                question_stats.append({
                    'question_id': qid,
                    'accuracy': 0,
                    'avg_time': 0,
                    'difficulty': '未知',
                })
                continue

            accuracy = round(stat['correct'] / stat['total'] * 100, 1)
            avg_time = round(sum(stat['times']) / len(stat['times']), 1) if stat['times'] else 0

            # 根据正确率推断难度
            if accuracy >= 80:
                difficulty = 'easy'
            elif accuracy >= 50:
                difficulty = 'medium'
            else:
                difficulty = 'hard'

            question_stats.append({
                'question_id': qid,
                'accuracy': accuracy,
                'avg_time': avg_time,
                'difficulty': difficulty,
            })

        # 得分分布
        score_distribution = {'high': 0, 'medium': 0, 'low': 0}
        for rate in scores:
            if rate >= 0.8:
                score_distribution['high'] += 1
            elif rate >= 0.5:
                score_distribution['medium'] += 1
            else:
                score_distribution['low'] += 1

        # 平均得分和正确率
        avg_score = round(sum(scores) / len(scores) * 100, 1) if scores else 0
        avg_accuracy = avg_score  # 得分率即正确率近似

        return {
            'exam_name': exam_name,
            'total_records': total_records,
            'question_stats': question_stats,
            'score_distribution': score_distribution,
            'avg_score': avg_score,
            'avg_accuracy': avg_accuracy,
            'latest_record_time': latest_record_time,
        }

    @classmethod
    def should_reanalyze(cls, existing_analysis, current_record_count):
        """判断是否需要重新分析。

        规则：
        - 答题记录增长 >=10% 时返回 True
        - 超过 7 天返回 True
        - 无已有分析返回 True

        Args:
            existing_analysis: 已有的分析结果 dict（可为 None）
            current_record_count: 当前答题记录数

        Returns:
            bool —— True 表示需要重新分析
        """
        if not existing_analysis or not isinstance(existing_analysis, dict):
            return True

        # 检查记录增长
        old_count = existing_analysis.get('total_records', 0)
        try:
            old_count = int(old_count)
        except (ValueError, TypeError):
            old_count = 0

        if old_count == 0:
            return True
        growth = (current_record_count - old_count) / old_count
        if growth >= cls.REANALYZE_RECORD_GROWTH_THRESHOLD:
            return True

        # 检查时间
        analyzed_at = existing_analysis.get('analyzed_at', '')
        if analyzed_at:
            try:
                from datetime import timedelta
                from django.utils.dateparse import parse_datetime
                dt = parse_datetime(analyzed_at)
                if dt and timezone.now() - dt > timedelta(days=cls.REANALYZE_DAYS_THRESHOLD):
                    return True
            except (ValueError, TypeError):
                return True

        return False


class LearningProfileService(AIServiceBase):
    """AI 答题分析（学习画像）服务。

    聚合用户近 50 条答题历史，调用 LLM 生成学习画像，
    存入 ai_learning_profile collection（doc_id = 'profile-{openid}'）。
    需要 ≥20 条答题记录才执行分析。
    """

    SERVICE_NAME = 'learning_profile'
    MIN_RECORDS = 20
    RECENT_LIMIT = 50
    CACHE_TTL_DAYS = 7
    RECORD_GROWTH_THRESHOLD = 20  # 新增 ≥20 条记录时缓存失效

    @classmethod
    def analyze(cls, openid, job_id):
        """AI 答题记录分析（异步，在守护线程中执行）。

        流程：
        1. aggregate_history(openid) 聚合近 50 条 historys
        2. 调用 LLM（complex 模型）生成学习画像
        3. 存入 ai_learning_profile collection（doc_id = 'profile-{openid}'）
        4. 更新 AIJobManager 状态

        Args:
            openid: 用户 openid
            job_id: AI 任务 ID
        """
        AIJobManager.update(job_id, progress=0, progress_text='开始答题分析',
                            status=AIJobManager.STATUS_RUNNING)

        # 1. 聚合答题历史
        AIJobManager.update(job_id, progress=20, progress_text='正在聚合答题历史')
        history_summary = cls.aggregate_history(openid)

        if not history_summary:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='无法获取答题历史', progress_text='分析失败')
            return

        total_count = history_summary.get('total_count', 0)
        if total_count < cls.MIN_RECORDS:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='答题记录不足 %d 条，当前 %d 条' % (cls.MIN_RECORDS, total_count),
                                progress_text='记录不足')
            return

        # 2. 构建缓存 key
        record_ids = history_summary.get('record_ids', [])
        content_hash = cls.compute_content_hash(
            openid,
            json.dumps(record_ids, sort_keys=True, ensure_ascii=False),
            str(total_count),
        )

        # 检查缓存
        profile_doc_id = 'profile-%s' % openid
        cached = cls.get_cache('ai_learning_profile', profile_doc_id, 'profile')
        if cached and isinstance(cached, dict) and cached.get('content_hash') == content_hash:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS,
                                progress=100, progress_text='分析完成（命中缓存）',
                                result=cached)
            return

        # 3. 脱敏后调用 LLM
        AIJobManager.update(job_id, progress=50, progress_text='正在生成学习画像')
        sanitized_summary = cls.sanitize_for_llm(history_summary)

        model_config = cls.get_model_config('learning_profile')
        if not model_config.get('enabled', True):
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='答题分析功能未启用', progress_text='功能未启用')
            return

        system_prompt = PromptBuilder.build_system_prompt('learning_profile')
        user_prompt = PromptBuilder.build_learning_profile_prompt(sanitized_summary)

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        content, err = cls.call_llm_with_fallback(
            messages, model_tier=model_config.get('tier', 'complex'),
            cache_key=content_hash, fallback=cached)

        if err and not content:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='AI 答题分析失败：%s' % err, progress_text='分析失败')
            return

        # 4. 解析 JSON
        result = PromptBuilder.parse_json_response(content)
        if not result or not isinstance(result, dict):
            if cached:
                AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS,
                                    progress=100, progress_text='分析完成（降级缓存）',
                                    result=cached)
                return
            AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                error='AI 分析结果解析失败', progress_text='解析失败')
            return

        # 5. 补充元数据
        result['openid'] = openid
        result['total_count'] = total_count
        result['content_hash'] = content_hash
        result['model'] = model_config.get('model', '')
        result['analyzed_at'] = timezone.now().isoformat()

        # 6. 存入 ai_learning_profile collection
        AIJobManager.update(job_id, progress=80, progress_text='正在保存学习画像')
        cls.set_cache('ai_learning_profile', profile_doc_id, 'profile', result, content_hash)

        AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS,
                            progress=100, progress_text='答题分析完成',
                            result=result)

    @classmethod
    def aggregate_history(cls, openid):
        """聚合用户答题历史。

        - 查询 historys 中该用户的记录
        - 按科目/标签维度统计正确率
        - 聚合近 50 条记录的摘要
        - 返回统计摘要 dict

        Args:
            openid: 用户 openid

        Returns:
            统计摘要 dict 或 None
        """
        # 查询用户答题记录
        history_qs = Document.objects.filter(
            collection='historys', data___openid=openid
        ).order_by('-pk')

        if not history_qs.exists():
            return None

        # 取近 50 条
        histories = list(history_qs[:cls.RECENT_LIMIT])
        total_count = history_qs.count()

        record_ids = []
        subject_map = {}  # subject -> {total, correct}
        qtype_map = {}  # qtype -> {total, correct}
        recent_accuracies = []  # 近 5 次正确率
        error_qtypes = {}  # qtype -> error_count
        # 题目查询带缓存（字符串形态下需查题判定对错与题型）
        question_lookup = make_question_lookup()

        for idx, h in enumerate(histories):
            h_data = h.data or {}
            h_id = h.doc_id or str(h.pk)
            record_ids.append(h_id)

            # items 可能是题目 ID 字符串数组（小程序写入）或对象数组（导入路径）
            # 只在需要判定对错时才传 question_lookup（避免不必要的 DB 查询）
            items = normalize_history_items(h_data, question_lookup)

            # 计算该次答题的正确率
            h_right = du.to_number(h_data.get('rightNum', 0))
            h_total_q = len(items)
            if h_total_q > 0:
                acc = h_right / h_total_q
                if idx < 5:  # 近 5 次
                    recent_accuracies.append(round(acc, 3))

            # 科目统计
            subject = du.subject_name(h_data) or '未分类'
            if subject not in subject_map:
                subject_map[subject] = {'total': 0, 'correct': 0}
            subject_map[subject]['total'] += h_total_q
            subject_map[subject]['correct'] += int(h_right)

            # 逐题统计题型（限制每条记录最多查 50 题，防止超长记录拖慢聚合）
            for item in items[:50]:
                qid = item['questionId']

                # 查找题目获取题型（已带缓存）
                q_doc = question_lookup(qid)
                qtype = 'unknown'
                if q_doc:
                    qtype = du.to_text(q_doc.data.get('qtype', 'unknown'))

                if qtype not in qtype_map:
                    qtype_map[qtype] = {'total': 0, 'correct': 0}
                qtype_map[qtype]['total'] += 1

                if item.get('is_correct'):
                    qtype_map[qtype]['correct'] += 1
                else:
                    error_qtypes[qtype] = error_qtypes.get(qtype, 0) + 1

        # 构建科目统计列表
        subject_stats = []
        for subject, counts in sorted(subject_map.items()):
            accuracy = round(counts['correct'] / counts['total'] * 100, 1) if counts['total'] > 0 else 0
            subject_stats.append({
                'subject': subject,
                'total': counts['total'],
                'correct': counts['correct'],
                'accuracy': accuracy,
            })

        # 构建题型统计列表
        qtype_stats = []
        for qtype, counts in sorted(qtype_map.items()):
            accuracy = round(counts['correct'] / counts['total'] * 100, 1) if counts['total'] > 0 else 0
            qtype_stats.append({
                'qtype': qtype,
                'accuracy': accuracy,
            })

        # 常错题型（按错误次数排序，取前 3）
        common_error_types = []
        for qtype, err_count in sorted(error_qtypes.items(), key=lambda x: x[1], reverse=True):
            common_error_types.append(qtype)
            if len(common_error_types) >= 3:
                break

        # 近期趋势（按时间正序）
        recent_trend = list(reversed(recent_accuracies))

        return {
            'total_count': total_count,
            'record_ids': record_ids,
            'subject_stats': subject_stats,
            'recent_trend': recent_trend,
            'common_error_types': common_error_types,
            'qtype_stats': qtype_stats,
        }

    @classmethod
    def get_profile(cls, openid):
        """获取用户学习画像（从缓存读取）。

        Args:
            openid: 用户 openid

        Returns:
            学习画像 dict 或 None
        """
        profile_doc_id = 'profile-%s' % openid
        cached = cls.get_cache('ai_learning_profile', profile_doc_id, 'profile')
        if cached and isinstance(cached, dict):
            # 移除内部缓存字段
            return {k: v for k, v in cached.items() if k not in ('cached_at',)}
        return None


class ReviewRecommendService(AIServiceBase):
    """AI 复习推荐服务。

    使用艾宾浩斯遗忘曲线算法生成基础复习清单，
    调用 LLM（lite 模型）优化优先级和推荐理由，
    存入 ai_review_plans collection（doc_id = 'review-{openid}-{YYYYMMDD}'）。
    同一用户同一天只生成一次。
    """

    SERVICE_NAME = 'review_recommend'

    # 艾宾浩斯复习间隔（天）
    EBINGHAUS_INTERVALS = [1, 2, 4, 7, 15]

    @classmethod
    def generate_plan(cls, openid):
        """生成今日复习推荐。

        流程：
        1. ebbinghaus_schedule(error_notes) 艾宾浩斯算法生成基础复习清单
        2. 调用 LLM（lite 模型）优化优先级和推荐理由
        3. 存入 ai_review_plans collection（doc_id = 'review-{openid}-{YYYYMMDD}'）
        4. 返回复习清单

        Args:
            openid: 用户 openid

        Returns:
            复习推荐结果 dict
        """
        today_str = timezone.now().strftime('%Y%m%d')
        plan_doc_id = 'review-%s-%s' % (openid, today_str)

        # 检查今日是否已生成
        existing = Document.objects.filter(
            collection='ai_review_plans', doc_id=plan_doc_id
        ).first()
        if existing and existing.data and existing.data.get('plan'):
            return existing.data.get('plan')

        # 1. 获取错题列表（限制数量，避免全量加载）
        max_notes = getattr(settings, 'AI_REVIEW_MAX_NOTES', 200)
        error_notes = []
        notes_qs = Document.objects.filter(
            collection='notes', data___openid=openid
        ).order_by('-pk')[:max_notes]
        for note in notes_qs:
            error_notes.append(note)

        if not error_notes:
            return {
                'review_items': [],
                'daily_summary': '当前没有需要复习的错题',
                'estimated_total_minutes': 0,
                'tips': ['坚持每日复习错题，效果会越来越好'],
            }

        # 2. 艾宾浩斯算法生成基础清单
        base_plan = cls.ebbinghaus_schedule(error_notes)

        review_items = base_plan.get('review_items', [])
        if not review_items:
            return {
                'review_items': [],
                'daily_summary': '今日暂无需要复习的错题，可以学习新内容',
                'estimated_total_minutes': 0,
                'tips': ['保持学习节奏，及时记录错题'],
            }

        # 3. 获取学习画像（用于优化推荐）
        learning_profile = LearningProfileService.get_profile(openid)

        # 4. 调用 LLM 优化
        model_config = cls.get_model_config('review_recommend')
        if not model_config.get('enabled', True):
            # 功能未启用，直接返回算法结果
            result = {
                'review_items': [
                    {
                        'note_id': item['note_id'],
                        'question_id': item.get('question_id', ''),
                        'priority': item.get('priority', 5),
                        'reason': item.get('reason', '根据遗忘曲线推荐复习'),
                        'review_type': item.get('review_type', 'reinforce'),
                        'estimated_minutes': 5,
                    }
                    for item in review_items
                ],
                'daily_summary': '今日共 %d 道错题需要复习' % len(review_items),
                'estimated_total_minutes': len(review_items) * 5,
                'tips': ['按优先级从高到低复习效果更好'],
            }
            cls._save_plan(plan_doc_id, openid, result)
            return result

        system_prompt = PromptBuilder.build_system_prompt('review_recommend')
        user_prompt = PromptBuilder.build_review_prompt(base_plan, learning_profile)

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        content, err = cls.call_llm_with_fallback(
            messages, model_tier=model_config.get('tier', 'lite'))

        if err and not content:
            # LLM 失败，降级返回算法结果
            logger.warning('Review recommend LLM failed: %s, falling back to algorithm', err)
            result = {
                'review_items': [
                    {
                        'note_id': item['note_id'],
                        'question_id': item.get('question_id', ''),
                        'priority': item.get('priority', 5),
                        'reason': item.get('reason', '根据遗忘曲线推荐复习'),
                        'review_type': item.get('review_type', 'reinforce'),
                        'estimated_minutes': 5,
                    }
                    for item in review_items
                ],
                'daily_summary': '今日共 %d 道错题需要复习' % len(review_items),
                'estimated_total_minutes': len(review_items) * 5,
                'tips': ['按优先级从高到低复习效果更好'],
            }
            cls._save_plan(plan_doc_id, openid, result)
            return result

        # 解析 JSON
        result = PromptBuilder.parse_json_response(content)
        if not result or not isinstance(result, dict) or not result.get('review_items'):
            # 解析失败，降级返回算法结果
            logger.warning('Review recommend LLM parse failed, falling back to algorithm')
            result = {
                'review_items': [
                    {
                        'note_id': item['note_id'],
                        'question_id': item.get('question_id', ''),
                        'priority': item.get('priority', 5),
                        'reason': item.get('reason', '根据遗忘曲线推荐复习'),
                        'review_type': item.get('review_type', 'reinforce'),
                        'estimated_minutes': 5,
                    }
                    for item in review_items
                ],
                'daily_summary': '今日共 %d 道错题需要复习' % len(review_items),
                'estimated_total_minutes': len(review_items) * 5,
                'tips': ['按优先级从高到低复习效果更好'],
            }

        # 补充元数据
        result['openid'] = openid
        result['date'] = today_str
        result['total_items'] = len(result.get('review_items', []))
        result['model'] = model_config.get('model', '')
        result['generated_at'] = timezone.now().isoformat()

        # 5. 存入 ai_review_plans collection
        cls._save_plan(plan_doc_id, openid, result)

        return result

    @classmethod
    def ebbinghaus_schedule(cls, error_notes):
        """艾宾浩斯遗忘曲线算法。

        根据错题加入时间和复习状态计算遗忘风险分，
        复习周期：1天/2天/4天/7天/15天，
        返回按优先级排序的复习清单。

        Args:
            error_notes: 错题文档列表（Document 对象列表）

        Returns:
            基础复习清单 dict：
            {
                'review_items': [{
                    'note_id': str,
                    'question_id': str,
                    'days_since_review': int,
                    'next_interval': int,
                    'risk_score': float,
                    'review_count': int,
                    'priority': int,
                    'reason': str,
                    'review_type': str,
                }],
                'total_items': int,
            }
        """
        now = timezone.now()
        review_items = []

        for note in error_notes:
            note_data = note.data or {}
            note_id = note.doc_id or str(note.pk)
            question_id = str(
                note_data.get('questionId') or
                note_data.get('qid') or
                note_data.get('_id') or
                ''
            )

            # 获取加入时间（优先用 data.createdAt，其次用 doc.created_at）
            created_str = note_data.get('createdAt', '')
            created_dt = du.parse_datetime(created_str) if created_str else None
            if not created_dt:
                created_dt = note.created_at
            if not created_dt:
                continue

            # 获取复习状态
            review_count = int(note_data.get('reviewCount', 0))
            review_status = note_data.get('reviewStatus', 'new')

            # 如果已掌握，跳过
            if review_status == 'mastered':
                continue

            # 获取上次复习时间
            last_review_str = note_data.get('lastReviewDate', '')
            last_review_dt = du.parse_datetime(last_review_str) if last_review_str else None

            # 计算距上次复习的天数（没有复习过则距加入时间）
            reference_dt = last_review_dt if last_review_dt else created_dt
            days_since_review = (now - reference_dt).days
            if days_since_review < 0:
                days_since_review = 0

            # 确定下一个复习间隔
            if review_count < len(cls.EBINGHAUS_INTERVALS):
                next_interval = cls.EBINGHAUS_INTERVALS[review_count]
            else:
                next_interval = cls.EBINGHAUS_INTERVALS[-1]

            # 判断是否需要复习：距上次复习天数 >= 下一个间隔
            if days_since_review < next_interval:
                continue

            # 计算遗忘风险分（0~1，越高越紧急）
            if next_interval > 0:
                risk_score = min(1.0, days_since_review / (next_interval * 2.0))
            else:
                risk_score = 1.0

            # 优先级（1~10，越高越优先）
            priority = max(1, min(10, int(risk_score * 10)))

            # 复习类型
            if review_count == 0:
                review_type = 'new_review'
            elif review_count >= len(cls.EBINGHAUS_INTERVALS) - 1:
                review_type = 'final_review'
            else:
                review_type = 'reinforce'

            # 推荐理由
            if review_count == 0:
                reason = '新错题，建议首次复习（加入 %d 天）' % (now - created_dt).days
            else:
                reason = '已复习 %d 次，距上次复习 %d 天，建议巩固' % (review_count, days_since_review)

            review_items.append({
                'note_id': note_id,
                'question_id': question_id,
                'days_since_review': days_since_review,
                'next_interval': next_interval,
                'risk_score': round(risk_score, 3),
                'review_count': review_count,
                'priority': priority,
                'reason': reason,
                'review_type': review_type,
            })

        # 按优先级降序排序
        review_items.sort(key=lambda x: x['priority'], reverse=True)

        # 限制每日最多 30 道题
        if len(review_items) > 30:
            review_items = review_items[:30]

        return {
            'review_items': review_items,
            'total_items': len(review_items),
        }

    @classmethod
    def get_today_plan(cls, openid):
        """获取今日复习计划（当天已生成则直接返回缓存）。

        Args:
            openid: 用户 openid

        Returns:
            复习计划 dict 或 None
        """
        today_str = timezone.now().strftime('%Y%m%d')
        plan_doc_id = 'review-%s-%s' % (openid, today_str)

        existing = Document.objects.filter(
            collection='ai_review_plans', doc_id=plan_doc_id
        ).first()

        if existing and existing.data:
            plan = existing.data.get('plan')
            if plan:
                return plan

        # 当天未生成，同步生成
        return cls.generate_plan(openid)

    @classmethod
    def _save_plan(cls, plan_doc_id, openid, plan):
        """保存复习计划到 ai_review_plans collection。"""
        doc, _ = Document.objects.update_or_create(
            collection='ai_review_plans',
            doc_id=plan_doc_id,
            defaults={
                'data': {
                    'plan': plan,
                    'openid': openid,
                    'created_at': timezone.now().isoformat(),
                }
            },
        )
        return doc


class ArticleEnhanceService(AIServiceBase):
    """AI 文章撰写增强服务。

    扩展已有 ai_assist 接口的 prompt，支持多种 action：
    - topic: 选题推荐
    - outline: 大纲生成
    - generate: 正文生成（默认）
    - title: 标题优化
    - summary: 摘要自动生成
    - image_suggest: 配图建议

    无持久化（无状态调用，结果直接返回）。
    """

    SERVICE_NAME = 'article_enhance'

    # 返回 Markdown 格式的 action（不解析 JSON）
    MARKDOWN_ACTIONS = ('generate', 'outline')

    # 返回 JSON 格式的 action
    JSON_ACTIONS = ('topic', 'title', 'summary', 'image_suggest')

    @classmethod
    def assist(cls, prompt, context='', action='generate'):
        """AI 文章撰写增强。

        Args:
            prompt: 用户输入的主题或正文
            context: 补充说明上下文
            action: 操作类型（topic/outline/generate/title/summary/image_suggest）

        Returns:
            结果 dict，包含 action 和对应的内容字段。
            Markdown 类 action 返回 {'content': '...', 'action': action}。
            JSON 类 action 返回解析后的 dict + {'action': action}。
            失败返回 {'error': '...', 'action': action}。
        """
        # 参数校验
        if not prompt or not prompt.strip():
            return {'error': '请输入内容', 'action': action}

        valid_actions = cls.MARKDOWN_ACTIONS + cls.JSON_ACTIONS
        if action not in valid_actions:
            action = 'generate'

        # 获取模型配置
        model_config = cls.get_model_config('article_enhance')
        if not model_config.get('enabled', True):
            return {'error': '文章增强功能未启用', 'action': action}

        # 构建 prompt
        system_prompt = PromptBuilder.build_system_prompt('article_enhance')
        user_prompt = PromptBuilder.build_article_enhance_prompt(action, prompt.strip(), context.strip())

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        # 调用 LLM
        content, err = cls.call_llm_with_fallback(
            messages, model_tier=model_config.get('tier', 'standard'))

        if err and not content:
            return {'error': 'AI 文章增强失败：%s' % err, 'action': action}

        # Markdown 类 action：直接返回原始内容
        if action in cls.MARKDOWN_ACTIONS:
            return {
                'content': content,
                'action': action,
                'model': model_config.get('model', ''),
                'generated_at': timezone.now().isoformat(),
            }

        # JSON 类 action：解析 JSON
        result = PromptBuilder.parse_json_response(content)
        if not result or not isinstance(result, dict):
            # 解析失败，返回原始内容作为降级
            return {
                'content': content,
                'action': action,
                'model': model_config.get('model', ''),
                'generated_at': timezone.now().isoformat(),
            }

        result['action'] = action
        result['model'] = model_config.get('model', '')
        result['generated_at'] = timezone.now().isoformat()
        return result


# ====================================================================
# P2 级 AI 服务
# ====================================================================

# 中文停用词（英文/数字单词的停用词也一并纳入）
_STOPWORDS = {
    '的', '了', '和', '是', '在', '我', '有', '就', '不', '人', '都', '一',
    '一个', '上', '也', '很', '到', '说', '要', '去', '会', '着', '没有',
    '看', '好', '自己', '这', '什么', '怎么', '如何', '哪些', '可以', '需要',
    'the', 'a', 'an', 'of', 'to', 'is', 'are', 'and', 'or', 'in', 'on',
    'for', 'how', 'what', 'which', 'why', 'do', 'does', 'with',
}


class KnowledgeRAGService(AIServiceBase):
    """知识库 RAG 问答服务。

    纯 Python 实现 TF-IDF 检索（零第三方依赖），语料来自
    collection='knowledgebase' 的全量文档。检索命中的知识片段
    送入 LLM 生成基于知识库的回答，结果缓存到 ai_kb_answers 集合。

    可追溯：语料支持两种来源
    - ``source='knowledgebase'``：知识库原生条目
    - ``source='article'``：由文章选择性加入的条目，携带 ``articleCode``
      （文章唯一编码 ``ART-YYYYMMDD-NNNN``）与 ``articleId``，
      文档 ``_id`` 固定为 ``KB_ART_<编码>``，实现「索引条目 ↔ 文章」双向可查。
    """

    SERVICE_NAME = 'kb_qa'
    COLLECTION = 'ai_kb_answers'          # 问答缓存集合
    SOURCE_COLLECTION = 'knowledgebase'   # 语料来源集合
    INDEX_META_COLLECTION = 'ai_kb_index' # 索引构建元数据
    INDEX_META_DOC_ID = 'status'
    TOP_K = 5
    MIN_SCORE = 0.05
    CONTENT_MAX_CHARS = 1200              # 单条语料纳入索引的正文上限（Token 控制）

    @classmethod
    def build_corpus(cls):
        """读取 knowledgebase 全部文档，构建 chunk 列表。

        每个 chunk = {'doc_id','title','category','type','text',
        'source','article_code','article_id','tokens'}

        text = title + summary + tags + toc 各级标题 + 正文摘要（截断）

        Returns:
            chunk 列表（list[dict]）
        """
        chunks = []
        for doc in Document.objects.filter(collection=cls.SOURCE_COLLECTION):
            data = doc.data or {}
            doc_id = doc.doc_id or str(doc.pk)
            title = du.to_text(data.get('title')) or du.to_text(data.get('name'))
            summary = du.to_text(data.get('summary')) or du.to_text(data.get('description'))
            category = du.to_text(data.get('category')) or du.to_text(data.get('subject'))
            doc_type = du.to_text(data.get('type'))

            # 溯源字段：区分知识库原生条目与「由文章加入」的条目
            article_code = du.to_text(data.get('articleCode')) or ac.parse_kb_art_doc_id(doc_id)
            source = du.to_text(data.get('source')) or ('article' if article_code else 'knowledgebase')
            article_id = du.to_text(data.get('articleId'))

            # 提取 toc（目录）各级标题
            toc_titles = []
            toc = data.get('toc') or data.get('chapters') or data.get('contents') or []
            if isinstance(toc, list):
                for item in toc:
                    if isinstance(item, dict):
                        t = du.to_text(item.get('title')) or du.to_text(item.get('name'))
                        if t:
                            toc_titles.append(t)
                    elif isinstance(item, str) and item.strip():
                        toc_titles.append(item.strip())

            # 标签
            tags = data.get('tags')
            tags_text = ' '.join(
                du.to_text(t) for t in tags if du.to_text(t)
            ) if isinstance(tags, list) else du.to_text(tags)

            # 正文摘要（截断，控制索引体量与 Token 成本）
            content = du.to_text(data.get('content'))
            if len(content) > cls.CONTENT_MAX_CHARS:
                content = content[:cls.CONTENT_MAX_CHARS]

            text_parts = [p for p in (title, summary, tags_text, ' '.join(toc_titles), content) if p]
            text = '\n'.join(text_parts)

            chunks.append({
                'doc_id': doc_id,
                'title': title,
                'category': category,
                'type': doc_type,
                'text': text,
                'source': source,
                'article_code': article_code or '',
                'article_id': article_id or '',
                'tokens': cls.tokenize(text),
            })
        return chunks

    @classmethod
    def tokenize(cls, text):
        """纯 Python 中文分词。

        正则提取中文 [\\u4e00-\\u9fa5]{2,} 并做 2-gram，追加 [a-zA-Z0-9]+
        英文/数字单词（全部小写），最后去除停用词。

        Args:
            text: 待分词文本

        Returns:
            token 列表（list[str]）
        """
        if not text or not isinstance(text, str):
            return []
        lower_text = text.lower()
        tokens = []

        # 中文 2-gram
        for segment in re.findall(r'[\u4e00-\u9fa5]{2,}', lower_text):
            if len(segment) == 2:
                tokens.append(segment)
            else:
                for i in range(len(segment) - 1):
                    tokens.append(segment[i:i + 2])

        # 英文 / 数字单词
        for word in re.findall(r'[a-zA-Z0-9]+', lower_text):
            tokens.append(word)

        return [t for t in tokens if t not in _STOPWORDS]

    @classmethod
    def retrieve(cls, question, top_k=None):
        """TF-IDF 简化打分（零依赖）。

        返回 [{'doc_id','title','text','score'}]，按 score 降序，
        score < MIN_SCORE 的过滤掉。语料为空时返回 []。

        Args:
            question: 用户问题
            top_k: 返回条数上限（默认 cls.TOP_K）

        Returns:
            检索结果列表
        """
        top_k = top_k or cls.TOP_K
        corpus = cls.build_corpus()
        if not corpus:
            return []

        query_tokens = cls.tokenize(question or '')
        if not query_tokens:
            return []

        # 文档频率 DF
        n = len(corpus)
        df = {}
        for chunk in corpus:
            for token in set(chunk['tokens']):
                df[token] = df.get(token, 0) + 1

        def idf(token):
            return math.log((n + 1) / (df.get(token, 0) + 1)) + 1.0

        # 查询向量 TF-IDF
        query_tf = {}
        for token in query_tokens:
            query_tf[token] = query_tf.get(token, 0) + 1
        query_vec = {t: (1 + math.log(c)) * idf(t) for t, c in query_tf.items()}
        query_norm = math.sqrt(sum(v * v for v in query_vec.values())) or 1.0

        results = []
        for chunk in corpus:
            tokens = chunk.get('tokens') or []
            if not tokens:
                continue
            doc_tf = {}
            for token in tokens:
                doc_tf[token] = doc_tf.get(token, 0) + 1

            dot = 0.0
            doc_norm_sq = 0.0
            for token, count in doc_tf.items():
                weight = (1 + math.log(count)) * idf(token)
                doc_norm_sq += weight * weight
                if token in query_vec:
                    dot += weight * query_vec[token]
            doc_norm = math.sqrt(doc_norm_sq) or 1.0

            score = dot / (query_norm * doc_norm)
            if score >= cls.MIN_SCORE:
                results.append({
                    'doc_id': chunk['doc_id'],
                    'title': chunk['title'],
                    'text': chunk['text'],
                    'score': round(score, 6),
                    # 溯源：来源类型 / 文章编码 / 文章 ID（非文章条目为空）
                    'source': chunk.get('source', 'knowledgebase'),
                    'article_code': chunk.get('article_code', ''),
                    'article_id': chunk.get('article_id', ''),
                })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

    @classmethod
    def ask(cls, question):
        """知识库问答主入口（同步）。

        1) 归一化问题 → compute_hash(['kb', q_norm])
        2) 查缓存
        3) 命中 → 直接返回（cached=True）
        4) 未命中 → retrieve → 构造 prompt → call_llm_with_fallback
        5) 存缓存 → 返回

        Returns:
            {'answer': str, 'sources': [{'doc_id','title'}], 'cached': bool}
        """
        question = question or ''
        # 归一化：strip + 合并多余空白
        q_norm = ' '.join(question.split())
        if not q_norm:
            return {'answer': '请输入你想了解的问题', 'sources': [], 'cached': False}

        content_hash = cls.compute_content_hash('kb', q_norm)

        # 检查缓存
        cached = cls.get_cache(cls.COLLECTION, content_hash, 'answer')
        if cached and isinstance(cached, dict) and cached.get('answer'):
            return {
                'answer': cached.get('answer'),
                'sources': cached.get('sources', []),
                'cached': True,
            }

        # 检索
        results = cls.retrieve(q_norm)
        if not results:
            return {
                'answer': '知识库中暂未找到相关内容，你可以换个说法再试试，'
                          '或联系客服获取帮助。',
                'sources': [],
                'cached': False,
            }

        sources = [
            {
                'doc_id': r['doc_id'],
                'title': r['title'],
                'source': r.get('source', 'knowledgebase'),
                'article_code': r.get('article_code', ''),
                'article_id': r.get('article_id', ''),
            }
            for r in results
        ]
        contexts = [{'title': r['title'], 'text': r['text']} for r in results]

        model_config = cls.get_model_config('kb_qa')
        if not model_config.get('enabled', True):
            return {
                'answer': '知识库问答功能未启用，请联系管理员开启。',
                'sources': sources,
                'cached': False,
            }

        system_prompt = PromptBuilder.build_system_prompt('kb_qa')
        user_prompt = PromptBuilder.build_kb_qa_prompt(q_norm, contexts)
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        content, err = cls.call_llm_with_fallback(
            messages, model_tier=model_config.get('tier', 'standard'))
        if err and not content:
            return {
                'answer': 'AI 服务暂时不可用：%s' % err,
                'sources': sources,
                'cached': False,
            }

        result = {'answer': content, 'sources': sources}
        # 确保缓存文档存在后写入缓存
        Document.objects.get_or_create(
            collection=cls.COLLECTION, doc_id=content_hash, defaults={'data': {}})
        cls.set_cache(cls.COLLECTION, content_hash, 'answer', result, content_hash)

        return {'answer': content, 'sources': sources, 'cached': False}

    # ---- 索引统计 / 构建 ----

    @classmethod
    def _corpus_counts(cls):
        """统计语料构成（不清算 token，供统计接口使用）。"""
        total = 0
        article_count = 0
        for doc in Document.objects.filter(collection=cls.SOURCE_COLLECTION).only('doc_id', 'data'):
            total += 1
            data = doc.data or {}
            code = du.to_text(data.get('articleCode')) or ac.parse_kb_art_doc_id(doc.doc_id or '')
            source = du.to_text(data.get('source')) or ('article' if code else 'knowledgebase')
            if source == 'article' and code:
                article_count += 1
        return {
            'corpus_size': total,
            'article_count': article_count,
            'kb_count': total - article_count,
        }

    @classmethod
    def invalidate_answer_cache(cls):
        """清空知识库问答缓存（语料变更后调用，避免旧答案与新语料不一致）。"""
        deleted, _ = Document.objects.filter(collection=cls.COLLECTION).delete()
        return deleted

    @classmethod
    def rebuild_index(cls):
        """重建知识库 RAG 索引。

        1) 清空 ai_kb_answers 问答缓存（语料快照变化后旧答案可能失真）
        2) 重新构建语料并记录索引元数据（ai_kb_index / 'status'）
        3) 返回语料构成与已纳入索引的文章编码清单（可追溯）

        Returns:
            {'cleared','corpus_size','kb_count','article_count',
             'article_codes','built_at'}
        """
        cleared = cls.invalidate_answer_cache()

        chunks = cls.build_corpus()
        article_chunks = [c for c in chunks if c.get('source') == 'article' and c.get('article_code')]
        article_codes = sorted({c['article_code'] for c in article_chunks})

        meta = {
            'built_at': timezone.now().isoformat(),
            'corpus_size': len(chunks),
            'kb_count': len(chunks) - len(article_chunks),
            'article_count': len(article_chunks),
            'article_codes': article_codes,
        }
        Document.objects.update_or_create(
            collection=cls.INDEX_META_COLLECTION,
            doc_id=cls.INDEX_META_DOC_ID,
            defaults={'data': meta},
        )

        return {
            'cleared': cleared,
            'corpus_size': meta['corpus_size'],
            'kb_count': meta['kb_count'],
            'article_count': meta['article_count'],
            'article_codes': article_codes,
            'built_at': meta['built_at'],
        }

    @classmethod
    def get_stats(cls):
        """返回索引统计。

        Returns:
            {'corpus_size','kb_count','article_count','cache_count','last_built_at'}
        """
        counts = cls._corpus_counts()
        meta_doc = Document.objects.filter(
            collection=cls.INDEX_META_COLLECTION, doc_id=cls.INDEX_META_DOC_ID).first()
        meta = (meta_doc.data if meta_doc else {}) or {}
        counts.update({
            'cache_count': Document.objects.filter(collection=cls.COLLECTION).count(),
            'last_built_at': du.to_text(meta.get('built_at')),
        })
        return counts

    # ---- 文章 ↔ 索引 的双向可追溯 ----

    @classmethod
    def get_indexed_articles(cls):
        """列出当前已纳入索引的文章条目（由知识库文档反查）。

        Returns:
            [{'article_code','article_id','kb_doc_id','title','indexed_at'}]
            按文章编码升序
        """
        items = []
        for doc in Document.objects.filter(collection=cls.SOURCE_COLLECTION).order_by('pk'):
            data = doc.data or {}
            doc_id = doc.doc_id or str(doc.pk)
            code = du.to_text(data.get('articleCode')) or ac.parse_kb_art_doc_id(doc_id)
            source = du.to_text(data.get('source')) or ('article' if code else '')
            if source != 'article' or not code:
                continue
            items.append({
                'article_code': code,
                'article_id': du.to_text(data.get('articleId')),
                'kb_doc_id': doc_id,
                'title': du.to_text(data.get('title')),
                'indexed_at': du.to_text(data.get('indexedAt')),
            })
        items.sort(key=lambda x: x['article_code'])
        return items

    @classmethod
    def add_article_to_index(cls, article_doc, operator=''):
        """把一篇文章加入知识库索引（幂等）。

        - 文章缺失编码时自动补码（复用 article_code 规则）
        - 生成/更新知识库文档 ``_id = KB_ART_<编码>``，携带
          ``source='article'`` / ``articleCode`` / ``articleId`` 溯源字段
        - 语料变化后清空问答缓存

        Args:
            article_doc: articles 集合的 core.Document
            operator:    操作人标识（写入 indexedBy，便于审计）

        Returns:
            ``{'kb_doc_id','article_code','article_id','created','title'}``
            或 ``{'error': 原因}``
        """
        if article_doc is None:
            return {'error': '文章不存在'}

        code = ac.assign_article_code(article_doc)
        if not ac.is_valid_article_code(code):
            return {'error': '文章编码生成失败'}

        data = article_doc.data or {}
        article_id = article_doc.doc_id or str(article_doc.pk)
        kb_doc_id = ac.kb_doc_id_for_code(code)
        title = du.to_text(data.get('title'))
        summary = du.to_text(data.get('summary'))
        content = du.to_text(data.get('content'))
        tags = data.get('tags') if isinstance(data.get('tags'), list) else []

        payload = {
            'title': title,
            'type': 'article',
            'category': '文章',
            'summary': summary or content[:120],
            'content': content,
            'tags': tags,
            'pages': max(1, (len(content) + 499) // 500),
            'sortWeight': 60,
            # ---- 溯源字段 ----
            'source': 'article',
            'articleCode': code,
            'articleId': article_id,
            'articleStatus': du.to_text(data.get('status')),
            'indexedAt': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
            'indexedBy': du.to_text(operator),
        }

        _, created = Document.objects.update_or_create(
            collection=cls.SOURCE_COLLECTION, doc_id=kb_doc_id,
            defaults={'data': payload},
        )
        cls.invalidate_answer_cache()
        return {
            'kb_doc_id': kb_doc_id,
            'article_code': code,
            'article_id': article_id,
            'created': created,
            'title': title,
        }

    @classmethod
    def remove_article_from_index(cls, article_doc):
        """把一篇文章从知识库索引中移除（幂等）。

        Returns:
            ``{'removed': n, 'article_code': code, 'kb_doc_id': id}``
        """
        if article_doc is None:
            return {'removed': 0, 'article_code': '', 'kb_doc_id': ''}
        code = ac.article_code_of(article_doc)
        if not code:
            return {'removed': 0, 'article_code': '', 'kb_doc_id': ''}
        kb_doc_id = ac.kb_doc_id_for_code(code)
        deleted, _ = Document.objects.filter(
            collection=cls.SOURCE_COLLECTION, doc_id=kb_doc_id).delete()
        if deleted:
            cls.invalidate_answer_cache()
        return {'removed': deleted, 'article_code': code, 'kb_doc_id': kb_doc_id or ''}

    @classmethod
    def indexed_article_codes(cls):
        """返回当前已纳入索引的文章编码集合（便于前端标记已加入状态）。"""
        return {item['article_code'] for item in cls.get_indexed_articles()}


class AutoTagService(AIServiceBase):
    """题目自动标签推荐服务。

    - suggest_tags：为单题推荐标签（优先复用 ai_analysis.suggested_tags）
    - suggest_batch：批量推荐（可异步）
    - apply_tags：按名称应用标签到 Tag / QuestionTag 并同步 doc.data['tag_ids']
    """

    SERVICE_NAME = 'auto_tag'
    BATCH_SIZE = 10
    DEFAULT_CATEGORY = 'knowledge'

    @classmethod
    def _valid_category(cls, category):
        """把标签分类规整为合法的 Tag.CATEGORY_CHOICES 取值。"""
        from .models import Tag
        valid = {c for c, _ in Tag.CATEGORY_CHOICES}
        category = du.to_text(category).strip()
        return category if category in valid else cls.DEFAULT_CATEGORY

    @classmethod
    def _normalize_tags(cls, tags):
        """把 LLM 返回的标签列表规整为 [{name, category, confidence}]。"""
        normalized = []
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, dict):
                    name = du.to_text(tag.get('name')).strip()
                    if not name:
                        continue
                    try:
                        confidence = float(tag.get('confidence', 0.8))
                    except (ValueError, TypeError):
                        confidence = 0.8
                    normalized.append({
                        'name': name,
                        'category': cls._valid_category(tag.get('category')),
                        'confidence': confidence,
                    })
                elif isinstance(tag, str) and tag.strip():
                    normalized.append({
                        'name': tag.strip(),
                        'category': cls.DEFAULT_CATEGORY,
                        'confidence': 0.8,
                    })
        return normalized

    @classmethod
    def suggest_tags(cls, question_doc):
        """为单题推荐标签。

        优先复用 question_doc.data['ai_analysis']['suggested_tags']，
        无则调用 LLM（build_auto_tag_prompt）。

        Returns:
            {'question_id': str, 'suggested_tags': [{'name','category','confidence'}],
             'source': 'cache'|'ai'}
        """
        data = question_doc.data or {}
        qid = question_doc.doc_id or str(question_doc.pk)

        # 1. 优先复用已有 AI 解析结果
        ai_analysis = data.get('ai_analysis') or {}
        cached_tags = ai_analysis.get('suggested_tags') if isinstance(ai_analysis, dict) else None
        normalized = cls._normalize_tags(cached_tags)
        if normalized:
            return {'question_id': qid, 'suggested_tags': normalized, 'source': 'cache'}

        # 2. 调用 LLM
        model_config = cls.get_model_config('auto_tag')
        if not model_config.get('enabled', True):
            return {'question_id': qid, 'suggested_tags': [], 'source': 'ai',
                    'error': '自动标签功能未启用'}

        content_md = du.to_text(data.get('content_md')) or du.to_text(data.get('title'))
        qtype = du.to_text(data.get('qtype'))
        title = du.to_text(data.get('title')) or content_md[:50]

        system_prompt = PromptBuilder.build_system_prompt('auto_tag')
        user_prompt = PromptBuilder.build_auto_tag_prompt(title, content_md, qtype)
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        content, err = cls.call_llm_with_fallback(
            messages, model_tier=model_config.get('tier', 'standard'))
        if err and not content:
            return {'question_id': qid, 'suggested_tags': [], 'source': 'ai',
                    'error': 'AI 推荐失败：%s' % err}

        result = PromptBuilder.parse_json_response(content)
        tags = None
        if isinstance(result, dict):
            tags = result.get('suggested_tags')
            if tags is None:
                tags = result.get('tags')
        elif isinstance(result, list):
            tags = result

        return {'question_id': qid, 'suggested_tags': cls._normalize_tags(tags), 'source': 'ai'}

    @classmethod
    def suggest_batch(cls, question_ids, job_id=None):
        """批量推荐标签（10 题/批）。

        有 job_id 时写入 AIJobManager 进度并返回 job_id；
        否则同步返回 {'items': [...], 'total': n}。
        """
        question_ids = question_ids or []
        total = len(question_ids)

        if job_id is not None:
            AIJobManager.update(job_id, progress=0, progress_text='开始批量推荐标签',
                                status=AIJobManager.STATUS_RUNNING)
            items = []
            processed = 0
            guard = JobTimeoutGuard(job_id)
            for start in range(0, total, cls.BATCH_SIZE):
                if guard.exceeded():
                    logger.warning('AutoTag batch timeout after %ds, processed %d/%d',
                                   int(guard.elapsed()), processed, total)
                    AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                        error='批量标签推荐超时（%ds），已完成 %d/%d 题'
                                              % (int(guard.elapsed()), processed, total),
                                        progress_text='推荐超时')
                    break
                batch = question_ids[start:start + cls.BATCH_SIZE]
                for qid in batch:
                    doc = cls._find_question_doc(qid)
                    if doc:
                        items.append(cls.suggest_tags(doc))
                    else:
                        items.append({'question_id': str(qid), 'suggested_tags': [],
                                      'source': 'ai', 'error': '题目不存在'})
                processed += len(batch)
                progress = int(processed / total * 100) if total else 100
                AIJobManager.update(job_id, progress=progress,
                                    progress_text='已推荐 %d/%d 题' % (processed, total))
            AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS, progress=100,
                                progress_text='批量标签推荐完成',
                                result={'items': items, 'total': total})
            return job_id

        items = []
        for qid in question_ids:
            doc = cls._find_question_doc(qid)
            if doc:
                items.append(cls.suggest_tags(doc))
            else:
                items.append({'question_id': str(qid), 'suggested_tags': [],
                              'source': 'ai', 'error': '题目不存在'})
        return {'items': items, 'total': total}

    @classmethod
    def apply_tags(cls, question_id, tag_names):
        """按名称应用标签。

        - 对每个 name，在 Tag 表按 name 查（同 category 优先）；
          不存在则以 category='knowledge' 创建
        - 写 QuestionTag 绑定（unique_together）+ 同步 doc.data['tag_ids']

        Returns:
            {'applied': n, 'tag_ids': [...]}
        """
        from .models import QuestionTag, Tag

        question = cls._find_question_doc(question_id)
        if not question:
            return {'applied': 0, 'tag_ids': [], 'error': '题目不存在'}

        if not isinstance(tag_names, list):
            tag_names = []

        for raw in tag_names:
            if isinstance(raw, dict):
                name = du.to_text(raw.get('name')).strip()
                category = cls._valid_category(raw.get('category'))
            else:
                name = du.to_text(raw).strip()
                category = cls.DEFAULT_CATEGORY
            if not name:
                continue
            # 同 category 优先
            tag = Tag.objects.filter(name=name, category=category).first()
            if not tag:
                # 退而求其次：同名任意分类
                tag = Tag.objects.filter(name=name).first()
            if not tag:
                tag = Tag.objects.create(name=name, category=category)
            QuestionTag.objects.get_or_create(question=question, tag=tag)

        # 同步 doc.data['tag_ids']
        ids = sorted(question.tag_bindings.values_list('tag_id', flat=True))
        data = dict(question.data)
        data['tag_ids'] = ids
        question.data = data
        question.save(update_fields=['data'])

        return {'applied': len(ids), 'tag_ids': ids}

    # ---- AI 标签与标签管理联动 ----

    @classmethod
    def sync_tags_to_db(cls, tags):
        """将 AI 推荐标签同步到 Tag 表（不存在则创建）。

        对每个推荐标签：
        1. 按 name + category 精确匹配；命中 → 复用
        2. 按 name 任意 category 模糊匹配；命中 → 复用
        3. 都未命中 → 创建新 Tag（category 取推荐值或默认 knowledge）

        Args:
            tags: 规整后的标签列表 [{name, category, confidence}]

        Returns:
            list[dict]，每项含 {tag_id, name, category, is_new, confidence}
        """
        from .models import Tag

        result = []
        for tag_info in tags:
            name = tag_info.get('name', '').strip()
            if not name:
                continue
            category = cls._valid_category(tag_info.get('category'))
            confidence = tag_info.get('confidence', 0.8)

            # 1. 同名同分类精确匹配
            tag = Tag.objects.filter(name=name, category=category).first()
            is_new = False
            if not tag:
                # 2. 同名任意分类
                tag = Tag.objects.filter(name=name).first()
            if not tag:
                # 3. 创建新标签
                tag = Tag.objects.create(
                    name=name, category=category,
                    description='AI 自动识别',
                )
                is_new = True
                logger.info('AutoTag sync: created new Tag #%d "%s" (%s)', tag.pk, name, category)

            result.append({
                'tag_id': tag.pk,
                'name': tag.name,
                'category': tag.category,
                'is_new': is_new,
                'confidence': confidence,
            })
        return result

    @classmethod
    def auto_tag_sync(cls, question_doc, auto_bind=True):
        """AI 标签推荐 + 自动同步到标签管理 + 可选自动绑定。

        完整联动流程：
        1. 调用 suggest_tags 获取 AI 推荐标签
        2. sync_tags_to_db 同步到 Tag 表（不存在则创建）
        3. （可选）自动绑定到题目 QuestionTag + 同步 tag_ids

        Args:
            question_doc: core.Document (collection='questions')
            auto_bind: 是否自动绑定到题目

        Returns:
            {
                'question_id': str,
                'suggested_tags': [...],      # 原始推荐
                'synced_tags': [...],         # 同步后的标签（含 tag_id, is_new）
                'bound': bool,                # 是否已绑定
                'tag_ids': [...],             # 绑定后的 tag_id 列表
                'source': 'cache'|'ai',
            }
        """
        from .models import QuestionTag

        # 1. AI 推荐
        suggest_result = cls.suggest_tags(question_doc)
        if suggest_result.get('error'):
            return suggest_result

        suggested_tags = suggest_result.get('suggested_tags', [])

        # 2. 同步到 Tag 表
        synced = cls.sync_tags_to_db(suggested_tags)

        result = {
            'question_id': suggest_result.get('question_id', ''),
            'suggested_tags': suggested_tags,
            'synced_tags': synced,
            'source': suggest_result.get('source', 'ai'),
            'bound': False,
            'tag_ids': [],
        }

        # 3. 自动绑定
        if auto_bind and synced:
            qid = question_doc.doc_id or str(question_doc.pk)
            for item in synced:
                tag = None
                try:
                    from .models import Tag
                    tag = Tag.objects.get(pk=item['tag_id'])
                except Exception:
                    continue
                if tag:
                    QuestionTag.objects.get_or_create(question=question_doc, tag=tag)

            # 同步 doc.data['tag_ids']
            ids = sorted(question_doc.tag_bindings.values_list('tag_id', flat=True))
            data = dict(question_doc.data or {})
            data['tag_ids'] = ids
            question_doc.data = data
            question_doc.save(update_fields=['data'])

            result['bound'] = True
            result['tag_ids'] = ids

        return result

    @classmethod
    def _auto_tag_sync_batch_impl(cls, question_ids, job_id=None, auto_bind=True):
        """批量 AI 标签推荐 + 自动同步 + 自动绑定（内部实现）。

        Args:
            question_ids: 题目 ID 列表
            job_id: AI 任务 ID（异步模式）
            auto_bind: 是否自动绑定到题目
        """
        question_ids = question_ids or []
        total = len(question_ids)

        if job_id is not None:
            AIJobManager.update(job_id, progress=0, progress_text='开始批量AI标签同步',
                                status=AIJobManager.STATUS_RUNNING)
            items = []
            processed = 0
            total_new_tags = 0
            guard = JobTimeoutGuard(job_id)
            for start in range(0, total, cls.BATCH_SIZE):
                if guard.exceeded():
                    logger.warning('AutoTag sync batch timeout after %ds, processed %d/%d',
                                   int(guard.elapsed()), processed, total)
                    AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                        error='批量标签同步超时（%ds），已完成 %d/%d 题'
                                              % (int(guard.elapsed()), processed, total),
                                        progress_text='同步超时')
                    break
                batch = question_ids[start:start + cls.BATCH_SIZE]
                for qid in batch:
                    doc = cls._find_question_doc(qid)
                    if doc:
                        sync_result = cls.auto_tag_sync(doc, auto_bind=auto_bind)
                        new_count = sum(1 for t in sync_result.get('synced_tags', []) if t.get('is_new'))
                        total_new_tags += new_count
                        items.append({
                            'question_id': sync_result.get('question_id', str(qid)),
                            'synced_count': len(sync_result.get('synced_tags', [])),
                            'new_tag_count': new_count,
                            'bound': sync_result.get('bound', False),
                            'tag_ids': sync_result.get('tag_ids', []),
                        })
                    else:
                        items.append({'question_id': str(qid), 'error': '题目不存在',
                                      'synced_count': 0, 'new_tag_count': 0})
                processed += len(batch)
                progress = int(processed / total * 100) if total else 100
                AIJobManager.update(job_id, progress=progress,
                                    progress_text='已同步 %d/%d 题（新增标签 %d）' % (processed, total, total_new_tags))
            AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS, progress=100,
                                progress_text='批量AI标签同步完成（新增标签 %d）' % total_new_tags,
                                result={'items': items, 'total': total, 'new_tag_count': total_new_tags})
            return job_id

        # 同步模式
        items = []
        for qid in question_ids:
            doc = cls._find_question_doc(qid)
            if doc:
                sync_result = cls.auto_tag_sync(doc, auto_bind=auto_bind)
                items.append(sync_result)
            else:
                items.append({'question_id': str(qid), 'error': '题目不存在'})
        return {'items': items, 'total': total}


class ExcelValidateService(AIServiceBase):
    """Excel 导入智能校验服务。

    分批（BATCH_SIZE 行）调用 LLM 校验导入数据质量并汇总，
    LLM 失败时降级返回基础结构（不抛异常）。
    """

    SERVICE_NAME = 'excel_validate'
    BATCH_SIZE = 20

    @staticmethod
    def _to_int(value, default=0):
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @classmethod
    def _base_result(cls, total):
        """构造基础返回结构（降级 / 空数据时使用）。"""
        return {
            'total': total,
            'valid_count': total,
            'error_count': 0,
            'errors': [],
            'corrections': [],
            'column_mapping': {},
        }

    @classmethod
    def validate_rows(cls, rows, qtype, job_id=None):
        """AI 校验导入数据质量。

        Args:
            rows: list[dict]（每行 = 表头映射后的字典）
            qtype: 题型代码
            job_id: 可选的 AI 任务 ID（异步时写入进度）

        Returns:
            {'total','valid_count','error_count','errors','corrections','column_mapping'}
        """
        rows = rows if isinstance(rows, list) else []
        total = len(rows)

        if total == 0:
            base = cls._base_result(0)
            if job_id:
                AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS, progress=100,
                                    progress_text='无数据需要校验', result=base)
            return base

        if job_id:
            AIJobManager.update(job_id, progress=0, progress_text='开始校验',
                                status=AIJobManager.STATUS_RUNNING)

        errors = []
        corrections = []
        column_mapping = {}
        processed = 0
        guard = JobTimeoutGuard(job_id)

        for start in range(0, total, cls.BATCH_SIZE):
            if guard.exceeded():
                logger.warning('Excel validate timeout after %ds, processed %d/%d',
                               int(guard.elapsed()), processed, total)
                if job_id:
                    AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                        error='Excel 校验超时（%ds），已完成 %d/%d 行'
                                              % (int(guard.elapsed()), processed, total),
                                        progress_text='校验超时')
                break
            batch = rows[start:start + cls.BATCH_SIZE]
            try:
                model_config = cls.get_model_config('excel_validate')
                if not model_config.get('enabled', True):
                    processed += len(batch)
                    continue

                system_prompt = PromptBuilder.build_system_prompt('excel_validate')
                user_prompt = PromptBuilder.build_excel_validate_prompt(batch, qtype)
                messages = [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ]

                content, err = cls.call_llm_with_fallback(
                    messages, model_tier=model_config.get('tier', 'complex'))
                if err and not content:
                    logger.warning('Excel validate batch failed: %s', err)
                else:
                    result = PromptBuilder.parse_json_response(content)
                    if isinstance(result, dict):
                        for e in (result.get('errors') or []):
                            if isinstance(e, dict):
                                level = e.get('level')
                                errors.append({
                                    'row': cls._to_int(e.get('row'), start + 1),
                                    'field': du.to_text(e.get('field')),
                                    'level': level if level in ('error', 'warning') else 'error',
                                    'message': du.to_text(e.get('message')),
                                    'suggestion': du.to_text(e.get('suggestion')),
                                })
                        for c in (result.get('corrections') or []):
                            if isinstance(c, dict):
                                corrections.append({
                                    'row': cls._to_int(c.get('row'), start + 1),
                                    'field': du.to_text(c.get('field')),
                                    'original': du.to_text(c.get('original')),
                                    'corrected': du.to_text(c.get('corrected')),
                                })
                        cm = result.get('column_mapping')
                        if isinstance(cm, dict):
                            column_mapping.update(cm)
            except Exception as e:
                # 任何异常都降级，不向上抛
                logger.error('Excel validate batch error: %s', e)

            processed += len(batch)
            if job_id:
                progress = int(processed / total * 100) if total else 100
                AIJobManager.update(job_id, progress=progress,
                                    progress_text='已校验 %d/%d 行' % (processed, total))

        # 统计错误行（level='error'）
        error_count = 0
        error_rows = set()
        for e in errors:
            if e.get('level') == 'error':
                error_count += 1
                error_rows.add(e.get('row'))
        valid_count = max(0, total - len(error_rows))

        result_out = {
            'total': total,
            'valid_count': valid_count,
            'error_count': error_count,
            'errors': errors,
            'corrections': corrections,
            'column_mapping': column_mapping,
        }

        if job_id:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS, progress=100,
                                progress_text='校验完成', result=result_out)

        return result_out


class LearningReportService(AIServiceBase):
    """用户学习报告服务。

    聚合用户周期内的答题记录，调用 LLM 生成学习报告，
    写入 ai_reports 集合（doc_id='report-{openid}-{type}-{period}'）。
    """

    SERVICE_NAME = 'learning_report'
    COLLECTION = 'ai_reports'
    MIN_RECORDS = 5
    TYPES = ('weekly', 'monthly', 'pre_exam')

    @classmethod
    def _period_range(cls, report_type):
        """返回 (period_key, start_date, end_date) 字符串。

        weekly → 近 7 天（period_key='YYYY-WW'）；
        monthly → 近 30 天（period_key='YYYY-MM'）；
        pre_exam → 近 14 天（period_key='pre-YYYYMMDD'）
        """
        now = timezone.now()
        if report_type == 'monthly':
            start = now - timedelta(days=30)
            period_key = now.strftime('%Y-%m')
        elif report_type == 'pre_exam':
            start = now - timedelta(days=14)
            period_key = 'pre-%s' % now.strftime('%Y%m%d')
        else:  # weekly（默认）
            start = now - timedelta(days=7)
            period_key = now.strftime('%Y-%W')
        return period_key, start.strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')

    @classmethod
    def _period_days(cls, report_type):
        """返回周期天数（用于聚合过滤）。"""
        if report_type == 'monthly':
            return 30
        if report_type == 'pre_exam':
            return 14
        return 7

    @classmethod
    def aggregate(cls, openid, report_type):
        """聚合周期内 historys + notes。

        Returns:
            {'record_count','avg_accuracy','accuracy_trend':[{'date','accuracy'}],
             'subject_stats':{...}, 'wrong_count', 'study_days'}
        """
        if report_type not in cls.TYPES:
            report_type = 'weekly'

        days = cls._period_days(report_type)
        now = timezone.now()
        start_dt = now - timedelta(days=days)

        histories = []
        for doc in Document.objects.filter(
                collection='historys', data___openid=openid).order_by('pk'):
            data = doc.data or {}
            dt = du.parse_datetime(data.get('createTime')) or \
                du.parse_datetime(data.get('time')) or doc.created_at
            if dt and dt >= start_dt:
                histories.append((dt, data))

        histories.sort(key=lambda x: x[0])

        record_count = len(histories)
        accuracies = []
        date_acc = {}
        subject_map = {}
        wrong_count = 0
        study_days = set()
        # 题目查询带缓存（字符串形态下需查题判定对错）
        question_lookup = make_question_lookup()

        for dt, data in histories:
            # items 可能是题目 ID 字符串数组（小程序写入）或对象数组（导入路径）
            items = normalize_history_items(data, question_lookup)
            total_q = len(items)
            right = du.to_number(data.get('rightNum', 0))

            if total_q > 0:
                acc = max(0.0, min(1.0, right / float(total_q)))
                accuracies.append(acc)
                day = dt.date().isoformat()
                date_acc.setdefault(day, []).append(acc)
            study_days.add(dt.date().isoformat())

            subject = du.subject_name(data) or '未分类'
            stat = subject_map.setdefault(subject, {'total': 0, 'correct': 0})
            stat['total'] += total_q
            stat['correct'] += int(right)

            for item in items:
                if not item.get('is_correct'):
                    wrong_count += 1

        avg_accuracy = round(sum(accuracies) / len(accuracies) * 100, 1) if accuracies else 0

        accuracy_trend = []
        for day in sorted(date_acc.keys()):
            vals = date_acc[day]
            accuracy_trend.append({
                'date': day,
                'accuracy': round(sum(vals) / len(vals) * 100, 1),
            })

        subject_stats = {}
        for subject, counts in subject_map.items():
            subject_stats[subject] = {
                'total': counts['total'],
                'correct': counts['correct'],
                'accuracy': round(counts['correct'] / counts['total'] * 100, 1)
                if counts['total'] else 0,
            }

        return {
            'record_count': record_count,
            'avg_accuracy': avg_accuracy,
            'accuracy_trend': accuracy_trend,
            'subject_stats': subject_stats,
            'wrong_count': wrong_count,
            'study_days': len(study_days),
        }

    @classmethod
    def generate(cls, openid, report_type, job_id=None):
        """异步/同步生成学习报告。

        aggregate → LLM → 写入 ai_reports
        （doc_id='report-{openid}-{type}-{period}'）

        Returns:
            报告 dict {'_openid','report_type','period','content_md','summary',
            'highlights','suggestions','generated_at'}
        """
        if report_type not in cls.TYPES:
            report_type = 'weekly'

        period_key, _start_date, _end_date = cls._period_range(report_type)
        doc_id = 'report-%s-%s-%s' % (openid, report_type, period_key)

        if job_id:
            AIJobManager.update(job_id, progress=10, progress_text='正在聚合学习数据',
                                status=AIJobManager.STATUS_RUNNING)

        stats = cls.aggregate(openid, report_type)
        record_count = stats.get('record_count', 0)

        report = {
            '_openid': openid,
            'report_type': report_type,
            'period': period_key,
            'content_md': '',
            'summary': '',
            'highlights': [],
            'suggestions': [],
            'generated_at': timezone.now().isoformat(),
        }

        # 记录不足：返回提示报告
        if record_count < cls.MIN_RECORDS:
            report['summary'] = '报告数据不足'
            report['content_md'] = (
                '当前周期内答题记录不足 %d 条（当前 %d 条），'
                '暂时无法生成完整学习报告。请先完成更多练习。'
                % (cls.MIN_RECORDS, record_count)
            )
            report['suggestions'] = ['每天坚持练习，积累更多答题记录后即可生成报告']
            cls._save_report(doc_id, report)
            if job_id:
                AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS, progress=100,
                                    progress_text='记录不足', result=report)
            return report

        model_config = cls.get_model_config('learning_report')
        if not model_config.get('enabled', True):
            report['summary'] = '学习报告功能未启用'
            report['content_md'] = '学习报告功能未启用，请联系管理员开启。'
            cls._save_report(doc_id, report)
            if job_id:
                AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                    error='学习报告功能未启用', progress_text='功能未启用')
            return report

        if job_id:
            AIJobManager.update(job_id, progress=40, progress_text='正在生成学习报告')

        sanitized_stats = cls.sanitize_for_llm(stats)
        system_prompt = PromptBuilder.build_system_prompt('learning_report')
        user_prompt = PromptBuilder.build_learning_report_prompt(sanitized_stats, report_type)
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        content, err = cls.call_llm_with_fallback(
            messages, model_tier=model_config.get('tier', 'complex'))
        if err and not content:
            report['summary'] = '报告生成失败'
            report['content_md'] = 'AI 生成学习报告失败：%s' % err
            cls._save_report(doc_id, report)
            if job_id:
                AIJobManager.update(job_id, status=AIJobManager.STATUS_FAILED,
                                    error='AI 生成报告失败：%s' % err, progress_text='生成失败')
            return report

        result = PromptBuilder.parse_json_response(content)
        if isinstance(result, dict) and (result.get('content_md') or result.get('summary')):
            inner_md = du.to_text(result.get('content_md'))
            # 安全检查：如果 to_text 返回空但原始 content 是 JSON，尝试直接提取
            if not inner_md and content and content.strip().startswith('{'):
                try:
                    import json as _json
                    _inner = _json.loads(content)
                    inner_md = du.to_text(_inner.get('content_md')) or content
                except (ValueError, TypeError):
                    inner_md = content
            report['content_md'] = inner_md or content
            report['summary'] = du.to_text(result.get('summary'))
            highlights = result.get('highlights')
            report['highlights'] = [du.to_text(h) for h in highlights if du.to_text(h)] \
                if isinstance(highlights, list) else []
            suggestions = result.get('suggestions')
            report['suggestions'] = [du.to_text(s) for s in suggestions if du.to_text(s)] \
                if isinstance(suggestions, list) else []
        else:
            # 解析失败：如果原始内容是 JSON 字符串，尝试二次提取
            if content and content.strip().startswith('{'):
                try:
                    import json as _json
                    _inner = _json.loads(content)
                    if isinstance(_inner, dict):
                        report['content_md'] = du.to_text(_inner.get('content_md')) or content
                        report['summary'] = du.to_text(_inner.get('summary')) or '学习报告'
                        _hl = _inner.get('highlights')
                        if isinstance(_hl, list):
                            report['highlights'] = [du.to_text(h) for h in _hl if du.to_text(h)]
                        _sg = _inner.get('suggestions')
                        if isinstance(_sg, list):
                            report['suggestions'] = [du.to_text(s) for s in _sg if du.to_text(s)]
                    else:
                        report['content_md'] = content
                        report['summary'] = '学习报告'
                except (ValueError, TypeError):
                    report['content_md'] = content
                    report['summary'] = '学习报告'
            else:
                report['content_md'] = content
                report['summary'] = '学习报告'

        report['generated_at'] = timezone.now().isoformat()
        cls._save_report(doc_id, report)

        if job_id:
            AIJobManager.update(job_id, status=AIJobManager.STATUS_SUCCESS, progress=100,
                                progress_text='学习报告生成完成', result=report)

        return report

    @classmethod
    def get_report(cls, openid, report_type='weekly'):
        """读取该用户该类型最新一份报告。

        Returns:
            报告 dict 或 None
        """
        if report_type not in cls.TYPES:
            report_type = 'weekly'
        doc = Document.objects.filter(
            collection=cls.COLLECTION,
            data___openid=openid,
            data__report_type=report_type,
        ).order_by('-pk').first()
        if not doc:
            return None
        report = dict(doc.data or {})
        report['_id'] = doc.doc_id if doc.doc_id else str(doc.pk)
        return report

    @classmethod
    def _save_report(cls, doc_id, report):
        """写入报告到 ai_reports collection。"""
        Document.objects.update_or_create(
            collection=cls.COLLECTION,
            doc_id=doc_id,
            defaults={'data': report},
        )


class CustomerService(AIServiceBase):
    """智能客服 / 答疑服务（无持久化）。

    system prompt 注入平台规则（app_config doc_id='rules'）与知识库 top3 摘要，
    结合最近 6 条对话历史实时回答，并返回 3 条推荐追问。
    """

    SERVICE_NAME = 'cs_chat'
    MAX_HISTORY = 6

    # 内置默认 FAQ（app_config 读不到时使用）
    DEFAULT_FAQ = (
        '常见问题：\n'
        '1. 如何开始练习？—— 进入「题库」选择科目/章节，点击「开始练习」即可。\n'
        '2. 错题怎么复习？—— 在「错题本」中查看错题，系统会按遗忘曲线推荐复习。\n'
        '3. 如何查看学习报告？—— 进入「我的-学习报告」，可查看周报、月报与考前报告。\n'
        '4. 账号问题？—— 如遇登录或账号异常，请通过意见反馈提交，我们会尽快处理。'
    )

    @classmethod
    def _load_faq(cls):
        """从 app_config doc_id='rules' 读取平台规则文本（读不到用内置默认 FAQ）。"""
        doc = Document.objects.filter(collection='app_config', doc_id='rules').first()
        if doc and doc.data:
            data = doc.data
            for key in ('faq', 'content', 'rules', 'text'):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return cls.DEFAULT_FAQ

    @classmethod
    def _default_suggestions(cls):
        """默认推荐追问。"""
        return ['如何开始练习？', '错题怎么复习？', '如何查看学习报告？']

    @classmethod
    def chat(cls, openid, message, history=None):
        """实时对话（无持久化）。

        Args:
            openid: 用户 openid（暂未用于持久化，保留签名）
            message: 用户消息
            history: [{'role':'user'|'assistant','content':str}]（最多取最近 6 条）

        Returns:
            {'reply': str, 'suggestions': [str]}
        """
        message = (message or '').strip()
        if not message:
            return {'reply': '请输入你的问题，我会尽力解答。', 'suggestions': cls._default_suggestions()}

        # 规整历史（最近 6 条）
        history = history if isinstance(history, list) else []
        recent = []
        for item in history[-cls.MAX_HISTORY:]:
            if not isinstance(item, dict):
                continue
            role = item.get('role')
            content = du.to_text(item.get('content')).strip()
            if role in ('user', 'assistant') and content:
                recent.append({'role': role, 'content': content})

        faq_text = cls._load_faq()

        # 知识库 top3 摘要（失败不影响主流程）
        kb_context = ''
        try:
            results = KnowledgeRAGService.retrieve(message, top_k=3)
            kb_lines = []
            for r in results:
                snippet = du.to_text(r.get('text'))[:200]
                kb_lines.append('- %s：%s' % (r.get('title', ''), snippet))
            kb_context = '\n'.join(kb_lines)
        except Exception as e:
            logger.warning('CS chat kb retrieve failed: %s', e)
            kb_context = ''

        model_config = cls.get_model_config('cs_chat')
        if not model_config.get('enabled', True):
            return {'reply': '智能客服功能未启用，请联系管理员。',
                    'suggestions': cls._default_suggestions()}

        system_prompt = PromptBuilder.build_system_prompt('cs_chat')
        # system 含 FAQ + 知识库 top3 摘要
        system_content = system_prompt + '\n\n【平台规则】\n' + faq_text
        if kb_context:
            system_content += '\n\n【知识库参考】\n' + kb_context

        messages = [{'role': 'system', 'content': system_content}]
        messages.extend(recent)
        messages.append({
            'role': 'user',
            'content': PromptBuilder.build_cs_chat_prompt(message, faq_text, kb_context),
        })

        content, err = cls.call_llm_with_fallback(
            messages, model_tier=model_config.get('tier', 'standard'))
        if err and not content:
            return {'reply': '抱歉，智能客服暂时无法回答，请稍后再试。',
                    'suggestions': cls._default_suggestions()}

        # 解析 JSON；解析失败则把原始文本当作回复
        result = PromptBuilder.parse_json_response(content)
        reply = ''
        suggestions = []
        if isinstance(result, dict) and result.get('reply'):
            reply = du.to_text(result.get('reply'))
            raw_suggestions = result.get('suggestions')
            if isinstance(raw_suggestions, list):
                for s in raw_suggestions:
                    text = du.to_text(s).strip()
                    if text:
                        suggestions.append(text)
        else:
            reply = content

        if not suggestions:
            suggestions = cls._default_suggestions()

        return {'reply': reply, 'suggestions': suggestions[:3]}
