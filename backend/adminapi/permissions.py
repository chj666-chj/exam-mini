"""角色权限点定义与鉴权装饰器。

权限点采用「资源.动作」命名，管理端菜单、按钮与后端校验共用同一份定义，
避免出现「前端按钮隐藏了但接口仍可调用」的越权问题。
"""
import functools
import json
import secrets

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .responses import ErrorCode, fail

# ---- 权限点定义：(代码, 名称, 分组) ----
PERMISSION_DEFS = [
    ('dashboard.view', '查看数据看板', '数据看板'),
    ('user.view', '查看小程序用户', '用户管理'),
    ('user.manage', '编辑/停用小程序用户', '用户管理'),
    ('exam.view', '查看考试', '考试管理'),
    ('exam.manage', '编辑考试', '考试管理'),
    ('subject.view', '查看科目', '科目管理'),
    ('subject.manage', '编辑科目', '科目管理'),
    ('question.view', '查看题目', '题目管理'),
    ('question.manage', '编辑题目', '题目管理'),
    ('question.import', '批量导入题目', '题目管理'),
    ('tag.view', '查看标签', '标签管理'),
    ('tag.manage', '编辑标签与绑定', '标签管理'),
    ('record.view', '查看答题记录', '答题记录'),
    ('record.manage', '编辑答题记录', '答题记录'),
    ('note.view', '查看错题笔记', '错题笔记'),
    ('note.manage', '编辑错题笔记', '错题笔记'),
    ('knowledge.view', '查看知识库', '知识库管理'),
    ('knowledge.manage', '编辑知识库', '知识库管理'),
    ('studynote.view', '查看学习笔记', '学习笔记'),
    ('studynote.manage', '编辑学习笔记', '学习笔记'),
    ('article.view', '查看文章', '文章管理'),
    ('article.manage', '编辑文章', '文章管理'),
    ('article.audit', '审核文章', '文章管理'),
    ('ai.config', 'AI配置管理', 'AI设置'),
    ('ai.use', '使用AI辅助', 'AI设置'),
    ('ai.analyze', 'AI题目解析', 'AI设置'),
    ('ai.compose', 'AI智能组卷', 'AI设置'),
    ('ai.grade', 'AI智能判卷', 'AI设置'),
    ('ai.report', 'AI分析报告', 'AI设置'),
    ('ai.recommend', 'AI推荐管理', 'AI设置'),
    ('ai.job.view', 'AI任务查看', 'AI设置'),
    ('data.view', '浏览原始数据集合', '数据浏览'),
    ('admin.view', '查看管理员与角色', '系统管理'),
    ('admin.manage', '编辑管理员与角色', '系统管理'),
]

PERMISSION_CODES = [p[0] for p in PERMISSION_DEFS]

# 内置角色默认权限
DEFAULT_ROLE_PERMISSIONS = {
    'superadmin': list(PERMISSION_CODES),
    'operator': [
        'dashboard.view',
        'user.view', 'user.manage',
        'exam.view', 'exam.manage',
        'subject.view', 'subject.manage',
        'question.view', 'question.manage', 'question.import',
        'tag.view', 'tag.manage',
        'record.view', 'record.manage',
        'note.view', 'note.manage',
        'knowledge.view', 'knowledge.manage',
        'studynote.view', 'studynote.manage',
        'data.view',
        'article.view', 'article.manage', 'article.audit',
        'ai.config', 'ai.use',
        'ai.analyze', 'ai.compose', 'ai.grade',
        'ai.report', 'ai.recommend', 'ai.job.view',
    ],
    'viewer': [
        'dashboard.view',
        'user.view', 'exam.view', 'subject.view',
        'question.view', 'tag.view', 'record.view', 'note.view',
        'knowledge.view', 'studynote.view',
        'data.view',
        'article.view',
        'ai.job.view',
    ],
}


def all_permissions():
    return list(PERMISSION_CODES)


def is_valid_permission(code):
    return code in PERMISSION_CODES


def permission_options():
    """返回按分组组织的权限点（供前端角色配置使用）。"""
    groups = {}
    for code, name, group in PERMISSION_DEFS:
        groups.setdefault(group, []).append({'code': code, 'name': name})
    return [{'group': g, 'items': items} for g, items in groups.items()]


# ---- 令牌 ----
TOKEN_HEADER_CANDIDATES = ('HTTP_AUTHORIZATION',)


def _extract_token(request):
    """从 Authorization: Bearer <token> 或 X-Admin-Token 中提取令牌。"""
    auth = request.META.get('HTTP_AUTHORIZATION', '')
    if auth:
        parts = auth.split()
        if len(parts) == 2 and parts[0].lower() == 'bearer':
            return parts[1]
        if len(parts) == 1:
            return parts[0]
    return request.headers.get('X-Admin-Token') or ''


def issue_token(user, ttl_hours=12):
    from .models import AdminToken
    token = secrets.token_hex(32)
    expires_at = timezone.now() + timezone.timedelta(hours=ttl_hours)
    obj = AdminToken.objects.create(user=user, token=token, expires_at=expires_at)
    return obj


def get_request_admin(request):
    """解析请求中的管理员。返回 (user, error_response)。"""
    from .models import AdminToken
    token = _extract_token(request)
    if not token:
        return None, fail(ErrorCode.UNAUTHORIZED, '未登录或缺少令牌')
    try:
        obj = AdminToken.objects.select_related('user', 'user__role').get(token=token)
    except AdminToken.DoesNotExist:
        return None, fail(ErrorCode.UNAUTHORIZED, '令牌无效，请重新登录')
    if obj.is_expired:
        obj.delete()
        return None, fail(ErrorCode.TOKEN_EXPIRED, '令牌已过期，请重新登录')
    user = obj.user
    if not user.is_active:
        return None, fail(ErrorCode.ACCOUNT_DISABLED, '账号已停用，请联系超级管理员')
    return user, None


def client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '') or ''


def require_login(view_func):
    """仅要求登录，不校验具体权限点。"""

    @functools.wraps(view_func)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        user, err = get_request_admin(request)
        if err:
            return err
        request.admin_user = user
        return view_func(request, *args, **kwargs)

    return wrapper


def require_perms(*perms, methods=None):
    """要求登录并具备全部权限点。

    methods: 可选，限定哪些 HTTP 方法需要 `manage` 级校验；
    缺省对所有方法校验传入的权限点。
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        @csrf_exempt
        def wrapper(request, *args, **kwargs):
            user, err = get_request_admin(request)
            if err:
                return err
            needed = perms
            if methods and request.method.upper() not in methods:
                # 例如列表接口 GET 只需 *.view，写操作才需要 *.manage
                needed = tuple(p for p in perms if not p.endswith('.manage'))
            if needed and not user.is_superuser:
                missing = [p for p in needed if p not in user.permissions]
                if missing:
                    return fail(ErrorCode.FORBIDDEN, f'无操作权限（缺少 {", ".join(missing)}）')
            request.admin_user = user
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def json_body(request):
    """解析 JSON 请求体；返回 (data, error_response)。"""
    if not request.body:
        return {}, None
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return None, fail(ErrorCode.PARAM_ERROR, '请求体不是合法 JSON')
    if not isinstance(data, dict):
        return None, fail(ErrorCode.PARAM_ERROR, '请求体必须是 JSON 对象')
    return data, None


def log_action(user, action, target='', detail='', ip=''):
    """记录操作日志（失败不影响主流程）。"""
    try:
        from .models import OperationLog
        OperationLog.objects.create(
            user=user,
            username=user.username if user else '',
            action=action,
            target=str(target)[:128],
            detail=str(detail)[:2000],
            ip=ip,
        )
    except Exception:
        pass


def not_found(message='资源不存在'):
    return fail(ErrorCode.NOT_FOUND, message)


def bad_request(message='参数错误'):
    return fail(ErrorCode.PARAM_ERROR, message)


def server_error(message='服务内部错误'):
    return fail(ErrorCode.SERVER_ERROR, message)


def json_ok(data=None, message='ok'):
    from .responses import ok
    return ok(data, message)
