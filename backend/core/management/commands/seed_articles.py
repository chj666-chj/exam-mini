# -*- coding: utf-8 -*-
"""导入文章演示数据到 articles 集合（小程序「文章」tab 数据源）。

用法：python manage.py seed_articles
"""
from django.core.management.base import BaseCommand
from core.models import Document
from adminapi import article_code

ARTICLES = [
    {
        '_id': 'art-001',
        'title': '高效刷题的五个方法，助你轻松备考',
        'summary': '盲目刷题不如精准刷题，掌握正确的方法可以让复习效率翻倍。',
        'content': '盲目刷题不如精准刷题。第一个方法是错题优先：把错题本里的题目反复做三遍，比做三十道新题更有价值。\n\n第二个方法是限时训练，模拟真实考试节奏，训练答题速度与心态。\n\n第三个方法是专题突破，针对薄弱题型集中练习，逐个击破。\n\n第四个方法是睡前回顾，利用记忆黄金期复习当天错题。\n\n第五个方法是定期模拟，每周一次完整模拟考，检验阶段成果。',
        'cover': '',
        'images': [
            'https://via.placeholder.com/600x400/4A90F3/ffffff?text=Study+Tips+1',
            'https://via.placeholder.com/600x400/67C23A/ffffff?text=Study+Tips+2',
        ],
        'tags': ['备考技巧', '刷题方法', '高效学习'],
        'status': 'published',
        'author': '考试宝',
        'views': 1024,
        'createTime': '2026/09/01 10:00',
        'updateTime': '2026/09/01 10:00',
    },
    {
        '_id': 'art-002',
        'title': '考前一周复习规划指南',
        'summary': '考前一周不要做新题，重点回顾错题本和知识框架，保持手感。',
        'content': '考前一周的核心策略是「回归」而非「拓展」。\n\n周一到周三：快速过一遍错题本，标记仍不熟练的题目。\n\n周四到周五：只做标记的题目和经典题型，保持手感。\n\n周六：完整做一次模拟考，按照真实考试时间执行。\n\n周日：休整心态，准备考试用品，早睡早起。',
        'cover': '',
        'images': [
            'https://via.placeholder.com/600x400/E6A23C/ffffff?text=Exam+Prep+Plan',
        ],
        'tags': ['考前规划', '复习策略'],
        'status': 'published',
        'author': '考试宝',
        'views': 866,
        'createTime': '2026/09/03 14:30',
        'updateTime': '2026/09/03 14:30',
    },
    {
        '_id': 'art-003',
        'title': '多选题答题技巧：宁缺勿滥原则',
        'summary': '多选题判分严格，没有把握的选项不要选，稳扎稳打拿稳分数。',
        'content': '多选题的判分规则通常是「错选不得分，少选得部分分」。\n\n因此最重要的原则是：宁缺勿滥。对每个选项都要独立判断，没有把握的选项果断放弃。\n\n排除法是好帮手：先排除明显错误的选项，再在剩余选项中权衡。\n\n注意绝对化表述，出现「一定」「必须」「所有」字样的选项往往是错的。',
        'cover': '',
        'images': [],
        'tags': ['答题技巧', '多选题'],
        'status': 'published',
        'author': '考试宝',
        'views': 753,
        'createTime': '2026/09/05 09:15',
        'updateTime': '2026/09/05 09:15',
    },
    {
        '_id': 'art-004',
        'title': '如何利用碎片时间提高学习效率',
        'summary': '通勤、排队等碎片时间用小程序刷几道题，积少成多效果惊人。',
        'content': '每天通勤 30 分钟，一年就是 180 小时，相当于 22 个完整学习日。\n\n碎片时间学习的关键是「小而频」：每次刷 5-10 道题，配合自动记录的错题本，系统会帮你沉淀薄弱点。\n\n建议把碎片时间用于「做题为」，整块时间留给「纠错与总结」，两者配合效果最佳。',
        'cover': '',
        'images': [
            'https://via.placeholder.com/600x400/409EFF/ffffff?text=Fragment+Time',
            'https://via.placeholder.com/600x400/F56C6C/ffffff?text=Efficiency',
            'https://via.placeholder.com/600x400/909399/ffffff?text=Study+Smart',
        ],
        'tags': [],
        'status': 'published',
        'author': '考试宝',
        'views': 620,
        'createTime': '2026/09/06 20:00',
        'updateTime': '2026/09/06 20:00',
    },
]


class Command(BaseCommand):
    help = '导入文章演示数据（articles 集合）'

    def handle(self, *args, **options):
        created = 0
        codes = []
        for item in ARTICLES:
            doc, is_new = Document.objects.update_or_create(
                collection='articles',
                doc_id=item['_id'],
                defaults={'data': item},
            )
            # 统一生成唯一编码 ART-YYYYMMDD-NNNN（供知识库索引溯源）
            code = article_code.assign_article_code(doc)
            codes.append(code)
            created += 1 if is_new else 0
        self.stdout.write(self.style.SUCCESS(
            f'articles 导入完成：新增 {created} 篇，共 {len(ARTICLES)} 篇\n'
            f'文章编码：{", ".join(codes)}'
        ))
