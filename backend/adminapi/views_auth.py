"""管理端认证接口：登录 / 登出 / 当前账号 / 修改密码。"""
import time

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import permissions as perm
from .models import AdminToken, AdminUser
from .responses import ErrorCode, fail, ok

# 登录失败限流（使用 Django cache 后端，生产环境为 Redis，本地为 LocMem）
MAX_FAILS = 5
LOCK_SECONDS = 600
_LOGIN_FAIL_KEY = 'auth:login_fails:{username}'


def _is_locked(username):
    """检查用户是否因连续登录失败被锁定。"""
    key = _LOGIN_FAIL_KEY.format(username=username)
    count = cache.get(key, 0)
    return count >= MAX_FAILS


def _note_fail(username):
    """记录一次登录失败，递增计数器。"""
    key = _LOGIN_FAIL_KEY.format(username=username)
    try:
        # 尝试原子递增（Redis 后端支持）
        count = cache.incr(key)
    except ValueError:
        # key 不存在或后端不支持 incr，手动 get+set
        count = cache.get(key, 0) + 1
        cache.set(key, count, LOCK_SECONDS)
        return
    # 确保 TTL 设置（incr 不自动设 TTL）
    cache.expire(key, LOCK_SECONDS)


def _clear_fails(username):
    """登录成功后清除失败计数。"""
    cache.delete(_LOGIN_FAIL_KEY.format(username=username))


@csrf_exempt
def login(request):
    """POST /api/admin/auth/login/  {username, password}"""
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '请使用 POST 提交', http_status=405)
    body, err = perm.json_body(request)
    if err:
        return err
    username = str(body.get('username', '')).strip()
    password = str(body.get('password', ''))
    if not username or not password:
        return fail(ErrorCode.PARAM_ERROR, '账号与密码不能为空')
    if _is_locked(username):
        return fail(ErrorCode.FORBIDDEN, f'连续输错密码 {MAX_FAILS} 次，请 10 分钟后再试')

    try:
        user = AdminUser.objects.select_related('role').get(username=username)
    except AdminUser.DoesNotExist:
        _note_fail(username)
        return fail(ErrorCode.INVALID_CREDENTIALS, '账号或密码错误')

    if not user.check_password(password):
        _note_fail(username)
        return fail(ErrorCode.INVALID_CREDENTIALS, '账号或密码错误')
    if not user.is_active:
        return fail(ErrorCode.ACCOUNT_DISABLED, '账号已停用，请联系超级管理员')

    ttl = getattr(settings, 'ADMIN_TOKEN_TTL_HOURS', 12)
    token_obj = perm.issue_token(user, ttl_hours=ttl)
    user.last_login_at = timezone.now()
    user.last_login_ip = perm.client_ip(request)
    user.save(update_fields=['last_login_at', 'last_login_ip'])
    perm.log_action(user, 'auth.login', target=username, ip=user.last_login_ip)
    _clear_fails(username)

    return ok({
        'token': token_obj.token,
        'expires_at': token_obj.expires_at.strftime('%Y-%m-%d %H:%M:%S'),
        'user': user.to_client(),
    }, '登录成功')


@csrf_exempt
@perm.require_login
def logout(request):
    """POST /api/admin/auth/logout/"""
    token = perm._extract_token(request)
    AdminToken.objects.filter(token=token).delete()
    perm.log_action(request.admin_user, 'auth.logout')
    return ok(message='已退出登录')


@perm.require_login
def profile(request):
    """GET /api/admin/auth/profile/"""
    return ok(request.admin_user.to_client())


@csrf_exempt
@perm.require_login
def change_password(request):
    """POST /api/admin/auth/password/  {old_password, new_password}"""
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '请使用 POST 提交', http_status=405)
    body, err = perm.json_body(request)
    if err:
        return err
    old = str(body.get('old_password', ''))
    new = str(body.get('new_password', ''))
    if len(new) < 6:
        return fail(ErrorCode.PARAM_ERROR, '新密码至少 6 位')
    user = request.admin_user
    if not user.check_password(old):
        return fail(ErrorCode.INVALID_CREDENTIALS, '原密码不正确')
    user.set_password(new)
    user.save(update_fields=['password_hash'])
    # 修改密码后强制其它端重新登录
    AdminToken.objects.filter(user=user).exclude(token=perm._extract_token(request)).delete()
    perm.log_action(user, 'auth.change_password')
    return ok(message='密码修改成功')


@perm.require_login
def permission_tree(request):
    """GET /api/admin/auth/permissions/  返回权限点分组（角色配置用）"""
    return ok(perm.permission_options())
