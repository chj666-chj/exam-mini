"""把原仓库 data/*.jsonl 题库数据导入 Document 集合。

用法：
    python manage.py load_exam_data          # 导入前清空所有集合
    python manage.py load_exam_data --append # 追加不清空
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import Document

# 文件名 -> 集合名（文件内每行一个 JSON 文档，即 JSON Lines 格式）
FILE_TO_COLLECTION = {
    'exam.json': 'exam',
    'subjects.json': 'subjects',
    'questions.json': 'questions',
    'historys.json': 'historys',
    'notes.json': 'notes',
    'profiles.json': 'profiles',
}


# 演示数据中的科目信息（原仓库 data 只有这一个科目，用于补齐 historys 展示字段）
DEMO_SUBJECT = {'_id': '001001', 'name': '微信测评一', 'pid': '001'}


def normalize_history(doc):
    """把原作者导出的 historys 演示数据补齐为页面渲染所需字段。

    页面（history/study/review）期望：subject / rightNum / createTime / items
    演示数据实际为：nums / questions / _id(时间戳)
    """
    if 'subject' not in doc:
        doc['subject'] = dict(DEMO_SUBJECT)
    if 'rightNum' not in doc and 'nums' in doc:
        doc['rightNum'] = doc['nums']
    if 'items' not in doc and 'questions' in doc:
        doc['items'] = [q.get('_id') for q in doc['questions'] if q.get('_id')]
    if 'createTime' not in doc:
        doc_id = str(doc.get('_id', ''))
        if len(doc_id) == 14 and doc_id.isdigit():
            doc['createTime'] = (
                f'{doc_id[0:4]}/{doc_id[4:6]}/{doc_id[6:8]} {doc_id[8:10]}:{doc_id[10:12]}'
            )
    return doc


class Command(BaseCommand):
    help = '导入原仓库 data/ 目录下的 JSONL 题库数据'

    def add_arguments(self, parser):
        parser.add_argument('--append', action='store_true', help='不清空已有数据，追加导入')

    def handle(self, *args, **options):
        data_dir = Path(settings.EXAM_DATA_DIR)
        if not data_dir.is_dir():
            self.stderr.write(self.style.ERROR(f'数据目录不存在: {data_dir}'))
            return

        if not options['append']:
            deleted, _ = Document.objects.all().delete()
            self.stdout.write(f'已清空原有文档 {deleted} 条')

        total = 0
        for filename, collection in FILE_TO_COLLECTION.items():
            path = data_dir / filename
            if not path.is_file():
                self.stdout.write(self.style.WARNING(f'跳过缺失文件: {filename}'))
                continue
            count = 0
            with open(path, encoding='utf-8') as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        doc = json.loads(line)
                    except ValueError as e:
                        self.stderr.write(f'{filename}:{line_no} 解析失败: {e}')
                        continue
                    doc_id = doc.pop('_id', None)
                    if collection == 'historys':
                        # 演示数据规范化后再落库
                        doc['_id'] = doc_id
                        doc = normalize_history(doc)
                        doc_id = doc.pop('_id', None)
                    Document.objects.update_or_create(
                        collection=collection,
                        doc_id=str(doc_id) if doc_id is not None else None,
                        defaults={'data': doc},
                    )
                    count += 1
            total += count
            self.stdout.write(self.style.SUCCESS(f'{collection:<10} {count:>5} 条  <- {filename}'))

        self.stdout.write(self.style.SUCCESS(f'完成，共导入 {total} 条文档'))

        # 输出各 openid 的记录数，方便确定演示账号
        from django.db.models import Count
        stats = (
            Document.objects.filter(collection='historys', data___openid__isnull=False)
            .values('data___openid')
            .annotate(n=Count('id'))
            .order_by('-n')[:5]
        )
        if stats:
            self.stdout.write('historys 记录数 Top5 openid（login 接口将返回第一名，用于演示数据）:')
            for s in stats:
                self.stdout.write(f"  {s['data___openid']}  {s['n']} 条")
