"""
文章唯一编码 / 文章入知识库索引 / 可溯源 RAG 检索 —— 验证测试

覆盖：
1. 编码规则 ART-YYYYMMDD-NNNN 的格式、唯一性、幂等补码
2. 编码 ↔ 知识库条目（KB_ART_<编码>）双向追溯
3. 文章选择性加入/移出知识库索引
4. KnowledgeRAGService 语料构建与检索的来源溯源字段
5. historys 两种数据形态（题目 ID 字符串数组 / 对象数组）的归一化
6. 新增 4 条路由注册与视图可调用

运行方式: python test_article_kb.py
（测试自行创建/清理临时数据，测试后库结构无残留）
"""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.urls import reverse  # noqa: E402

from core.models import Document  # noqa: E402
from adminapi import article_code as ac  # noqa: E402
from adminapi.ai_services import (  # noqa: E402
    KnowledgeRAGService,
    normalize_history_items,
    item_is_correct,
    _question_correct_codes,
    _normalize_answer,
)
from adminapi.views_ai import (  # noqa: E402
    kb_indexed_articles,
    kb_article_link,
    kb_articles_batch_link,
)

passed = 0
failed = 0

TEST_PREFIX = '__test_kb_'
TEST_ARTICLE_ID = TEST_PREFIX + 'art'
TEST_KB_IDS = ()


def check(condition, msg):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print('  FAIL: %s' % msg)


def cleanup():
    Document.objects.filter(
        collection='articles', doc_id__startswith=TEST_PREFIX).delete()
    Document.objects.filter(
        collection='knowledgebase', doc_id__startswith='KB_ART_' + TEST_PREFIX).delete()


print('=' * 60)
print('文章编码 / 知识库索引溯源 验证测试')
print('=' * 60)

cleanup()

# ---------------------------------------------------------------- 1. 编码规则
print('\n[1] 编码规则与解析')
sample = ac.generate_article_code()
check(ac.is_valid_article_code(sample), '生成的编码应通过格式校验：%s' % sample)
check(ac.CODE_RE.match(sample) is not None, '编码应匹配 ART-YYYYMMDD-NNNN')
check(len(sample) == 17, '编码长度应为 17（ART- + 8 + - + 4），实际 %d' % len(sample))

parsed = ac.parse_article_code('ART-20260912-0042')
check(parsed == {'code': 'ART-20260912-0042', 'date': '20260912', 'seq': 42},
      'parse_article_code 应正确解析日期与流水号')
check(ac.parse_article_code('ART-2026-0042') is None, '非法日期位数应解析为 None')
check(ac.parse_article_code('art-20260912-0042') is None, '前缀必须大写，小写应判为非法')
check(ac.parse_article_code('ART-20260912-42') is None, '流水号必须 4 位补零')
check(ac.parse_article_code(None) is None, 'None 输入应返回 None')
check(ac.parse_article_code(123) is None, '非字符串输入应返回 None')

# ---------------------------------------------------------------- 2. 双向追溯
print('\n[2] 编码 ↔ 知识库条目 双向追溯')
kb_doc_id = ac.kb_doc_id_for_code('ART-20260912-0042')
check(kb_doc_id == 'KB_ART_ART-20260912-0042', 'KB 条目标 _id 应为 KB_ART_<编码>')
check(ac.parse_kb_art_doc_id(kb_doc_id) == 'ART-20260912-0042', '应能从 KB _id 反解文章编码')
check(ac.parse_kb_art_doc_id('KB_RJJS_01') is None, '非文章派生条目不应被误解析')
check(ac.kb_doc_id_for_code('bad-code') is None, '非法编码不应生成 KB _id')

# ---------------------------------------------------------------- 3. 唯一性
print('\n[3] 编码唯一性与幂等')
# 唯一性由 assign_article_code（生成即落库）保证，故通过批量建文章验证
tmp_docs = []
for i in range(5):
    tmp_docs.append(Document.objects.create(
        collection='articles', doc_id='%suniq%d' % (TEST_PREFIX, i),
        data={'title': '唯一性测试 %d' % i, 'status': 'published'}))
codes = {ac.assign_article_code(d) for d in tmp_docs}
check(len(codes) == 5, '连续分配 5 个编码应互不相同（实际 %d 个）' % len(codes))
for d in tmp_docs:
    d.delete()

doc = Document.objects.create(
    collection='articles', doc_id=TEST_ARTICLE_ID,
    data={'title': '测试文章', 'status': 'published', 'content': '死锁预防策略与资源分配讲解'})
code1 = ac.assign_article_code(doc)
code2 = ac.assign_article_code(doc)
check(code1 == code2, 'assign_article_code 应为幂等（同一文章两次结果一致）')
check(ac.is_valid_article_code(code1), '分配出的编码应合法：%s' % code1)

bf1 = ac.backfill_article_codes()
bf2 = ac.backfill_article_codes()
check(bf2['assigned'] == 0, 'backfill 第二次应补 0 条（幂等），实际 %d' % bf2['assigned'])
check(bf1['total'] >= 1, 'backfill 应至少覆盖 1 篇文章')

# ---------------------------------------------------------------- 4. 文章入索引
print('\n[4] 文章选择性加入 / 移出知识库索引')
doc.refresh_from_db()
result = KnowledgeRAGService.add_article_to_index(doc, operator='test')
check(isinstance(result, dict) and not result.get('error'), 'add_article_to_index 不应报错')
check(result.get('article_code') == ac.article_code_of(doc), '返回编码应与文章一致')
check(result.get('kb_doc_id') == ac.kb_doc_id_for_code(ac.article_code_of(doc)),
      '返回 KB _id 应可由编码推导')

kb_doc = Document.objects.filter(
    collection='knowledgebase', doc_id=result['kb_doc_id']).first()
check(kb_doc is not None, '知识库集合应生成对应文档')
if kb_doc:
    kb_data = kb_doc.data or {}
    check(kb_data.get('source') == 'article', "KB 文档 source 应为 'article'")
    check(kb_data.get('articleCode') == result['article_code'], 'KB 文档应携带 articleCode')
    check(kb_data.get('articleId') == TEST_ARTICLE_ID, 'KB 文档应携带 articleId 溯源')
    check(kb_data.get('type') == 'article', "KB 文档 type 应为 'article'")
    check(result['article_code'] in str(kb_doc.doc_id), 'KB _id 应包含文章编码')

# 幂等：重复加入不产生第二条
again = KnowledgeRAGService.add_article_to_index(doc, operator='test')
count = Document.objects.filter(collection='knowledgebase', doc_id=result['kb_doc_id']).count()
check(count == 1, '重复加入应保持单条（幂等），实际 %d' % count)
check(again.get('created') is False, '第二次加入 created 应为 False')

indexed = KnowledgeRAGService.get_indexed_articles()
codes_indexed = {x['article_code'] for x in indexed}
check(result['article_code'] in codes_indexed, 'get_indexed_articles 应包含该文章编码')
entry = next((x for x in indexed if x['article_code'] == result['article_code']), {})
check(entry.get('article_id') == TEST_ARTICLE_ID, '索引清单应可反查文章 _id')
check(entry.get('kb_doc_id') == result['kb_doc_id'], '索引清单应给出 KB _id')

# ---------------------------------------------------------------- 5. 语料与检索
print('\n[5] 语料构建与可溯源检索')
corpus = KnowledgeRAGService.build_corpus()
target = next((c for c in corpus if c['doc_id'] == result['kb_doc_id']), None)
check(target is not None, 'build_corpus 应包含文章派生条目')
if target:
    check(target.get('source') == 'article', 'chunk.source 应为 article')
    check(target.get('article_code') == result['article_code'], 'chunk.article_code 应正确')
    check(target.get('article_id') == TEST_ARTICLE_ID, 'chunk.article_id 应正确')

hits = KnowledgeRAGService.retrieve('死锁预防策略')
check(len(hits) > 0, '对文章内容的检索应命中结果')
if hits:
    hit = hits[0]
    check('source' in hit and 'article_code' in hit and 'article_id' in hit,
          '检索结果应包含溯源字段')
    matched = any(h.get('article_code') == result['article_code'] for h in hits)
    check(matched, '命中结果中应包含该文章编码，便于引用标注')

stats = KnowledgeRAGService.get_stats()
check(stats.get('article_count', 0) >= 1, 'get_stats 的 article_count 应 >= 1')
check(stats.get('corpus_size', 0) >= stats.get('article_count', 0),
      'corpus_size 应不小于 article_count')
check('last_built_at' in stats, 'get_stats 应包含 last_built_at 字段')

rebuilt = KnowledgeRAGService.rebuild_index()
check(rebuilt.get('corpus_size') == stats.get('corpus_size'),
      'rebuild 前后语料数应一致（%s vs %s）' % (rebuilt.get('corpus_size'), stats.get('corpus_size')))
check(rebuilt.get('article_count') >= 1, 'rebuild 应统计出文章条目数')
check(bool(rebuilt.get('built_at')), 'rebuild 应返回构建时间')
check(result['article_code'] in rebuilt.get('article_codes', []),
      'rebuild 应返回已索引文章编码清单')

removed = KnowledgeRAGService.remove_article_from_index(doc)
check(removed.get('removed') == 1, '移出应删除 1 条，实际 %s' % removed.get('removed'))
check(Document.objects.filter(
    collection='knowledgebase', doc_id=result['kb_doc_id']).count() == 0,
    '移出后知识库不应残留该条目')
removed_again = KnowledgeRAGService.remove_article_from_index(doc)
check(removed_again.get('removed') == 0, '重复移出应返回 0（幂等）')

# ---------------------------------------------------------------- 6. 记录归一化
print('\n[6] historys 数据形态归一化')
q_doc = Document.objects.filter(collection='questions').first()
if q_doc:
    correct = _question_correct_codes(q_doc)
    check(bool(correct), '题目正确答案应可解析')
    qid = q_doc.doc_id or str(q_doc.pk)
    right_answer = sorted(correct)
    wrong_answer = ['Z'] if 'Z' not in correct else ['Y']

    lookup = lambda q: q_doc  # noqa: E731
    items = normalize_history_items(
        {'items': [qid, qid], 'score_arr': [right_answer, wrong_answer]}, lookup)
    check(len(items) == 2, '字符串数组形态应归一化为 2 项')
    check(items[0]['questionId'] == qid, '归一化后 questionId 应正确')
    check(items[0]['is_correct'] is True, '正确作答应判定为 True')
    check(items[1]['is_correct'] is False, '错误作答应判定为 False')

    dict_items = normalize_history_items(
        {'items': [{'questionId': qid, 'isCorrect': True},
                   {'questionId': qid, 'isCorrect': False}]})
    check(len(dict_items) == 2, '对象数组形态应归一化为 2 项')
    check(dict_items[0]['is_correct'] is True and dict_items[1]['is_correct'] is False,
          '对象形态应沿用显式 isCorrect')

    check(normalize_history_items({}) == [], '空记录应返回空列表')
    check(normalize_history_items({'items': []}) == [], '空数组应返回空列表')
    check(normalize_history_items({'items': [None, 123, '']}) == [], '非法项应被过滤')
    check(item_is_correct({}, None) is None, '无判定依据时应返回 None')
    check(_normalize_answer('AB') == {'A', 'B'}, '字符串作答应拆分为选项码集合')
    check(_normalize_answer(['a', 'b']) == {'A', 'B'}, '列表作答应大写归一')
else:
    print('  SKIP: questions 集合无数据，跳过归一化对错判定断言')

# ---------------------------------------------------------------- 7. 路由与视图
print('\n[7] 路由注册与视图可调用')
route_names = [
    ('admin-article-to-knowledge', {'doc_id': 'x'}),
    ('admin-articles-to-knowledge', {}),
    ('ai-kb-indexed-articles', {}),
]
for name, kwargs in route_names:
    try:
        url = reverse(name, kwargs=kwargs)
        check(bool(url), '路由 %s 应可 reverse，实际 %s' % (name, url))
    except Exception as exc:
        check(False, '路由 %s reverse 失败：%s' % (name, exc))

check(callable(kb_indexed_articles), '视图 kb_indexed_articles 应可调用')
check(callable(kb_article_link), '视图 kb_article_link 应可调用')
check(callable(kb_articles_batch_link), '视图 kb_articles_batch_link 应可调用')

# ---------------------------------------------------------------- 清理
cleanup()
Document.objects.filter(
    collection='knowledgebase', doc_id__startswith='KB_ART_' + TEST_PREFIX).delete()

print('\n' + '=' * 60)
print('结果: 通过 %d, 失败 %d' % (passed, failed))
print('=' * 60)

sys.exit(1 if failed else 0)
