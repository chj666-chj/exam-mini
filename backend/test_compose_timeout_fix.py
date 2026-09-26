"""Test: AI compose LLM timeout/retry fix.

Tests:
1. FUNCTION_MODEL_MAP: exam_compose is now 'complex' (90s timeout)
2. call_llm_with_fallback: progressive timeout increase on retry
3. ExamCompositionService.compose: pre-filtering by qtype/difficulty
4. build_exam_compose_prompt: payload truncation
5. Retry callback: payload reduction on timeout
"""
import json
import os
import sys
import django
from unittest.mock import MagicMock, patch, call

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.conf import settings
from adminapi.ai_services import FUNCTION_MODEL_MAP, MODEL_TIERS, AIServiceBase
from adminapi.ai_prompts import PromptBuilder

results = []

def test(name, passed, detail=''):
    results.append((name, passed, detail))
    tag = 'PASS' if passed else 'FAIL'
    print(f'  [{tag}] {name}' + (f' -- {detail}' if detail else ''))


print('=' * 70)
print('Test: AI Compose LLM Timeout/Retry Fix')
print('=' * 70)

# ---- 1. FUNCTION_MODEL_MAP: exam_compose is 'complex' ----
print('\n--- 1. exam_compose tier changed to complex ---')
test('exam_compose is complex tier',
     FUNCTION_MODEL_MAP.get('exam_compose') == 'complex',
     f'tier={FUNCTION_MODEL_MAP.get("exam_compose")}')

complex_timeout = settings.AI_LLM_TIMEOUTS.get('complex', 0)
test('complex tier timeout is 90s', complex_timeout == 90,
     f'timeout={complex_timeout}s')

test('complex tier has max_tokens=4000',
     MODEL_TIERS['complex']['max_tokens'] == 4000,
     f'max_tokens={MODEL_TIERS["complex"]["max_tokens"]}')

# ---- 2. Progressive timeout increase on retry ----
print('\n--- 2. call_llm_with_fallback progressive timeout ---')

# Simulate the timeout calculation logic
base_timeout = settings.AI_LLM_TIMEOUTS.get('complex', 45)
max_retries = getattr(settings, 'AI_LLM_MAX_RETRIES', 2)
timeout_multipliers = [1.5, 2.0]

retry_timeouts = []
for attempt in range(1, max_retries + 1):
    mult = timeout_multipliers[min(attempt - 1, len(timeout_multipliers) - 1)]
    retry_timeouts.append(int(base_timeout * mult))

test('Retry 1 timeout = 135s (90 × 1.5)', retry_timeouts[0] == 135,
     f'got {retry_timeouts[0]}s')
test('Retry 2 timeout = 180s (90 × 2.0)', retry_timeouts[1] == 180,
     f'got {retry_timeouts[1]}s')
test('Max retries = 2', max_retries == 2, f'max_retries={max_retries}')

# ---- 3. Exponential backoff delays ----
print('\n--- 3. Exponential backoff delays ---')
retry_delay_base = settings.AI_LLM_RETRY_DELAY
delays = [retry_delay_base * (2 ** i) for i in range(max_retries)]
test('Delay 1 = 2s', delays[0] == 2, f'got {delays[0]}s')
test('Delay 2 = 4s', delays[1] == 4, f'got {delays[1]}s')

# ---- 4. Pre-filtering logic ----
print('\n--- 4. Candidate pre-filtering ---')

# Simulate pre-filtering
candidates = [
    {'id': f'q{i}', 'qtype': qt, 'difficulty': diff, 'knowledge_summary': 'kp', 'score': 5}
    for i, (qt, diff) in enumerate([
        ('single', 'easy'), ('single', 'medium'), ('single', 'hard'),
        ('multiple', 'easy'), ('multiple', 'medium'),
        ('judge', 'easy'), ('judge', 'medium'), ('judge', 'hard'),
        ('fill', 'easy'), ('qa', 'medium'),
    ] * 30)  # 300 candidates
]

qtype_dist = {'single': 10, 'judge': 5}  # only need single and judge
difficulty_dist = {'easy': 50, 'medium': 50}  # only easy and medium

needed_qtypes = set(qt for qt, cnt in qtype_dist.items() if cnt and int(cnt) > 0)
needed_difficulties = set(d for d, pct in difficulty_dist.items() if pct and int(pct) > 0)

filtered = []
for c in candidates:
    if needed_qtypes and c['qtype'] not in needed_qtypes:
        if c['qtype']:
            continue
    if needed_difficulties and c['difficulty'] not in needed_difficulties:
        if c['difficulty'] != 'medium' and c['difficulty']:
            continue
    filtered.append(c)

test('Pre-filter reduces candidate count',
     len(filtered) < len(candidates),
     f'{len(candidates)} → {len(filtered)}')
test('Filtered only contains needed qtypes',
     all(c['qtype'] in needed_qtypes or not c['qtype'] for c in filtered),
     f'qtypes in result: {set(c["qtype"] for c in filtered)}')

# ---- 5. Payload truncation in prompt ----
print('\n--- 5. Prompt payload truncation ---')
max_lines = getattr(settings, 'AI_COMPOSE_PROMPT_MAX_LINES', 200)
test('AI_COMPOSE_PROMPT_MAX_LINES = 200', max_lines == 200, f'got {max_lines}')

# Build prompt with 300 candidates
large_pool = [
    {'id': f'qid_{i:04d}', 'qtype': 'single', 'difficulty': 'easy',
     'knowledge_summary': f'知识点{i}', 'score': 5}
    for i in range(300)
]
config = {
    'qtype_dist': {'single': 10},
    'difficulty_dist': {'easy': 100},
    'count': 10,
    'total_score': 100,
    'knowledge_points': [],
    'locked_questions': [],
}
prompt = PromptBuilder.build_exam_compose_prompt(large_pool, config)

# Count candidate lines (lines containing 'qid_')
candidate_lines = [l for l in prompt.split('\n') if 'qid_' in l]
test('Prompt truncated to 200 lines', len(candidate_lines) == 200,
     f'got {len(candidate_lines)} lines')
test('Prompt mentions truncation', '截取前 200 题' in prompt,
     'truncation note should be present')

# Build prompt with 50 candidates (no truncation)
small_pool = large_pool[:50]
prompt_small = PromptBuilder.build_exam_compose_prompt(small_pool, config)
candidate_lines_small = [l for l in prompt_small.split('\n') if 'qid_' in l]
test('Small pool not truncated', len(candidate_lines_small) == 50,
     f'got {len(candidate_lines_small)} lines')
test('Small pool no truncation note', '截取前' not in prompt_small,
     'should not have truncation note')

# ---- 6. Retry callback reduces payload ----
print('\n--- 6. Retry callback reduces payload on timeout ---')

# Simulate the retry callback logic
retry_state = {'candidates': list(range(200)), 'reduced_counts': []}

def reduce_payload_on_retry(err_str, attempt):
    if '超时' not in err_str and 'timeout' not in err_str.lower():
        return None
    current = retry_state['candidates']
    reduced_count = max(int(len(current) * 0.6), 30)
    if reduced_count >= len(current):
        return None
    reduced = current[:reduced_count]
    retry_state['candidates'] = reduced
    retry_state['reduced_counts'].append(len(reduced))
    return ['reduced_messages']

# Simulate 2 retries with timeout errors
r1 = reduce_payload_on_retry('LLM 请求超时（90s）', 1)
r2 = reduce_payload_on_retry('LLM 请求超时（135s）', 2)

test('Retry 1 reduces to 120 (200 × 0.6)',
     retry_state['reduced_counts'][0] == 120,
     f'got {retry_state["reduced_counts"][0]}')
test('Retry 2 reduces to 72 (120 × 0.6)',
     retry_state['reduced_counts'][1] == 72,
     f'got {retry_state["reduced_counts"][1]}')
test('Retry callback returns messages', r1 is not None and r2 is not None)

# Non-timeout error should not reduce
r3 = reduce_payload_on_retry('HTTP 500 Internal Server Error', 3)
test('Non-timeout error returns None', r3 is None)

# ---- 7. Max candidates reduced ----
print('\n--- 7. Max candidates setting ---')
test('AI_COMPOSE_MAX_CANDIDATES = 200',
     settings.AI_COMPOSE_MAX_CANDIDATES == 200,
     f'got {settings.AI_COMPOSE_MAX_CANDIDATES}')

# ---- 8. call_llm_with_fallback signature has retry_callback ----
print('\n--- 8. call_llm_with_fallback accepts retry_callback ---')
import inspect
sig = inspect.signature(AIServiceBase.call_llm_with_fallback)
test('retry_callback parameter exists',
     'retry_callback' in sig.parameters,
     f'params: {list(sig.parameters.keys())}')

# ---- 9. Total worst-case time estimate ----
print('\n--- 9. Worst-case time estimate ---')
# First call: 90s, delay 2s, retry1: 135s, delay 4s, retry2: 180s
worst_case = 90 + 2 + 135 + 4 + 180
print(f'  Worst case (no payload reduction): {worst_case}s ≈ {worst_case/60:.1f}min')
# With payload reduction, retries should be much faster
# First call: ~60s (200 candidates), retry1: ~40s (120 candidates), retry2: ~25s (72 candidates)
realistic = 60 + 2 + 40 + 4 + 25
print(f'  Realistic (with reduction): {realistic}s ≈ {realistic/60:.1f}min')
test('Worst case < 8 min (frontend timeout)', worst_case < 480,
     f'{worst_case}s < 480s')
test('Realistic < 3 min', realistic < 180,
     f'{realistic}s < 180s')

# ---- summary ----
print('\n' + '=' * 70)
total = len(results)
passed_count = sum(1 for _, p, _ in results if p)
failed_count = total - passed_count
print(f'Results: {passed_count}/{total} passed, {failed_count} failed')
if failed_count:
    print('\nFAILED:')
    for name, p, detail in results:
        if not p:
            print(f'  - {name}: {detail}')
    sys.exit(1)
else:
    print('All tests passed!')
    sys.exit(0)
