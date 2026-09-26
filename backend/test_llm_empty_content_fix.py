"""Test: LLM empty content response fix for exam analysis.

Tests the fix for the "LLM attempt 2 failed: None" error caused by
_call_llm returning (None, None) when the LLM returns HTTP 200 but
empty content in the response body.

Root cause:
  - _call_llm returned (content, None) where content='' (falsy)
  - call_llm_with_fallback saw `if content:` as False, entered retry
  - err was None → log printed "LLM attempt 2 failed: None"
  - All retries got same empty response → all failed

Fix:
  1. _call_llm: check finish_reason, return descriptive error for empty content
  2. call_llm_with_fallback: ensure err is never None when content is falsy,
     skip retries for non-retryable empty-content (content_filter, function_call)
     limit retries for non-timeout empty content
"""
import os
import sys
import json
import django
from unittest.mock import patch, MagicMock

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from adminapi.views_ai import _call_llm
from adminapi.ai_services import AIServiceBase

results = []

def test(name, passed, detail=''):
    results.append((name, passed, detail))
    tag = 'PASS' if passed else 'FAIL'
    print(f'  [{tag}] {name}' + (f' -- {detail}' if detail else ''))


print('=' * 70)
print('Test: LLM empty content response fix')
print('=' * 70)


# ===========================================================================
# 1. _call_llm — empty content handling
# ===========================================================================
print('\n--- 1. _call_llm 空内容响应处理 ---')

config = {
    'apiUrl': 'https://api.openai.com/v1/chat/completions',
    'apiKey': 'test-key',
    'model': 'gpt-4o',
    'temperature': 0.7,
    'maxTokens': 4000,
    'tier': 'complex',
}

def make_mock_urlopen(response_body):
    """创建 mock urlopen，正确模拟分块读取（第一次返回数据，第二次返回空）。"""
    def mock_urlopen(req, timeout):
        mock_resp = MagicMock()
        data = json.dumps(response_body).encode('utf-8')
        read_count = [0]
        def mock_read(n=65536):
            if read_count[0] == 0:
                read_count[0] += 1
                return data
            return b''  # EOF
        mock_resp.read = mock_read
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp
    return mock_urlopen

# 1.1 Normal content
with patch('adminapi.views_ai.urllib.request.urlopen',
           side_effect=make_mock_urlopen({
               'choices': [{'message': {'content': '正常分析结果'}, 'finish_reason': 'stop'}]
           })):
    content, err = _call_llm(config, [{'role': 'user', 'content': 'test'}])
    test('正常内容返回', content == '正常分析结果' and err is None,
         f'content={repr(content)}, err={repr(err)}')

# 1.2 Empty content with finish_reason=stop
with patch('adminapi.views_ai.urllib.request.urlopen',
           side_effect=make_mock_urlopen({
               'choices': [{'message': {'content': ''}, 'finish_reason': 'stop'}]
           })):
    content, err = _call_llm(config, [{'role': 'user', 'content': 'test'}])
    test('空内容 stop → 返回描述性错误', content is None and err is not None,
         f'content={repr(content)}, err={repr(err)}')
    test('空内容 stop 错误包含 finish_reason', 'finish_reason=stop' in (err or ''),
         f'err={repr(err)}')

# 1.3 Empty content with finish_reason=length (truncated)
with patch('adminapi.views_ai.urllib.request.urlopen',
           side_effect=make_mock_urlopen({
               'choices': [{'message': {'content': ''}, 'finish_reason': 'length'}]
           })):
    content, err = _call_llm(config, [{'role': 'user', 'content': 'test'}])
    test('截断 length → 错误包含 max_tokens 信息', 'max_tokens' in (err or ''),
         f'err={repr(err)}')
    test('截断 length → 错误包含 finish_reason=length', 'finish_reason=length' in (err or ''),
         f'err={repr(err)}')

# 1.4 Empty content with finish_reason=content_filter
with patch('adminapi.views_ai.urllib.request.urlopen',
           side_effect=make_mock_urlopen({
               'choices': [{'message': {'content': ''}, 'finish_reason': 'content_filter'}]
           })):
    content, err = _call_llm(config, [{'role': 'user', 'content': 'test'}])
    test('内容过滤 → 错误包含 content_filter', 'content_filter' in (err or ''),
         f'err={repr(err)}')

# 1.5 content = None (some providers return null)
with patch('adminapi.views_ai.urllib.request.urlopen',
           side_effect=make_mock_urlopen({
               'choices': [{'message': {'content': None}, 'finish_reason': 'stop'}]
           })):
    content, err = _call_llm(config, [{'role': 'user', 'content': 'test'}])
    test('content=null → 返回描述性错误（不崩溃）', content is None and err is not None,
         f'content={repr(content)}, err={repr(err)}')

# 1.6 Empty choices with error field
with patch('adminapi.views_ai.urllib.request.urlopen',
           side_effect=make_mock_urlopen({
               'choices': [],
               'error': {'message': 'Rate limit exceeded'}
           })):
    content, err = _call_llm(config, [{'role': 'user', 'content': 'test'}])
    test('空 choices + error 字段 → 返回 API 错误信息', 'Rate limit exceeded' in (err or ''),
         f'err={repr(err)}')

# 1.7 Empty choices without error field
with patch('adminapi.views_ai.urllib.request.urlopen',
           side_effect=make_mock_urlopen({'choices': []})):
    content, err = _call_llm(config, [{'role': 'user', 'content': 'test'}])
    test('空 choices 无 error → 返回描述性错误', 'choices 为空' in (err or ''),
         f'err={repr(err)}')


# ===========================================================================
# 2. call_llm_with_fallback — err never None when content is falsy
# ===========================================================================
print('\n--- 2. call_llm_with_fallback err 不为 None ---')

# 2.1 Mock: always returns empty content with err=None (the old bug scenario)
call_count = [0]

def mock_call_llm_empty(config, messages):
    call_count[0] += 1
    return '', None  # This is the bug scenario

with patch('adminapi.views_ai._get_ai_config') as mock_config, \
     patch('adminapi.ai_models.get_active_model', return_value={'model': 'gpt-4o', 'source': 'legacy', 'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key'}), \
     patch('adminapi.ai_models.resolve_model', return_value=({'model': 'gpt-4o', 'source': 'legacy', 'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key'}, None)), \
     patch('adminapi.ai_models.build_call_config', return_value=({'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key', 'model': 'gpt-4o', 'temperature': 0.7, 'maxTokens': 4000, 'tier': 'complex'}, None)), \
     patch('adminapi.views_ai._call_llm', side_effect=mock_call_llm_empty):
    mock_config.return_value = ({'enabled': True}, MagicMock())

    call_count[0] = 0
    content, err = AIServiceBase.call_llm_with_fallback(
        [{'role': 'user', 'content': 'test'}],
        model_tier='complex',
        func_name='exam_analyze',
    )

    test('空内容场景 → 最终 err 不为 None', err is not None,
         f'err={repr(err)}')
    test('空内容场景 → err 包含描述性文字', '空内容' in (err or '') or 'empty' in (err or '').lower(),
         f'err={repr(err)}')
    test('空内容场景 → 不再打印 "None"', 'None' != err,
         f'err={repr(err)}')
    # 非超时空内容只重试一次（attempt 0 + attempt 1 = 2 次调用）
    test('非超时空内容 → 限制重试次数', call_count[0] <= 2,
         f'call_count={call_count[0]}')


# 2.2 content_filter 不重试
call_count2 = [0]
def mock_call_llm_content_filter(config, messages):
    call_count2[0] += 1
    return None, 'LLM 输出被内容过滤（finish_reason=content_filter）'

with patch('adminapi.views_ai._get_ai_config') as mock_config, \
     patch('adminapi.ai_models.get_active_model', return_value={'model': 'gpt-4o', 'source': 'legacy', 'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key'}), \
     patch('adminapi.ai_models.resolve_model', return_value=({'model': 'gpt-4o', 'source': 'legacy', 'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key'}, None)), \
     patch('adminapi.ai_models.build_call_config', return_value=({'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key', 'model': 'gpt-4o', 'temperature': 0.7, 'maxTokens': 4000, 'tier': 'complex'}, None)), \
     patch('adminapi.views_ai._call_llm', side_effect=mock_call_llm_content_filter):
    mock_config.return_value = ({'enabled': True}, MagicMock())

    call_count2[0] = 0
    content, err = AIServiceBase.call_llm_with_fallback(
        [{'role': 'user', 'content': 'test'}],
        model_tier='complex',
        func_name='exam_analyze',
    )

    test('content_filter → 不重试', call_count2[0] == 1,
         f'call_count={call_count2[0]}')
    test('content_filter → 返回具体错误', 'content_filter' in (err or ''),
         f'err={repr(err)}')


# 2.3 finish_reason=length 允许重试
call_count3 = [0]
def mock_call_llm_length(config, messages):
    call_count3[0] += 1
    return None, 'LLM 输出被截断（finish_reason=length），max_tokens=4000 可能过小'

with patch('adminapi.views_ai._get_ai_config') as mock_config, \
     patch('adminapi.ai_models.get_active_model', return_value={'model': 'gpt-4o', 'source': 'legacy', 'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key'}), \
     patch('adminapi.ai_models.resolve_model', return_value=({'model': 'gpt-4o', 'source': 'legacy', 'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key'}, None)), \
     patch('adminapi.ai_models.build_call_config', return_value=({'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key', 'model': 'gpt-4o', 'temperature': 0.7, 'maxTokens': 4000, 'tier': 'complex'}, None)), \
     patch('adminapi.views_ai._call_llm', side_effect=mock_call_llm_length):
    mock_config.return_value = ({'enabled': True}, MagicMock())

    call_count3[0] = 0
    content, err = AIServiceBase.call_llm_with_fallback(
        [{'role': 'user', 'content': 'test'}],
        model_tier='complex',
        func_name='exam_analyze',
    )

    test('finish_reason=length → 允许重试', call_count3[0] >= 2,
         f'call_count={call_count3[0]}')


# 2.4 timeout 允许重试
call_count4 = [0]
def mock_call_llm_timeout(config, messages):
    call_count4[0] += 1
    return None, 'LLM 请求超时（90s）'

with patch('adminapi.views_ai._get_ai_config') as mock_config, \
     patch('adminapi.ai_models.get_active_model', return_value={'model': 'gpt-4o', 'source': 'legacy', 'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key'}), \
     patch('adminapi.ai_models.resolve_model', return_value=({'model': 'gpt-4o', 'source': 'legacy', 'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key'}, None)), \
     patch('adminapi.ai_models.build_call_config', return_value=({'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key', 'model': 'gpt-4o', 'temperature': 0.7, 'maxTokens': 4000, 'tier': 'complex'}, None)), \
     patch('adminapi.views_ai._call_llm', side_effect=mock_call_llm_timeout):
    mock_config.return_value = ({'enabled': True}, MagicMock())

    call_count4[0] = 0
    content, err = AIServiceBase.call_llm_with_fallback(
        [{'role': 'user', 'content': 'test'}],
        model_tier='complex',
        func_name='exam_analyze',
    )

    test('超时 → 允许全部重试', call_count4[0] >= 2,
         f'call_count={call_count4[0]}')


# 2.5 正常成功不重试
call_count5 = [0]
def mock_call_llm_success(config, messages):
    call_count5[0] += 1
    return '成功结果', None

with patch('adminapi.views_ai._get_ai_config') as mock_config, \
     patch('adminapi.ai_models.get_active_model', return_value={'model': 'gpt-4o', 'source': 'legacy', 'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key'}), \
     patch('adminapi.ai_models.resolve_model', return_value=({'model': 'gpt-4o', 'source': 'legacy', 'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key'}, None)), \
     patch('adminapi.ai_models.build_call_config', return_value=({'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key', 'model': 'gpt-4o', 'temperature': 0.7, 'maxTokens': 4000, 'tier': 'complex'}, None)), \
     patch('adminapi.views_ai._call_llm', side_effect=mock_call_llm_success):
    mock_config.return_value = ({'enabled': True}, MagicMock())

    call_count5[0] = 0
    content, err = AIServiceBase.call_llm_with_fallback(
        [{'role': 'user', 'content': 'test'}],
        model_tier='complex',
        func_name='exam_analyze',
    )

    test('成功 → 不重试', call_count5[0] == 1,
         f'call_count={call_count5[0]}')
    test('成功 → 返回内容', content == '成功结果' and err is None,
         f'content={repr(content)}, err={repr(err)}')


# ===========================================================================
# 3. fallback 降级机制
# ===========================================================================
print('\n--- 3. fallback 降级 ---')

cached_result = {'summary': 'cached analysis', 'content_hash': 'abc123'}

def mock_call_llm_always_fail(config, messages):
    return None, 'LLM 返回空内容（finish_reason=stop）'

with patch('adminapi.views_ai._get_ai_config') as mock_config, \
     patch('adminapi.ai_models.get_active_model', return_value={'model': 'gpt-4o', 'source': 'legacy', 'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key'}), \
     patch('adminapi.ai_models.resolve_model', return_value=({'model': 'gpt-4o', 'source': 'legacy', 'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key'}, None)), \
     patch('adminapi.ai_models.build_call_config', return_value=({'apiUrl': 'https://api.openai.com/v1/chat/completions', 'apiKey': 'test-key', 'model': 'gpt-4o', 'temperature': 0.7, 'maxTokens': 4000, 'tier': 'complex'}, None)), \
     patch('adminapi.views_ai._call_llm', side_effect=mock_call_llm_always_fail):
    mock_config.return_value = ({'enabled': True}, MagicMock())

    content, err = AIServiceBase.call_llm_with_fallback(
        [{'role': 'user', 'content': 'test'}],
        model_tier='complex',
        func_name='exam_analyze',
        fallback=cached_result,
    )

    test('有 fallback → 返回缓存结果', content == cached_result,
         f'content={repr(content)}')
    test('有 fallback → err 为 None', err is None,
         f'err={repr(err)}')


# ===========================================================================
# 汇总
# ===========================================================================
print('\n' + '=' * 70)
passed = sum(1 for _, p, _ in results if p)
failed = sum(1 for _, p, _ in results if not p)
total = len(results)
print(f'Results: {passed} passed, {failed} failed, {total} total')
print('=' * 70)

if failed > 0:
    print('\nFailed tests:')
    for name, p, detail in results:
        if not p:
            print(f'  [FAIL] {name} -- {detail}')
    sys.exit(1)
else:
    print('\nAll tests passed!')
    sys.exit(0)
