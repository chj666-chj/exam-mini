"""Test: max_tokens fix for exam analysis LLM truncation.

Root cause: ai_models entry has maxTokens=2000, but exam_analyze (complex tier)
needs 4000. The database feature_config is empty, and AI_FEATURE_CONFIG_DEFAULTS
from settings.py was never applied as a fallback, so maxTokens stayed at 2000
→ LLM output truncated (finish_reason=length) → analysis failed.

Fix:
  1. build_call_config: merge AI_FEATURE_CONFIG_DEFAULTS as base, DB overrides on top
  2. call_llm_with_fallback: tier-based max_tokens as floor for non-legacy models

Test flow: verify the full resolution chain produces maxTokens=4000 for exam_analyze
even when the model entry has maxTokens=2000 and DB feature_config is empty.
"""
import os
import sys
import json
import django
from unittest.mock import patch, MagicMock

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.conf import settings
from adminapi.ai_models import build_call_config
from adminapi.ai_services import MODEL_TIERS, FUNCTION_MODEL_MAP, AIServiceBase

results = []

def test(name, passed, detail=''):
    results.append((name, passed, detail))
    tag = 'PASS' if passed else 'FAIL'
    print(f'  [{tag}] {name}' + (f' -- {detail}' if detail else ''))


print('=' * 70)
print('Test: max_tokens fix for exam analysis LLM truncation')
print('=' * 70)


# ===========================================================================
# 1. build_call_config — AI_FEATURE_CONFIG_DEFAULTS fallback
# ===========================================================================
print('\n--- 1. build_call_config: AI_FEATURE_CONFIG_DEFAULTS fallback ---')

mock_model = {
    'apiUrl': 'https://api.example.com/v1/chat/completions',
    'apiKey': 'test-key',
    'model': 'glm5.2',
    'temperature': 0.7,
    'maxTokens': 2000,  # Too small for complex tier
    'source': 'global-default',
}

# 1.1 DB feature_config is empty → should fall back to settings defaults
mock_ai_config = {'enabled': True, 'feature_config': {}}

with patch('adminapi.views_ai._get_ai_config', return_value=(mock_ai_config, MagicMock())):
    call_config, err = build_call_config(mock_model, func_name='exam_analyze', explicit=False)
    test('DB feature_config 空 → maxTokens 从 settings defaults 获取 4000',
         call_config and call_config.get('maxTokens') == 4000,
         f'maxTokens={call_config.get("maxTokens") if call_config else "N/A"}, err={err}')
    test('DB feature_config 空 → temperature 从 settings defaults 获取 0.7',
         call_config and call_config.get('temperature') == 0.7,
         f'temperature={call_config.get("temperature") if call_config else "N/A"}')

# 1.2 DB feature_config has explicit max_tokens → should override settings defaults
mock_ai_config_override = {
    'enabled': True,
    'feature_config': {'exam_analyze': {'max_tokens': 6000, 'temperature': 0.5}},
}

with patch('adminapi.views_ai._get_ai_config', return_value=(mock_ai_config_override, MagicMock())):
    call_config, err = build_call_config(mock_model, func_name='exam_analyze', explicit=False)
    test('DB feature_config 有值 → DB max_tokens 覆盖 settings defaults',
         call_config and call_config.get('maxTokens') == 6000,
         f'maxTokens={call_config.get("maxTokens") if call_config else "N/A"}')
    test('DB feature_config 有值 → DB temperature 覆盖 settings defaults',
         call_config and call_config.get('temperature') == 0.5,
         f'temperature={call_config.get("temperature") if call_config else "N/A"}')

# 1.3 No func_name → no feature_config applied, use model entry maxTokens
with patch('adminapi.views_ai._get_ai_config', return_value=(mock_ai_config, MagicMock())):
    call_config, err = build_call_config(mock_model, func_name=None, explicit=False)
    test('无 func_name → 使用模型条目 maxTokens=2000',
         call_config and call_config.get('maxTokens') == 2000,
         f'maxTokens={call_config.get("maxTokens") if call_config else "N/A"}')

# 1.4 Different functions get different defaults
mock_ai_config_empty = {'enabled': True, 'feature_config': {}}

with patch('adminapi.views_ai._get_ai_config', return_value=(mock_ai_config_empty, MagicMock())):
    # exam_analyze → complex → 4000
    cc_complex, _ = build_call_config(mock_model, func_name='exam_analyze', explicit=False)
    test('exam_analyze (complex) → maxTokens=4000',
         cc_complex and cc_complex.get('maxTokens') == 4000,
         f'maxTokens={cc_complex.get("maxTokens")}')

    # review_recommend → lite → 1000
    cc_lite, _ = build_call_config(mock_model, func_name='review_recommend', explicit=False)
    test('review_recommend (lite) → maxTokens=1000',
         cc_lite and cc_lite.get('maxTokens') == 1000,
         f'maxTokens={cc_lite.get("maxTokens")}')

    # question_analyze → standard → 2000
    cc_std, _ = build_call_config(mock_model, func_name='question_analyze', explicit=False)
    test('question_analyze (standard) → maxTokens=2000',
         cc_std and cc_std.get('maxTokens') == 2000,
         f'maxTokens={cc_std.get("maxTokens")}')


# ===========================================================================
# 2. call_llm_with_fallback — tier floor for non-legacy models
# ===========================================================================
print('\n--- 2. call_llm_with_fallback: tier floor for non-legacy models ---')

# 2.1 Non-legacy model with small maxTokens → should be raised to tier minimum
call_count = [0]
captured_config = {}

def mock_call_llm_capture(config, messages):
    call_count[0] += 1
    captured_config.update(config)
    return 'success', None

mock_resolved = {
    'model': 'glm5.2',
    'source': 'global-default',
    'apiUrl': 'https://api.example.com/v1/chat/completions',
    'apiKey': 'test-key',
    'maxTokens': 2000,
    'temperature': 0.7,
}

with patch('adminapi.views_ai._get_ai_config', return_value=({'enabled': True, 'feature_config': {}}, MagicMock())), \
     patch('adminapi.ai_models.get_active_model', return_value=mock_resolved), \
     patch('adminapi.ai_models.resolve_model', return_value=(mock_resolved, None)), \
     patch('adminapi.ai_models.build_call_config', return_value=({
         'apiUrl': 'https://api.example.com/v1/chat/completions',
         'apiKey': 'test-key',
         'model': 'glm5.2',
         'temperature': 0.7,
         'maxTokens': 2000,  # Simulate small maxTokens from model entry
     }, None)), \
     patch('adminapi.views_ai._call_llm', side_effect=mock_call_llm_capture):

    call_count[0] = 0
    content, err = AIServiceBase.call_llm_with_fallback(
        [{'role': 'user', 'content': 'test'}],
        model_tier='complex',  # exam_analyze tier
        func_name='exam_analyze',
    )

    test('非 legacy 模型 maxTokens < tier 最小值 → 提升',
         captured_config.get('maxTokens') == 4000,
         f'maxTokens sent to LLM={captured_config.get("maxTokens")}')

# 2.2 Non-legacy model with large maxTokens → should NOT be reduced
with patch('adminapi.views_ai._get_ai_config', return_value=({'enabled': True, 'feature_config': {}}, MagicMock())), \
     patch('adminapi.ai_models.get_active_model', return_value=mock_resolved), \
     patch('adminapi.ai_models.resolve_model', return_value=(mock_resolved, None)), \
     patch('adminapi.ai_models.build_call_config', return_value=({
         'apiUrl': 'https://api.example.com/v1/chat/completions',
         'apiKey': 'test-key',
         'model': 'glm5.2',
         'temperature': 0.7,
         'maxTokens': 8000,  # Larger than tier minimum
     }, None)), \
     patch('adminapi.views_ai._call_llm', side_effect=mock_call_llm_capture):

    call_count[0] = 0
    captured_config.clear()
    content, err = AIServiceBase.call_llm_with_fallback(
        [{'role': 'user', 'content': 'test'}],
        model_tier='complex',
        func_name='exam_analyze',
    )

    test('非 legacy 模型 maxTokens > tier 最小值 → 保持不变',
         captured_config.get('maxTokens') == 8000,
         f'maxTokens sent to LLM={captured_config.get("maxTokens")}')

# 2.3 Legacy model → tier config fully overrides (existing behavior)
mock_legacy = {
    'model': 'old-model',
    'source': 'legacy',
    'apiUrl': 'https://api.example.com/v1/chat/completions',
    'apiKey': 'test-key',
    'maxTokens': 1000,
    'temperature': 0.3,
}

with patch('adminapi.views_ai._get_ai_config', return_value=({'enabled': True, 'feature_config': {}}, MagicMock())), \
     patch('adminapi.ai_models.get_active_model', return_value=mock_legacy), \
     patch('adminapi.ai_models.resolve_model', return_value=(mock_legacy, None)), \
     patch('adminapi.ai_models.build_call_config', return_value=({
         'apiUrl': 'https://api.example.com/v1/chat/completions',
         'apiKey': 'test-key',
         'model': 'old-model',
         'temperature': 0.3,
         'maxTokens': 1000,
     }, None)), \
     patch('adminapi.views_ai._call_llm', side_effect=mock_call_llm_capture):

    call_count[0] = 0
    captured_config.clear()
    content, err = AIServiceBase.call_llm_with_fallback(
        [{'role': 'user', 'content': 'test'}],
        model_tier='complex',
        func_name='exam_analyze',
    )

    test('legacy 模型 → tier maxTokens 完全覆盖',
         captured_config.get('maxTokens') == 4000,
         f'maxTokens sent to LLM={captured_config.get("maxTokens")}')
    test('legacy 模型 → tier model 完全覆盖',
         captured_config.get('model') == 'gpt-4o',
         f'model sent to LLM={captured_config.get("model")}')


# ===========================================================================
# 3. Full resolution chain — real DB data simulation
# ===========================================================================
print('\n--- 3. 完整解析链验证 ---')

# Simulate the actual database state:
# - ai_models: glm5.2 with maxTokens=2000, isDefault=True
# - ai_config: feature_config = {} (empty)
# - settings: AI_FEATURE_CONFIG_DEFAULTS[exam_analyze] = {max_tokens: 4000}

mock_ai_config_real = {
    'enabled': True,
    'apiUrl': 'https://api.openai.com/v1/chat/completions',
    'apiKey': '',  # Empty in legacy config
    'model': 'gpt-4o-mini',
    'feature_config': {},  # Empty in DB
}

mock_model_real = {
    'name': 'CMCC-glm5.2',
    'model': 'glm5.2',
    'apiUrl': 'https://api.example.com/v1',
    'apiKey': 'sk-FAKE-TEST-KEY-XXXX',
    'maxTokens': 2000,
    'temperature': 0.7,
    'enabled': True,
    'isDefault': True,
    'source': 'global-default',
}

with patch('adminapi.views_ai._get_ai_config', return_value=(mock_ai_config_real, MagicMock())), \
     patch('adminapi.ai_models.get_active_model', return_value=mock_model_real), \
     patch('adminapi.ai_models.resolve_model', return_value=(mock_model_real, None)), \
     patch('adminapi.views_ai._call_llm', side_effect=mock_call_llm_capture):

    call_count[0] = 0
    captured_config.clear()
    content, err = AIServiceBase.call_llm_with_fallback(
        [{'role': 'user', 'content': 'analyze this exam'}],
        model_tier='complex',
        func_name='exam_analyze',
    )

    test('真实场景 → 使用 ai_models 的 apiUrl（非 legacy config）',
         'ynai.cloudhubportal.com' in (captured_config.get('apiUrl') or ''),
         f'apiUrl={captured_config.get("apiUrl","")[:50]}')
    test('真实场景 → 使用 ai_models 的 apiKey（非 legacy config）',
         'sk-dMJjug9' in (captured_config.get('apiKey') or ''),
         f'apiKey={(captured_config.get("apiKey") or "")[:10]}...')
    test('真实场景 → 使用 ai_models 的 model（glm5.2）',
         captured_config.get('model') == 'glm5.2',
         f'model={captured_config.get("model")}')
    test('真实场景 → maxTokens >= 4000（tier floor 生效）',
         captured_config.get('maxTokens', 0) >= 4000,
         f'maxTokens={captured_config.get("maxTokens")}')
    test('真实场景 → LLM 调用成功', content == 'success' and err is None,
         f'content={repr(content)}, err={repr(err)}')


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
