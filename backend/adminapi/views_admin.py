"""管理员账号与角色权限管理接口。"""
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt

from . import permissions as perm
from .models import AdminToken, AdminUser, Role
from .responses import ErrorCode, fail, ok, paginate, parse_page

WRITE_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']


def _serialize_role(role):
    return {
        'id': role.pk,
        'code': role.code,
        'name': role.name,
        'description': role.description,
        'permissions': role.clean_permissions(),
        'is_system': role.is_system,
        'user_count': role.users.count(),
    }


@perm.require_perms('admin.view', 'admin.manage', methods=WRITE_METHODS)
def admin_list(request):
    """GET 列表 / POST 新增管理员"""
    if request.method not in ('GET', 'POST'):
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET / POST', http_status=405)
    if request.method == 'GET':
        page, page_size = parse_page(request)
        qs = AdminUser.objects.select_related('role').all()
        keyword = request.GET.get('keyword', '').strip()
        status = request.GET.get('status', '').strip()
        role = request.GET.get('role', '').strip()
        if keyword:
            qs = qs.filter(username__icontains=keyword) | qs.filter(nickname__icontains=keyword)
        if status:
            qs = qs.filter(status=status)
        if role:
            qs = qs.filter(role__code=role)
        total = qs.count()
        items = [u.to_client() for u in qs[(page - 1) * page_size: page * page_size]]
        return ok(paginate(items, total, page, page_size))

    body, err = perm.json_body(request)
    if err:
        return err
    username = str(body.get('username', '')).strip()
    password = str(body.get('password', ''))
    role_code = str(body.get('role', '')).strip()
    if not username or not password:
        return fail(ErrorCode.PARAM_ERROR, '账号与密码不能为空')
    if len(password) < 6:
        return fail(ErrorCode.PARAM_ERROR, '密码至少 6 位')
    if AdminUser.objects.filter(username=username).exists():
        return fail(ErrorCode.CONFLICT, '该登录账号已存在')
    role = Role.objects.filter(code=role_code).first() if role_code else None
    if role_code and not role:
        return fail(ErrorCode.PARAM_ERROR, '角色不存在')
    with transaction.atomic():
        user = AdminUser(
            username=username,
            nickname=str(body.get('nickname', '')).strip(),
            role=role,
            status=body.get('status') or AdminUser.STATUS_ACTIVE,
        )
        user.set_password(password)
        user.save()
    perm.log_action(request.admin_user, 'admin.create', target=username, ip=perm.client_ip(request))
    return ok(user.to_client(), '管理员创建成功')


@perm.require_perms('admin.view', 'admin.manage', methods=WRITE_METHODS)
def admin_detail(request, pk):
    try:
        user = AdminUser.objects.select_related('role').get(pk=pk)
    except AdminUser.DoesNotExist:
        return fail(ErrorCode.NOT_FOUND, '管理员不存在')

    if request.method == 'GET':
        return ok(user.to_client())

    if request.method in ('PUT', 'PATCH'):
        body, err = perm.json_body(request)
        if err:
            return err
        if 'nickname' in body:
            user.nickname = str(body.get('nickname', '')).strip()
        if 'status' in body:
            status = str(body.get('status'))
            if status not in (AdminUser.STATUS_ACTIVE, AdminUser.STATUS_DISABLED):
                return fail(ErrorCode.PARAM_ERROR, '状态值非法')
            if user.pk == request.admin_user.pk and status != AdminUser.STATUS_ACTIVE:
                return fail(ErrorCode.PARAM_ERROR, '不能停用当前登录的账号')
            if user.is_superuser and status != AdminUser.STATUS_ACTIVE:
                others = AdminUser.objects.filter(
                    role__code='superadmin', status=AdminUser.STATUS_ACTIVE
                ).exclude(pk=user.pk).count()
                if others == 0:
                    return fail(ErrorCode.PARAM_ERROR, '至少保留一个启用的超级管理员')
            user.status = status
        if 'role' in body:
            if user.pk == request.admin_user.pk:
                return fail(ErrorCode.PARAM_ERROR, '不能修改自己的角色')
            role = Role.objects.filter(code=str(body.get('role'))).first()
            if not role:
                return fail(ErrorCode.PARAM_ERROR, '角色不存在')
            user.role = role
        if 'password' in body and str(body.get('password')):
            pwd = str(body.get('password'))
            if len(pwd) < 6:
                return fail(ErrorCode.PARAM_ERROR, '密码至少 6 位')
            user.set_password(pwd)
            AdminToken.objects.filter(user=user).delete()
        user.save()
        perm.log_action(request.admin_user, 'admin.update', target=user.username, ip=perm.client_ip(request))
        return ok(user.to_client(), '保存成功')

    if request.method == 'DELETE':
        if user.pk == request.admin_user.pk:
            return fail(ErrorCode.PARAM_ERROR, '不能删除当前登录的账号')
        if user.is_superuser:
            others = AdminUser.objects.filter(role__code='superadmin').exclude(pk=user.pk).count()
            if others == 0:
                return fail(ErrorCode.PARAM_ERROR, '至少保留一个超级管理员')
        username = user.username
        user.delete()
        perm.log_action(request.admin_user, 'admin.delete', target=username, ip=perm.client_ip(request))
        return ok({'deleted': True}, '已删除')

    return fail(ErrorCode.PARAM_ERROR, '方法不支持', http_status=405)


@perm.require_perms('admin.manage')
def admin_reset_password(request, pk):
    """POST /api/admin/admins/<id>/reset-password/  {password}"""
    if request.method != 'POST':
        return fail(ErrorCode.PARAM_ERROR, '请使用 POST 提交', http_status=405)
    try:
        user = AdminUser.objects.get(pk=pk)
    except AdminUser.DoesNotExist:
        return fail(ErrorCode.NOT_FOUND, '管理员不存在')
    body, err = perm.json_body(request)
    if err:
        return err
    pwd = str(body.get('password', ''))
    if len(pwd) < 6:
        return fail(ErrorCode.PARAM_ERROR, '密码至少 6 位')
    user.set_password(pwd)
    user.save(update_fields=['password_hash'])
    AdminToken.objects.filter(user=user).delete()
    perm.log_action(request.admin_user, 'admin.reset_password', target=user.username, ip=perm.client_ip(request))
    return ok(message='密码已重置，该账号需重新登录')


@perm.require_perms('admin.view')
def role_list(request):
    """GET /api/admin/roles/"""
    if request.method != 'GET':
        return fail(ErrorCode.PARAM_ERROR, '该接口仅支持 GET', http_status=405)
    roles = Role.objects.all()
    return ok([_serialize_role(r) for r in roles])


@perm.require_perms('admin.view', 'admin.manage', methods=WRITE_METHODS)
def role_detail(request, pk):
    try:
        role = Role.objects.get(pk=pk)
    except Role.DoesNotExist:
        return fail(ErrorCode.NOT_FOUND, '角色不存在')

    if request.method == 'GET':
        return ok(_serialize_role(role))

    if request.method in ('PUT', 'PATCH'):
        if not request.admin_user.is_superuser:
            return fail(ErrorCode.FORBIDDEN, '仅超级管理员可修改角色权限')
        body, err = perm.json_body(request)
        if err:
            return err
        if 'name' in body:
            role.name = str(body.get('name')).strip() or role.name
        if 'description' in body:
            role.description = str(body.get('description')).strip()
        if 'permissions' in body:
            perms = body.get('permissions')
            if not isinstance(perms, list):
                return fail(ErrorCode.PARAM_ERROR, 'permissions 必须是数组')
            invalid = [p for p in perms if not perm.is_valid_permission(p)]
            if invalid:
                return fail(ErrorCode.PARAM_ERROR, f'存在无效权限点：{", ".join(invalid)}')
            if role.code == 'superadmin' and set(perms) != set(perm.all_permissions()):
                return fail(ErrorCode.PARAM_ERROR, '超级管理员角色必须拥有全部权限')
            role.permissions = perms
        role.save()
        perm.log_action(request.admin_user, 'role.update', target=role.code, ip=perm.client_ip(request))
        return ok(_serialize_role(role), '角色已保存')

    return fail(ErrorCode.PARAM_ERROR, '方法不支持', http_status=405)
