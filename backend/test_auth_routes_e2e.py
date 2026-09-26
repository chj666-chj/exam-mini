"""端到端鉴权链路验证：新增文章编码 / 知识库索引路由。

验证目标（直接走 Django test Client 跑真实 URLConf + 视图，不依赖外部 HTTP 服务）：
  1. 无令牌访问 → 401（业务错误码 40101，证实鉴权生效）
  2. 携带有效令牌访问 → 非 401（证实路由可达、视图可执行）
  3. 文章编码生成规则统一且唯一（ART-YYYYMMDD-NNNN）
  4. 知识库索引与文章编码双向可追溯（KB_ART_<code> ↔ code）
  5. 知识库服务索引状态与文章列表一致

运行：
  cd backend
  python test_auth_routes_e2e.py
"""
import os
import sys
import json
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.test import Client  # noqa: E402
from django.urls import reverse  # noqa: E402

from adminapi import article_code as ac  # noqa: E402
from adminapi.models import AdminUser  # noqa: E402
from adminapi.permissions import issue_token  # noqa: E402
from core.models import Document  # noqa: E402

PASS = 0
FAIL = 0
FAILED = []


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  [OK]   {label}')
    else:
        FAIL += 1
        FAILED.append(label)
        print(f'  [FAIL] {label}')


def section(title):
    print(f'\n== {title} ==')


def body_of(resp):
    try:
        return json.loads(resp.content.decode('utf-8'))
    except Exception:
        return {}


def get_superadmin():
    for u in AdminUser.objects.select_related('role').all():
        if u.is_superuser:
            return u
    return None


def main():
    client = Client()

    # 无令牌：路由 + 方法
    section('1. 无令牌鉴权（应 401 / code=40101）')
    no_token = [
        ('post', 'admin-article-to-knowledge', {'doc_id': 'X'}),
        ('delete', 'admin-article-to-knowledge', {'doc_id': 'X'}),
        ('post', 'admin-articles-to-knowledge', {}),
        ('get', 'ai-kb-indexed-articles', {}),
        ('get', 'ai-kb-stats', {}),
        ('post', 'ai-kb-rebuild', {}),
    ]
    for method, name, kwargs in no_token:
        url = reverse(name, kwargs=kwargs)
        # 鉴权中间件在解析请求体之前即返回 401，GET/DELETE 无需携带 body
        resp = getattr(client, method)(url)
        b = body_of(resp)
        check(resp.status_code == 401 and b.get('code') == 40101,
              f'{method.upper():6} {url} -> HTTP {resp.status_code} code={b.get("code")}')

    section('2. 有效令牌鉴权（应非 401）')
    admin = get_superadmin()
    if not admin:
        check(False, '未找到超级管理员账号，跳过')
    else:
        print(f'  使用管理员：{admin.username}')
        # 准备一篇带编码的文章
        target = None
        for d in Document.objects.filter(collection='articles'):
            if ac.is_valid_article_code(d.data.get('code')) and d.doc_id:
                target = d
                break
        if target is None:
            target = Document.objects.create(
                collection='articles', doc_id='auth-probe-001',
                data={'title': '__auth_probe__', 'content': 'probe', 'status': 'published'},
            )
            ac.assign_article_code(target)
        tid = str(target.doc_id)

        tok = issue_token(admin, ttl_hours=1)
        H = {'HTTP_AUTHORIZATION': f'Bearer {tok.token}'}

        # (method, name, url_kwargs, body_dict)
        with_token = [
            ('get', 'ai-kb-stats', {}, None),
            ('get', 'ai-kb-indexed-articles', {}, None),
            ('post', 'admin-articles-to-knowledge', {}, {'ids': [tid], 'action': 'add'}),
            ('post', 'admin-article-to-knowledge', {'doc_id': tid}, None),
            ('delete', 'admin-article-to-knowledge', {'doc_id': tid}, None),
            ('post', 'ai-kb-rebuild', {}, None),
        ]
        for method, name, kwargs, body in with_token:
            url = reverse(name, kwargs=kwargs)
            if method in ('post', 'put', 'patch'):
                resp = getattr(client, method)(
                    url, data=json.dumps(body if body is not None else {}),
                    content_type='application/json', **H)
            else:
                resp = getattr(client, method)(url, **H)
            b = body_of(resp)
            check(resp.status_code != 401,
                  f'{method.upper():6} {url} -> HTTP {resp.status_code} code={b.get("code")} msg={b.get("message") or b.get("msg")}')
        tok.delete()

    section('3. 文章编码规则统一且唯一')
    codes = []
    missing = []
    for d in Document.objects.filter(collection='articles'):
        c = d.data.get('code')
        if c:
            codes.append(c)
            if not ac.is_valid_article_code(c):
                check(False, f'编码格式非法：{c}')
        else:
            missing.append(d.doc_id or d.pk)
    check(not missing, f'所有文章均有编码（缺失 {len(missing)} 篇：{missing[:5]}）')
    check(len(codes) == len(set(codes)),
          f'编码全局唯一（{len(codes)} 条 / 去重 {len(set(codes))} 条）')

    section('4. 知识库索引 ↔ 文章编码 双向可追溯')
    if codes:
        s = codes[0]
        kb = ac.kb_doc_id_for_code(s)
        check(kb == f'KB_ART_{s}', f'编码 -> KB _id：{s} -> {kb}')
        check(ac.parse_kb_art_doc_id(kb) == s, f'KB _id -> 编码 反解：{kb} -> {ac.parse_kb_art_doc_id(kb)}')
    check(ac.parse_kb_art_doc_id('KB_ART_bad') is None, '非法 KB_ART doc_id -> None')
    check(ac.parse_kb_art_doc_id('KB_manual_001') is None, '普通知识库 doc_id -> None')

    section('5. 知识库服务索引状态一致性')
    from adminapi.ai_services import KnowledgeRAGService
    stats = KnowledgeRAGService.get_stats()
    indexed = KnowledgeRAGService.get_indexed_articles()
    idx_codes = set(KnowledgeRAGService.indexed_article_codes())
    print(f'  stats={stats}')
    print(f'  indexed_codes={sorted(idx_codes)}')
    check(idx_codes.issubset(set(codes)),
          f'已索引编码 ⊂ 文章编码（{len(idx_codes)} ⊂ {len(set(codes))}）')
    check(stats.get('article_count', 0) == len(indexed),
          f'stats.article_count({stats.get("article_count")}) == 已索引文章数({len(indexed)})')

    print('\n========================================')
    print(f'  结果：{PASS} 通过 / {FAIL} 失败')
    for f in FAILED:
        print(f'    - FAIL: {f}')
    print('========================================')
    return 0 if FAIL == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
