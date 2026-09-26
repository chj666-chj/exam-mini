"""管理端账号与角色权限模型。

说明：本模块独立于 django.contrib.auth，避免引入 session/中间件依赖，
管理端完全基于「令牌 + 角色权限点」做无状态鉴权。
"""
from django.db import models
from django.utils import timezone

from .permissions import DEFAULT_ROLE_PERMISSIONS, is_valid_permission


class Role(models.Model):
    """角色：一组权限点的集合。"""

    code = models.CharField('角色代码', max_length=32, unique=True)
    name = models.CharField('角色名称', max_length=64)
    description = models.TextField('说明', blank=True, default='')
    permissions = models.JSONField('权限点', default=list)
    is_system = models.BooleanField('内置角色', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '角色'
        verbose_name_plural = '角色'
        ordering = ['id']

    def __str__(self):
        return f'{self.name}({self.code})'

    def clean_permissions(self):
        """过滤掉非法 / 已下线的权限点。"""
        if not isinstance(self.permissions, list):
            return []
        return [p for p in self.permissions if is_valid_permission(p)]


class AdminUser(models.Model):
    """管理端账号。"""

    STATUS_ACTIVE = 'active'
    STATUS_DISABLED = 'disabled'
    STATUS_CHOICES = (
        (STATUS_ACTIVE, '启用'),
        (STATUS_DISABLED, '停用'),
    )

    username = models.CharField('登录账号', max_length=64, unique=True)
    password_hash = models.CharField('密码哈希', max_length=255)
    nickname = models.CharField('姓名/昵称', max_length=64, blank=True, default='')
    role = models.ForeignKey(
        Role, verbose_name='角色', null=True, blank=True,
        on_delete=models.PROTECT, related_name='users',
    )
    status = models.CharField('状态', max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    last_login_at = models.DateTimeField('最后登录时间', null=True, blank=True)
    last_login_ip = models.CharField('最后登录IP', max_length=64, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '管理员'
        verbose_name_plural = '管理员'
        ordering = ['id']

    def __str__(self):
        return self.username

    # ---- 密码 ----
    def set_password(self, raw_password):
        from django.contrib.auth.hashers import make_password
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        from django.contrib.auth.hashers import check_password
        if not self.password_hash:
            return False
        return check_password(raw_password, self.password_hash)

    # ---- 权限 ----
    @property
    def is_superuser(self):
        return bool(self.role_id and self.role.code == 'superadmin')

    @property
    def permissions(self):
        if self.is_superuser:
            from .permissions import all_permissions
            return all_permissions()
        if not self.role_id:
            return []
        return self.role.clean_permissions()

    def has_perm(self, perm):
        return self.is_superuser or perm in self.permissions

    @property
    def is_active(self):
        return self.status == self.STATUS_ACTIVE

    def to_client(self):
        return {
            'id': self.pk,
            'username': self.username,
            'nickname': self.nickname or self.username,
            'role': self.role.code if self.role_id else '',
            'role_name': self.role.name if self.role_id else '未分配',
            'status': self.status,
            'permissions': self.permissions,
            'is_superuser': self.is_superuser,
            'last_login_at': self.last_login_at.strftime('%Y-%m-%d %H:%M:%S') if self.last_login_at else '',
            'last_login_ip': self.last_login_ip,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        }


class AdminToken(models.Model):
    """管理端登录令牌。"""

    token = models.CharField('令牌', max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(AdminUser, verbose_name='管理员', on_delete=models.CASCADE, related_name='tokens')
    expires_at = models.DateTimeField('过期时间')
    created_at = models.DateTimeField('签发时间', auto_now_add=True)
    last_access_at = models.DateTimeField('最近访问', auto_now=True)

    class Meta:
        verbose_name = '登录令牌'
        verbose_name_plural = '登录令牌'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username}:{self.token[:8]}'

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class OperationLog(models.Model):
    """管理端操作审计日志。"""

    user = models.ForeignKey(
        AdminUser, verbose_name='操作人', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='logs',
    )
    username = models.CharField('操作账号', max_length=64, blank=True, default='')
    action = models.CharField('动作', max_length=64)          # 如 question.create
    target = models.CharField('对象', max_length=128, blank=True, default='')
    detail = models.TextField('详情', blank=True, default='')
    ip = models.CharField('IP', max_length=64, blank=True, default='')
    created_at = models.DateTimeField('时间', auto_now_add=True)

    class Meta:
        verbose_name = '操作日志'
        verbose_name_plural = '操作日志'
        ordering = ['-id']

    def __str__(self):
        return f'{self.username} {self.action}'

    def to_client(self):
        return {
            'id': self.pk,
            'username': self.username,
            'action': self.action,
            'target': self.target,
            'detail': self.detail,
            'ip': self.ip,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        }


class Tag(models.Model):
    """题目标签：支持知识点、难度、题目类型等多分类标签。"""

    CATEGORY_CHOICES = (
        ('knowledge', '知识点'),
        ('difficulty', '难度'),
        ('qtype', '题目类型'),
        ('scene', '使用场景'),
    )

    name = models.CharField('标签名', max_length=64)
    category = models.CharField('分类', max_length=32, choices=CATEGORY_CHOICES)
    description = models.CharField('说明', max_length=255, blank=True, default='')
    color = models.CharField('颜色', max_length=16, blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '标签'
        verbose_name_plural = '标签'
        unique_together = ('name', 'category')
        ordering = ['category', 'name']

    def __str__(self):
        return f'{self.get_category_display()}:{self.name}'

    def to_client(self):
        return {
            'id': self.pk,
            'name': self.name,
            'category': self.category,
            'category_name': self.get_category_display(),
            'description': self.description,
            'color': self.color,
            'usage_count': self.bindings.count(),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        }


class QuestionTag(models.Model):
    """题目与标签的绑定关系（题目为 core.Document collection=questions）。"""

    question = models.ForeignKey(
        'core.Document', verbose_name='题目文档',
        on_delete=models.CASCADE, related_name='tag_bindings',
    )
    tag = models.ForeignKey(Tag, verbose_name='标签', on_delete=models.CASCADE, related_name='bindings')
    created_at = models.DateTimeField('绑定时间', auto_now_add=True)

    class Meta:
        verbose_name = '题目标签'
        verbose_name_plural = '题目标签'
        unique_together = ('question', 'tag')

    def __str__(self):
        return f'{self.question_id}:{self.tag_id}'


class ImportJob(models.Model):
    """题库批量导入任务（支持异步后台执行）。"""

    STATUS_CHOICES = (
        ('pending', '排队中'),
        ('processing', '处理中'),
        ('success', '全部成功'),
        ('partial', '部分成功'),
        ('failed', '失败'),
    )
    MODE_CHOICES = (('sync', '同步'), ('async', '异步'))

    created_by = models.ForeignKey(
        AdminUser, verbose_name='发起人', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='import_jobs',
    )
    mode = models.CharField('执行模式', max_length=16, choices=MODE_CHOICES, default='sync')
    status = models.CharField('状态', max_length=16, choices=STATUS_CHOICES, default='pending')
    total = models.IntegerField('题目总数', default=0)
    succeeded = models.IntegerField('成功', default=0)
    failed = models.IntegerField('失败', default=0)
    skipped = models.IntegerField('跳过（重复）', default=0)
    payload = models.JSONField('导入数据', default=dict)
    results = models.JSONField('逐题结果', default=list)
    error = models.TextField('失败原因', blank=True, default='')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    started_at = models.DateTimeField('开始时间', null=True, blank=True)
    finished_at = models.DateTimeField('完成时间', null=True, blank=True)

    class Meta:
        verbose_name = '导入任务'
        verbose_name_plural = '导入任务'
        ordering = ['-id']

    def __str__(self):
        return f'导入任务#{self.pk} {self.status}'

    @property
    def progress(self):
        done = self.succeeded + self.failed + self.skipped
        if self.total == 0:
            return 0 if self.status == 'pending' else 100
        return round(done / self.total * 100)

    def to_client(self, with_results=False):
        data = {
            'id': self.pk,
            'mode': self.mode,
            'status': self.status,
            'status_text': self.get_status_display(),
            'total': self.total,
            'succeeded': self.succeeded,
            'failed': self.failed,
            'skipped': self.skipped,
            'progress': self.progress,
            'error': self.error,
            'created_by': self.created_by.username if self.created_by else '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'finished_at': self.finished_at.strftime('%Y-%m-%d %H:%M:%S') if self.finished_at else '',
        }
        if with_results:
            data['results'] = self.results
        return data


def ensure_default_roles():
    """确保内置角色存在（含权限点刷新），返回 {code: Role}。"""
    result = {}
    for code, perms in DEFAULT_ROLE_PERMISSIONS.items():
        name = {'superadmin': '超级管理员', 'operator': '运营人员', 'viewer': '只读访客'}.get(code, code)
        role, _ = Role.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'permissions': perms,
                'is_system': True,
                'description': '系统内置角色',
            },
        )
        result[code] = role
    return result
