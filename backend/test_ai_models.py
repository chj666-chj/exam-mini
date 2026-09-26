"""AI 多模型配置功能测试。

覆盖：
  A. 模块基础（限制 / 预设 / 脱敏 / 地址校验 / 签名）
  B. 全局模型 CRUD（上限、默认唯一、掩码 Key、删除后默认接替）
  C. 用户模型 CRUD（归属校验、越权、用户上限、首选全局模型指针）
  D. 运行时解析链优先级（显式 > 功能级 > 用户默认 > 全局默认 > legacy）
  E. 缓存按模型隔离（compute_content_hash 纳入生效模型签名）
  F. 路由可达性 + 鉴权（管理端需要令牌、小程序端需要 X-Openid）
  G. 端到端 HTTP CRUD
  H. 功能级配置选择模型（管理端「AI 功能级配置」下拉 → 实际参与调用解析）

测试会暂时清空并随后还原 ai_models / ai_model_prefs 两个集合，保证不污染数据。

运行：
  cd backend
  python test_ai_models.py
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

from adminapi import ai_models as am  # noqa: E402
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
        print(f'  [PASS] {label}')
    else:
        FAIL += 1
        FAILED.append(label)
        print(f'  [FAIL] {label}')


def section(title):
    print(f'\n== {title} ==')


def snapshot(name):
    return [(d.doc_id, dict(d.data or {})) for d in Document.objects.filter(collection=name)]


def clear(name):
    Document.objects.filter(collection=name).delete()


def make_global(name, **over):
    payload = {
        'name': name,
        'provider': 'openai',
        'apiUrl': 'https://api.openai.com/v1/chat/completions',
        'apiKey': 'sk-FAKE-TEST-KEY-0001',
        'model': 'gpt-4o-mini',
        'temperature': 0.5,
        'maxTokens': 1500,
        'enabled': True,
    }
    payload.update(over)
    model, err = am.create_model(payload, scope=am.SCOPE_GLOBAL)
    assert err is None, f'create failed: {err}'
    return model


def main():
    # ---------- 快照并清空 ----------
    snap_models = snapshot(am.MODEL_COLLECTION)
    snap_pref = snapshot(am.PREF_COLLECTION)
    clear(am.MODEL_COLLECTION)
    clear(am.PREF_COLLECTION)

    try:
        # ============ A. 模块基础 ============
        section('A. 模块基础')
        limits = am.get_limits()
        check(limits.get('global') == 10 and limits.get('user') == 5,
              f'数量上限 global=10 / user=5（实际 {limits}）')
        check(len(am.get_presets()) >= 5, f'Provider 预设 >= 5 个（实际 {len(am.get_presets())}）')
        check(am.mask_key('sk-FAKE-1234567890') == '****7890', 'mask_key 仅保留末 4 位')
        check(am.mask_key('abc') == '****', 'mask_key 短串全掩码')
        check(am.is_masked_key('****7890') and not am.is_masked_key('sk-FAKE-real'), 'is_masked_key 判定正确')
        check(am.validate_api_url('ftp://x.com') is not None, '拒绝非 http/https 协议')
        check(am.validate_api_url('http://127.0.0.1:9/v1') is not None, '拒绝内网/回环地址')
        check(am.validate_api_url('https://api.openai.com/v1/chat/completions') is None,
              '合法公网地址通过')
        sig = am.model_signature({'model_id': 'm1', 'model': 'gpt-4o-mini'})
        check(sig == 'm1:gpt-4o-mini', f'model_signature 格式正确（{sig}）')

        # ============ B. 全局模型 CRUD ============
        section('B. 全局模型 CRUD')
        m1 = make_global('T-OpenAI-A')
        check(m1.get('isDefault') is True, '首个模型自动设为默认')
        check(m1.get('scope') == am.SCOPE_GLOBAL, '作用域为 global')
        m2 = make_global('T-DeepSeek-B', provider='deepseek',
                         apiUrl='https://api.deepseek.com/v1/chat/completions',
                         apiKey='sk-FAKE-TEST-KEY-9999', model='deepseek-chat')
        check(m2.get('isDefault') is False, '第二个模型不自动成为默认')
        check(am.count_models(am.SCOPE_GLOBAL) == 2, '全局模型计数 = 2')

        # 默认唯一性
        am.set_default(m2['_id'], scope=am.SCOPE_GLOBAL)
        defaults = [m for m in am.list_models(scope=am.SCOPE_GLOBAL) if m.get('isDefault')]
        check(len(defaults) == 1 and defaults[0]['_id'] == m2['_id'],
              'set_default 保证同作用域默认唯一')

        # 脱敏
        client_model = am.to_client(am.get_model(m1['_id']))
        check(client_model['apiKey'] == '****cdef' and client_model['hasApiKey'] is True,
              'to_client 返回脱敏 Key')
        check('sk-FAKE-TEST-KEY-0001' not in json.dumps(client_model), 'to_client 不泄露明文 Key')

        # 掩码更新保持原值
        am.update_model(m1['_id'], {'name': 'T-OpenAI-A2', 'apiKey': '****cdef'},
                        scope=am.SCOPE_GLOBAL)
        after = am.get_model(m1['_id'])
        check(after['name'] == 'T-OpenAI-A2', '更新名称生效')
        check(after['apiKey'] == 'sk-FAKE-TEST-KEY-0001', '掩码 Key 更新时保留原值')

        # 换新 Key
        am.update_model(m1['_id'], {'apiKey': 'sk-new-key-8888'}, scope=am.SCOPE_GLOBAL)
        check(am.get_model(m1['_id'])['apiKey'] == 'sk-new-key-8888', '传入新 Key 时覆盖')

        # 校验失败
        _bad, err = am.update_model(m1['_id'], {'apiUrl': 'http://localhost/v1'}, scope=am.SCOPE_GLOBAL)
        check(err is not None, '更新为内网地址被拒绝')
        _bad2, err2 = am.create_model({'name': '', 'apiUrl': 'https://a.com', 'apiKey': 'k', 'model': 'm'})
        check(err2 is not None, '缺失名称为拒绝')

        # 上限
        for i in range(3, 11):
            make_global('T-Fill-%d' % i)
        check(am.count_models(am.SCOPE_GLOBAL) == 10, '全局模型达到上限 10')
        _overflow, err3 = am.create_model({
            'name': 'T-overflow', 'apiUrl': 'https://a.com/v1', 'apiKey': 'k', 'model': 'm',
        }, scope=am.SCOPE_GLOBAL)
        check(_overflow is None and '上限' in (err3 or ''), f'超出上限被拒绝（{err3}）')

        # 删除默认模型 → 自动接替
        before_ids = {m['_id'] for m in am.list_models(scope=am.SCOPE_GLOBAL)}
        deleted, derr = am.delete_model(m2['_id'], scope=am.SCOPE_GLOBAL)
        check(deleted and derr is None, '删除默认模型成功')
        remaining = am.list_models(scope=am.SCOPE_GLOBAL)
        new_defaults = [m for m in remaining if m.get('isDefault')]
        check(len(new_defaults) == 1 and new_defaults[0]['_id'] in before_ids - {m2['_id']},
              '删除默认模型后自动指定新的默认')

        # ============ C. 用户模型 ============
        section('C. 用户模型 / 归属')
        clear(am.MODEL_COLLECTION)
        clear(am.PREF_COLLECTION)
        g1 = make_global('T-Global-1', model='gpt-4o-mini')

        _none, err_owner = am.create_model({
            'name': 'u', 'apiUrl': 'https://a.com/v1', 'apiKey': 'k', 'model': 'm',
        }, scope=am.SCOPE_USER, owner_key='')
        check(_none is None and err_owner, '用户模型缺少 owner 被拒绝')

        u_a = am.create_model({
            'name': 'T-UserA', 'apiUrl': 'https://api.deepseek.com/v1/chat/completions',
            'apiKey': 'sk-userA', 'model': 'deepseek-chat',
        }, scope=am.SCOPE_USER, owner_key='openid-A')[0]
        u_b = am.create_model({
            'name': 'T-UserB', 'apiUrl': 'https://api.deepseek.com/v1/chat/completions',
            'apiKey': 'sk-userB', 'model': 'deepseek-chat',
        }, scope=am.SCOPE_USER, owner_key='openid-B')[0]
        check(u_a and u_b, '两个用户各自创建模型成功')
        check(am.count_models(am.SCOPE_USER, 'openid-A') == 1, 'A 的用户模型计数 = 1')
        check(len(am.list_accessible_models('openid-A')) == 2,
              'A 可见 = 1 全局 + 1 自有 = 2')

        # 越权：B 无法改 A 的模型
        _x, err_cross = am.update_model(u_a['_id'], {'name': 'hack'},
                                        scope=am.SCOPE_USER, owner_key='openid-B')
        check(err_cross is not None, '越权修改他人模型被拒绝')
        _y, err_cross2 = am.delete_model(u_a['_id'], scope=am.SCOPE_USER, owner_key='openid-B')
        check(err_cross2 is not None, '越权删除他人模型被拒绝')

        # 用户上限 5
        for i in range(2, 6):
            am.create_model({
                'name': 'T-UserA-%d' % i, 'apiUrl': 'https://a.com/v1',
                'apiKey': 'k%d' % i, 'model': 'm',
            }, scope=am.SCOPE_USER, owner_key='openid-A')
        check(am.count_models(am.SCOPE_USER, 'openid-A') == 5, '用户模型达到上限 5')
        _ov, err_ov = am.create_model({
            'name': 'T-over', 'apiUrl': 'https://a.com/v1', 'apiKey': 'k', 'model': 'm',
        }, scope=am.SCOPE_USER, owner_key='openid-A')
        check(_ov is None and '上限' in (err_ov or ''), f'用户超上限被拒绝（{err_ov}）')

        # 首选全局模型指针
        cleared = am.set_user_preferred_global('openid-B', g1['_id'])[0]
        check(cleared is not None, '可将全局模型设为用户首选')
        check(am.get_user_preferred_model('openid-B')['_id'] == g1['_id'],
              '用户首选指针可读回')

        # ============ D. 解析链优先级 ============
        section('D. 运行时解析链')
        clear(am.MODEL_COLLECTION)
        clear(am.PREF_COLLECTION)
        gd = make_global('T-Global-Default')
        am.set_default(gd['_id'], scope=am.SCOPE_GLOBAL)
        g2 = make_global('T-Global-Second', model='gpt-4o')
        ud = am.create_model({
            'name': 'T-User-Default', 'apiUrl': 'https://api.deepseek.com/v1/chat/completions',
            'apiKey': 'sk-ud', 'model': 'deepseek-chat',
        }, scope=am.SCOPE_USER, owner_key='openid-X')[0]

        # 1) 显式指定
        r, e = am.resolve_model(model_id=g2['_id'], openid='openid-X')
        check(e is None and r['_id'] == g2['_id'] and r['source'] == 'explicit',
              '显式 model_id 优先（source=explicit）')

        # 2) 用户默认优先于全局默认
        r2, e2 = am.resolve_model(model_id=None, openid='openid-X')
        check(e2 is None and r2['_id'] == ud['_id'] and r2['source'] == 'user-default',
              '未指定时使用用户默认（source=user-default）')

        # 3) 无用户模型 → 全局默认
        r3, e3 = am.resolve_model(model_id=None, openid='openid-Z')
        check(e3 is None and r3['_id'] == gd['_id'] and r3['source'] == 'global-default',
              '无用户模型时落到全局默认（source=global-default）')

        # 4) 显式指定他人模型 → 回退
        r4, e4 = am.resolve_model(model_id=ud['_id'], openid='openid-Z')
        check(e4 is None and r4['source'] == 'global-default',
              '显式指定不可访问模型时回退到全局默认')

        # 5) 无任何模型条目 → legacy（临时注入旧配置以验证）
        from adminapi.views_ai import _AI_CONFIG_COLLECTION, _AI_CONFIG_DOC_ID
        cfg_doc = Document.objects.filter(
            collection=_AI_CONFIG_COLLECTION, doc_id=_AI_CONFIG_DOC_ID).first()
        cfg_backup = dict(cfg_doc.data) if cfg_doc else None
        cfg_data = dict(cfg_backup or {})
        cfg_data['apiKey'] = 'sk-legacy-test'
        cfg_data['apiUrl'] = cfg_data.get('apiUrl') or 'https://api.openai.com/v1/chat/completions'
        cfg_data['model'] = cfg_data.get('model') or 'gpt-4o-mini'
        # 注入一条功能级配置，验证 legacy 下的模型名覆盖行为
        cfg_data['feature_config'] = {'ai_grade': {
            'enabled': True, 'model': 'gpt-4o', 'temperature': 0.2, 'max_tokens': 4000}}
        if cfg_doc:
            cfg_doc.data = cfg_data
            cfg_doc.save(update_fields=['data'])
        else:
            Document.objects.create(
                collection=_AI_CONFIG_COLLECTION, doc_id=_AI_CONFIG_DOC_ID, data=cfg_data)
        clear(am.MODEL_COLLECTION)
        r5, e5 = am.resolve_model(model_id=None, openid='openid-Z')
        check(r5 is not None and r5['source'] == 'legacy',
              '无模型条目时回退旧版单配置（source=legacy）')

        # build_call_config：登记模型后功能级模型名覆盖失效；legacy 下仍生效
        mcfg = {'apiUrl': 'https://x/v1', 'apiKey': 'k', 'model': 'entry-model',
                'temperature': 0.9, 'maxTokens': 999, 'source': 'global-default'}
        call_cfg, cerr = am.build_call_config(mcfg, func_name='ai_grade', explicit=False)
        check(cerr is None and call_cfg['model'] == 'entry-model',
              '登记模型后不再被 feature_config 的模型名覆盖')
        legacy_cfg, _ = am.build_call_config(
            {'apiUrl': 'https://x/v1', 'apiKey': 'k', 'model': 'legacy-model',
             'temperature': 0.5, 'maxTokens': 100, 'source': 'legacy'},
            func_name='ai_grade', explicit=False)
        check(legacy_cfg['model'] == 'gpt-4o',
              'legacy 模式保留 feature_config 模型名覆盖（ai_grade → gpt-4o）')

        # 还原 ai_config
        if cfg_backup is None:
            Document.objects.filter(
                collection=_AI_CONFIG_COLLECTION, doc_id=_AI_CONFIG_DOC_ID).delete()
        else:
            d = Document.objects.get(
                collection=_AI_CONFIG_COLLECTION, doc_id=_AI_CONFIG_DOC_ID)
            d.data = cfg_backup
            d.save(update_fields=['data'])

        # ============ E. 缓存按模型隔离 ============
        section('E. 缓存按模型隔离')
        from adminapi.ai_services import AIServiceBase
        base_hash = AIServiceBase.compute_content_hash('same-content', 'type-a')
        am.set_active_model({'model_id': 'm-1', 'model': 'gpt-4o-mini'})
        hash_a = AIServiceBase.compute_content_hash('same-content', 'type-a')
        am.set_active_model({'model_id': 'm-2', 'model': 'deepseek-chat'})
        hash_b = AIServiceBase.compute_content_hash('same-content', 'type-a')
        am.clear_active_model()
        hash_none = AIServiceBase.compute_content_hash('same-content', 'type-a')
        check(base_hash != hash_a, '同一内容在不同模型下哈希不同（隔离生效）')
        check(hash_a != hash_b, '切换模型后哈希改变（下次调用不命中旧缓存）')
        check(base_hash == hash_none, '清除生效模型后哈希回到基线')

        # use_model 上下文自动恢复
        with am.use_model(model=g1):
            inside = am.get_active_signature()
        check(inside == am.model_signature(g1) and am.get_active_model() is None,
              'use_model 上下文进入/退出正确恢复')

        # ============ F. 路由与鉴权 ============
        section('F. 路由与鉴权')
        admin_routes = [
            ('ai-models-dispatch', {'method': 'get'}),
            ('ai-models-meta', {'method': 'get'}),
            ('ai-model-detail', {'method': 'put', 'kwargs': {'model_id': 'X'}}),
            ('ai-model-set-default', {'method': 'post', 'kwargs': {'model_id': 'X'}}),
            ('ai-model-test', {'method': 'post', 'kwargs': {'model_id': 'X'}}),
        ]
        anon = Client()
        for name, spec in admin_routes:
            url = reverse(name, kwargs=spec.get('kwargs'))
            resp = getattr(anon, spec['method'])(url)
            body = json.loads(resp.content.decode('utf-8'))
            check(resp.status_code == 401 and body.get('code') == 40101,
                  f'{spec["method"].upper():5} {url} 未登录 → 401/40101')

        # 带令牌 → 非 401
        admin = None
        for u in AdminUser.objects.select_related('role').all():
            if u.is_superuser:
                admin = u
                break
        if admin:
            tok = issue_token(admin, ttl_hours=1)
            H = {'HTTP_AUTHORIZATION': 'Bearer ' + tok.token}
            resp = anon.get(reverse('ai-models-dispatch'), **H)
            check(resp.status_code == 200, '带令牌 GET /api/admin/ai/models/ → 200')
            resp2 = anon.get(reverse('ai-models-meta'), **H)
            b2 = json.loads(resp2.content.decode('utf-8'))
            check(resp2.status_code == 200 and 'limits' in (b2.get('data') or {}),
                  '带令牌 GET /api/admin/ai/models/meta/ 返回 limits')
            tok.delete()

        mp_routes = [
            ('ai-models-mp', 'get', {}),
            ('ai-models-meta-mp', 'get', {}),
            ('ai-model-detail-mp', 'put', {'model_id': 'X'}),
            ('ai-model-set-default-mp', 'post', {'model_id': 'X'}),
            ('ai-model-test-mp', 'post', {'model_id': 'X'}),
        ]
        for name, method, kwargs in mp_routes:
            url = reverse(name, kwargs=kwargs)
            resp = getattr(anon, method)(url)
            body = json.loads(resp.content.decode('utf-8'))
            check(resp.status_code == 401 and body.get('code') == 40101,
                  f'小程序 {method.upper():5} {url} 无 openid → 401/40101')

        mpc = Client()
        H_OPENID = {'HTTP_X_OPENID': 'openid-smoke'}
        resp = mpc.get(reverse('ai-models-mp'), **H_OPENID)
        b = json.loads(resp.content.decode('utf-8'))
        check(resp.status_code == 200 and 'list' in (b.get('data') or {}),
              '小程序带 X-Openid GET /api/ai/models/ → 200 且返回 list')

        # ============ G. 端到端 HTTP CRUD（不触发真实网络）============
        section('G. 端到端 HTTP CRUD')
        clear(am.MODEL_COLLECTION)
        clear(am.PREF_COLLECTION)
        hc = Client()

        if admin:
            tok2 = issue_token(admin, ttl_hours=1)
            HA = {'HTTP_AUTHORIZATION': 'Bearer ' + tok2.token}
            # 新增
            resp = hc.post(reverse('ai-models-dispatch'), data=json.dumps({
                'name': 'HTTP-Global', 'provider': 'deepseek',
                'apiUrl': 'https://api.deepseek.com/v1/chat/completions',
                'apiKey': 'sk-http-global-1234', 'model': 'deepseek-chat',
            }), content_type='application/json', **HA)
            b = json.loads(resp.content.decode('utf-8'))
            created = b.get('data') or {}
            check(resp.status_code == 200 and created.get('_id'), 'HTTP 新增全局模型成功')
            check(created.get('apiKey') == '****1234', 'HTTP 响应仅返回脱敏 Key')
            mid = created.get('_id')

            # 列表
            resp = hc.get(reverse('ai-models-dispatch'), **HA)
            b = json.loads(resp.content.decode('utf-8'))
            check(len((b.get('data') or {}).get('list') or []) == 1, 'HTTP 列表返回 1 条')

            # 设为默认
            resp = hc.post(reverse('ai-model-set-default', kwargs={'model_id': mid}), **HA)
            check(resp.status_code == 200, 'HTTP 设为全局默认成功')

            # 掩码更新保留原 Key
            resp = hc.put(reverse('ai-model-detail', kwargs={'model_id': mid}),
                          data=json.dumps({'apiKey': '****1234', 'remark': 'x'}),
                          content_type='application/json', **HA)
            resp2 = hc.get(reverse('ai-models-dispatch'), **HA)
            b2 = json.loads(resp2.content.decode('utf-8'))
            item = ((b2.get('data') or {}).get('list') or [{}])[0]
            check(resp.status_code == 200 and item.get('apiKey') == '****1234'
                  and item.get('remark') == 'x', 'HTTP 掩码更新保留原 Key')

            # 测试路由：不存在的模型 → 404（不触发网络）
            resp = hc.post(reverse('ai-model-test', kwargs={'model_id': 'nope'}), **HA)
            b = json.loads(resp.content.decode('utf-8'))
            check(resp.status_code == 404 and b.get('code') == 40401,
                  'HTTP 模型测试路由可用（不存在 → 404/40401）')

            # 上限接口
            resp = hc.get(reverse('ai-models-dispatch'), **HA)
            meta = (json.loads(resp.content.decode('utf-8')).get('data') or {}).get('meta') or {}
            check(meta.get('limits', {}).get('global') == 10 and meta.get('defaultModelId') == mid,
                  'HTTP meta 返回上限与当前默认模型')

            # 删除
            resp = hc.delete(reverse('ai-model-detail', kwargs={'model_id': mid}), **HA)
            check(resp.status_code == 200 and am.count_models(am.SCOPE_GLOBAL) == 0,
                  'HTTP 删除全局模型成功')
            tok2.delete()

        # 小程序端 CRUD
        HM = {'HTTP_X_OPENID': 'openid-http'}
        resp = hc.post(reverse('ai-models-mp'), data=json.dumps({
            'name': 'HTTP-User', 'provider': 'openai',
            'apiUrl': 'https://api.openai.com/v1/chat/completions',
            'apiKey': 'sk-http-user-9999', 'model': 'gpt-4o-mini',
        }), content_type='application/json', **HM)
        b = json.loads(resp.content.decode('utf-8'))
        ucreated = b.get('data') or {}
        check(resp.status_code == 200 and ucreated.get('_id'), '小程序 HTTP 新增自有模型成功')
        umid = ucreated.get('_id')

        # 越权：其他 openid 不能修改
        resp = hc.put(reverse('ai-model-detail-mp', kwargs={'model_id': umid}),
                      data=json.dumps({'name': 'hack'}), content_type='application/json',
                      HTTP_X_OPENID='openid-other')
        check(resp.status_code == 403, '小程序越权修改他人模型 → 403')

        # 设默认
        resp = hc.post(reverse('ai-model-set-default-mp', kwargs={'model_id': umid}), **HM)
        check(resp.status_code == 200, '小程序设为我的默认成功')

        # 列表按用户隔离
        resp = hc.get(reverse('ai-models-mp'), HTTP_X_OPENID='openid-other')
        b = json.loads(resp.content.decode('utf-8'))
        check(len((b.get('data') or {}).get('list') or []) == 0, '小程序模型列表按用户隔离')

        # 违规地址被拒
        resp = hc.post(reverse('ai-models-mp'), data=json.dumps({
            'name': 'bad', 'apiUrl': 'http://127.0.0.1:9/v1', 'apiKey': 'k', 'model': 'm',
        }), content_type='application/json', **HM)
        check(resp.status_code == 400, '小程序提交内网地址 → 400')

        # 删除
        resp = hc.delete(reverse('ai-model-detail-mp', kwargs={'model_id': umid}), **HM)
        check(resp.status_code == 200, '小程序删除自有模型成功')

        # ============ H. 功能级配置选择模型（管理端「功能级配置」下拉） ============
        section('H. 功能级配置选择模型')
        clear(am.MODEL_COLLECTION)
        clear(am.PREF_COLLECTION)
        hd = make_global('H-Global-Default', model='gpt-4o-mini')
        am.set_default(hd['_id'], scope=am.SCOPE_GLOBAL)
        h2 = make_global('H-Grade-Model', provider='deepseek',
                         apiUrl='https://api.deepseek.com/v1/chat/completions',
                         apiKey='sk-FAKE-TEST-KEY-7777', model='deepseek-reasoner',
                         temperature=0.9, maxTokens=3000)
        hd_off = make_global('H-Disabled', model='gpt-4o', enabled=False)

        cfg_doc2 = Document.objects.filter(
            collection=_AI_CONFIG_COLLECTION, doc_id=_AI_CONFIG_DOC_ID).first()
        cfg_backup2 = dict(cfg_doc2.data) if cfg_doc2 else None

        def _put_feature(fc, enabled=True):
            d = Document.objects.filter(
                collection=_AI_CONFIG_COLLECTION, doc_id=_AI_CONFIG_DOC_ID).first()
            data = dict(d.data or {})
            data['enabled'] = enabled
            data['feature_config'] = fc
            d.data = data
            d.save(update_fields=['data'])

        # H1) 目录元信息
        meta_features = am.model_meta().get('features') or []
        feat_keys = {f['key'] for f in meta_features}
        check(len(meta_features) >= 12 and 'kb_qa' in feat_keys and 'ai_grade' in feat_keys,
              f'model_meta.features 暴露完整功能目录（{len(meta_features)} 项）')
        check(all(f.get('label') for f in meta_features), '每个功能都有可读 label')

        # H2) 按模型 ID 命中 → source=feature
        _put_feature({'ai_grade': {'enabled': True, 'model': h2['_id'],
                                   'temperature': 0.2, 'max_tokens': 1200}})
        rh, eh = am.resolve_model(model_id=None, openid='openid-F', func_name='ai_grade')
        check(eh is None and rh and rh['_id'] == h2['_id'] and rh['source'] == 'feature',
              '功能级配置按 model_id 命中（source=feature）')

        # H3) 命中时功能级 temperature / max_tokens 叠加生效
        cc_h, cch_err = am.build_call_config(rh, func_name='ai_grade', explicit=False)
        check(cch_err is None and cc_h['temperature'] == 0.2 and cc_h['maxTokens'] == 1200,
              f'功能级 temperature/max_tokens 叠加生效（{cc_h and (cc_h["temperature"], cc_h["maxTokens"])}）')
        check(cc_h['model'] == 'deepseek-reasoner',
              '功能级命中时模型标识以条目为准，不被覆盖')

        # H4) 按「模型标识」字符串命中（兼容历史遗留值）
        _put_feature({'ai_grade': {'enabled': True, 'model': 'deepseek-reasoner'}})
        rh4, _ = am.resolve_model(model_id=None, openid='openid-F', func_name='ai_grade')
        check(rh4 and rh4['source'] == 'feature' and rh4['_id'] == h2['_id'],
              '功能级配置按「模型标识」字符串命中已登记模型')

        # H5) 未知值 → 回退默认（不回退为名称覆盖）
        _put_feature({'ai_grade': {'enabled': True, 'model': 'no-such-model-xyz'}})
        rf, fn = am.resolve_feature_model('ai_grade')
        check(rf is None and fn == 'no-such-model-xyz',
              'resolve_feature_model 未命中时返回名称覆盖')
        rh5, _ = am.resolve_model(model_id=None, openid='openid-F', func_name='ai_grade')
        check(rh5 and rh5['source'] == 'global-default' and rh5['_id'] == hd['_id'],
              '功能级未知值回退到全局默认（source=global-default）')

        # H6) 命中的模型已禁用 → 不生效、回退默认
        _put_feature({'ai_grade': {'enabled': True, 'model': hd_off['_id']}})
        rf6, _ = am.resolve_feature_model('ai_grade')
        check(rf6 is None, '命中已禁用模型时不返回该模型（不生效）')
        rh6, _ = am.resolve_model(model_id=None, openid='openid-F', func_name='ai_grade')
        check(rh6 and rh6['source'] == 'global-default' and rh6['_id'] == hd['_id'],
              '功能级模型被禁用时回退到全局默认')

        # H7) 请求显式 model_id 优先于功能级配置
        _put_feature({'ai_grade': {'enabled': True, 'model': h2['_id']}})
        rh7, _ = am.resolve_model(model_id=hd['_id'], openid='openid-F', func_name='ai_grade')
        check(rh7 and rh7['source'] == 'explicit' and rh7['_id'] == hd['_id'],
              '请求显式 model_id 优先于功能级配置（source=explicit）')

        # H8) 服务自动以 SERVICE_NAME 参与解析（无需调用点改代码）
        am.clear_active_model()
        _put_feature({'kb_qa': {'enabled': True, 'model': h2['_id']}})
        from adminapi import ai_services as asvc
        import adminapi.views_ai as vw

        captured = {}

        class _ProbeService(asvc.AIServiceBase):
            SERVICE_NAME = 'kb_qa'

        orig_call = vw._call_llm

        def _stub(call_config, messages):
            captured['config'] = dict(call_config)
            return 'ok-stub', None

        vw._call_llm = _stub
        try:
            content_h, err_h = _ProbeService.call_llm_with_fallback(
                [{'role': 'user', 'content': 'hi'}])
        finally:
            vw._call_llm = orig_call
        check(content_h == 'ok-stub' and err_h is None,
              'call_llm_with_fallback 正常返回（stub 拦截）')
        check(captured.get('config', {}).get('model') == 'deepseek-reasoner',
              f'服务自动以 SERVICE_NAME 解析到功能级模型（{captured.get("config", {}).get("model")}）')

        # H9) 显式 use_model 仍覆盖功能级（服务内部直接复用线程模型）
        am.clear_active_model()
        _put_feature({'kb_qa': {'enabled': True, 'model': h2['_id']}})
        captured.clear()
        vw._call_llm = _stub
        try:
            with am.use_model(model_id=hd['_id'], openid='openid-F', func_name='kb_qa'):
                _ProbeService.call_llm_with_fallback([{'role': 'user', 'content': 'hi'}])
        finally:
            vw._call_llm = orig_call
            am.clear_active_model()
        check(captured.get('config', {}).get('model') == 'gpt-4o-mini',
              'use_model 显式指定时覆盖功能级配置')

        # 还原 ai_config
        if cfg_backup2 is None:
            Document.objects.filter(
                collection=_AI_CONFIG_COLLECTION, doc_id=_AI_CONFIG_DOC_ID).delete()
        else:
            d2 = Document.objects.get(
                collection=_AI_CONFIG_COLLECTION, doc_id=_AI_CONFIG_DOC_ID)
            d2.data = cfg_backup2
            d2.save(update_fields=['data'])

    finally:
        # ---------- 还原 ----------
        clear(am.MODEL_COLLECTION)
        clear(am.PREF_COLLECTION)
        for doc_id, data in snap_models:
            Document.objects.create(collection=am.MODEL_COLLECTION, doc_id=doc_id, data=data)
        for doc_id, data in snap_pref:
            Document.objects.create(collection=am.PREF_COLLECTION, doc_id=doc_id, data=data)
        am.clear_active_model()

    print('\n' + '=' * 44)
    print(f'  结果: 通过 {PASS}, 失败 {FAIL}')
    for f in FAILED:
        print(f'    - {f}')
    print('=' * 44)
    return 0 if FAIL == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
