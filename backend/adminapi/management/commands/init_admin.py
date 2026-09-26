"""初始化管理端内置角色与默认管理员。

用法：
    python manage.py init_admin                       # 创建/刷新内置角色 + 默认超级管理员
    python manage.py init_admin --username admin --password 123456
    python manage.py init_admin --reset-password      # 强制重置默认账号密码
"""
from django.core.management.base import BaseCommand

from adminapi.models import AdminUser, ensure_default_roles


class Command(BaseCommand):
    help = '初始化管理端角色与默认管理员账号'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='admin', help='默认超级管理员账号')
        parser.add_argument('--password', default='admin123', help='默认超级管理员密码')
        parser.add_argument('--reset-password', action='store_true', help='强制重置密码')

    def handle(self, *args, **options):
        roles = ensure_default_roles()
        self.stdout.write(self.style.SUCCESS(f'内置角色已就绪：{", ".join(roles.keys())}'))

        username = options['username']
        password = options['password']
        user = AdminUser.objects.filter(username=username).first()
        created = False
        if not user:
            user = AdminUser(username=username, nickname='超级管理员', role=roles['superadmin'])
            user.set_password(password)
            user.save()
            created = True
        elif options['reset_password']:
            user.set_password(password)
            user.role = roles['superadmin']
            user.status = AdminUser.STATUS_ACTIVE
            user.save()

        action = '创建' if created else ('重置密码' if options['reset_password'] else '已存在，未修改')
        self.stdout.write(self.style.SUCCESS(
            f'{action}账号：{username} / {password}（角色：{user.role.code if user.role_id else "未分配"}）'
        ))
        self.stdout.write('提示：本地开发默认口令仅用于演示，部署到公网前请务必修改。')
