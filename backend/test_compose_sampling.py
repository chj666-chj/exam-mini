"""Test: Stratified random sampling for AI compose.

Tests the new _stratified_sample and _sample_by_difficulty methods
to verify they correctly reduce candidate pool while maintaining
coverage of required question types and difficulty distributions.
"""
import os
import sys
import random
import django
from collections import Counter

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.conf import settings
from adminapi.ai_services import ExamCompositionService

results = []

def test(name, passed, detail=''):
    results.append((name, passed, detail))
    tag = 'PASS' if passed else 'FAIL'
    print(f'  [{tag}] {name}' + (f' -- {detail}' if detail else ''))


print('=' * 70)
print('Test: Stratified Random Sampling for AI Compose')
print('=' * 70)

# ---- Helper: generate a mock candidate pool ----
def make_pool(qtype_counts, difficulty_dist='balanced'):
    """Generate a mock candidate pool.

    Args:
        qtype_counts: dict {qtype: count} e.g. {'single': 200, 'judge': 100}
        difficulty_dist: 'balanced' (equal easy/medium/hard) or dict
    """
    pool = []
    idx = 0
    for qt, count in qtype_counts.items():
        for i in range(count):
            if difficulty_dist == 'balanced':
                diffs = ['easy', 'medium', 'hard']
                diff = diffs[i % 3]
            elif isinstance(difficulty_dist, dict):
                diffs = []
                for d, pct in difficulty_dist.items():
                    diffs.extend([d] * pct)
                diff = diffs[i % len(diffs)] if diffs else 'medium'
            else:
                diff = 'medium'

            pool.append({
                'id': f'{qt}_{idx}',
                'qtype': qt,
                'difficulty': diff,
                'knowledge_summary': f'知识点{idx % 10}',
                'knowledge_tags': [f'kp{idx % 5}'],
                'score': 5,
            })
            idx += 1
    return pool


# ---- 1. Basic stratified sampling ----
print('\n--- 1. Basic stratified sampling by qtype ---')
random.seed(42)
pool = make_pool({'single': 200, 'multiple': 100, 'judge': 50, 'fill': 30, 'qa': 20})
config = {
    'qtype_dist': {'single': 10, 'multiple': 5, 'judge': 5},  # only need 3 types
    'difficulty_dist': {'easy': 30, 'medium': 50, 'hard': 20},
    'count': 20,
    'knowledge_points': [],
}
sampled = ExamCompositionService._stratified_sample(pool, config)

test('Sampled is smaller than pool', len(sampled) < len(pool),
     f'{len(pool)} → {len(sampled)}')
test('Only needed qtypes in sample',
     all(c['qtype'] in ('single', 'multiple', 'judge') or not c['qtype'] for c in sampled),
     f'qtypes: {set(c["qtype"] for c in sampled)}')

# Check each qtype has enough candidates
qt_counts = Counter(c['qtype'] for c in sampled if c['qtype'])
test('Single has >= 10 candidates', qt_counts.get('single', 0) >= 10,
     f'single: {qt_counts.get("single", 0)}')
test('Multiple has >= 5 candidates', qt_counts.get('multiple', 0) >= 5,
     f'multiple: {qt_counts.get("multiple", 0)}')
test('Judge has >= 5 candidates', qt_counts.get('judge', 0) >= 5,
     f'judge: {qt_counts.get("judge", 0)}')


# ---- 2. Sampling ratio works correctly ----
print('\n--- 2. Sampling ratio (5x needed count) ---')
random.seed(42)
pool2 = make_pool({'single': 500, 'judge': 500})
config2 = {
    'qtype_dist': {'single': 10, 'judge': 10},
    'difficulty_dist': {},
    'count': 20,
    'knowledge_points': [],
}
sampled2 = ExamCompositionService._stratified_sample(pool2, config2, sample_ratio=5)
qt_counts2 = Counter(c['qtype'] for c in sampled2 if c['qtype'])
# 10 * 5 = 50 per qtype, but capped at max_per_qtype=60
test('Single sampled ~50 (10 × 5)', qt_counts2.get('single', 0) == 50,
     f'single: {qt_counts2.get("single", 0)}')
test('Judge sampled ~50 (10 × 5)', qt_counts2.get('judge', 0) == 50,
     f'judge: {qt_counts2.get("judge", 0)}')


# ---- 3. Max per qtype cap ----
print('\n--- 3. Max per qtype cap (60) ---')
random.seed(42)
pool3 = make_pool({'single': 500})
config3 = {
    'qtype_dist': {'single': 50},  # 50 * 5 = 250, should be capped at 60
    'difficulty_dist': {},
    'count': 50,
    'knowledge_points': [],
}
sampled3 = ExamCompositionService._stratified_sample(pool3, config3)
qt_counts3 = Counter(c['qtype'] for c in sampled3 if c['qtype'])
test('Capped at max_per_qtype=60', qt_counts3.get('single', 0) <= 60,
     f'single: {qt_counts3.get("single", 0)}')


# ---- 4. Min per qtype floor ----
print('\n--- 4. Min per qtype floor (10) ---')
random.seed(42)
pool4 = make_pool({'single': 100})
config4 = {
    'qtype_dist': {'single': 1},  # 1 * 5 = 5, should be floored at 10
    'difficulty_dist': {},
    'count': 1,
    'knowledge_points': [],
}
sampled4 = ExamCompositionService._stratified_sample(pool4, config4)
qt_counts4 = Counter(c['qtype'] for c in sampled4 if c['qtype'])
test('Floored at min_per_qtype=10', qt_counts4.get('single', 0) >= 10,
     f'single: {qt_counts4.get("single", 0)}')


# ---- 5. Difficulty distribution in sample ----
print('\n--- 5. Difficulty distribution proportional ---')
random.seed(42)
# Pool with balanced difficulties
pool5 = make_pool({'single': 300}, difficulty_dist='balanced')
config5 = {
    'qtype_dist': {'single': 10},
    'difficulty_dist': {'easy': 30, 'medium': 50, 'hard': 20},  # 30/50/20
    'count': 10,
    'knowledge_points': [],
}
sampled5 = ExamCompositionService._stratified_sample(pool5, config5)
diff_counts = Counter(c['difficulty'] for c in sampled5)
total_sampled = len(sampled5)
if total_sampled > 0:
    easy_pct = diff_counts.get('easy', 0) / total_sampled * 100
    medium_pct = diff_counts.get('medium', 0) / total_sampled * 100
    hard_pct = diff_counts.get('hard', 0) / total_sampled * 100
    test('Easy ~30%', 15 <= easy_pct <= 45,
         f'easy: {easy_pct:.0f}%')
    test('Medium ~50%', 35 <= medium_pct <= 65,
         f'medium: {medium_pct:.0f}%')
    test('Hard ~20%', 5 <= hard_pct <= 35,
         f'hard: {hard_pct:.0f}%')


# ---- 6. Knowledge point priority ----
print('\n--- 6. Knowledge point priority sampling ---')
random.seed(42)
# Pool where only some questions have matching knowledge points
pool6 = []
for i in range(100):
    pool6.append({
        'id': f'single_{i}',
        'qtype': 'single',
        'difficulty': 'medium',
        'knowledge_summary': f'kp{i % 5}',
        'knowledge_tags': [f'kp{i % 5}'],  # kp0-kp4
        'score': 5,
    })
config6 = {
    'qtype_dist': {'single': 10},
    'difficulty_dist': {},
    'count': 10,
    'knowledge_points': ['kp0', 'kp1'],  # only want kp0 and kp1
}
sampled6 = ExamCompositionService._stratified_sample(pool6, config6)
# All sampled should have kp0 or kp1 (or at least majority)
matched = sum(1 for c in sampled6 if any(kp in c['knowledge_tags'] for kp in ['kp0', 'kp1']))
test('Knowledge point matched questions prioritized',
     matched >= len(sampled6) * 0.7,  # at least 70% should match
     f'{matched}/{len(sampled6)} matched kp0/kp1')


# ---- 7. Randomness: different runs produce different samples ----
print('\n--- 7. Randomness: different runs → different samples ---')
pool7 = make_pool({'single': 300})
config7 = {
    'qtype_dist': {'single': 10},
    'difficulty_dist': {},
    'count': 10,
    'knowledge_points': [],
}
random.seed(1)
sample_a = ExamCompositionService._stratified_sample(pool7, config7)
random.seed(2)
sample_b = ExamCompositionService._stratified_sample(pool7, config7)
ids_a = set(c['id'] for c in sample_a)
ids_b = set(c['id'] for c in sample_b)
test('Different seeds produce different samples', ids_a != ids_b,
     f'overlap: {len(ids_a & ids_b)} / {len(ids_a)}')


# ---- 8. Insufficient candidates (pool smaller than sample target) ----
print('\n--- 8. Insufficient candidates in pool ---')
random.seed(42)
pool8 = make_pool({'single': 5})  # only 5 available, but need 10
config8 = {
    'qtype_dist': {'single': 10},
    'difficulty_dist': {},
    'count': 10,
    'knowledge_points': [],
}
sampled8 = ExamCompositionService._stratified_sample(pool8, config8)
test('Takes all available when pool < target', len(sampled8) == 5,
     f'sampled {len(sampled8)} from pool of 5')


# ---- 9. Empty pool ----
print('\n--- 9. Empty candidate pool ---')
config9 = {
    'qtype_dist': {'single': 10},
    'difficulty_dist': {},
    'count': 10,
    'knowledge_points': [],
}
sampled9 = ExamCompositionService._stratified_sample([], config9)
test('Empty pool returns empty list', len(sampled9) == 0)


# ---- 10. No qtype_dist specified (fallback to random) ----
print('\n--- 10. No qtype_dist (fallback sampling) ---')
random.seed(42)
pool10 = make_pool({'single': 100, 'judge': 100, 'fill': 100})
config10 = {
    'qtype_dist': {},  # no qtype specified
    'difficulty_dist': {},
    'count': 20,
    'knowledge_points': [],
}
sampled10 = ExamCompositionService._stratified_sample(pool10, config10)
test('No qtype_dist returns non-empty sample', len(sampled10) > 0,
     f'sampled {len(sampled10)}')
test('No qtype_dist includes multiple qtypes',
     len(set(c['qtype'] for c in sampled10)) > 1,
     f'qtypes: {set(c["qtype"] for c in sampled10)}')


# ---- 11. _sample_by_difficulty with uneven distribution ----
print('\n--- 11. _sample_by_difficulty proportional allocation ---')
random.seed(42)
group = []
for i in range(90):
    group.append({
        'id': f'q_{i}',
        'qtype': 'single',
        'difficulty': ['easy', 'medium', 'hard'][i % 3],  # 30 each
        'score': 5,
    })
# Request 30 samples with 20/60/20 difficulty split
result = ExamCompositionService._sample_by_difficulty(
    group, {'easy': 20, 'medium': 60, 'hard': 20}, 30)
diff_result = Counter(c['difficulty'] for c in result)
test('Difficulty sample count = 30', len(result) == 30,
     f'got {len(result)}')
test('Easy ~6 (20% of 30)', diff_result.get('easy', 0) == 6,
     f'easy: {diff_result.get("easy", 0)}')
test('Medium ~18 (60% of 30)', diff_result.get('medium', 0) == 18,
     f'medium: {diff_result.get("medium", 0)}')
test('Hard ~6 (20% of 30)', diff_result.get('hard', 0) == 6,
     f'hard: {diff_result.get("hard", 0)}')


# ---- 12. _sample_by_difficulty with missing difficulty in pool ----
print('\n--- 12. Difficulty sampling: pool missing some difficulties ---')
random.seed(42)
group2 = []
for i in range(60):
    group2.append({
        'id': f'q_{i}',
        'qtype': 'single',
        'difficulty': 'medium',  # all medium, no easy/hard
        'score': 5,
    })
# Request 30 samples with 30/50/20 but only medium available
result2 = ExamCompositionService._sample_by_difficulty(
    group2, {'easy': 30, 'medium': 50, 'hard': 20}, 30)
test('Fills from available when some difficulties missing',
     len(result2) == 30,
     f'got {len(result2)} (all from medium pool)')
test('All sampled are medium', all(c['difficulty'] == 'medium' for c in result2))


# ---- 13. Settings exist ----
print('\n--- 13. Configuration settings ---')
test('AI_COMPOSE_SAMPLE_RATIO = 5',
     getattr(settings, 'AI_COMPOSE_SAMPLE_RATIO', None) == 5,
     f'got {getattr(settings, "AI_COMPOSE_SAMPLE_RATIO", "NOT SET")}')
test('AI_COMPOSE_SAMPLE_MAX_PER_QTYPE = 60',
     getattr(settings, 'AI_COMPOSE_SAMPLE_MAX_PER_QTYPE', None) == 60,
     f'got {getattr(settings, "AI_COMPOSE_SAMPLE_MAX_PER_QTYPE", "NOT SET")}')
test('AI_COMPOSE_SAMPLE_MIN_PER_QTYPE = 10',
     getattr(settings, 'AI_COMPOSE_SAMPLE_MIN_PER_QTYPE', None) == 10,
     f'got {getattr(settings, "AI_COMPOSE_SAMPLE_MIN_PER_QTYPE", "NOT SET")}')


# ---- 14. Payload reduction estimate ----
print('\n--- 14. Payload size reduction estimate ---')
# Before: 500 questions all sent to LLM
# After: stratified sample ~50-60 per qtype
random.seed(42)
pool14 = make_pool({'single': 200, 'multiple': 100, 'judge': 50, 'fill': 30, 'qa': 20})
config14 = {
    'qtype_dist': {'single': 10, 'multiple': 5, 'judge': 5},
    'difficulty_dist': {'easy': 30, 'medium': 50, 'hard': 20},
    'count': 20,
    'knowledge_points': [],
}
sampled14 = ExamCompositionService._stratified_sample(pool14, config14)
before_lines = len(pool14)
after_lines = len(sampled14)
reduction_pct = (1 - after_lines / before_lines) * 100
print(f'  Pool: {before_lines} questions')
print(f'  Sampled: {after_lines} questions')
print(f'  Reduction: {reduction_pct:.0f}%')
test('Payload reduced by > 50%', reduction_pct > 50,
     f'{before_lines} → {after_lines} ({reduction_pct:.0f}% reduction)')


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
