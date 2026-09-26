"""AI 模型注册表 —— 多模型自定义配置与运行时选择。

本模块解决「用户自定义接入并添加多个模型、使用时自由选择调用哪个模型」的需求。

核心概念
--------
- 模型条目（Model Entry）：一条 ``ai_models`` 集合文档，描述一个可调用的 LLM，
  包含 provider / apiUrl / apiKey / model / temperature / maxTokens 等。
- 作用域（scope）：
    * ``global`` —— 管理员在后台创建，全部用户可见可用；上限 ``AI_MODEL_LIMITS['global']``。
    * ``user``   —— 小程序用户自行创建（携带自己的 Key），仅本人可见可用；
                    上限 ``AI_MODEL_LIMITS['user']``。
- 默认模型（isDefault）：同一作用域（同理同一用户）内至多一个默认模型。

调用解析优先级（``resolve_model``）
-----------------------------------
1. 请求显式指定的 ``model_id``（且该模型可用：启用、全局 或 属于调用者）
2. 「AI 功能级配置」为该功能指定的模型（``feature_config[func_name].model``）
3. 调用者（openid）自己的默认模型
4. 全局默认模型
5. 兼容兜底：旧的 ``ai_config`` 顶层 apiKey/apiUrl/model（保证历史行为不中断）

若显式指定的 model_id 不可用，则**自动回退**到下一级，并在结果 ``source`` 中如实标注，
避免用户模型被删除后所有调用直接失败。

生效时机
--------
配置写入数据库后，**下一次 AI 调用立即生效**（无进程缓存、无需重启）。
同时 ``set_active_model`` / ``use_model`` 会把当前生效模型签名注入缓存哈希，
确保「同一内容换模型」不会命中旧模型的缓存结果。
"""
import ipaddress
import logging
import threading
import uuid
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

from core.models import Document

logger = logging.getLogger(__name__)

# ---- 集合与作用域 ----
MODEL_COLLECTION = 'ai_models'
SCOPE_GLOBAL = 'global'
SCOPE_USER = 'user'
SCOPE_CHOICES = (SCOPE_GLOBAL, SCOPE_USER)

# ---- 数量上限（可被 settings.AI_MODEL_LIMITS 覆盖）----
DEFAULT_MODEL_LIMITS = {
    SCOPE_GLOBAL: 10,   # 全局模型：管理员在后台最多添加 10 个
    SCOPE_USER: 5,      # 每个小程序用户最多添加 5 个自有模型
}

# ---- Provider 预设（前端下拉，可被 settings.AI_PROVIDER_PRESETS 覆盖）----
DEFAULT_PROVIDER_PRESETS = [
    {
        'key': 'openai', 'name': 'OpenAI',
        'apiUrl': 'https://api.openai.com/v1/chat/completions',
        'models': ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini', 'gpt-3.5-turbo'],
    },
    {
        'key': 'deepseek', 'name': 'DeepSeek',
        'apiUrl': 'https://api.deepseek.com/v1/chat/completions',
        'models': ['deepseek-chat', 'deepseek-reasoner'],
    },
    {
        'key': 'qwen', 'name': '通义千问',
        'apiUrl': 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        'models': ['qwen-plus', 'qwen-turbo', 'qwen-max'],
    },
    {
        'key': 'moonshot', 'name': 'Moonshot 月之暗面',
        'apiUrl': 'https://api.moonshot.cn/v1/chat/completions',
        'models': ['moonshot-v1-8k', 'moonshot-v1-32k'],
    },
    {
        'key': 'zhipu', 'name': '智谱 GLM',
        'apiUrl': 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
        'models': ['glm-4-flash', 'glm-4-air', 'glm-4'],
    },
    {
        'key': 'custom', 'name': '自定义 / 兼容 OpenAI 协议',
        'apiUrl': '', 'models': [],
    },
]

# ---- 功能级配置目录（前端「AI 功能级配置」区块使用）----
# 与 settings.AI_FEATURE_CONFIG_DEFAULTS 的 key 保持一一对应；
# 每个功能可在后台为其指定「使用哪个已登记模型」，从而按功能分流调用不同模型。
DEFAULT_FEATURE_CATALOG = [
    {'key': 'question_analyze', 'label': 'AI 题目解析',
     'desc': '自动分析题目知识点、难度、题型及答案解析'},
    {'key': 'exam_compose', 'label': 'AI 智能组卷',
     'desc': '根据题型分布与难度要求自动生成试卷'},
    {'key': 'ai_grade', 'label': 'AI 智能判卷',
     'desc': '对主观题自动评分并生成评语，低置信度转人工复核'},
    {'key': 'exam_analyze', 'label': 'AI 试卷分析',
     'desc': '汇总考试数据，生成成绩分布与薄弱知识点分析'},
    {'key': 'learning_profile', 'label': 'AI 答题记录分析',
     'desc': '分析个人答题记录，生成学习能力画像'},
    {'key': 'review_recommend', 'label': 'AI 错题复习推荐',
     'desc': '依据错题与掌握度推荐复习顺序与重点'},
    {'key': 'article_enhance', 'label': 'AI 文章撰写增强',
     'desc': '辅助撰写 / 润色备考文章'},
    {'key': 'kb_qa', 'label': 'AI 知识库问答',
     'desc': '基于平台知识库与已索引文章的 RAG 智能问答'},
    {'key': 'auto_tag', 'label': 'AI 题目自动标签',
     'desc': '自动为题目推荐知识点 / 难度 / 题型标签'},
    {'key': 'excel_validate', 'label': 'AI Excel 智能校验',
     'desc': '校对导入数据格式与内容（Excel 导入场景）'},
    {'key': 'learning_report', 'label': 'AI 学习报告',
     'desc': '生成周期性学习报告'},
    {'key': 'cs_chat', 'label': 'AI 智能客服',
     'desc': '解答平台使用与备考常见问题'},
]

_MASK_PREFIX = '****'


# --------------------------------------------------------------------------
# 线程局部：当前生效模型（供缓存哈希隔离 + LLM 调用共用一次解析结果）
# --------------------------------------------------------------------------

_local = threading.local()


def set_active_model(model):
    """设置当前线程的生效模型（传 resolve_model 得到的 dict）。"""
    _local.model = model if isinstance(model, dict) else None


def get_active_model():
    """读取当前线程的生效模型 dict；无则返回 None。"""
    return getattr(_local, 'model', None)


def get_active_signature():
    """读取当前线程生效模型的缓存签名；无则返回空串。"""
    return model_signature(get_active_model())


def clear_active_model():
    _local.model = None


class use_model:
    """上下文管理器：在作用域内固定使用某个模型。

    传入 ``model``（已解析的 dict）优先；否则用 ``model_id`` / ``openid`` / ``func_name`` 解析。
    该区间内的缓存哈希会带上模型签名，LLM 调用也会复用同一个模型。

    用法::

        with use_model(model_id, openid, func_name='kb_qa'):
            service.ask(...)
    """

    def __init__(self, model_id=None, openid=None, model=None, func_name=None):
        self._resolved = model
        if self._resolved is None:
            self._resolved, _err = resolve_model(
                model_id=model_id, openid=openid, func_name=func_name)
        self._previous = None

    def __enter__(self):
        self._previous = get_active_model()
        set_active_model(self._resolved)
        return self._resolved

    def __exit__(self, exc_type, exc, tb):
        set_active_model(self._previous)
        return False


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

def get_limits():
    """返回数量上限配置 dict。"""
    limits = getattr(settings, 'AI_MODEL_LIMITS', None) or DEFAULT_MODEL_LIMITS
    return dict(limits)


def get_presets():
    """返回 Provider 预设列表。"""
    return list(getattr(settings, 'AI_PROVIDER_PRESETS', None) or DEFAULT_PROVIDER_PRESETS)


def get_feature_catalog():
    """返回「AI 功能级配置」的功能目录。

    以 settings.AI_FEATURE_CONFIG_DEFAULTS 的 key 为准做一次对齐，
    避免新增功能后前端目录滞后（目录里有而默认值没有的条目会被保留）。
    """
    catalog = [dict(item) for item in
               (getattr(settings, 'AI_FEATURE_CATALOG', None) or DEFAULT_FEATURE_CATALOG)]
    known = {item['key'] for item in catalog}
    defaults = getattr(settings, 'AI_FEATURE_CONFIG_DEFAULTS', {}) or {}
    for key in defaults:
        if key not in known:
            catalog.append({'key': key, 'label': key, 'desc': ''})
    return catalog


def mask_key(key):
    """API Key 脱敏：仅保留末 4 位。"""
    if not key or not isinstance(key, str):
        return ''
    if len(key) <= 4:
        return _MASK_PREFIX
    return _MASK_PREFIX + key[-4:]


def is_masked_key(key):
    """判断传入的 Key 是否为脱敏占位（表示「保持原值不变」）。"""
    return bool(key) and isinstance(key, str) and key.startswith(_MASK_PREFIX)


def _new_doc_id():
    return 'aim-' + uuid.uuid4().hex[:12]


def _now_iso():
    return timezone.now().isoformat()


def _to_text(value, default=''):
    if value is None:
        return default
    return str(value).strip()


def _to_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def validate_api_url(api_url):
    """校验 API 地址：协议 + 禁止内网（SSRF 基础防护）。返回错误信息或 None。"""
    url = _to_text(api_url)
    if not url:
        return 'API 地址不能为空'
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return 'API 地址协议不合法，仅支持 http/https'
    hostname = parsed.hostname or ''
    if not hostname:
        return 'API 地址格式不合法'
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            return 'API 地址不允许指向内网地址'
    except ValueError:
        if hostname.lower() in ('localhost', '0.0.0.0'):
            return 'API 地址不允许指向内网地址'
    return None


def model_signature(model):
    """模型签名：用于缓存哈希隔离，形如 ``<model_id>:<model_name>``。"""
    if not isinstance(model, dict):
        return ''
    mid = _to_text(model.get('model_id') or model.get('_id'))
    name = _to_text(model.get('model'))
    if not mid and not name:
        return ''
    return '%s:%s' % (mid, name)


# --------------------------------------------------------------------------
# 查询
# --------------------------------------------------------------------------

def _data_of(doc):
    data = dict(doc.data or {})
    data['_id'] = _to_text(data.get('_id') or doc.doc_id or doc.pk)
    if not data.get('doc_id'):
        data['doc_id'] = data['_id']
    if not data.get('model_id'):
        data['model_id'] = data['_id']
    return data


def _all_models():
    docs = Document.objects.filter(collection=MODEL_COLLECTION).order_by('id')
    return [_data_of(d) for d in docs]


def list_models(scope=None, owner_key=None, include_disabled=True):
    """列出模型条目。

    Args:
        scope:         ``'global'`` / ``'user'`` / None（全部）
        owner_key:     scope='user' 时的用户标识（openid）
        include_disabled: 是否包含已禁用的模型
    """
    items = []
    for m in _all_models():
        m_scope = m.get('scope') or SCOPE_GLOBAL
        if scope and m_scope != scope:
            continue
        if scope == SCOPE_USER and _to_text(owner_key) and _to_text(m.get('ownerKey')) != _to_text(owner_key):
            continue
        if not include_disabled and not m.get('enabled', True):
            continue
        items.append(m)
    items.sort(key=lambda x: (0 if x.get('isDefault') else 1, x.get('sort', 0), x.get('createTime', '')))
    return items


def list_accessible_models(openid=None):
    """列出某调用者可用的模型：全局启用的 + 本人启用的。"""
    openid = _to_text(openid)
    result = []
    for m in _all_models():
        if not m.get('enabled', True):
            continue
        m_scope = m.get('scope') or SCOPE_GLOBAL
        if m_scope == SCOPE_GLOBAL:
            result.append(m)
        elif m_scope == SCOPE_USER and openid and _to_text(m.get('ownerKey')) == openid:
            result.append(m)
    result.sort(key=lambda x: (0 if x.get('isDefault') else 1, x.get('sort', 0), x.get('createTime', '')))
    return result


def get_model(model_id):
    """按 model_id / doc_id / pk 获取模型条目（dict）。"""
    key = _to_text(model_id)
    if not key:
        return None
    doc = Document.objects.filter(collection=MODEL_COLLECTION, doc_id=key).first()
    if not doc and key.isdigit():
        doc = Document.objects.filter(collection=MODEL_COLLECTION, pk=int(key), doc_id=None).first()
    if not doc:
        return None
    return _data_of(doc)


def count_models(scope, owner_key=None):
    return len(list_models(scope=scope, owner_key=owner_key, include_disabled=True))


def get_default_model(scope=SCOPE_GLOBAL, owner_key=None):
    """取某作用域的默认模型；无 isDefault 时回退为该作用域首个条目。"""
    for m in list_models(scope=scope, owner_key=owner_key, include_disabled=True):
        if m.get('isDefault'):
            return m
    candidates = list_models(scope=scope, owner_key=owner_key, include_disabled=True)
    return candidates[0] if candidates else None


# ---- 用户首选模型指针（允许把某个「全局模型」设为个人默认）----

PREF_COLLECTION = 'ai_model_prefs'


def get_user_preference(openid):
    """读取某用户的首选模型指针。返回 dict 或 None。"""
    openid = _to_text(openid)
    if not openid:
        return None
    doc = Document.objects.filter(collection=PREF_COLLECTION, doc_id=openid).first()
    if not doc:
        return None
    data = dict(doc.data or {})
    if not _to_text(data.get('preferredModelId')):
        return None
    return data


def clear_user_preference(openid):
    openid = _to_text(openid)
    if openid:
        Document.objects.filter(collection=PREF_COLLECTION, doc_id=openid).delete()


def set_user_preferred_global(openid, model_id):
    """把某个全局模型设为用户的首选默认。返回 (model, error)。"""
    openid = _to_text(openid)
    if not openid:
        return None, '缺少用户标识'
    model = get_model(model_id)
    if not model:
        return None, '模型不存在'
    if (model.get('scope') or SCOPE_GLOBAL) != SCOPE_GLOBAL:
        return None, '仅可把全局模型设为首选'
    if not model.get('enabled', True):
        return None, '该模型已禁用'

    doc = Document.objects.filter(collection=PREF_COLLECTION, doc_id=openid).first()
    payload = {
        'openid': openid,
        'preferredModelId': model['_id'],
        'updateTime': _now_iso(),
    }
    if doc:
        doc.data = payload
        doc.save(update_fields=['data'])
    else:
        Document.objects.create(collection=PREF_COLLECTION, doc_id=openid, data=payload)
    return model, None


def get_user_preferred_model(openid):
    """按用户首选指针解析出模型（校验仍可用）。"""
    pref = get_user_preference(openid)
    if not pref:
        return None
    model = get_model(pref.get('preferredModelId'))
    if not model or not model.get('enabled', True):
        return None
    if (model.get('scope') or SCOPE_GLOBAL) != SCOPE_GLOBAL:
        return None
    return model


def to_client(model, mask=True):
    """转成前端安全结构（默认脱敏 apiKey）。"""
    if not model:
        return None
    data = dict(model)
    raw_key = _to_text(model.get('apiKey'))
    if mask:
        data['apiKey'] = mask_key(raw_key)
        data['apiKeyMasked'] = data['apiKey']
    else:
        data['apiKey'] = raw_key
        data['apiKeyMasked'] = mask_key(raw_key)
    data['hasApiKey'] = bool(raw_key)
    data['scope'] = data.get('scope') or SCOPE_GLOBAL
    data['ownerKey'] = data.get('ownerKey', '')
    data['enabled'] = bool(data.get('enabled', True))
    data['isDefault'] = bool(data.get('isDefault'))
    return data


# --------------------------------------------------------------------------
# 写入
# --------------------------------------------------------------------------

def _normalize_payload(payload, existing=None):
    """规范化输入字段；existing 用于「脱敏 Key 保持原值」。"""
    base = dict(existing or {})
    result = {
        'name': _to_text(payload.get('name', base.get('name'))),
        'provider': _to_text(payload.get('provider', base.get('provider'))) or 'custom',
        'apiUrl': _to_text(payload.get('apiUrl', base.get('apiUrl'))),
        'model': _to_text(payload.get('model', base.get('model'))),
        'temperature': _to_float(payload.get('temperature', base.get('temperature', 0.7)), 0.7),
        'maxTokens': _to_int(payload.get('maxTokens', base.get('maxTokens', 2000)), 2000),
        'remark': _to_text(payload.get('remark', base.get('remark'))),
        'enabled': bool(payload.get('enabled', base.get('enabled', True))),
    }
    # apiKey：脱敏格式表示保持原值
    if 'apiKey' in payload:
        key = payload.get('apiKey')
        if is_masked_key(key):
            result['apiKey'] = base.get('apiKey', '')
        else:
            result['apiKey'] = _to_text(key)
    else:
        result['apiKey'] = base.get('apiKey', '')
    return result


def _validate_fields(data):
    if not data.get('name'):
        return '模型名称不能为空'
    if not data.get('apiUrl'):
        return 'API 地址不能为空'
    err = validate_api_url(data.get('apiUrl'))
    if err:
        return err
    if not data.get('apiKey'):
        return 'API Key 不能为空'
    if not data.get('model'):
        return '模型标识（model）不能为空'
    if data.get('temperature') is None or not (0 <= data['temperature'] <= 2):
        return 'temperature 需在 0~2 之间'
    if not data.get('maxTokens') or data['maxTokens'] < 1:
        return 'maxTokens 需为正整数'
    return None


def create_model(payload, scope=SCOPE_GLOBAL, owner_key=''):
    """新增模型条目，返回 (model_dict, error)。

    上限校验：全局 ≤ AI_MODEL_LIMITS['global']；单用户 ≤ AI_MODEL_LIMITS['user']。
    首个条目自动设为默认。
    """
    scope = scope if scope in SCOPE_CHOICES else SCOPE_GLOBAL
    owner_key = _to_text(owner_key)
    if scope == SCOPE_USER and not owner_key:
        return None, '缺少用户标识'

    limits = get_limits()
    limit = limits.get(scope, 0)
    if limit and count_models(scope, owner_key) >= limit:
        scope_label = '全局' if scope == SCOPE_GLOBAL else '个人'
        return None, '%s模型数量已达上限（最多 %d 个）' % (scope_label, limit)

    data = _normalize_payload(payload)
    err = _validate_fields(data)
    if err:
        return None, err

    existing = list_models(scope=scope, owner_key=owner_key, include_disabled=True)
    now = _now_iso()
    doc_id = _new_doc_id()
    data.update({
        'scope': scope,
        'ownerKey': owner_key,
        'isDefault': not existing,   # 首个自动设为默认
        'sort': len(existing),
        'createTime': now,
        'updateTime': now,
    })
    doc = Document.objects.create(collection=MODEL_COLLECTION, doc_id=doc_id, data=data)
    data['_id'] = doc_id
    data['doc_id'] = doc_id
    data['model_id'] = doc_id
    return data, None


def _can_manage(model, scope, owner_key):
    """校验管理权限：全局模型仅管理员；用户模型仅本人。"""
    m_scope = model.get('scope') or SCOPE_GLOBAL
    if scope == SCOPE_GLOBAL:
        return m_scope == SCOPE_GLOBAL
    if scope == SCOPE_USER:
        return m_scope == SCOPE_USER and _to_text(model.get('ownerKey')) == _to_text(owner_key)
    return False


def update_model(model_id, payload, scope=SCOPE_GLOBAL, owner_key=''):
    """更新模型条目，返回 (model_dict, error)。"""
    model = get_model(model_id)
    if not model:
        return None, '模型不存在'
    if not _can_manage(model, scope, owner_key):
        return None, '无权操作该模型'

    merged = _normalize_payload(payload, existing=model)
    err = _validate_fields(merged)
    if err:
        return None, err

    doc = Document.objects.filter(collection=MODEL_COLLECTION, doc_id=model['_id']).first()
    if not doc:
        return None, '模型不存在'
    data = dict(doc.data or {})
    data.update(merged)
    data['updateTime'] = _now_iso()
    doc.data = data
    doc.save(update_fields=['data'])

    merged['_id'] = model['_id']
    merged['doc_id'] = model['_id']
    merged['model_id'] = model['_id']
    merged['scope'] = model.get('scope') or SCOPE_GLOBAL
    merged['ownerKey'] = model.get('ownerKey', '')
    merged['isDefault'] = bool(model.get('isDefault'))
    merged['createTime'] = model.get('createTime', '')
    return merged, None


def delete_model(model_id, scope=SCOPE_GLOBAL, owner_key=''):
    """删除模型条目，返回 (deleted_bool, error)。

    若删除的是默认模型，且该作用域仍有其它模型，则自动把第一个设为默认。
    """
    model = get_model(model_id)
    if not model:
        return False, '模型不存在'
    if not _can_manage(model, scope, owner_key):
        return False, '无权操作该模型'

    Document.objects.filter(collection=MODEL_COLLECTION, doc_id=model['_id']).delete()

    if model.get('isDefault'):
        remaining = list_models(
            scope=model.get('scope') or SCOPE_GLOBAL,
            owner_key=model.get('ownerKey', ''),
            include_disabled=True,
        )
        if remaining:
            set_default(remaining[0]['_id'], scope=scope, owner_key=owner_key)
    return True, None


def set_default(model_id, scope=SCOPE_GLOBAL, owner_key=''):
    """把某模型设为所在作用域的默认模型（同作用域内互斥），返回 (model, error)。"""
    model = get_model(model_id)
    if not model:
        return None, '模型不存在'
    if not _can_manage(model, scope, owner_key):
        return None, '无权操作该模型'

    target_scope = model.get('scope') or SCOPE_GLOBAL
    target_owner = model.get('ownerKey', '')
    for m in list_models(scope=target_scope, owner_key=target_owner, include_disabled=True):
        should_default = (m['_id'] == model['_id'])
        if bool(m.get('isDefault')) == should_default:
            continue
        doc = Document.objects.filter(collection=MODEL_COLLECTION, doc_id=m['_id']).first()
        if not doc:
            continue
        data = dict(doc.data or {})
        data['isDefault'] = should_default
        data['updateTime'] = _now_iso()
        doc.data = data
        doc.save(update_fields=['data'])

    # 设为「自有模型默认」时，清除可能存在的「首选全局模型」指针，保证语义唯一
    if target_scope == SCOPE_USER and target_owner:
        clear_user_preference(target_owner)

    refreshed = get_model(model['_id'])
    return refreshed, None


# --------------------------------------------------------------------------
# 运行时解析
# --------------------------------------------------------------------------

def _legacy_config():
    """读取旧版单配置（ai_config），用于兼容兜底。"""
    from .views_ai import _get_ai_config
    config, _ = _get_ai_config()
    return {
        'model_id': '',
        'name': '默认（全局单配置）',
        'provider': 'legacy',
        'apiUrl': _to_text(config.get('apiUrl')),
        'apiKey': _to_text(config.get('apiKey')),
        'model': _to_text(config.get('model')) or 'gpt-4o-mini',
        'temperature': _to_float(config.get('temperature'), 0.7),
        'maxTokens': _to_int(config.get('maxTokens'), 2000),
        'scope': 'legacy',
        'ownerKey': '',
        'isDefault': True,
        'source': 'legacy',
    }


def _match_model_by_ref(ref):
    """按 model_id → 模型标识(model) → 名称(name) 的顺序查找启用中的模型条目。"""
    ref = _to_text(ref)
    if not ref:
        return None
    model = get_model(ref)
    if model:
        return model
    for m in list_models(include_disabled=False):
        if _to_text(m.get('model')) == ref or _to_text(m.get('name')) == ref:
            return m
    return None


def resolve_feature_model(func_name):
    """解析「AI 功能级配置」为该功能指定的模型。

    读取 ``ai_config.feature_config[func_name].model``，其取值可能是：
      * 已登记模型的 ``model_id``（新后台下拉存储的就是 id）；
      * 已登记模型的「模型标识 / 名称」字符串（兼容旧数据，如 ``gpt-4o``）。

    Returns:
        (model_dict, name_override)
        - 命中启用中的已登记模型 → ``(model_dict, '')``
        - 未命中任何登记模型（视为旧版「模型名称覆盖」）→ ``(None, '模型名')``
        - 未配置 / 命中的模型已禁用 → ``(None, '')``
    """
    func_name = _to_text(func_name)
    if not func_name:
        return None, ''
    try:
        from .views_ai import _get_ai_config
        ai_config, _ = _get_ai_config()
    except Exception:
        return None, ''
    func_config = (ai_config.get('feature_config') or {}).get(func_name) or {}
    if not isinstance(func_config, dict):
        return None, ''
    ref = _to_text(func_config.get('model'))
    if not ref:
        return None, ''
    model = _match_model_by_ref(ref)
    if model:
        if model.get('enabled', True):
            return model, ''
        # 命中了但已禁用：不回退为「名称覆盖」，避免误用其它供应商的模型
        return None, ''
    return None, ref


def resolve_model(model_id=None, openid=None, func_name=None):
    """解析本次调用实际使用的模型。

    优先级：
    1. 显式指定的 ``model_id``（请求级选择，最高优先）
    2. 功能级配置为该功能指定的模型（``feature_config[func_name].model``）
    3. 调用者（openid）的默认模型
    4. 全局默认模型
    5. 兼容兜底：旧的 ``ai_config`` 顶层 apiKey/apiUrl/model

    Returns:
        (model_dict, error)。model_dict 含 ``source`` 字段说明来源；
        ``source`` 取值：explicit / feature / user-default / global-default / legacy。
        error 非空时表示显式模型不可用且无任何兜底（旧配置也未启用）。
    """
    openid = _to_text(openid)
    explicit_id = _to_text(model_id)

    if explicit_id:
        model = get_model(explicit_id)
        if model and model.get('enabled', True):
            m_scope = model.get('scope') or SCOPE_GLOBAL
            accessible = (m_scope == SCOPE_GLOBAL) or (
                m_scope == SCOPE_USER and openid and _to_text(model.get('ownerKey')) == openid
            )
            if accessible:
                result = dict(model)
                result['source'] = 'explicit'
                return result, None
            # 无权访问 → 记录并回退
            logger.warning(
                'model_id=%s 对 openid=%s 不可访问，回退默认模型', explicit_id, openid)
        else:
            logger.warning(
                'model_id=%s 不存在或已禁用，回退默认模型', explicit_id)

    # 功能级配置指定的模型（管理员在「AI 功能级配置」中为该功能选定）
    feature_model, _feature_name = resolve_feature_model(func_name)
    if feature_model:
        result = dict(feature_model)
        result['source'] = 'feature'
        return result, None

    if openid:
        # 优先使用「用户首选全局模型」指针
        preferred = get_user_preferred_model(openid)
        if preferred:
            result = dict(preferred)
            result['source'] = 'user-default'
            return result, None
        user_default = get_default_model(scope=SCOPE_USER, owner_key=openid)
        if user_default and user_default.get('enabled', True):
            result = dict(user_default)
            result['source'] = 'user-default'
            return result, None

    global_default = get_default_model(scope=SCOPE_GLOBAL)
    if global_default and global_default.get('enabled', True):
        result = dict(global_default)
        result['source'] = 'global-default'
        return result, None

    legacy = _legacy_config()
    if legacy.get('apiKey'):
        return legacy, None

    return None, '未配置任何可用模型，请先在「AI 模型配置」中添加模型'


def build_call_config(model, func_name=None, explicit=False):
    """把模型条目 + 功能级配置合成为 ``_call_llm`` 所需的调用参数。

    Args:
        model:      resolve_model 得到的模型 dict
        func_name:  功能名（用于叠加 ai_config.feature_config 覆盖）
        explicit:   本次是否为显式指定模型；显式指定时功能级 model 名称不覆盖

    Returns:
        (call_config, error)
    """
    if not model:
        return None, '未配置可用模型'

    call_config = {
        'apiUrl': model.get('apiUrl'),
        'apiKey': model.get('apiKey'),
        'model': model.get('model'),
        'temperature': _to_float(model.get('temperature'), 0.7),
        'maxTokens': _to_int(model.get('maxTokens'), 2000),
    }

    if func_name:
        # 功能级配置合并优先级（低→高）：
        #   1. settings.AI_FEATURE_CONFIG_DEFAULTS（代码级默认值）
        #   2. ai_config.feature_config（数据库用户配置，覆盖默认值）
        # 数据库中 feature_config 可能为空 {}，此时必须回退到 settings 默认值，
        # 否则模型条目自身的 maxTokens（如 2000）会直接生效，
        # 而 complex 功能（试卷分析/组卷）需要 4000 tokens。
        settings_defaults = getattr(settings, 'AI_FEATURE_CONFIG_DEFAULTS', {}) or {}
        func_defaults = settings_defaults.get(func_name, {})
        if not isinstance(func_defaults, dict):
            func_defaults = {}

        try:
            from .views_ai import _get_ai_config
            ai_config, _ = _get_ai_config()
            db_feature_config = (ai_config.get('feature_config') or {}).get(func_name) or {}
        except Exception:
            db_feature_config = {}
        if not isinstance(db_feature_config, dict):
            db_feature_config = {}

        # 合并：DB 覆盖 settings 默认值（DB 有值时优先）
        merged = dict(func_defaults)
        merged.update(db_feature_config)

        if merged.get('temperature') is not None:
            call_config['temperature'] = _to_float(
                merged.get('temperature'), call_config['temperature'])
        if merged.get('max_tokens'):
            call_config['maxTokens'] = _to_int(
                merged.get('max_tokens'), call_config['maxTokens'])
        # 仅「旧版单配置」允许功能级覆盖模型名称；一旦登记了模型条目，
        # 模型名称一律以条目为准，避免出现「模型名与供应商不匹配」的调用。
        if model.get('source') == 'legacy' and not explicit and merged.get('model'):
            call_config['model'] = _to_text(merged.get('model'))

    if not call_config.get('apiUrl'):
        return None, 'API 地址未配置'
    if not call_config.get('apiKey'):
        return None, 'API Key 未配置'
    return call_config, None


def resolve_llm_call(model_id=None, openid=None, func_name=None):
    """解析出一次 LLM 调用所需的完整参数。

    Returns:
        (call_config, model_dict, error)
    """
    model, err = resolve_model(model_id=model_id, openid=openid, func_name=func_name)
    if err or not model:
        return None, None, err or '模型解析失败'
    call_config, err = build_call_config(
        model, func_name=func_name, explicit=bool(_to_text(model_id)))
    if err:
        return None, model, err
    return call_config, model, None


def model_meta(openid=None):
    """模型配置元信息：数量上限、当前使用量、Provider 预设、默认模型、说明。"""
    limits = get_limits()
    global_models = list_models(scope=SCOPE_GLOBAL, include_disabled=True)
    user_models = list_models(scope=SCOPE_USER, owner_key=openid, include_disabled=True) if openid else []
    default_model = get_default_model(scope=SCOPE_GLOBAL)
    user_default_id = ''
    if openid:
        preferred = get_user_preferred_model(openid)
        if preferred:
            user_default_id = preferred['_id']
        else:
            user_default = get_default_model(scope=SCOPE_USER, owner_key=openid)
            user_default_id = (user_default or {}).get('_id', '')

    return {
        'limits': limits,
        'presets': get_presets(),
        'features': get_feature_catalog(),
        'usage': {
            'global': len(global_models),
            'user': len(user_models),
            'global_max': limits.get(SCOPE_GLOBAL, 0),
            'user_max': limits.get(SCOPE_USER, 0),
        },
        'defaultModelId': (default_model or {}).get('_id', ''),
        'userDefaultModelId': user_default_id,
        'effectTiming': '保存后立即写入数据库，下一次 AI 调用即生效（无需重启）；缓存按模型隔离，切换模型不会命中旧模型结果。',
        'resolutionOrder': [
            '请求显式指定的模型（model_id）',
            '功能级配置为该功能指定的模型',
            '当前用户的默认模型',
            '全局默认模型',
            '兼容兜底：旧版全局单配置',
        ],
    }
