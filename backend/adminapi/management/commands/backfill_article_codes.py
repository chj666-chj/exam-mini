# -*- coding: utf-8 -*-
"""为缺失唯一编码的文章补码（backfill）。

编码规则：``ART-YYYYMMDD-NNNN``（见 adminapi.article_code）。
按文章 ``createTime`` 归属日期分组、组内按 pk 升序分配当日流水号，
幂等：已有合法编码的文章保持不变。

用法：
    python manage.py backfill_article_codes
"""
from django.core.management.base import BaseCommand

from adminapi.article_code import ARTICLE_COLLECTION, backfill_article_codes


class Command(BaseCommand):
    help = '为 articles 集合中缺少 code 的文章批量生成唯一编码'

    def handle(self, *args, **options):
        result = backfill_article_codes()
        self.stdout.write(self.style.SUCCESS(
            '[%s] 编码回填完成：总数 %d，本次补码 %d，已有编码 %d'
            % (ARTICLE_COLLECTION, result['total'], result['assigned'], result['skipped'])
        ))
