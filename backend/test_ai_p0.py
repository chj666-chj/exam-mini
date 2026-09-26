#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""考试宝 P0 级 AI 功能后端综合测试脚本。

测试范围：
  1. 模块导入测试
  2. AICacheManager 测试
  3. AIJobManager 测试
  4. PromptBuilder 测试
  5. AIServiceBase 测试
  6. 权限点测试
  7. 路由注册测试
  8. settings 配置测试
  9. 缓存失效测试（DB 集成）
 10. Django check

运行方式：
  cd backend
  python test_ai_p0.py
"""
import os
import sys
import json
import traceback

# ---- Django 初始化 ----
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django
django.setup()

from django.conf import settings
from django.urls import reverse
from django.test.utils import get_runner

# ---- 测试框架 ----

_results = []  # (test_name, passed, detail)


def test(name):
    """测试装饰器/上下文管理器替代 —— 简单的断言记录器。"""

    def _record(passed, detail=''):
        _results.append((name, passed, detail))
        status = 'PASS' if passed else 'FAIL'
        print('  [%s] %s%s' % (status, name, (' -- ' + detail) if detail else ''))

    return _record


def assert_true(name, condition, detail=''):
    """断言 condition 为 True。"""
    passed = bool(condition)
    _results.append((name, passed, detail if not passed else ''))
    status = 'PASS' if passed else 'FAIL'
    print('  [%s] %s%s' % (status, name, (' -- ' + detail) if not passed else ''))
    return passed


def assert_equal(name, actual, expected, detail=''):
    """断言 actual == expected。"""
    passed = actual == expected
    if not passed:
        msg = detail or ('expected %r, got %r' % (expected, actual))
    else:
        msg = ''
    _results.append((name, passed, msg))
    status = 'PASS' if passed else 'FAIL'
    print('  [%s] %s%s' % (status, name, (' -- ' + msg) if not passed else ''))
    return passed


def assert_in(name, item, container, detail=''):
    """断言 item in container。"""
    passed = item in container
    if not passed:
        msg = detail or ('%r not in container (len=%d)' % (item, len(container)))
    else:
        msg = ''
    _results.append((name, passed, msg))
    status = 'PASS' if passed else 'FAIL'
    print('  [%s] %s%s' % (status, name, (' -- ' + msg) if not passed else ''))
    return passed


def assert_not_in(name, item, container, detail=''):
    """断言 item not in container。"""
    passed = item not in container
    if not passed:
        msg = detail or ('%r should not be in container' % (item,))
    else:
        msg = ''
    _results.append((name, passed, msg))
    status = 'PASS' if passed else 'FAIL'
    print('  [%s] %s%s' % (status, name, (' -- ' + msg) if not passed else ''))
    return passed


# ====================================================================
# 测试用例
# ====================================================================

def test_module_imports():
    """测试 1：模块导入测试"""
    print('\n=== 测试 1：模块导入测试 ===')

    # 1.1 四个新模块能正常导入
    try:
        from adminapi import ai_cache, ai_jobs, ai_prompts, ai_services
        assert_true('import ai_cache', True)
        assert_true('import ai_jobs', True)
        assert_true('import ai_prompts', True)
        assert_true('import ai_services', True)
    except Exception as e:
        assert_true('import ai modules', False, str(e))

    # 1.2 ai_services.py 中的 4 个类能正常引用
    try:
        from adminapi.ai_services import (
            AIServiceBase, QuestionAnalysisService,
            ExamCompositionService, GradingService,
        )
        assert_true('ref AIServiceBase', AIServiceBase is not None)
        assert_true('ref QuestionAnalysisService', QuestionAnalysisService is not None)
        assert_true('ref ExamCompositionService', ExamCompositionService is not None)
        assert_true('ref GradingService', GradingService is not None)
    except Exception as e:
        assert_true('ref ai_services classes', False, str(e))


def test_ai_cache_manager():
    """测试 2：AICacheManager 测试"""
    print('\n=== 测试 2：AICacheManager 测试 ===')
    from adminapi.ai_cache import AICacheManager

    # 2.1 相同输入相同 hash
    h1 = AICacheManager.compute_hash('abc', 'def')
    h2 = AICacheManager.compute_hash('abc', 'def')
    assert_equal('compute_hash 相同输入相同 hash', h1, h2)

    # 2.2 不同输入不同 hash
    h3 = AICacheManager.compute_hash('abc', 'xyz')
    assert_true('compute_hash 不同输入不同 hash', h1 != h3,
                'h1=%s, h3=%s' % (h1, h3))

    # 2.3 None 不报错
    try:
        h_none = AICacheManager.compute_hash(None)
        assert_true('compute_hash(None) 不报错', isinstance(h_none, str) and len(h_none) > 0)
    except Exception as e:
        assert_true('compute_hash(None) 不报错', False, str(e))

    # 2.4 hash 长度 == 16
    h_len = AICacheManager.compute_hash('test', 'data', 123)
    assert_equal('compute_hash 返回长度 == 16', len(h_len), 16)


def test_ai_job_manager():
    """测试 3：AIJobManager 测试"""
    print('\n=== 测试 3：AIJobManager 测试 ===')
    from adminapi.ai_jobs import AIJobManager

    created_job_ids = []

    # 3.1 create 返回有效 job_id
    try:
        job_id = AIJobManager.create('test_job', {'foo': 'bar'})
        created_job_ids.append(job_id)
        assert_true('create 返回非空字符串 job_id',
                    isinstance(job_id, str) and len(job_id) > 0)
    except Exception as e:
        assert_true('create 返回非空字符串 job_id', False, str(e))
        return

    # 3.2 get 返回包含 status='pending' 的 dict
    job_data = AIJobManager.get(job_id)
    assert_true('get 返回 dict', isinstance(job_data, dict))
    if isinstance(job_data, dict):
        assert_equal('get 初始 status=pending', job_data.get('status'), 'pending')
        assert_equal('get job_type', job_data.get('job_type'), 'test_job')

    # 3.3 update 更新状态
    AIJobManager.update(job_id, status='running', progress=50)
    job_data = AIJobManager.get(job_id)
    assert_equal('update status=running', job_data.get('status'), 'running')
    assert_equal('update progress=50', job_data.get('progress'), 50)

    # 3.4 list 返回分页结果
    # 先创建另一个 job 确保 list 非空
    job_id2 = AIJobManager.create('test_job2', {'foo': 'bar2'})
    created_job_ids.append(job_id2)
    result = AIJobManager.list()
    assert_true('list 返回 dict', isinstance(result, dict))
    if isinstance(result, dict):
        assert_true('list 包含 list key', 'list' in result)
        assert_true('list 包含 total key', 'total' in result)
        assert_true('list 包含 page key', 'page' in result)
        assert_true('list 包含 page_size key', 'page_size' in result)
        assert_true('list total >= 2', result.get('total', 0) >= 2,
                    'total=%s' % result.get('total'))
        assert_true('list items 是列表', isinstance(result.get('list'), list))

    # 3.5 cancel 能将状态改为 cancelled
    AIJobManager.cancel(job_id2)
    job_data2 = AIJobManager.get(job_id2)
    assert_equal('cancel status=cancelled', job_data2.get('status'), 'cancelled')

    # 清理测试数据
    from core.models import Document
    for jid in created_job_ids:
        Document.objects.filter(collection=AIJobManager.COLLECTION, doc_id=jid).delete()


def test_prompt_builder():
    """测试 4：PromptBuilder 测试"""
    print('\n=== 测试 4：PromptBuilder 测试 ===')
    from adminapi.ai_prompts import PromptBuilder

    # 4.1 build_system_prompt 各功能返回非空字符串
    sp1 = PromptBuilder.build_system_prompt('question_analyze')
    assert_true('build_system_prompt(question_analyze) 非空',
                isinstance(sp1, str) and len(sp1) > 0)

    sp2 = PromptBuilder.build_system_prompt('exam_compose')
    assert_true('build_system_prompt(exam_compose) 非空',
                isinstance(sp2, str) and len(sp2) > 0)

    sp3 = PromptBuilder.build_system_prompt('ai_grade')
    assert_true('build_system_prompt(ai_grade) 非空',
                isinstance(sp3, str) and len(sp3) > 0)

    # 4.2 build_question_analyze_prompt 包含题干
    content = '以下哪项是正确答案？'
    uap = PromptBuilder.build_question_analyze_prompt(content, 'single', [])
    assert_true('build_question_analyze_prompt 非空',
                isinstance(uap, str) and len(uap) > 0)
    assert_true('build_question_analyze_prompt 包含题干',
                content in uap, '题干未出现在 prompt 中')

    # 4.3 build_grading_prompt 返回非空字符串
    question_data = {
        'content_md': '请简述 TCP 三次握手过程。',
        'qtype': 'qa',
        'options': [],
        'answer_md': 'SYN, SYN-ACK, ACK',
    }
    gp = PromptBuilder.build_grading_prompt(question_data, '考生答案内容', '评分标准', 10)
    assert_true('build_grading_prompt 非空',
                isinstance(gp, str) and len(gp) > 0)

    # 4.4 parse_json_response 纯 JSON
    r1 = PromptBuilder.parse_json_response('{"key": "value"}')
    assert_equal('parse_json_response 纯 JSON', r1, {'key': 'value'})

    # 4.5 parse_json_response ```json 代码块
    r2 = PromptBuilder.parse_json_response('```json\n{"key": "value"}\n```')
    assert_equal('parse_json_response ```json 代码块', r2, {'key': 'value'})

    # 4.6 parse_json_response 前后多余文字
    r3 = PromptBuilder.parse_json_response('some text {"key": "value"} more text')
    assert_equal('parse_json_response 前后多余文字', r3, {'key': 'value'})


def test_ai_service_base():
    """测试 5：AIServiceBase 测试"""
    print('\n=== 测试 5：AIServiceBase 测试 ===')
    from adminapi.ai_services import AIServiceBase

    # 5.1 sanitize_for_llm 移除 _openid 和 nickName，保留 content
    data1 = {'_openid': 'xxx', 'content': 'hello', 'nickName': 'test'}
    sanitized1 = AIServiceBase.sanitize_for_llm(data1)
    assert_not_in('sanitize 移除 _openid', '_openid', sanitized1)
    assert_not_in('sanitize 移除 nickName', 'nickName', sanitized1)
    assert_in('sanitize 保留 content', 'content', sanitized1)
    assert_equal('sanitize content 值', sanitized1.get('content'), 'hello')

    # 5.2 sanitize_for_llm 递归移除嵌套 PII
    data2 = {'nested': {'_openid': 'xxx', 'data': 'keep'}}
    sanitized2 = AIServiceBase.sanitize_for_llm(data2)
    nested = sanitized2.get('nested', {})
    assert_not_in('sanitize 嵌套移除 _openid', '_openid', nested)
    assert_equal('sanitize 嵌套保留 data', nested.get('data'), 'keep')

    # 5.3 sanitize_for_llm 递归移除列表中的 PII
    data3 = {'list': [{'_openid': 'xxx', 'data': 'keep'}]}
    sanitized3 = AIServiceBase.sanitize_for_llm(data3)
    lst = sanitized3.get('list', [])
    assert_true('sanitize list 非空', isinstance(lst, list) and len(lst) > 0)
    if lst:
        assert_not_in('sanitize 列表项移除 _openid', '_openid', lst[0])
        assert_equal('sanitize 列表项保留 data', lst[0].get('data'), 'keep')

    # 5.4 get_model_config('question_analyze') 返回包含必要 key 的 dict
    try:
        cfg1 = AIServiceBase.get_model_config('question_analyze')
        assert_true('get_model_config(question_analyze) 返回 dict', isinstance(cfg1, dict))
        if isinstance(cfg1, dict):
            for key in ('model', 'max_tokens', 'temperature', 'tier', 'enabled'):
                assert_in('get_model_config(question_analyze) 含 %s' % key, key, cfg1)
    except Exception as e:
        assert_true('get_model_config(question_analyze)', False, str(e))

    # 5.5 get_model_config('ai_grade') 返回 tier='complex'
    try:
        cfg2 = AIServiceBase.get_model_config('ai_grade')
        assert_true('get_model_config(ai_grade) 返回 dict', isinstance(cfg2, dict))
        if isinstance(cfg2, dict):
            assert_equal('get_model_config(ai_grade) tier=complex',
                         cfg2.get('tier'), 'complex')
    except Exception as e:
        assert_true('get_model_config(ai_grade)', False, str(e))


def test_permissions():
    """测试 6：权限点测试"""
    print('\n=== 测试 6：权限点测试 ===')
    from adminapi.permissions import PERMISSION_DEFS, PERMISSION_CODES, DEFAULT_ROLE_PERMISSIONS

    # 6.1 六个 AI 权限点都在 PERMISSION_CODES 中
    ai_perms = ['ai.analyze', 'ai.compose', 'ai.grade',
                'ai.report', 'ai.recommend', 'ai.job.view']
    for perm in ai_perms:
        assert_in('PERMISSION_CODES 含 %s' % perm, perm, PERMISSION_CODES)

    # 6.2 PERMISSION_DEFS 是三元组列表
    assert_true('PERMISSION_DEFS 非空', len(PERMISSION_DEFS) > 0)

    # 6.3 operator 角色包含全部 6 个 AI 权限点
    operator_perms = DEFAULT_ROLE_PERMISSIONS.get('operator', [])
    for perm in ai_perms:
        assert_in('operator 含 %s' % perm, perm, operator_perms)

    # 6.4 viewer 角色包含 ai.job.view
    viewer_perms = DEFAULT_ROLE_PERMISSIONS.get('viewer', [])
    assert_in('viewer 含 ai.job.view', 'ai.job.view', viewer_perms)


def test_url_routes():
    """测试 7：路由注册测试"""
    print('\n=== 测试 7：路由注册测试 ===')
    route_names = [
        'ai-job-list', 'ai-job-status', 'ai-job-cancel',
        'ai-question-analyze', 'ai-question-analyze-batch',
        'ai-exam-compose', 'ai-compose-status', 'ai-compose-confirm',
        'ai-grade-batch', 'ai-grade-review-list', 'ai-grade-review',
    ]
    for name in route_names:
        try:
            # 带参数的路由需要提供参数
            if name in ('ai-job-status', 'ai-job-cancel', 'ai-compose-status',
                        'ai-compose-confirm', 'ai-question-analyze', 'ai-grade-review'):
                if name == 'ai-question-analyze':
                    url = reverse(name, args=['test123'])
                elif name == 'ai-grade-review':
                    url = reverse(name, args=['hist001'])
                else:
                    url = reverse(name, args=['job001'])
            else:
                url = reverse(name)
            assert_true('reverse(%s) 成功' % name, isinstance(url, str) and len(url) > 0)
        except Exception as e:
            assert_true('reverse(%s)' % name, False, str(e))


def test_settings():
    """测试 8：settings 配置测试"""
    print('\n=== 测试 8：settings 配置测试 ===')

    # 8.1 AI_FEATURE_CONFIG_DEFAULTS 存在
    assert_true('settings.AI_FEATURE_CONFIG_DEFAULTS 存在',
                hasattr(settings, 'AI_FEATURE_CONFIG_DEFAULTS'))

    if hasattr(settings, 'AI_FEATURE_CONFIG_DEFAULTS'):
        cfg = settings.AI_FEATURE_CONFIG_DEFAULTS
        assert_true('AI_FEATURE_CONFIG_DEFAULTS 是 dict', isinstance(cfg, dict))

        # 8.2 包含三个 key
        for key in ('question_analyze', 'exam_compose', 'ai_grade'):
            assert_in('AI_FEATURE_CONFIG_DEFAULTS 含 %s' % key, key, cfg)


def test_cache_invalidation():
    """测试 9：缓存失效测试（DB 集成）"""
    print('\n=== 测试 9：缓存失效测试 ===')
    from adminapi.ai_cache import AICacheManager
    from core.models import Document
    from django.utils import timezone

    # 创建临时题目文档
    test_doc_id = 'test-cache-invalid-%s' % timezone.now().strftime('%Y%m%d%H%M%S')
    doc = Document.objects.create(
        collection='questions',
        doc_id=test_doc_id,
        data={
            'content_md': '测试题干内容',
            'qtype': 'single',
            'options': [],
        },
    )

    try:
        # 9.1 写入 ai_analysis 缓存
        content_hash = AICacheManager.compute_hash('测试题干内容', 'single', '[]')
        cache_data = {
            'knowledge_points': [{'name': '测试知识点', 'confidence': 0.9}],
            'difficulty': 'easy',
            'difficulty_score': 3,
        }
        AICacheManager.set('questions', test_doc_id, 'ai_analysis',
                           cache_data, content_hash)
        assert_true('AICacheManager.set 写入缓存', True)

        # 9.2 get 能读取到
        cached = AICacheManager.get('questions', test_doc_id, 'ai_analysis')
        assert_true('AICacheManager.get 读取缓存非 None', cached is not None)
        if cached:
            assert_equal('缓存 content_hash 匹配',
                         cached.get('content_hash'), content_hash)
            assert_in('缓存含 knowledge_points', 'knowledge_points', cached)
            assert_equal('缓存 difficulty', cached.get('difficulty'), 'easy')

        # 9.3 invalidate 清除
        AICacheManager.invalidate('questions', test_doc_id, 'ai_analysis')
        assert_true('AICacheManager.invalidate 执行', True)

        # 9.4 get 返回 None
        cached_after = AICacheManager.get('questions', test_doc_id, 'ai_analysis')
        assert_true('AICacheManager.get 失效后返回 None', cached_after is None,
                    'got %r' % cached_after)

    finally:
        # 清理临时文档
        Document.objects.filter(collection='questions', doc_id=test_doc_id).delete()


def test_django_check():
    """测试 10：Django check"""
    print('\n=== 测试 10：Django check ===')
    from django.core.management import call_command
    from io import StringIO

    try:
        out = StringIO()
        err = StringIO()
        call_command('check', stdout=out, stderr=err)
        output = out.getvalue() + err.getvalue()
        # Django check 成功时输出 "System check identified no issues"
        has_no_issues = 'no issues' in output.lower() or '0 issues' in output.lower()
        assert_true('Django check 无错误', has_no_issues, output.strip()[:200])
    except Exception as e:
        assert_true('Django check 无错误', False, str(e))


# ====================================================================
# 主执行入口
# ====================================================================

def main():
    print('=' * 70)
    print('考试宝 P0 级 AI 功能后端综合测试')
    print('=' * 70)

    tests = [
        test_module_imports,
        test_ai_cache_manager,
        test_ai_job_manager,
        test_prompt_builder,
        test_ai_service_base,
        test_permissions,
        test_url_routes,
        test_settings,
        test_cache_invalidation,
        test_django_check,
    ]

    for test_func in tests:
        try:
            test_func()
        except Exception as e:
            print('  [ERROR] %s 异常: %s' % (test_func.__name__, e))
            traceback.print_exc()
            _results.append((test_func.__name__, False, str(e)))

    # ---- 汇总 ----
    print('\n' + '=' * 70)
    print('测试汇总')
    print('=' * 70)

    total = len(_results)
    passed = sum(1 for _, p, _ in _results if p)
    failed = total - passed

    print('总测试数: %d | 通过: %d | 失败: %d' % (total, passed, failed))
    print()

    if failed > 0:
        print('--- 失败用例详情 ---')
        for name, p, detail in _results:
            if not p:
                print('  FAIL: %s' % name)
                if detail:
                    print('        %s' % detail)
        print()

    print('Routing Decision: %s' % (
        'NoOne (全部通过)' if failed == 0 else
        '需分析失败原因（源码 Bug 或测试 Bug）'
    ))

    # 返回退出码
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
