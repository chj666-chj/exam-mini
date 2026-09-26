from django.db import models


class Document(models.Model):
    """通用文档模型 —— 模拟微信云开发数据库的集合/文档语义。

    - collection: 集合名（exam / subjects / questions / historys / notes ...）
    - doc_id:     客户端指定的文档 _id（云数据库允许 add 时指定 _id），可为空
    - data:       文档原始 JSON（包含 _openid）
    """
    collection = models.CharField('集合名', max_length=64, db_index=True)
    doc_id = models.CharField('文档_id', max_length=128, null=True, blank=True)
    data = models.JSONField('文档数据', default=dict)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '文档'
        verbose_name_plural = '文档'
        unique_together = ('collection', 'doc_id')

    def __str__(self):
        return f'[{self.collection}] {self.doc_id or self.pk}'

    def to_client(self):
        """输出给小程序的文档结构：_id 与文档字段平铺在同一层。"""
        doc = dict(self.data)
        doc['_id'] = self.doc_id if self.doc_id else str(self.pk)
        return doc
