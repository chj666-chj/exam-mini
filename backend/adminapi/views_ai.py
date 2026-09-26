"""AI 服务层 —— 管理 AI 配置、测试连接与 AI 辅助写作。

所有接口均使用 urllib.request（标准库）调用 LLM，不引入第三方依赖。

接口一览：
- GET/PUT  /api/admin/ai/config/   -> 查询/保存 AI 配置（API Key 脱敏返回）
- POST     /api/admin/ai/test/     -> 测试 LLM 连接
- POST     /api/ai/assist/         -> AI 辅助写作（小程序端，无需 admin 鉴权）
"""
import json
import logging
import threading
import time
import urllib.request
import urllib.error
from urllib.parse import urlparse
import ipaddress

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

from core.models import Document
from . import ai_models
from .ai_usage_logger import AIUsageLogger
from .permissions import require_perms, json_body, get_request_admin
from .responses import ok, fail, ErrorCode

logger = logging.getLogger(__name__)

# 线程局部存储：记录最近一次 _call_llm 的 token 用量
# （异步任务在独立线程中运行，各线程互不干扰）
_llm_call_local = threading.local()


def _get_last_call_usage():
    """获取当前线程最近一次 _call_llm 的 token 用量。

    返回 {prompt_tokens, completion_tokens, total_tokens} 或 None。
    """
    return getattr(_llm_call_local, 'last_usage', None)


def _log_ai_usage(func_name, source='admin', openid='', admin_user='',
                  status='success', model='', error='', job_id=''):
    """记录一次 AI 使用日志（自动从线程局部读取 token 用量与耗时）。

    在 AI view 函数调用 LLM 服务之后调用本函数。
    """
    usage = _get_last_call_usage() or {}
    # 清除线程局部，避免下次误读
    _llm_call_local.last_usage = None
    AIUsageLogger.log(
        func_name=func_name,
        source=source,
        openid=openid or '',
        admin_user=admin_user or '',
        status=status,
        model=model or '',
        tokens_prompt=usage.get('prompt_tokens', 0),
        tokens_completion=usage.get('completion_tokens', 0),
        tokens_total=usage.get('total_tokens', 0),
        duration_ms=int(getattr(_llm_call_local, 'last_duration_ms', 0) or 0),
        error=error,
        job_id=job_id,
    )

# ---- AI 配置读写 ----

_AI_CONFIG_COLLECTION = 'ai_config'
_AI_CONFIG_DOC_ID = 'ai-config'


def _get_ai_config():
    """读取 AI 配置；若不存在则用 settings.AI_CONFIG_DEFAULTS 创建默认配置。"""
    doc = Document.objects.filter(
        collection=_AI_CONFIG_COLLECTION, doc_id=_AI_CONFIG_DOC_ID
    ).first()
    if doc:
        config = dict(doc.data)
        # 确保所有默认字段都存在
        defaults = getattr(settings, 'AI_CONFIG_DEFAULTS', {})
        for key, val in defaults.items():
            if key not in config:
                config[key] = val
        return config, doc
    # 创建默认配置
    defaults = dict(getattr(settings, 'AI_CONFIG_DEFAULTS', {
        'apiUrl': 'https://api.openai.com/v1/chat/completions',
        'apiKey': '',
        'model': 'gpt-4o-mini',
        'systemPrompt': '你是一个专业的备考文章写作助手。',
        'temperature': 0.7,
        'maxTokens': 2000,
        'enabled': False,
    }))
    doc = Document.objects.create(
        collection=_AI_CONFIG_COLLECTION,
        doc_id=_AI_CONFIG_DOC_ID,
        data=defaults,
    )
    return defaults, doc


def _mask_key(key):
    """API Key 脱敏：仅显示后 4 位，前面用 **** 替代。"""
    if not key or not isinstance(key, str):
        return ''
    if len(key) <= 4:
        return '****'
    return '****' + key[-4:]


def _call_llm(config, messages):
    """调用 LLM 接口，返回 (content, error)。

    使用 urllib.request 构建 POST 请求，支持分级超时和错误处理。
    超时按 model_tier 从 settings.AI_LLM_TIMEOUTS 读取，缺省 45s。
    响应体限制在 AI_LLM_MAX_RESPONSE_BYTES 以内，防止 OOM。

    副作用：将 token 用量与调用耗时写入线程局部 _llm_call_local，
    供 _log_ai_usage() 读取记录到 ai_usage_logs。
    """
    # 初始化线程局部：每次调用前清空，错误路径自动为 None
    _llm_call_local.last_usage = None
    _llm_call_local.last_duration_ms = 0
    _llm_call_local._start_ts = time.time()

    api_url = (config.get('apiUrl') or '').strip()
    api_key = (config.get('apiKey') or '').strip()
    model = config.get('model') or 'gpt-4o-mini'
    temperature = float(config.get('temperature') or 0.7)
    max_tokens = int(config.get('maxTokens') or 2000)

    if not api_url:
        return None, 'API 地址未配置'
    if not api_key:
        return None, 'API Key 未配置'

    # 自动补全 URL：如果 URL 不含 /chat/completions 后缀，自动追加
    if not api_url.rstrip('/').endswith('/chat/completions'):
        api_url = api_url.rstrip('/') + '/chat/completions'

    # P0-3b 修复：SSRF 防护 — 校验 URL 协议和目标地址
    parsed = urlparse(api_url)
    if parsed.scheme not in ('http', 'https'):
        return None, 'API 地址协议不合法，仅支持 http/https'
    hostname = parsed.hostname or ''
    if not hostname:
        return None, 'API 地址格式不合法'
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            return None, 'API 地址不允许指向内网'
    except ValueError:
        if hostname.lower() in ('localhost', '0.0.0.0'):
            return None, 'API 地址不允许指向内网'

    payload = json.dumps({
        'model': model,
        'messages': messages,
        'temperature': float(temperature),
        'max_tokens': int(max_tokens),
    }).encode('utf-8')

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            'Authorization': 'Bearer ' + api_key,
            'Content-Type': 'application/json',
        },
        method='POST',
    )

    # 分级超时：从 config 或 settings 读取，优先用 config 中的 _timeout
    timeout = config.get('_timeout')
    if timeout is None:
        tier = config.get('tier', 'standard')
        timeouts = getattr(settings, 'AI_LLM_TIMEOUTS', {})
        timeout = timeouts.get(tier, timeouts.get('default', 45))
    timeout = int(timeout)

    # 响应体大小上限
    max_bytes = getattr(settings, 'AI_LLM_MAX_RESPONSE_BYTES', 10 * 1024 * 1024)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # 分块读取，限制总大小
            chunks = []
            total = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    return None, 'LLM 响应体过大（超过 %d 字节），已中止' % max_bytes
                chunks.append(chunk)
            body = json.loads(b''.join(chunks).decode('utf-8'))

            # 提取 token 用量到线程局部（OpenAI 兼容格式）
            _usage = body.get('usage') or {}
            _llm_call_local.last_usage = {
                'prompt_tokens': int(_usage.get('prompt_tokens', 0) or 0),
                'completion_tokens': int(_usage.get('completion_tokens', 0) or 0),
                'total_tokens': int(_usage.get('total_tokens', 0) or 0),
            }
            _llm_call_local.last_duration_ms = int((time.time() - _llm_call_local._start_ts) * 1000)

            choices = body.get('choices', [])
            if not choices:
                # 有些代理/网关在错误时返回 200 + 空 choices + error 字段
                api_error = body.get('error')
                if api_error:
                    if isinstance(api_error, dict):
                        return None, 'LLM 返回错误：%s' % api_error.get('message', str(api_error))
                    return None, 'LLM 返回错误：%s' % str(api_error)
                return None, 'LLM 返回结果为空（choices 为空）'
            choice = choices[0]
            msg = choice.get('message') or {}
            content = msg.get('content', '')
            finish_reason = choice.get('finish_reason', '')

            # 推理模型兼容：部分模型（如 glm5.2 / deepseek-reasoner）会把思考过程
            # 放在 reasoning 字段而 content 为空。content 为空时回退到 reasoning，
            # 避免推理模型被误判为「空内容」而报错（finish_reason=length 截断时尤其常见）。
            if not content:
                reasoning = msg.get('reasoning') or ''
                if reasoning:
                    content = reasoning

            # content 为 None 时统一转为空字符串
            if content is None:
                content = ''

            if not content:
                # 空内容：根据 finish_reason 给出具体原因
                if finish_reason == 'length':
                    return None, 'LLM 输出被截断（finish_reason=length），max_tokens=%d 可能过小' % max_tokens
                elif finish_reason == 'content_filter':
                    return None, 'LLM 输出被内容过滤（finish_reason=content_filter）'
                elif finish_reason == 'function_call':
                    return None, 'LLM 返回了 function_call 而非文本内容'
                else:
                    return None, 'LLM 返回空内容（finish_reason=%s）' % (finish_reason or 'unknown')

            return content, None
    except urllib.error.HTTPError as e:
        error_msg = 'LLM 接口返回 HTTP %d' % e.code
        try:
            err_body = json.loads(e.read().decode('utf-8'))
            error_msg = err_body.get('error', {}).get('message', error_msg)
        except (ValueError, UnicodeDecodeError):
            pass
        return None, error_msg
    except urllib.error.URLError as e:
        reason = str(e.reason)
        # 区分超时和其他网络错误
        if 'timed out' in reason.lower() or 'timeout' in reason.lower():
            return None, 'LLM 请求超时（%ds）：%s' % (timeout, reason)
        return None, '连接 LLM 接口失败：%s' % reason
    except Exception as e:
        exc_name = type(e).__name__
        if exc_name == 'timeout' or 'timed out' in str(e).lower():
            return None, 'LLM 请求超时（%ds）' % timeout
        return None, '调用 LLM 异常：%s' % str(e)


# tier 级 max_tokens 下限：推理模型 / 长文生成需要更多 token 预算，
# 避免模型条目 maxTokens 过小导致输出被截断（finish_reason=length）。
# 推理模型的 reasoning 会占用 max_tokens 预算，过小则正文被截断。
_TIER_MAX_TOKENS_FLOOR = {'lite': 1000, 'standard': 2000, 'complex': 4000}


def _call_llm_for(messages, model_id=None, openid=None, func_name=None,
                  tier='standard', timeout=None, retry_on_timeout=True):
    """按「模型解析链」选择模型并调用 LLM（分级超时 + tier max_tokens 下限 + 超时重试）。

    优先级：显式 model_id → 功能级配置 → 用户默认 → 全局默认 → 旧版单配置。
    返回 (content, error, model_dict)。

    Args:
        tier:    分级 lite/standard/complex，决定默认超时与 max_tokens 下限
        timeout: 显式超时（秒），覆盖 tier 默认值（适配推理模型长耗时场景）
        retry_on_timeout: 超时/截断时按 ×1.5 递增超时重试一次（给推理模型更多生成时间）
    """
    call_config, model, err = ai_models.resolve_llm_call(
        model_id=model_id, openid=openid, func_name=func_name)
    if err:
        return None, err, None

    # 注入分级超时（_call_llm 读取 tier → settings.AI_LLM_TIMEOUTS）
    call_config['tier'] = tier
    if timeout is not None:
        call_config['_timeout'] = int(timeout)

    # tier 级 max_tokens 下限：complex 功能（文章撰写等）需要 4000 token，
    # 推理模型的 reasoning 会占用 token 预算，过小则正文被截断
    tier_floor = _TIER_MAX_TOKENS_FLOOR.get(tier, 2000)
    try:
        current_max = int(call_config.get('maxTokens') or 2000)
        if current_max < tier_floor:
            call_config['maxTokens'] = tier_floor
    except (TypeError, ValueError):
        call_config['maxTokens'] = tier_floor

    content, err = _call_llm(call_config, messages)
    if content:
        return content, None, model

    # 超时 / 截断时按 ×1.5 递增超时重试一次（给推理模型更多生成时间）
    if retry_on_timeout and err:
        err_str = str(err)
        if ('超时' in err_str or 'timeout' in err_str.lower()
                or '截断' in err_str or 'length' in err_str.lower()):
            base = call_config.get('_timeout') or getattr(
                settings, 'AI_LLM_TIMEOUTS', {}).get(tier, 45)
            call_config['_timeout'] = int(base * 1.5)
            logger.info('LLM retry with timeout %ds (x1.5, tier=%s)',
                        call_config['_timeout'], tier)
            content, err = _call_llm(call_config, messages)
    return content, err, model


def _extract_model_id(body=None, request=None):
    """从请求体或查询串中提取 model_id（兼容 modelId 写法）。"""
    if isinstance(body, dict):
        value = body.get('model_id') or body.get('modelId')
        if value:
            return str(value).strip()
    if request is not None:
        value = request.GET.get('model_id') or request.GET.get('modelId')
        if value:
            return str(value).strip()
    return ''


# ---- 管理端接口 ----

@require_perms('ai.config')
def ai_config_dispatch(request):
    """GET 返回 AI 配置（apiKey 脱敏）/ PUT 保存 AI 配置。"""
    config, doc = _get_ai_config()

    if request.method == 'GET':
        safe_config = dict(config)
        safe_config['apiKey'] = _mask_key(config.get('apiKey', ''))
        # 确保 feature_config 存在并合并默认值
        feature_config = dict(config.get('feature_config') or {})
        defaults = getattr(settings, 'AI_FEATURE_CONFIG_DEFAULTS', {})
        for func_name, default_cfg in defaults.items():
            if func_name not in feature_config:
                feature_config[func_name] = dict(default_cfg)
        safe_config['feature_config'] = feature_config
        return ok(safe_config)

    if request.method == 'PUT':
        body, err = json_body(request)
        if err:
            return err

        new_config = dict(config)
        # 逐字段更新
        for field in ('apiUrl', 'model', 'systemPrompt', 'temperature', 'maxTokens', 'enabled'):
            if field in body:
                new_config[field] = body[field]

        # feature_config 更新（合并而非全量替换）
        if 'feature_config' in body and isinstance(body['feature_config'], dict):
            existing_fc = dict(new_config.get('feature_config') or {})
            for func_name, func_cfg in body['feature_config'].items():
                if isinstance(func_cfg, dict):
                    if func_name in existing_fc and isinstance(existing_fc[func_name], dict):
                        existing_fc[func_name].update(func_cfg)
                    else:
                        existing_fc[func_name] = func_cfg
            new_config['feature_config'] = existing_fc

        # apiKey 特殊处理：若为脱敏格式（以 **** 开头）则保留原值
        if 'apiKey' in body:
            incoming_key = body['apiKey']
            if incoming_key and incoming_key.startswith('****'):
                # 保留原值
                pass
            else:
                new_config['apiKey'] = incoming_key

        doc.data = new_config
        doc.save()

        safe_config = dict(new_config)
        safe_config['apiKey'] = _mask_key(new_config.get('apiKey', ''))
        # 确保 feature_config 在返回中存在
        if 'feature_config' not in safe_config:
            safe_config['feature_config'] = getattr(settings, 'AI_FEATURE_CONFIG_DEFAULTS', {})
        return ok(safe_config, '配置已保存')

    return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET / PUT', http_status=405)


@require_perms('ai.config')
def ai_test(request):
    """POST 发送测试 prompt 到 LLM，返回测试结果。

    请求体可选 ``{model_id}``：指定则测试该模型（无需先启用全局开关），
    未指定则使用全局默认 / 旧版单配置。
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    body, err = json_body(request)
    if err:
        return err
    model_id = _extract_model_id(body, request)

    messages = [
        {'role': 'system', 'content': '你是一个测试助手。'},
        {'role': 'user', 'content': '请回复：连接成功'},
    ]

    if model_id:
        model = ai_models.get_model(model_id)
        if not model:
            return fail(ErrorCode.NOT_FOUND, '模型不存在')
        call_config, cerr = ai_models.build_call_config(model, explicit=True)
        if cerr:
            return fail(ErrorCode.PARAM_ERROR, cerr)
        content, lerr = _call_llm(call_config, messages)
        if lerr:
            return fail(ErrorCode.PARAM_ERROR, '测试失败：%s' % lerr)
        return ok({
            'response': content,
            'model': model.get('model'),
            'name': model.get('name'),
        }, '连接测试成功')

    config, _ = _get_ai_config()
    if not config.get('enabled'):
        return fail(ErrorCode.PARAM_ERROR, 'AI 功能未启用，请先在配置中开启')

    content, lerr = _call_llm(config, messages)
    if lerr:
        return fail(ErrorCode.PARAM_ERROR, '测试失败：%s' % lerr)

    return ok({'response': content}, '连接测试成功')


# ---- 小程序端接口（无需 admin 鉴权，但需 openid 鉴权 + 限流）----

# AI 接口限流（使用 Django cache 后端，生产环境为 Redis，本地为 LocMem）
_AI_RATE_MAX = 10
_AI_RATE_WINDOW = 60  # 秒
_AI_RATE_KEY = 'ai:rate:{openid}'


def _check_ai_rate_limit(openid):
    """检查 AI 接口调用频率，返回 (allowed, error_msg)。

    使用 cache.incr 原子计数器 + TTL 实现固定窗口限流。
    """
    from django.core.cache import cache
    key = _AI_RATE_KEY.format(openid=openid)
    try:
        count = cache.incr(key)
        if count == 1:
            cache.expire(key, _AI_RATE_WINDOW)
        if count > _AI_RATE_MAX:
            return False, 'AI 辅助写作请求过于频繁，请稍后再试'
    except ValueError:
        # key 不存在，首次调用
        cache.set(key, 1, _AI_RATE_WINDOW)
    except Exception:
        # cache 后端异常时降级放行（不因限流故障阻断业务）
        pass
    return True, None


# ---- AI 辅助写作参数校验常量 ----
_AI_ASSIST_ACTIONS = ('generate', 'topic', 'outline', 'title', 'summary', 'image_suggest')
_AI_ASSIST_MAX_PROMPT = 2000      # 主题/正文最大长度（字符）
_AI_ASSIST_MAX_CONTEXT = 4000     # 补充说明最大长度（字符）
# 配置类错误关键词：命中则返回 503（服务未就绪），否则返回 502（上游故障）
_CONFIG_ERR_KEYWORDS = ('未配置', '未启用', '不能为空', '未开启', '不存在或已禁用')


def _is_config_error(err_msg):
    """区分配置/可用性问题（503）与 LLM 上游故障（502）。"""
    if not err_msg:
        return False
    msg = str(err_msg)
    return any(kw in msg for kw in _CONFIG_ERR_KEYWORDS)


@csrf_exempt
def ai_assist(request):
    """POST /api/ai/assist/  AI 辅助写作（小程序端与管理端共用）。

    鉴权：小程序端携带 ``X-Openid``；管理端携带 ``Authorization: Bearer <token>``。
    请求体：{prompt: string, context?: string, action?: string, model_id?: string}
    返回：{content: string, model?: string, model_name?: string}

    错误码语义：
      400 PARAM_ERROR         — 参数缺失/非法（空 prompt、未知 action、超长输入）
      401 UNAUTHORIZED        — 未登录（无 openid 且无有效管理员令牌）
      503 SERVICE_UNAVAILABLE — AI 服务未就绪（功能未启用 / 未配置模型 / 缺 API Key）
      502 BAD_GATEWAY         — LLM 上游故障（超时 / 连接失败 / 上游返回错误）
      500 SERVER_ERROR        — 未预期的服务器内部异常
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    # ---- 双轨鉴权：优先 X-Openid（小程序），回退 Bearer 令牌（管理端）----
    openid = request.headers.get('X-Openid') or ''
    admin_user = None
    admin_name = ''
    source = 'mp'
    if not openid:
        admin_user, auth_err = get_request_admin(request)
        if auth_err:
            return auth_err
        admin_name = getattr(admin_user, 'username', '') or 'admin'
        source = 'admin'

    try:
        # ---- 限流（仅小程序端；管理员不受限）----
        if not admin_user:
            allowed, rate_msg = _check_ai_rate_limit(openid)
            if not allowed:
                return fail(ErrorCode.PARAM_ERROR, rate_msg)

        body, err = json_body(request)
        if err:
            return err

        prompt = (body.get('prompt') or '').strip()
        context = (body.get('context') or '').strip()
        action = (body.get('action') or 'generate').strip().lower()
        if not prompt:
            return fail(ErrorCode.PARAM_ERROR, '请输入文章标题或主题')
        if len(prompt) > _AI_ASSIST_MAX_PROMPT:
            return fail(ErrorCode.PARAM_ERROR,
                        '主题长度不能超过 %d 字' % _AI_ASSIST_MAX_PROMPT)
        if len(context) > _AI_ASSIST_MAX_CONTEXT:
            return fail(ErrorCode.PARAM_ERROR,
                        '补充说明长度不能超过 %d 字' % _AI_ASSIST_MAX_CONTEXT)
        # action 白名单校验（防御非法输入）
        if action not in _AI_ASSIST_ACTIONS:
            return fail(ErrorCode.PARAM_ERROR,
                        '不支持的操作类型「%s」，支持：%s' % (action, '、'.join(_AI_ASSIST_ACTIONS)))

        # ---- 文章增强 —— 非 generate 的 action 路由到 ArticleEnhanceService ----
        if action != 'generate':
            from .ai_services import ArticleEnhanceService
            result = ArticleEnhanceService.assist(prompt, context, action)
            if isinstance(result, dict) and 'error' in result:
                err_msg = result.get('error', '')
                _log_ai_usage('article_enhance', source=source, openid=openid,
                              admin_user=admin_name, status='failed', error=err_msg)
                if _is_config_error(err_msg):
                    return fail(ErrorCode.SERVICE_UNAVAILABLE, err_msg)
                return fail(ErrorCode.BAD_GATEWAY, err_msg)
            _log_ai_usage('article_enhance', source=source, openid=openid,
                          admin_user=admin_name, status='success')
            return ok(result, '生成成功')

        # ---- generate 路径 ----
        config, _ = _get_ai_config()
        if not config.get('enabled'):
            return fail(ErrorCode.SERVICE_UNAVAILABLE,
                        'AI 功能未启用，请联系管理员在后台「AI 配置」中开启')

        system_prompt = config.get('systemPrompt', '你是一个专业的备考文章写作助手。')
        if context:
            user_content = '主题：%s\n补充说明：%s\n\n请根据以上信息撰写一篇结构清晰、内容充实的 Markdown 格式备考文章。' % (prompt, context)
        else:
            user_content = '请根据以下主题撰写一篇结构清晰、内容充实的 Markdown 格式备考文章：\n\n%s' % prompt

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_content},
        ]

        # 支持用户在选择入口指定的模型（model_id）；未指定则走解析链默认。
        # 管理端无 openid，仅解析全局模型；小程序端可命中用户首选模型。
        model_id = _extract_model_id(body)
        # 文章撰写为长文生成（complex 分级）：推理模型（如 glm5.2）的 reasoning
        # 阶段耗时较长，显式 timeout=120s + complex 分级 max_tokens 下限 4000 +
        # 超时重试，确保推理模型有足够时间与 token 预算产出正文。
        content, llm_err, used_model = _call_llm_for(
            messages, model_id=model_id, openid=openid or None,
            func_name='article_enhance', tier='complex', timeout=120)
        if llm_err:
            _log_ai_usage('ai_assist', source=source, openid=openid,
                          admin_user=admin_name, status='failed', error=str(llm_err))
            if _is_config_error(llm_err):
                return fail(ErrorCode.SERVICE_UNAVAILABLE,
                            'AI 服务未就绪：%s' % llm_err)
            return fail(ErrorCode.BAD_GATEWAY, 'AI 生成失败：%s' % llm_err)

        _log_ai_usage('ai_assist', source=source, openid=openid,
                      admin_user=admin_name, status='success',
                      model=(used_model or {}).get('model', ''))
        return ok({
            'content': content,
            'model': (used_model or {}).get('model', ''),
            'model_name': (used_model or {}).get('name', ''),
        }, '生成成功')
    except Exception as e:
        logger.exception('ai_assist 未预期异常: %s', e)
        try:
            _log_ai_usage('ai_assist', source=source, openid=openid,
                          admin_user=admin_name, status='failed',
                          error='服务器内部错误：%s' % e)
        except Exception:
            pass
        return fail(ErrorCode.SERVER_ERROR, 'AI 服务异常，请稍后重试')


# ====================================================================
# AI P0 功能接口 —— 题目解析 / 智能组卷 / 智能判卷 / 任务管理
# ====================================================================

from .responses import paginate, parse_page  # noqa: E402
from .ai_jobs import AIJobManager  # noqa: E402


def _admin_name(request):
    """从 request 中提取管理员用户名（用于日志记录）。"""
    _u = getattr(request, 'admin_user', None)
    return getattr(_u, 'username', '') or ''


# ---- AI 任务管理 ----

@require_perms('ai.job.view')
def ai_job_list(request):
    """GET /api/admin/ai/jobs/  分页返回 AI 任务列表。

    查询参数：page, page_size, status, job_type
    """
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    page, page_size = parse_page(request)
    status = request.GET.get('status', '').strip() or None
    job_type = request.GET.get('job_type', '').strip() or None
    result = AIJobManager.list(status=status, job_type=job_type, page=page, page_size=page_size)
    return ok(result)


@require_perms('ai.job.view')
def ai_job_status(request, job_id):
    """GET /api/admin/ai/jobs/<job_id>/  返回单个任务状态。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    job_data = AIJobManager.get(job_id)
    if not job_data:
        return fail(ErrorCode.NOT_FOUND, '任务不存在')
    return ok(job_data)


@require_perms('ai.job.view')
def ai_job_cancel(request, job_id):
    """POST /api/admin/ai/jobs/<job_id>/cancel/  取消任务。"""
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)
    job_data = AIJobManager.get(job_id)
    if not job_data:
        return fail(ErrorCode.NOT_FOUND, '任务不存在')
    if job_data.get('status') not in ('pending', 'running'):
        return fail(ErrorCode.PARAM_ERROR, '任务已结束，无法取消')
    AIJobManager.cancel(job_id)
    return ok({'job_id': job_id, 'status': 'cancelled'}, '任务已取消')


# ---- AI 题目解析 ----

@require_perms('ai.analyze')
def question_analyze(request, doc_id):
    """POST /api/admin/ai/questions/<doc_id>/analyze/  单题 AI 解析（同步）。

    返回 ai_analysis 结果。
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    from .ai_services import QuestionAnalysisService
    from core.models import Document as Doc

    question_doc = Doc.objects.filter(collection='questions', doc_id=str(doc_id)).first()
    if not question_doc and str(doc_id).isdigit():
        question_doc = Doc.objects.filter(collection='questions', pk=int(doc_id), doc_id=None).first()
    if not question_doc:
        return fail(ErrorCode.NOT_FOUND, '题目不存在')

    result = QuestionAnalysisService.analyze_single(question_doc)

    _admin = getattr(request, 'admin_user', None)
    _admin_name = _admin.username if _admin else ''
    if isinstance(result, dict) and 'error' in result:
        _log_ai_usage('question_analyze', source='admin', admin_user=_admin_name,
                      status='failed', error=result.get('error', ''))
        return fail(ErrorCode.SERVER_ERROR, result['error'])

    _log_ai_usage('question_analyze', source='admin', admin_user=_admin_name, status='success')
    return ok(result, 'AI 解析完成')


@require_perms('ai.analyze')
def question_analyze_batch(request):
    """POST /api/admin/ai/questions/analyze-batch/  批量解析（异步，返回 job_id）。

    请求体：{question_ids: ["id1", "id2", ...]}
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    body, err = json_body(request)
    if err:
        return err

    question_ids = body.get('question_ids')
    if not isinstance(question_ids, list) or not question_ids:
        return fail(ErrorCode.PARAM_ERROR, 'question_ids 不能为空数组')
    if len(question_ids) > 500:
        return fail(ErrorCode.PARAM_ERROR, '单次最多解析 500 道题目')

    from .ai_services import QuestionAnalysisService

    config = {
        'question_ids': question_ids,
        'count': len(question_ids),
    }
    job_id = AIJobManager.create('question_analyze', config)

    def _task(jid):
        QuestionAnalysisService.analyze_batch(question_ids, jid)

    AIJobManager.start(job_id, _task)

    _log_ai_usage('question_analyze', source='admin', admin_user=_admin_name(request),
                  status='pending', job_id=job_id)
    return ok({'job_id': job_id, 'status': 'pending', 'total': len(question_ids)},
              '批量解析任务已创建')


# ---- AI 智能组卷 ----

@require_perms('ai.compose')
def exam_compose(request):
    """POST /api/admin/ai/compose/  智能组卷（异步，返回 job_id）。

    请求体（兼容前端两种命名风格，优先原始字段名，回退前端别名）：
      - examid / subject_id            科目 ID（必填，用于筛选候选题池）
      - qtype_dist / type_dist         题型分布，如 {"single": 10, "multiple": 5}
      - difficulty_dist / difficulty   难度分布，如 {"easy": 30, "medium": 50, "hard": 20}
      - total_score                    总分（默认 100，必须 > 0）
      - count / question_count         题目总数（默认取 qtype_dist 各项之和，必须 > 0）
      - knowledge_points / knowledge_tags  知识点筛选（可选）
      - locked_questions               锁定题目 ID 列表（可选）
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    body, err = json_body(request)
    if err:
        return err

    # ---- 兼容前端两种字段命名 ----
    examid = body.get('examid') or body.get('subject_id') or ''
    if not examid:
        return fail(ErrorCode.PARAM_ERROR, 'examid（或 subject_id）不能为空')

    qtype_dist = body.get('qtype_dist') or body.get('type_dist') or {}
    difficulty_dist = body.get('difficulty_dist') or body.get('difficulty') or {}
    knowledge_points = body.get('knowledge_points') or body.get('knowledge_tags') or []
    locked_questions = body.get('locked_questions') or []

    # count：优先显式传入，否则从 qtype_dist 各项之和自动推断
    count = body.get('count')
    if count is None:
        count = body.get('question_count', 0)
    if not count:
        try:
            count = sum(int(v) for v in qtype_dist.values()) if qtype_dist else 0
        except (TypeError, ValueError):
            return fail(ErrorCode.PARAM_ERROR, 'qtype_dist（或 type_dist）的值必须为数字')

    # total_score
    total_score = body.get('total_score', 100)

    # ---- 参数校验 ----
    try:
        total_score = int(total_score)
    except (TypeError, ValueError):
        return fail(ErrorCode.PARAM_ERROR, 'total_score 必须为整数')
    if total_score <= 0:
        return fail(ErrorCode.PARAM_ERROR, 'total_score 必须大于 0')

    try:
        count = int(count)
    except (TypeError, ValueError):
        return fail(ErrorCode.PARAM_ERROR, 'count 必须为整数')
    if count <= 0:
        return fail(ErrorCode.PARAM_ERROR,
                     '题目总数必须大于 0（请检查 qtype_dist/count 或 type_dist/question_count 参数）')

    # 难度分布总和应为 100（若提供了难度分布）
    if difficulty_dist:
        try:
            diff_sum = sum(int(v) for v in difficulty_dist.values())
        except (TypeError, ValueError):
            return fail(ErrorCode.PARAM_ERROR, 'difficulty_dist（或 difficulty）的值必须为数字')
        if diff_sum != 100:
            return fail(ErrorCode.PARAM_ERROR,
                         '难度比例总和应为 100，当前为 %d' % diff_sum)

    config = {
        'examid': str(examid),
        'qtype_dist': qtype_dist,
        'difficulty_dist': difficulty_dist,
        'total_score': total_score,
        'count': count,
        'knowledge_points': knowledge_points,
        'locked_questions': locked_questions,
    }

    from .ai_services import ExamCompositionService

    job_id = AIJobManager.create('exam_compose', config)

    def _task(jid):
        ExamCompositionService.compose(config, jid)

    AIJobManager.start(job_id, _task)

    _log_ai_usage('exam_compose', source='admin', admin_user=_admin_name(request),
                  status='pending', job_id=job_id)
    return ok({'job_id': job_id, 'status': 'pending'}, '组卷任务已创建')


@require_perms('ai.compose')
def compose_status(request, job_id):
    """GET /api/admin/ai/compose/<job_id>/  组卷状态查询（兼容新旧两种组卷任务）。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    job_data = AIJobManager.get(job_id)
    if not job_data:
        return fail(ErrorCode.NOT_FOUND, '组卷任务不存在')
    job_type = job_data.get('job_type', '')
    if job_type not in ('exam_compose', 'smart_compose'):
        return fail(ErrorCode.PARAM_ERROR, '该任务不是组卷任务')
    return ok(job_data)


@require_perms('ai.compose')
def compose_confirm(request, job_id):
    """POST /api/admin/ai/compose/<job_id>/confirm/  确认组卷结果。

    请求体：{exam_name: "考试名称"}
    返回：{exam_id: "..."}
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    job_data = AIJobManager.get(job_id)
    if not job_data:
        return fail(ErrorCode.NOT_FOUND, '组卷任务不存在')
    if job_data.get('status') != 'success':
        return fail(ErrorCode.PARAM_ERROR, '组卷任务尚未完成或已失败')

    body, err = json_body(request)
    if err:
        return err
    exam_name = (body.get('exam_name') or '').strip()

    # 兼容新旧两种组卷任务的 confirm
    job_type = job_data.get('job_type', 'exam_compose')
    if job_type == 'smart_compose':
        from .smart_compose import SmartComposeService
        exam_id = SmartComposeService.confirm_draft(job_id, exam_name)
    else:
        from .ai_services import ExamCompositionService
        exam_id = ExamCompositionService.confirm_draft(job_id, exam_name)
    if not exam_id:
        return fail(ErrorCode.SERVER_ERROR, '创建考试草稿失败')

    return ok({'exam_id': exam_id}, '组卷结果已确认，考试草稿已创建')


# ---- AI 智能组卷 V2（三阶段定向组卷）----

_COMPOSE_JOB_TYPES = ('exam_compose', 'smart_compose')


@require_perms('ai.compose')
def smart_compose(request):
    """POST /api/admin/ai/smart-compose/  智能组卷 V2（三阶段定向组卷，异步）。

    请求体：
      - exam_type: 考试类型 monthly/midterm/final/mock/custom（默认 final）
      - examid / subject_id: 科目 ID（必填）
      - qtype_dist / type_dist: 题型分布
      - difficulty_dist / difficulty: 难度分布
      - total_score: 总分（默认 100）
      - count / question_count: 题目总数
      - knowledge_points / knowledge_tags: 可选，手动指定知识点
      - use_llm_blueprint: 可选，是否用 LLM 辅助蓝图（默认 true）
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    body, err = json_body(request)
    if err:
        return err

    examid = body.get('examid') or body.get('subject_id') or ''
    if not examid:
        return fail(ErrorCode.PARAM_ERROR, 'examid（或 subject_id）不能为空')

    exam_type = body.get('exam_type', 'final')
    if exam_type not in ('monthly', 'midterm', 'final', 'mock', 'custom'):
        return fail(ErrorCode.PARAM_ERROR,
                     'exam_type 必须是 monthly/midterm/final/mock/custom 之一')

    qtype_dist = body.get('qtype_dist') or body.get('type_dist') or {}
    difficulty_dist = body.get('difficulty_dist') or body.get('difficulty') or {}
    knowledge_points = body.get('knowledge_points') or body.get('knowledge_tags') or []

    count = body.get('count')
    if count is None:
        count = body.get('question_count', 0)
    if not count:
        count = sum(int(v) for v in qtype_dist.values() if v) if qtype_dist else 0
    try:
        count = int(count)
    except (TypeError, ValueError):
        return fail(ErrorCode.PARAM_ERROR, 'count 必须为整数')
    if count <= 0:
        return fail(ErrorCode.PARAM_ERROR, '题目总数必须大于 0')

    total_score = body.get('total_score', 100)
    try:
        total_score = int(total_score)
    except (TypeError, ValueError):
        return fail(ErrorCode.PARAM_ERROR, 'total_score 必须为整数')
    if total_score <= 0:
        return fail(ErrorCode.PARAM_ERROR, 'total_score 必须大于 0')

    config = {
        'exam_type': exam_type,
        'examid': str(examid),
        'qtype_dist': qtype_dist,
        'difficulty_dist': difficulty_dist,
        'total_score': total_score,
        'count': count,
        'knowledge_points': knowledge_points,
        'use_llm_blueprint': body.get('use_llm_blueprint', True),
    }

    from .smart_compose import SmartComposeService

    job_id = AIJobManager.create('smart_compose', config)

    def _task(jid):
        SmartComposeService.compose(config, jid)

    AIJobManager.start(job_id, _task)

    _log_ai_usage('smart_compose', source='admin', admin_user=_admin_name(request),
                  status='pending', job_id=job_id)
    return ok({'job_id': job_id, 'status': 'pending'}, '智能组卷任务已创建')


@require_perms('ai.compose')
def smart_compose_kp_stats(request):
    """GET /api/admin/ai/smart-compose/kp-stats/?examid=<科目ID>
    查询某科目的知识点索引统计（用于前端展示可用知识点）。
    """
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)

    examid = request.GET.get('examid') or request.GET.get('subject_id') or ''
    if not examid:
        return fail(ErrorCode.PARAM_ERROR, 'examid 参数不能为空')

    from .smart_compose import KnowledgePointIndex
    stats = KnowledgePointIndex.get_index_stats(examid)
    return ok(stats)


@require_perms('ai.compose')
def smart_compose_rebuild_index(request):
    """POST /api/admin/ai/smart-compose/rebuild-index/
    手动重建某科目的知识点索引。请求体：{examid: "科目ID"}
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    body, err = json_body(request)
    if err:
        return err

    examid = body.get('examid') or body.get('subject_id') or ''
    if not examid:
        return fail(ErrorCode.PARAM_ERROR, 'examid 不能为空')

    from .smart_compose import KnowledgePointIndex
    kp_count, q_count = KnowledgePointIndex.build_index(examid, force=True)
    return ok({
        'examid': str(examid),
        'kp_count': kp_count,
        'question_count': q_count,
    }, '知识点索引已重建')


# ---- AI 智能判卷 ----

@require_perms('ai.grade')
def ai_grade_batch(request):
    """POST /api/admin/ai/grade-batch/  批量判卷（异步，返回 job_id）。

    请求体：{history_id: "答题记录ID"}
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    body, err = json_body(request)
    if err:
        return err

    history_id = body.get('history_id')
    if not history_id:
        return fail(ErrorCode.PARAM_ERROR, 'history_id 不能为空')

    from .ai_services import GradingService

    config = {'history_id': str(history_id)}
    job_id = AIJobManager.create('ai_grade', config)

    def _task(jid):
        GradingService.grade_batch(str(history_id), jid)

    AIJobManager.start(job_id, _task)

    _log_ai_usage('ai_grade', source='admin', admin_user=_admin_name(request),
                  status='pending', job_id=job_id)
    return ok({'job_id': job_id, 'status': 'pending'}, '批量判卷任务已创建')


@require_perms('ai.grade')
def ai_grade_review_list(request):
    """GET /api/admin/ai/grade/review-list/  待人工复核列表。

    查询 historys 集合中 items[n].ai_grading.human_review.reviewed=false 的记录。
    """
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)

    from core.models import Document as Doc
    from . import data_utils as du

    page, page_size = parse_page(request, default_size=20)

    # 遍历 historys，查找待复核项
    review_items = []
    for doc in Doc.objects.filter(collection='historys').order_by('-pk'):
        data = doc.data or {}
        items = data.get('items', [])
        if not isinstance(items, list):
            continue
        openid = data.get('_openid', '')
        history_id = doc.doc_id or str(doc.pk)
        create_time = du.to_text(data.get('createTime'))

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            ai_grading = item.get('ai_grading')
            if not isinstance(ai_grading, dict):
                continue
            human_review = ai_grading.get('human_review')
            if not isinstance(human_review, dict):
                continue
            if human_review.get('reviewed'):
                continue
            # 需要 reviewed=false 才加入待复核列表
            review_items.append({
                'history_id': history_id,
                'item_index': idx,
                'openid': openid,
                'create_time': create_time,
                'question_id': item.get('questionId') or item.get('qid') or item.get('_id', ''),
                'answer': du.to_text(item.get('answer')) or du.to_text(item.get('userAnswer')),
                'score': ai_grading.get('score'),
                'max_score': ai_grading.get('max_score'),
                'confidence': ai_grading.get('confidence', 0),
                'feedback_md': ai_grading.get('feedback_md', ''),
                'needs_human_review': ai_grading.get('needs_human_review', True),
            })

    total = len(review_items)
    start = (page - 1) * page_size
    end = start + page_size
    return ok(paginate(review_items[start:end], total, page, page_size))


@require_perms('ai.grade')
def ai_grade_review(request, history_id):
    """PUT /api/admin/ai/grade/<history_id>/review/  人工复核。

    请求体：{item_index: int, adjusted_score: number, feedback: string}
    """
    if request.method != 'PUT':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 PUT', http_status=405)

    body, err = json_body(request)
    if err:
        return err

    item_index = body.get('item_index')
    if item_index is None:
        return fail(ErrorCode.PARAM_ERROR, 'item_index 不能为空')
    try:
        item_index = int(item_index)
    except (ValueError, TypeError):
        return fail(ErrorCode.PARAM_ERROR, 'item_index 必须是整数')

    adjusted_score = body.get('adjusted_score')
    feedback = body.get('feedback', '')

    from core.models import Document as Doc

    history_doc = Doc.objects.filter(collection='historys', doc_id=str(history_id)).first()
    if not history_doc and str(history_id).isdigit():
        history_doc = Doc.objects.filter(collection='historys', pk=int(history_id), doc_id=None).first()
    if not history_doc:
        return fail(ErrorCode.NOT_FOUND, '答题记录不存在')

    data = dict(history_doc.data)
    items = data.get('items', [])
    if not isinstance(items, list) or item_index < 0 or item_index >= len(items):
        return fail(ErrorCode.PARAM_ERROR, 'item_index 超出范围')

    item = items[item_index]
    if not isinstance(item, dict):
        return fail(ErrorCode.PARAM_ERROR, '该题目项无效')

    ai_grading = item.get('ai_grading')
    if not isinstance(ai_grading, dict):
        return fail(ErrorCode.PARAM_ERROR, '该题目未经过 AI 判卷')

    # 更新人工复核信息
    ai_grading.setdefault('human_review', {})
    ai_grading['human_review']['reviewed'] = True
    ai_grading['human_review']['adjusted_score'] = adjusted_score
    ai_grading['human_review']['reviewer'] = getattr(request, 'admin_user', None) and \
        request.admin_user.username or ''
    ai_grading['human_review']['reviewed_at'] = _now_iso()
    if feedback:
        ai_grading['human_review']['feedback'] = feedback
    # 如果有调整分数，更新最终分数
    if adjusted_score is not None:
        try:
            ai_grading['final_score'] = float(adjusted_score)
        except (ValueError, TypeError):
            pass
    ai_grading['needs_human_review'] = False

    items[item_index]['ai_grading'] = ai_grading
    data['items'] = items
    history_doc.data = data
    history_doc.save(update_fields=['data'])

    return ok({
        'history_id': history_id,
        'item_index': item_index,
        'reviewed': True,
        'adjusted_score': adjusted_score,
    }, '人工复核已完成')


def _now_iso():
    """返回当前时间的 ISO 格式字符串。"""
    from django.utils import timezone
    return timezone.now().isoformat()


# ====================================================================
# AI P1 功能接口 —— 试卷分析 / 复习推荐 / 答题分析 / 文章增强 / 小程序任务状态
# ====================================================================


def _check_ai_rate_limit_custom(openid, feature, max_count=1, window=86400):
    """自定义窗口的 AI 接口限流。

    Args:
        openid: 用户 openid
        feature: 功能名称（用于 cache key 隔离）
        max_count: 窗口内最大调用次数
        window: 时间窗口（秒）

    Returns:
        (allowed, error_msg) —— allowed=True 表示放行。
    """
    from django.core.cache import cache
    key = 'ai:rate:%s:%s' % (feature, openid)
    try:
        count = cache.incr(key)
        if count == 1:
            cache.expire(key, window)
        if count > max_count:
            return False, '%s请求次数已达上限，请稍后再试' % feature
    except ValueError:
        cache.set(key, 1, window)
    except Exception:
        pass
    return True, None


# ---- P1: 试卷分析（管理端）----

@require_perms('ai.report')
def exam_analyze(request, examid):
    """POST /api/admin/ai/exams/<examid>/analyze/  触发试卷分析（异步）。

    检查答题记录数 ≥10，创建 AIJob 并启动线程调用 ExamAnalysisService.analyze。
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    from .ai_services import ExamAnalysisService

    # 预检查答题记录数
    stats = ExamAnalysisService.aggregate_stats(examid)
    if not stats:
        return fail(ErrorCode.NOT_FOUND, '试卷不存在')

    total_records = stats.get('total_records', 0)
    if total_records < ExamAnalysisService.MIN_RECORDS:
        return fail(ErrorCode.PARAM_ERROR,
                     '答题记录不足 %d 份，当前仅 %d 份' % (ExamAnalysisService.MIN_RECORDS, total_records))

    config = {'examid': str(examid), 'total_records': total_records}
    job_id = AIJobManager.create('exam_analyze', config)

    def _task(jid):
        ExamAnalysisService.analyze(str(examid), jid)

    AIJobManager.start(job_id, _task)

    _log_ai_usage('exam_analyze', source='admin', admin_user=_admin_name(request),
                  status='pending', job_id=job_id)
    return ok({'job_id': job_id, 'status': 'pending', 'total_records': total_records},
              '试卷分析任务已创建')


@require_perms('ai.report')
def exam_analysis_result(request, examid):
    """GET /api/admin/ai/exams/<examid>/analysis/  获取试卷分析结果。

    从 exam 文档的 ai_analysis 字段读取分析结果。
    """
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)

    from core.models import Document as Doc

    exam_doc = Doc.objects.filter(collection='exam', doc_id=str(examid)).first()
    if not exam_doc and str(examid).isdigit():
        exam_doc = Doc.objects.filter(collection='exam', pk=int(examid), doc_id=None).first()
    if not exam_doc:
        return fail(ErrorCode.NOT_FOUND, '试卷不存在')

    analysis = (exam_doc.data or {}).get('ai_analysis')
    if not analysis or not isinstance(analysis, dict):
        return fail(ErrorCode.NOT_FOUND, '暂无分析结果，请先触发试卷分析')

    # 检查是否需要重新分析
    stats = ExamAnalysisService_aggregate_stats_safe(examid)
    if stats:
        current_count = stats.get('total_records', 0)
        needs_reanalyze = ExamAnalysisService_should_reanalyze_safe(analysis, current_count)
        analysis = dict(analysis)
        analysis['needs_reanalyze'] = needs_reanalyze

    return ok(analysis)


def ExamAnalysisService_aggregate_stats_safe(examid):
    """安全调用 aggregate_stats，异常时返回 None。"""
    try:
        from .ai_services import ExamAnalysisService
        return ExamAnalysisService.aggregate_stats(examid)
    except Exception:
        return None


def ExamAnalysisService_should_reanalyze_safe(analysis, count):
    """安全调用 should_reanalyze，异常时返回 False。"""
    try:
        from .ai_services import ExamAnalysisService
        return ExamAnalysisService.should_reanalyze(analysis, count)
    except Exception:
        return False


# ---- P1: 小程序端 AI 接口 ----

@csrf_exempt
def review_plan(request):
    """POST /api/admin/ai/review-plan/  生成今日复习推荐（异步）
    GET  /api/admin/ai/review-plan/  获取今日推荐（同步）

    小程序端接口，使用 X-Openid 鉴权 + 限流（1 次/天/用户）。
    """
    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return fail(ErrorCode.UNAUTHORIZED, '未登录：请先调用 login 获取 openid')

    from .ai_services import ReviewRecommendService

    if request.method == 'POST':
        # 限流：1 次/天/用户
        allowed, rate_msg = _check_ai_rate_limit_custom(
            openid, 'review_plan', max_count=1, window=86400)
        if not allowed:
            return fail(ErrorCode.PARAM_ERROR, rate_msg)

        config = {'openid': openid}
        job_id = AIJobManager.create('review_recommend', config, openid=openid)

        def _task(jid):
            try:
                plan = ReviewRecommendService.generate_plan(openid)
                AIJobManager.update(jid, status=AIJobManager.STATUS_SUCCESS,
                                    progress=100, progress_text='复习推荐生成完成',
                                    result=plan)
            except Exception as e:
                AIJobManager.update(jid, status=AIJobManager.STATUS_FAILED,
                                    error=str(e)[:500], progress_text='生成失败')

        AIJobManager.start(job_id, _task)
        _log_ai_usage('review_recommend', source='mp', openid=openid,
                      status='pending', job_id=job_id)
        return ok({'job_id': job_id, 'status': 'pending'}, '复习推荐任务已创建')

    if request.method == 'GET':
        try:
            plan = ReviewRecommendService.get_today_plan(openid)
            if not plan:
                return fail(ErrorCode.NOT_FOUND, '暂无今日复习计划')
            return ok(plan)
        except Exception as e:
            return fail(ErrorCode.SERVER_ERROR, '获取复习计划失败：%s' % str(e))

    return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET / POST', http_status=405)


@csrf_exempt
def learning_profile(request):
    """POST /api/admin/ai/learning-profile/  生成答题分析（异步）
    GET  /api/admin/ai/learning-profile/  获取分析结果

    小程序端接口，使用 X-Openid 鉴权 + 限流（1 次/7天/用户）。
    POST 前检查答题记录 ≥20 条。
    """
    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return fail(ErrorCode.UNAUTHORIZED, '未登录：请先调用 login 获取 openid')

    from .ai_services import LearningProfileService

    if request.method == 'POST':
        # 限流：1 次/7天/用户
        allowed, rate_msg = _check_ai_rate_limit_custom(
            openid, 'learning_profile', max_count=1, window=7 * 86400)
        if not allowed:
            return fail(ErrorCode.PARAM_ERROR, rate_msg)

        # 预检查答题记录数
        history_summary = LearningProfileService.aggregate_history(openid)
        if not history_summary:
            return fail(ErrorCode.PARAM_ERROR, '无法获取答题历史，请先完成一些答题练习')

        total_count = history_summary.get('total_count', 0)
        if total_count < LearningProfileService.MIN_RECORDS:
            return fail(ErrorCode.PARAM_ERROR,
                         '答题记录不足 %d 条，当前仅 %d 条' % (LearningProfileService.MIN_RECORDS, total_count))

        config = {'openid': openid, 'total_count': total_count}
        job_id = AIJobManager.create('learning_profile', config, openid=openid)

        def _task(jid):
            LearningProfileService.analyze(openid, jid)

        AIJobManager.start(job_id, _task)
        _log_ai_usage('learning_profile', source='mp', openid=openid,
                      status='pending', job_id=job_id)
        return ok({'job_id': job_id, 'status': 'pending', 'total_count': total_count},
                  '答题分析任务已创建')

    if request.method == 'GET':
        try:
            profile = LearningProfileService.get_profile(openid)
            if not profile:
                return fail(ErrorCode.NOT_FOUND, '暂无学习画像，请先生成')
            return ok(profile)
        except Exception as e:
            return fail(ErrorCode.SERVER_ERROR, '获取学习画像失败：%s' % str(e))

    return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET / POST', http_status=405)


@csrf_exempt
def ai_job_status_mp(request, job_id):
    """GET /api/admin/ai/jobs/<job_id>/status/  小程序端查询异步任务状态。

    使用 X-Openid 鉴权，仅能查看本人发起的任务。
    """
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)

    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return fail(ErrorCode.UNAUTHORIZED, '未登录：请先调用 login 获取 openid')

    job_data = AIJobManager.get(job_id)
    if not job_data:
        return fail(ErrorCode.NOT_FOUND, '任务不存在')

    # 校验任务归属：仅能查看本人发起的任务
    job_openid = job_data.get('openid', '')
    if job_openid and job_openid != openid:
        return fail(ErrorCode.FORBIDDEN, '无权查看此任务')

    return ok(job_data)


# ====================================================================
# AI P2 功能接口 —— 知识库 RAG / 自动标签 / Excel 校验 / 学习报告 / 智能客服
# ====================================================================


def _find_question_doc(doc_id):
    """按 doc_id 或 pk 查找 questions 集合文档。"""
    from core.models import Document as Doc
    doc = Doc.objects.filter(collection='questions', doc_id=str(doc_id)).first()
    if not doc and str(doc_id).isdigit():
        doc = Doc.objects.filter(collection='questions', pk=int(doc_id), doc_id=None).first()
    return doc


# ---- P2: 知识库 RAG（管理端）----

@require_perms('ai.config')
def kb_rebuild(request):
    """POST /api/admin/ai/kb/rebuild/  重建知识库索引。"""
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    from .ai_services import KnowledgeRAGService
    result = KnowledgeRAGService.rebuild_index()
    return ok(result, '知识库索引已重建')


@require_perms('ai.config')
def kb_stats(request):
    """GET /api/admin/ai/kb/stats/  知识库索引统计。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)

    from .ai_services import KnowledgeRAGService
    return ok(KnowledgeRAGService.get_stats())


# ---- 文章 ↔ 知识库索引（选择性纳入，编码可追溯）----

def _find_article_doc(doc_id):
    """按 doc_id 或 pk 查找 articles 集合文档。"""
    doc = Document.objects.filter(collection='articles', doc_id=str(doc_id)).first()
    if not doc and str(doc_id).isdigit():
        doc = Document.objects.filter(collection='articles', pk=int(doc_id), doc_id=None).first()
    return doc


def _operator_name(request):
    """取当前管理员标识，用于写入 indexedBy 审计字段。"""
    user = getattr(request, 'admin_user', None)
    return getattr(user, 'username', '') or ''


@require_perms('knowledge.manage')
def kb_indexed_articles(request):
    """GET /api/admin/ai/kb/articles/  已纳入索引的文章清单（可追溯）。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)

    from .ai_services import KnowledgeRAGService
    items = KnowledgeRAGService.get_indexed_articles()
    return ok({'list': items, 'total': len(items)})


@require_perms('knowledge.manage')
def kb_article_link(request, doc_id):
    """将单篇文章加入 / 移出知识库索引。

    - POST   /api/admin/articles/<doc_id>/to-knowledge/  加入（幂等，自动补编码）
    - DELETE /api/admin/articles/<doc_id>/to-knowledge/  移出
    """
    article_doc = _find_article_doc(doc_id)
    if not article_doc:
        return fail(ErrorCode.NOT_FOUND, '文章不存在')

    from .ai_services import KnowledgeRAGService

    if request.method == 'POST':
        result = KnowledgeRAGService.add_article_to_index(
            article_doc, operator=_operator_name(request))
        if isinstance(result, dict) and result.get('error'):
            return fail(ErrorCode.SERVER_ERROR, result['error'])
        return ok(result, '已加入知识库索引')

    if request.method == 'DELETE':
        result = KnowledgeRAGService.remove_article_from_index(article_doc)
        if not result.get('removed'):
            return ok(result, '该文章尚未加入知识库索引')
        return ok(result, '已从知识库索引移出')

    return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST / DELETE', http_status=405)


@require_perms('knowledge.manage')
def kb_articles_batch_link(request):
    """POST /api/admin/articles/to-knowledge/  批量加入 / 移出知识库索引。

    请求体：``{ids: ["art-001", ...], action: "add" | "remove"}``（action 默认 add）
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    body, err = json_body(request)
    if err:
        return err

    ids = body.get('ids')
    if not isinstance(ids, list) or not ids:
        return fail(ErrorCode.PARAM_ERROR, 'ids 不能为空数组')
    if len(ids) > 200:
        return fail(ErrorCode.PARAM_ERROR, '单次最多处理 200 篇文章')

    action = (body.get('action') or 'add').strip().lower()
    if action not in ('add', 'remove'):
        return fail(ErrorCode.PARAM_ERROR, "action 仅支持 'add' 或 'remove'")

    from .ai_services import KnowledgeRAGService
    operator = _operator_name(request)

    succeeded = []
    failed = []
    for raw_id in ids:
        article_doc = _find_article_doc(raw_id)
        if not article_doc:
            failed.append({'id': str(raw_id), 'reason': '文章不存在'})
            continue
        if action == 'remove':
            result = KnowledgeRAGService.remove_article_from_index(article_doc)
            if result.get('removed'):
                succeeded.append({
                    'id': str(raw_id),
                    'article_code': result.get('article_code', ''),
                })
            else:
                failed.append({'id': str(raw_id), 'reason': '尚未加入索引'})
        else:
            result = KnowledgeRAGService.add_article_to_index(article_doc, operator=operator)
            if isinstance(result, dict) and result.get('error'):
                failed.append({'id': str(raw_id), 'reason': result['error']})
            else:
                succeeded.append({
                    'id': str(raw_id),
                    'article_code': result.get('article_code', ''),
                    'kb_doc_id': result.get('kb_doc_id', ''),
                })

    verb = '加入' if action == 'add' else '移出'
    message = '批量%s完成：成功 %d 篇，失败 %d 篇' % (verb, len(succeeded), len(failed))
    return ok({
        'action': action,
        'succeeded': succeeded,
        'failed': failed,
        'success_count': len(succeeded),
        'failed_count': len(failed),
    }, message)


# ---- P2: 题目自动标签（管理端）----

@require_perms('ai.analyze')
def question_suggest_tags(request, doc_id):
    """POST /api/admin/ai/questions/<doc_id>/suggest-tags/  单题标签推荐。"""
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    question_doc = _find_question_doc(doc_id)
    if not question_doc:
        return fail(ErrorCode.NOT_FOUND, '题目不存在')

    from .ai_services import AutoTagService
    result = AutoTagService.suggest_tags(question_doc)
    if isinstance(result, dict) and result.get('error'):
        _log_ai_usage('auto_tag', source='admin', admin_user=_admin_name(request),
                      status='failed', error=result.get('error', ''))
        return fail(ErrorCode.SERVER_ERROR, result['error'])
    _log_ai_usage('auto_tag', source='admin', admin_user=_admin_name(request), status='success')
    return ok(result, '标签推荐完成')


@require_perms('ai.analyze')
def question_auto_tag_batch(request):
    """POST /api/admin/ai/questions/auto-tag/  批量标签推荐（异步，返回 job_id）。

    请求体：{question_ids: ["id1", "id2", ...]}
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    body, err = json_body(request)
    if err:
        return err

    question_ids = body.get('question_ids')
    if not isinstance(question_ids, list) or not question_ids:
        return fail(ErrorCode.PARAM_ERROR, 'question_ids 不能为空数组')
    if len(question_ids) > 500:
        return fail(ErrorCode.PARAM_ERROR, '单次最多处理 500 道题目')

    from .ai_services import AutoTagService

    job_id = AIJobManager.create('auto_tag',
                                 {'question_ids': question_ids, 'count': len(question_ids)})

    def _task(jid):
        AutoTagService.suggest_batch(question_ids, job_id=jid)

    AIJobManager.start(job_id, _task)

    _log_ai_usage('auto_tag', source='admin', admin_user=_admin_name(request),
                  status='pending', job_id=job_id)
    return ok({'job_id': job_id, 'status': 'pending', 'total': len(question_ids)},
              '批量标签推荐任务已创建')


@require_perms('ai.analyze')
def question_apply_tags(request, doc_id):
    """PUT /api/admin/ai/questions/<doc_id>/tags/  按标签名应用（AI 标签推荐用）。

    body: {tag_names: [str]}
    """
    if request.method != 'PUT':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 PUT', http_status=405)
    body, err = json_body(request)
    if err:
        return err
    tag_names = body.get('tag_names') or []
    if not isinstance(tag_names, list):
        return fail(ErrorCode.PARAM_ERROR, 'tag_names 必须是数组')
    tag_names = [str(n).strip() for n in tag_names if str(n).strip()]
    from .ai_services import AutoTagService
    result = AutoTagService.apply_tags(str(doc_id), tag_names)
    if isinstance(result, dict) and 'error' in result:
        return fail(ErrorCode.SERVER_ERROR, result['error'])
    return ok(result, '标签已应用')


@require_perms('ai.analyze')
def question_auto_tag_sync(request, doc_id):
    """POST /api/admin/ai/questions/<doc_id>/auto-tag-sync/  AI标签推荐+自动同步+自动绑定。

    一步完成：AI 推荐标签 → 同步到标签管理（不存在则创建）→ 自动绑定到题目。

    请求体（可选）：{auto_bind: true|false}  默认 true
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    auto_bind = True
    body, berr = json_body(request)
    if not berr and isinstance(body, dict):
        auto_bind = body.get('auto_bind', True)

    question_doc = _find_question_doc(doc_id)
    if not question_doc:
        return fail(ErrorCode.NOT_FOUND, '题目不存在')

    from .ai_services import AutoTagService
    result = AutoTagService.auto_tag_sync(question_doc, auto_bind=auto_bind)
    if isinstance(result, dict) and result.get('error'):
        _log_ai_usage('auto_tag', source='admin', admin_user=_admin_name(request),
                      status='failed', error=result.get('error', ''))
        return fail(ErrorCode.SERVER_ERROR, result['error'])

    _log_ai_usage('auto_tag', source='admin', admin_user=_admin_name(request), status='success')
    new_count = sum(1 for t in result.get('synced_tags', []) if t.get('is_new'))
    msg = 'AI 标签推荐完成'
    if new_count:
        msg += f'（新增 {new_count} 个标签到标签管理）'
    if result.get('bound'):
        msg += f'，已绑定 {len(result.get("tag_ids", []))} 个标签'
    return ok(result, msg)


@require_perms('ai.analyze')
def question_auto_tag_sync_batch(request):
    """POST /api/admin/ai/questions/auto-tag-sync-batch/  批量AI标签推荐+自动同步+自动绑定（异步）。

    请求体：{question_ids: ["id1", "id2", ...], auto_bind: true}
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    body, err = json_body(request)
    if err:
        return err

    question_ids = body.get('question_ids')
    if not isinstance(question_ids, list) or not question_ids:
        return fail(ErrorCode.PARAM_ERROR, 'question_ids 不能为空数组')
    if len(question_ids) > 500:
        return fail(ErrorCode.PARAM_ERROR, '单次最多处理 500 道题目')

    auto_bind = body.get('auto_bind', True)

    from .ai_services import AutoTagService

    job_id = AIJobManager.create('auto_tag_sync',
                                 {'question_ids': question_ids, 'count': len(question_ids),
                                  'auto_bind': auto_bind})

    def _task(jid):
        AutoTagService._auto_tag_sync_batch_impl(question_ids, job_id=jid, auto_bind=auto_bind)

    AIJobManager.start(job_id, _task)

    _log_ai_usage('auto_tag', source='admin', admin_user=_admin_name(request),
                  status='pending', job_id=job_id)
    return ok({'job_id': job_id, 'status': 'pending', 'total': len(question_ids)},
              '批量AI标签同步任务已创建')


# ---- P2: Excel 智能校验（管理端）----

@require_perms('question.import')
def excel_validate(request):
    """POST /api/admin/ai/excel-validate/  Excel 导入智能校验（异步，返回 job_id）。

    请求体：{rows: [{...}, ...], qtype: 'single'}
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    body, err = json_body(request)
    if err:
        return err

    rows = body.get('rows')
    if not isinstance(rows, list) or not rows:
        return fail(ErrorCode.PARAM_ERROR, 'rows 不能为空数组')
    if len(rows) > 2000:
        return fail(ErrorCode.PARAM_ERROR, '单次最多校验 2000 行')

    qtype = (body.get('qtype') or 'single').strip() or 'single'

    from .ai_services import ExcelValidateService

    job_id = AIJobManager.create('excel_validate', {'qtype': qtype, 'count': len(rows)})

    def _task(jid):
        ExcelValidateService.validate_rows(rows, qtype, job_id=jid)

    AIJobManager.start(job_id, _task)

    _log_ai_usage('excel_validate', source='admin', admin_user=_admin_name(request),
                  status='pending', job_id=job_id)
    return ok({'job_id': job_id, 'status': 'pending', 'total': len(rows)},
              '数据校验任务已创建')


# ---- P2: 小程序端 AI 接口 ----

@csrf_exempt
def kb_ask(request):
    """POST /api/ai/kb-ask/  知识库 RAG 问答（小程序端）。

    请求体：{question: string}
    鉴权：X-Openid；限流：20 次/天/用户。
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return fail(ErrorCode.UNAUTHORIZED, '未登录：请先调用 login 获取 openid')

    allowed, rate_msg = _check_ai_rate_limit_custom(
        openid, 'kb_ask', max_count=20, window=86400)
    if not allowed:
        return fail(ErrorCode.PARAM_ERROR, rate_msg)

    body, err = json_body(request)
    if err:
        return err

    question = (body.get('question') or '').strip()
    if not question:
        return fail(ErrorCode.PARAM_ERROR, '请输入您的问题')

    # 支持在选择入口指定的模型；未指定走解析链默认（用户默认 → 全局默认）
    model_id = _extract_model_id(body)
    from .ai_services import KnowledgeRAGService
    with ai_models.use_model(model_id=model_id, openid=openid, func_name='kb_qa'):
        result = KnowledgeRAGService.ask(question)
    _log_ai_usage('kb_qa', source='mp', openid=openid, status='success')
    return ok(result, '回答完成')


@csrf_exempt
def learning_report(request):
    """GET  /api/ai/report/?type=weekly  获取最新学习报告
    POST /api/ai/report/               生成学习报告（异步，返回 job_id）

    鉴权：X-Openid；POST 限流：2 次/天/用户。
    """
    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return fail(ErrorCode.UNAUTHORIZED, '未登录：请先调用 login 获取 openid')

    from .ai_services import LearningReportService

    if request.method == 'GET':
        report_type = (request.GET.get('type') or 'weekly').strip()
        if report_type not in LearningReportService.TYPES:
            report_type = 'weekly'
        try:
            report = LearningReportService.get_report(openid, report_type)
        except Exception as e:
            return fail(ErrorCode.SERVER_ERROR, '获取学习报告失败：%s' % str(e))
        if not report:
            return ok(None, '暂无学习报告，请先生成')
        return ok(report)

    if request.method == 'POST':
        allowed, rate_msg = _check_ai_rate_limit_custom(
            openid, 'learning_report', max_count=5, window=86400)
        if not allowed:
            return fail(ErrorCode.PARAM_ERROR, rate_msg)

        body, err = json_body(request)
        if err:
            return err
        report_type = (body.get('type') or 'weekly').strip()
        if report_type not in LearningReportService.TYPES:
            report_type = 'weekly'

        # 不再前置拦截「答题记录不足」——generate() 内部会优雅返回提示报告
        # （content_md="答题记录不足..." + suggestions），而非 400 报错。
        # 前置拦截会导致小程序端收到 400 + toast 截断，用户体验差。
        # 直接创建异步任务，让 generate() 统一处理所有场景。

        try:
            job_id = AIJobManager.create('learning_report', {'report_type': report_type},
                                         openid=openid)

            def _task(jid):
                LearningReportService.generate(openid, report_type, job_id=jid)

            AIJobManager.start(job_id, _task)
        except Exception as e:
            logger.exception('learning_report create/start job failed: %s', e)
            return fail(ErrorCode.SERVER_ERROR, '创建报告任务失败，请稍后重试')

        _log_ai_usage('learning_report', source='mp', openid=openid,
                      status='pending', job_id=job_id)
        return ok({'job_id': job_id, 'status': 'pending', 'report_type': report_type},
                  '学习报告生成任务已创建')

    return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET / POST', http_status=405)


@csrf_exempt
def cs_chat(request):
    """POST /api/ai/cs-chat/  智能客服对话（小程序端）。

    请求体：{message: string, history?: [{role, content}]}
    鉴权：X-Openid；限流：30 次/天/用户。
    """
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return fail(ErrorCode.UNAUTHORIZED, '未登录：请先调用 login 获取 openid')

    allowed, rate_msg = _check_ai_rate_limit_custom(
        openid, 'cs_chat', max_count=30, window=86400)
    if not allowed:
        return fail(ErrorCode.PARAM_ERROR, rate_msg)

    body, err = json_body(request)
    if err:
        return err

    message = (body.get('message') or '').strip()
    if not message:
        return fail(ErrorCode.PARAM_ERROR, '请输入消息内容')

    history = body.get('history') or []
    if not isinstance(history, list):
        history = []

    model_id = _extract_model_id(body)
    from .ai_services import CustomerService
    with ai_models.use_model(model_id=model_id, openid=openid, func_name='cs_chat'):
        result = CustomerService.chat(openid, message, history)
    _log_ai_usage('cs_chat', source='mp', openid=openid, status='success')
    return ok(result, '回复完成')


# ====================================================================
# AI 多模型管理 —— 自定义接入、多模型、运行时选择
#
# 设计要点（详见 adminapi/ai_models.py 与 docs/AI模型配置说明.md）：
#   * 全局模型（global）：管理员在后台维护，全部用户可用，上限 AI_MODEL_LIMITS['global']
#   * 用户模型（user）  ：小程序用户自行添加（自己的 Key），仅本人可用，上限 ['user']
#   * 默认模型：同一作用域内互斥，调用未显式指定模型时按「用户默认 → 全局默认」解析
#   * 生效时机：保存即写库，下一次 AI 调用生效；缓存按模型签名隔离
# ====================================================================

_AI_MODEL_TEST_MESSAGES = [
    {'role': 'system', 'content': '你是一个测试助手。'},
    {'role': 'user', 'content': '请回复：连接成功'},
]


def _test_model_connection(model):
    """对给定模型发一次极简请求，返回 (ok_bool, content_or_msg)。"""
    call_config, err = ai_models.build_call_config(model, explicit=True)
    if err:
        return False, err
    content, lerr = _call_llm(call_config, _AI_MODEL_TEST_MESSAGES)
    if lerr:
        return False, lerr
    return True, content


def _model_test_response(ok_flag, payload, model):
    """统一构造模型测试的响应（配置错误→503，上游故障→502，成功→200）。"""
    if ok_flag:
        return ok({
            'response': payload,
            'model': model.get('model'),
            'name': model.get('name'),
        }, '连接测试成功')
    err_msg = str(payload)
    if _is_config_error(err_msg):
        return fail(ErrorCode.SERVICE_UNAVAILABLE,
                    '测试失败：%s' % err_msg)
    return fail(ErrorCode.BAD_GATEWAY, '测试失败：%s' % err_msg)


# ---- 管理端：全局模型 ----


@require_perms('ai.config')
def ai_models_dispatch(request):
    """GET  /api/admin/ai/models/  列出全局模型 + 元信息
    POST /api/admin/ai/models/  新增全局模型
    """
    if request.method == 'GET':
        items = [ai_models.to_client(m) for m in
                 ai_models.list_models(scope=ai_models.SCOPE_GLOBAL)]
        return ok({
            'list': items,
            'total': len(items),
            'meta': ai_models.model_meta(),
        })

    if request.method == 'POST':
        body, err = json_body(request)
        if err:
            return err
        model, err = ai_models.create_model(body, scope=ai_models.SCOPE_GLOBAL)
        if err:
            return fail(ErrorCode.PARAM_ERROR, err)
        return ok(ai_models.to_client(model), '模型已添加')

    return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET / POST', http_status=405)


@require_perms('ai.config')
def ai_models_meta(request):
    """GET /api/admin/ai/models/meta/  数量上限、Provider 预设、默认模型、生效说明。"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    return ok(ai_models.model_meta())


@require_perms('ai.config')
def ai_model_detail(request, model_id):
    """PUT / DELETE /api/admin/ai/models/<model_id>/  更新 / 删除全局模型。"""
    if request.method == 'PUT':
        body, err = json_body(request)
        if err:
            return err
        model, err = ai_models.update_model(
            model_id, body, scope=ai_models.SCOPE_GLOBAL)
        if err:
            return fail(ErrorCode.PARAM_ERROR, err)
        return ok(ai_models.to_client(model), '模型已更新')

    if request.method == 'DELETE':
        deleted, err = ai_models.delete_model(model_id, scope=ai_models.SCOPE_GLOBAL)
        if err:
            return fail(ErrorCode.PARAM_ERROR, err)
        return ok({'deleted': deleted}, '模型已删除')

    return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 PUT / DELETE', http_status=405)


@require_perms('ai.config')
def ai_model_set_default(request, model_id):
    """POST /api/admin/ai/models/<model_id>/default/  设为全局默认模型。"""
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)
    model, err = ai_models.set_default(model_id, scope=ai_models.SCOPE_GLOBAL)
    if err:
        return fail(ErrorCode.PARAM_ERROR, err)
    return ok(ai_models.to_client(model), '已设为默认模型')


@require_perms('ai.config')
def ai_model_test(request, model_id):
    """POST /api/admin/ai/models/<model_id>/test/  测试指定模型连通性。"""
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)
    model = ai_models.get_model(model_id)
    if not model:
        return fail(ErrorCode.NOT_FOUND, '模型不存在')
    try:
        ok_flag, payload = _test_model_connection(model)
    except Exception as e:
        logger.exception('ai_model_test 未预期异常: %s', e)
        return fail(ErrorCode.SERVER_ERROR, '测试时发生内部错误，请稍后重试')
    return _model_test_response(ok_flag, payload, model)


# ---- 小程序端：用户自有模型（X-Openid 鉴权）----


def _mp_require_openid(request):
    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return None, fail(ErrorCode.UNAUTHORIZED, '未登录：请先调用 login 获取 openid')
    return openid, None


@csrf_exempt
def mp_ai_models(request):
    """GET  /api/ai/models/  列出可用模型（全局 + 本人），含元信息与默认模型
    POST /api/ai/models/   新增本人模型（携带自己的 API Key）
    """
    openid, err = _mp_require_openid(request)
    if err:
        return err

    if request.method == 'GET':
        items = [ai_models.to_client(m) for m in ai_models.list_accessible_models(openid)]
        return ok({
            'list': items,
            'total': len(items),
            'meta': ai_models.model_meta(openid),
        })

    if request.method == 'POST':
        body, err = json_body(request)
        if err:
            return err
        model, err = ai_models.create_model(
            body, scope=ai_models.SCOPE_USER, owner_key=openid)
        if err:
            return fail(ErrorCode.PARAM_ERROR, err)
        return ok(ai_models.to_client(model), '模型已添加')

    return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET / POST', http_status=405)


@csrf_exempt
def mp_ai_model_detail(request, model_id):
    """PUT / DELETE /api/ai/models/<model_id>/  更新 / 删除本人模型。"""
    openid, err = _mp_require_openid(request)
    if err:
        return err

    if request.method == 'PUT':
        body, err = json_body(request)
        if err:
            return err
        model, err = ai_models.update_model(
            model_id, body, scope=ai_models.SCOPE_USER, owner_key=openid)
        if err:
            return fail(ErrorCode.PARAM_ERROR, err, http_status=403 if '无权' in err else None)
        return ok(ai_models.to_client(model), '模型已更新')

    if request.method == 'DELETE':
        deleted, err = ai_models.delete_model(
            model_id, scope=ai_models.SCOPE_USER, owner_key=openid)
        if err:
            return fail(ErrorCode.PARAM_ERROR, err, http_status=403 if '无权' in err else None)
        return ok({'deleted': deleted}, '模型已删除')

    return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 PUT / DELETE', http_status=405)


@csrf_exempt
def mp_ai_model_set_default(request, model_id):
    """POST /api/ai/models/<model_id>/default/  设为自己的默认模型。

    既可设自己的用户模型，也可把某个全局模型设为自己的默认。
    """
    openid, err = _mp_require_openid(request)
    if err:
        return err
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    model = ai_models.get_model(model_id)
    if not model:
        return fail(ErrorCode.NOT_FOUND, '模型不存在')

    m_scope = model.get('scope') or ai_models.SCOPE_GLOBAL
    if m_scope == ai_models.SCOPE_USER:
        if model.get('ownerKey') != openid:
            return fail(ErrorCode.FORBIDDEN, '无权操作该模型')
        updated, err = ai_models.set_default(
            model_id, scope=ai_models.SCOPE_USER, owner_key=openid)
    else:
        # 全局模型：记录为该用户的首选（通过用户默认指针实现）
        updated, err = ai_models.set_user_preferred_global(openid, model_id)
    if err:
        return fail(ErrorCode.PARAM_ERROR, err)
    return ok(ai_models.to_client(updated), '已设为默认模型')


@csrf_exempt
def mp_ai_model_test(request, model_id):
    """POST /api/ai/models/<model_id>/test/  测试该模型连通性。"""
    openid, err = _mp_require_openid(request)
    if err:
        return err
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    model = ai_models.get_model(model_id)
    if not model:
        return fail(ErrorCode.NOT_FOUND, '模型不存在')
    m_scope = model.get('scope') or ai_models.SCOPE_GLOBAL
    if m_scope == ai_models.SCOPE_USER and model.get('ownerKey') != openid:
        return fail(ErrorCode.FORBIDDEN, '无权操作该模型')

    try:
        ok_flag, payload = _test_model_connection(model)
    except Exception as e:
        logger.exception('mp_ai_model_test 未预期异常: %s', e)
        return fail(ErrorCode.SERVER_ERROR, '测试时发生内部错误，请稍后重试')
    return _model_test_response(ok_flag, payload, model)


@csrf_exempt
def mp_ai_models_meta(request):
    """GET /api/ai/models/meta/  数量上限、Provider 预设、默认模型、生效说明。"""
    openid, err = _mp_require_openid(request)
    if err:
        return err
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    return ok(ai_models.model_meta(openid))


# ====================================================================
# AI 题目解析 & 答题分析总结 —— 小程序端（VIP 权限校验）
#
# 功能：
#   1. 单题 AI 解析（缓存优先，未解析则触发 LLM 生成并入库复用）
#   2. 整份作答的 AI 分析总结（针对当前答题场次生成总结报告）
#   3. VIP 状态查询（前端据此决定是否展示 / 禁用入口）
#
# 权限：仅 VIP 用户可调用，后端通过 profiles 集合的 vip / roles 字段校验。
# 缓存：单题解析复用 QuestionAnalysisService 的 content_hash 缓存逻辑，
#       整份总结按 (openid + 题目集 + 作答) 哈希缓存。
# ====================================================================


def _check_vip(openid):
    """检查用户是否拥有 AI 解析权限（VIP）。

    判定规则（满足任一即放行）：
      1. profiles 文档 data.vip == True
      2. profiles 文档 data.roles（列表）包含 'vip' 或 'ai_analysis'
      3. profiles 文档 data.isVip == True（兼容前端写入）

    Returns:
        (is_vip: bool, profile_data: dict | None)
    """
    if not openid:
        return False, None
    from core.models import Document as Doc
    profile = Doc.objects.filter(collection='profiles', data___openid=openid).first()
    if not profile:
        return False, None
    data = profile.data or {}
    # 直接 vip 布尔字段
    if data.get('vip') is True or data.get('isVip') is True:
        return True, data
    # roles 数组
    roles = data.get('roles') or []
    if isinstance(roles, list) and ('vip' in roles or 'ai_analysis' in roles):
        return True, data
    return False, data


@csrf_exempt
def mp_vip_status(request):
    """GET /api/ai/vip-status/  查询当前用户 VIP 状态（前端用于控制入口显隐）。

    鉴权：X-Openid
    返回：{isVip: bool, features: ['question_analysis', 'exam_summary']}
    """
    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return fail(ErrorCode.UNAUTHORIZED, '未登录：请先调用 login 获取 openid')
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    is_vip, _ = _check_vip(openid)
    features = ['question_analysis', 'exam_summary'] if is_vip else []
    return ok({'isVip': is_vip, 'features': features})


@csrf_exempt
def mp_question_analysis(request, question_id):
    """GET/POST /api/ai/question-analysis/<question_id>/  单题 AI 解析（小程序端）。

    GET  —— 返回已缓存的 AI 解析（若有），不触发 LLM。前端可据此判断是否已解析。
    POST —— 触发 AI 解析（缓存优先：QuestionAnalysisService 内部按 content_hash 判断，
             已解析则直接返回缓存，未解析才调用 LLM 并写入 question.data['ai_analysis']）。

    权限：VIP 用户（_check_vip）
    限流：30 次/天/用户（仅 POST 计数）
    """
    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return fail(ErrorCode.UNAUTHORIZED, '未登录：请先调用 login 获取 openid')

    # 后端角色校验 —— 防止非 VIP 越权调用
    is_vip, _ = _check_vip(openid)
    if not is_vip:
        return fail(ErrorCode.FORBIDDEN, '该功能仅对 VIP 用户开放，请升级后使用')

    # 查找题目文档
    question_doc = _find_question_doc(question_id)
    if not question_doc:
        return fail(ErrorCode.NOT_FOUND, '题目不存在')

    data = question_doc.data or {}

    if request.method == 'GET':
        analysis = data.get('ai_analysis')
        if analysis and isinstance(analysis, dict) and analysis.get('content_hash'):
            return ok({'analysis': analysis, 'cached': True, 'hasAnalysis': True})
        return ok({'analysis': None, 'cached': False, 'hasAnalysis': False}, '该题暂无 AI 解析')

    if request.method == 'POST':
        # 限流：30 次/天/用户
        allowed, rate_msg = _check_ai_rate_limit_custom(
            openid, 'question_analysis', max_count=30, window=86400)
        if not allowed:
            return fail(ErrorCode.PARAM_ERROR, rate_msg)

        # 调用已有的 QuestionAnalysisService —— 缓存逻辑完全复用，不改动
        from .ai_services import QuestionAnalysisService
        result = QuestionAnalysisService.analyze_single(question_doc)

        if isinstance(result, dict) and 'error' in result:
            return fail(ErrorCode.SERVER_ERROR, result['error'])

        # 判断是否命中缓存（content_hash 与之前相同即缓存命中）
        old_hash = (data.get('ai_analysis') or {}).get('content_hash', '')
        is_cached = result.get('content_hash') == old_hash and bool(old_hash)

        return ok({
            'analysis': result,
            'cached': is_cached,
            'hasAnalysis': True,
        }, 'AI 解析完成（缓存命中）' if is_cached else 'AI 解析完成')

    return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET / POST', http_status=405)


@csrf_exempt
def mp_exam_summary_analysis(request):
    """POST /api/ai/exam-summary/  整份作答的 AI 分析总结（小程序端）。

    请求体：
      {
        questions: [{_id, title, qtype, options, difficulty, ...}, ...],
        answers:   [["A"], ["B","C"], [], ...]   // 与 questions 下标对齐
      }

    流程：
      1. VIP 校验
      2. 按 (openid + 题目集 + 作答) 计算 content_hash
      3. 缓存命中 → 直接返回（控制 Token 消耗）
      4. 未命中 → 构建 prompt 调用 LLM 生成总结，写入 ai_exam_summaries 集合缓存
      5. 返回 {summary: {overall, strengths, weaknesses, suggestions, ...}, cached: bool}

    限流：10 次/天/用户
    """
    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return fail(ErrorCode.UNAUTHORIZED, '未登录：请先调用 login 获取 openid')

    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 POST', http_status=405)

    # 后端角色校验
    is_vip, _ = _check_vip(openid)
    if not is_vip:
        return fail(ErrorCode.FORBIDDEN, '该功能仅对 VIP 用户开放，请升级后使用')

    # 限流
    allowed, rate_msg = _check_ai_rate_limit_custom(
        openid, 'exam_summary', max_count=10, window=86400)
    if not allowed:
        return fail(ErrorCode.PARAM_ERROR, rate_msg)

    body, err = json_body(request)
    if err:
        return err

    questions = body.get('questions')
    answers = body.get('answers')
    if not isinstance(questions, list) or not questions:
        return fail(ErrorCode.PARAM_ERROR, 'questions 不能为空')
    if not isinstance(answers, list) or len(answers) != len(questions):
        return fail(ErrorCode.PARAM_ERROR, 'answers 需与 questions 等长')
    if len(questions) > 200:
        return fail(ErrorCode.PARAM_ERROR, '单次最多分析 200 道题目')

    model_id = _extract_model_id(body)

    # ---- 构建分析数据 ----
    import hashlib as _hashlib
    from core.models import Document as Doc
    from .ai_services import AIServiceBase, PromptBuilder
    from . import data_utils as du

    # 逐题判定对错，汇总统计
    question_summaries = []
    correct_count = 0
    wrong_count = 0
    unanswered_count = 0
    by_qtype = {}

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        qid = du.to_text(q.get('_id') or q.get('id') or ('idx_%d' % i))
        title = du.to_text(q.get('title') or q.get('content_md') or '')
        qtype = du.to_text(q.get('qtype') or q.get('type') or 'single')
        difficulty = q.get('difficulty', 2)
        user_ans = answers[i] or []
        if isinstance(user_ans, list):
            user_ans_codes = [str(a).strip().upper() for a in user_ans if str(a).strip()]
        else:
            user_ans_codes = [str(user_ans).strip().upper()]

        # 正确答案
        correct_codes = []
        options = q.get('options') or []
        if isinstance(options, str):
            try:
                import json as _json
                options = _json.loads(options)
            except Exception:
                options = []
        for opt in options:
            if isinstance(opt, dict):
                is_correct = opt.get('value') in (1, '1', True, 'true') or \
                             opt.get('isCorrect') in (1, '1', True, 'true')
                if is_correct:
                    correct_codes.append(str(opt.get('code', '')).strip().upper())

        if not correct_codes and q.get('answer'):
            ans_val = q.get('answer')
            if isinstance(ans_val, list):
                correct_codes = [str(a).strip().upper() for a in ans_val if str(a).strip()]
            else:
                correct_codes = [str(ans_val).strip().upper()]

        is_answered = len(user_ans_codes) > 0
        is_correct = is_answered and sorted(user_ans_codes) == sorted(correct_codes)

        if not is_answered:
            unanswered_count += 1
            status = 'unanswered'
        elif is_correct:
            correct_count += 1
            status = 'correct'
        else:
            wrong_count += 1
            status = 'wrong'

        # 按题型统计
        if qtype not in by_qtype:
            by_qtype[qtype] = {'total': 0, 'correct': 0, 'wrong': 0}
        by_qtype[qtype]['total'] += 1
        if status == 'correct':
            by_qtype[qtype]['correct'] += 1
        elif status == 'wrong':
            by_qtype[qtype]['wrong'] += 1

        question_summaries.append({
            'index': i + 1,
            'qid': qid,
            'title': title[:100],  # 截断避免 prompt 过长
            'qtype': qtype,
            'difficulty': difficulty,
            'userAnswer': user_ans_codes,
            'correctAnswer': correct_codes,
            'status': status,
        })

    total = len(question_summaries)
    score = round(correct_count / total * 100) if total else 0

    # ---- 缓存检查 ----
    cache_input = json.dumps({
        'openid': openid,
        'questions': [{'qid': qs['qid'], 'status': qs['status']} for qs in question_summaries],
    }, sort_keys=True, ensure_ascii=False)
    content_hash = _hashlib.sha256(cache_input.encode('utf-8')).hexdigest()[:16]

    # 查找已有缓存
    cache_doc = Doc.objects.filter(
        collection='ai_exam_summaries',
        doc_id='summary_%s_%s' % (openid[-8:] if len(openid) > 8 else openid, content_hash)
    ).first()
    if cache_doc and cache_doc.data.get('content_hash') == content_hash:
        cached_summary = cache_doc.data.get('summary')
        if cached_summary:
            return ok({
                'summary': cached_summary,
                'cached': True,
                'stats': {
                    'total': total, 'correct': correct_count,
                    'wrong': wrong_count, 'unanswered': unanswered_count, 'score': score,
                    'byQtype': by_qtype,
                },
            }, '分析总结（缓存命中）')

    # ---- 构建 prompt 调用 LLM ----
    # 组装分析文本
    lines = []
    lines.append('本次答题共 %d 题，答对 %d 题，答错 %d 题，未答 %d 题，得分 %d 分。\n' % (
        total, correct_count, wrong_count, unanswered_count, score))
    lines.append('各题型正确率：')
    for qt, s in by_qtype.items():
        rate = round(s['correct'] / s['total'] * 100) if s['total'] else 0
        lines.append('  - %s: %d/%d (%d%%)' % (qt, s['correct'], s['total'], rate))
    lines.append('\n错题详情：')
    for qs in question_summaries:
        if qs['status'] == 'wrong':
            lines.append('  - 第%d题 [%s] %s | 学生答案: %s | 正确答案: %s' % (
                qs['index'], qs['qtype'], qs['title'],
                ', '.join(qs['userAnswer']) or '未答',
                ', '.join(qs['correctAnswer']) or '未知'))
    lines.append('\n未答题：')
    for qs in question_summaries:
        if qs['status'] == 'unanswered':
            lines.append('  - 第%d题 [%s] %s' % (qs['index'], qs['qtype'], qs['title']))

    exam_text = '\n'.join(lines)

    system_prompt = (
        '你是一位专业的考试分析专家。请根据学生的答题情况，生成一份结构化的分析总结报告。'
        '报告应包含以下部分（用 Markdown 格式）：\n'
        '1. **总体评价**：一句话概括本次答题表现\n'
        '2. **优势分析**：学生表现较好的方面\n'
        '3. **薄弱环节**：需要重点改进的地方\n'
        '4. **错题分析**：针对错误较多的题型或知识点给出具体建议\n'
        '5. **学习建议**：下一步学习方向和练习建议\n'
        '请用中文回答，语言简洁专业，每个部分不超过 3-4 句话。'
    )
    user_prompt = '请根据以下答题数据进行分析总结：\n\n%s' % exam_text

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]

    # 调用 LLM（复用已有的模型解析链）
    content, llm_err, used_model = _call_llm_for(
        messages, model_id=model_id, openid=openid, func_name='exam_summary')
    if llm_err and not content:
        return fail(ErrorCode.SERVER_ERROR, 'AI 分析失败：%s' % llm_err)

    summary = {
        'content': content or '',
        'overall': '得分 %d / 100，答对 %d 题，答错 %d 题' % (score, correct_count, wrong_count),
        'correctCount': correct_count,
        'wrongCount': wrong_count,
        'unansweredCount': unanswered_count,
        'score': score,
        'byQtype': by_qtype,
        'model': (used_model or {}).get('model', ''),
        'analyzedAt': _now_iso(),
    }

    # 写入缓存（content_hash 隔离，下次同份作答直接复用）
    Doc.objects.update_or_create(
        collection='ai_exam_summaries',
        doc_id='summary_%s_%s' % (openid[-8:] if len(openid) > 8 else openid, content_hash),
        defaults={'data': {
            'content_hash': content_hash,
            'summary': summary,
            '_openid': openid,
            'createTime': _now_iso(),
        }},
    )

    return ok({
        'summary': summary,
        'cached': False,
        'stats': {
            'total': total, 'correct': correct_count,
            'wrong': wrong_count, 'unanswered': unanswered_count, 'score': score,
            'byQtype': by_qtype,
        },
    }, 'AI 分析总结完成')
