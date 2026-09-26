"""初始化默认题目标签（幂等，可重复执行）。

用法：python manage.py seed_tags
"""
from django.core.management.base import BaseCommand

from adminapi.models import Tag

DEFAULT_TAGS = [
    # 难度
    ('入门', 'difficulty', '基础难度', '#63b56b'),
    ('简单', 'difficulty', '基础难度', '#97c459'),
    ('中等', 'difficulty', '中等难度', '#f0b34a'),
    ('困难', 'difficulty', '较高难度', '#e8833a'),
    ('挑战', 'difficulty', '高难度', '#d9534f'),
    # 题目类型
    ('单选题', 'qtype', '单选题型', '#4f7cff'),
    ('多选题', 'qtype', '多选题型', '#8a63f2'),
    ('判断题', 'qtype', '判断题型', '#2f9ee0'),
    ('填空题', 'qtype', '填空题型', '#1d9e75'),
    ('问答题', 'qtype', '问答题型', '#d85a8a'),
    ('一题多问', 'qtype', '复合题型', '#ba7517'),
    # 知识点示例
    ('基础知识', 'knowledge', '基础知识点', ''),
    ('进阶理解', 'knowledge', '进阶知识点', ''),
    ('易错点', 'knowledge', '常见易错点', '#d9534f'),
    # 使用场景
    ('课后练习', 'scene', '课后练习题', '#4f7cff'),
    ('模拟考试', 'scene', '模拟考试题', '#f0b34a'),
    ('历年真题', 'scene', '历年考试真题', '#d9534f'),
]

# 上述第三项为说明/别名占位，这里转换为 (name, category, description, color)


class Command(BaseCommand):
    help = '初始化默认题目标签'

    def handle(self, *args, **options):
        created, existed, updated = 0, 0, 0
        for name, category, description, color in DEFAULT_TAGS:
            obj, was_created = Tag.objects.get_or_create(
                name=name,
                category=category,
                defaults={'description': description, 'color': color},
            )
            if was_created:
                created += 1
            else:
                existed += 1
                # 补全缺失的 description / color
                changed = False
                if description and not obj.description:
                    obj.description = description
                    changed = True
                if color and not obj.color:
                    obj.color = color
                    changed = True
                if changed:
                    obj.save(update_fields=['description', 'color'])
                    updated += 1
        # 清理旧版错误标签（name='难度' 的 difficulty 标签）
        old_deleted, _ = Tag.objects.filter(name='难度', category='difficulty').delete()
        self.stdout.write(self.style.SUCCESS(
            f'完成：新建 {created} 个，已存在 {existed} 个，更新 {updated} 个'
            + (f'，清理旧标签 {old_deleted} 个' if old_deleted else '')
        ))
