"""Test: AI compose endpoint field-name compatibility fix.

Unit-tests the parameter validation logic of exam_compose() in isolation,
bypassing auth decorators and mocking AIJobManager to avoid DB operations.
"""
import json
import os
import sys
import django
from unittest.mock import MagicMock, patch

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.test import RequestFactory
from adminapi.views_ai import exam_compose

# ---- helpers ----

# Bypass @require_perms by calling the unwrapped inner function
_raw_compose = exam_compose.__wrapped__


def make_request(body_dict):
    """Build a POST request with JSON body."""
    rf = RequestFactory()
    return rf.post('/api/admin/ai/compose/',
                   data=json.dumps(body_dict),
                   content_type='application/json')


def call_view(body_dict):
    """Call the raw view logic, bypassing auth, mocking AIJobManager."""
    request = make_request(body_dict)
    request.admin_user = MagicMock(is_superuser=True)

    with patch('adminapi.views_ai.AIJobManager') as mock_mgr:
        mock_mgr.create.return_value = 'mock-job-001'
        resp = _raw_compose(request)
    return resp


def get_json(resp):
    return json.loads(resp.content.decode('utf-8'))


# ---- tests ----

results = []

def test(name, passed, detail=''):
    results.append((name, passed, detail))
    tag = 'PASS' if passed else 'FAIL'
    print(f'  [{tag}] {name}' + (f' -- {detail}' if detail else ''))


print('=' * 70)
print('Test: AI Compose Endpoint Field-Name Compatibility Fix')
print('=' * 70)

# 1. Frontend naming (the original bug scenario)
print('\n--- 1. Frontend field names (subject_id, type_dist, difficulty, ...) ---')
body_fe = {
    'subject_id': 'subj_001',
    'type_dist': {'single': 10, 'multiple': 5, 'judge': 5, 'fill': 5, 'qa': 0},
    'difficulty': {'easy': 30, 'medium': 50, 'hard': 20},
    'question_count': 25,
    'total_score': 100,
    'knowledge_tags': [],
}
r = call_view(body_fe)
d = get_json(r)
test('Frontend naming -> 200', r.status_code == 200,
     f'status={r.status_code}, code={d.get("code")}, msg={d.get("message")}')
test('Frontend naming -> job_id returned', bool(d.get('data', {}).get('job_id')),
     f'job_id={d.get("data", {}).get("job_id", "N/A")}')

# 2. Original naming (backward compat)
print('\n--- 2. Original field names (examid, qtype_dist, difficulty_dist, ...) ---')
body_orig = {
    'examid': 'exam_001',
    'qtype_dist': {'single': 8, 'judge': 7},
    'difficulty_dist': {'easy': 40, 'medium': 40, 'hard': 20},
    'count': 15,
    'total_score': 100,
    'knowledge_points': ['kp1', 'kp2'],
    'locked_questions': [],
}
r2 = call_view(body_orig)
d2 = get_json(r2)
test('Original naming -> 200', r2.status_code == 200,
     f'status={r2.status_code}, msg={d2.get("message")}')
test('Original naming -> job_id returned', bool(d2.get('data', {}).get('job_id')))

# 3. Auto-infer count from qtype_dist when not provided
print('\n--- 3. Auto-infer count from type_dist (no count/question_count) ---')
body_nc = {
    'subject_id': 'subj_002',
    'type_dist': {'single': 10, 'multiple': 5, 'judge': 5},  # sum=20
    'difficulty': {'easy': 30, 'medium': 50, 'hard': 20},
    'total_score': 100,
}
r3 = call_view(body_nc)
d3 = get_json(r3)
test('Auto-infer count -> 200', r3.status_code == 200,
     f'status={r3.status_code}, msg={d3.get("message")}')

# 4. Missing examid AND subject_id -> 400
print('\n--- 4. Missing both examid and subject_id ---')
r4 = call_view({
    'type_dist': {'single': 10},
    'difficulty': {'easy': 100},
    'total_score': 100,
})
d4 = get_json(r4)
test('Missing ID -> 400', r4.status_code == 400,
     f'status={r4.status_code}, msg={d4.get("message")}')
test('Error mentions both field names',
     'examid' in d4.get('message', '') and 'subject_id' in d4.get('message', ''),
     f'msg={d4.get("message")}')

# 5. total_score = 0 -> 400
print('\n--- 5. total_score = 0 ---')
r5 = call_view({
    'subject_id': 'subj_003',
    'type_dist': {'single': 10},
    'difficulty': {'easy': 100},
    'total_score': 0,
})
d5 = get_json(r5)
test('total_score=0 -> 400', r5.status_code == 400,
     f'status={r5.status_code}, msg={d5.get("message")}')

# 6. count=0 and empty type_dist -> 400
print('\n--- 6. count=0, empty type_dist ---')
r6 = call_view({
    'subject_id': 'subj_004',
    'type_dist': {},
    'difficulty': {'easy': 100},
    'total_score': 100,
})
d6 = get_json(r6)
test('Zero count + empty dist -> 400', r6.status_code == 400,
     f'status={r6.status_code}, msg={d6.get("message")}')

# 7. difficulty sum != 100 -> 400
print('\n--- 7. difficulty sum != 100 ---')
r7 = call_view({
    'subject_id': 'subj_005',
    'type_dist': {'single': 10},
    'difficulty': {'easy': 50, 'medium': 30, 'hard': 10},  # sum=90
    'total_score': 100,
})
d7 = get_json(r7)
test('Difficulty sum=90 -> 400', r7.status_code == 400,
     f'status={r7.status_code}, msg={d7.get("message")}')

# 8. difficulty sum = 100 (valid)
print('\n--- 8. Valid difficulty sum=100 ---')
r8 = call_view({
    'subject_id': 'subj_006',
    'type_dist': {'single': 10, 'judge': 10},
    'difficulty': {'easy': 30, 'medium': 50, 'hard': 20},
    'total_score': 100,
})
d8 = get_json(r8)
test('Valid difficulty -> 200', r8.status_code == 200,
     f'status={r8.status_code}, msg={d8.get("message")}')

# 9. No difficulty provided (optional)
print('\n--- 9. No difficulty field (optional) ---')
r9 = call_view({
    'subject_id': 'subj_007',
    'type_dist': {'single': 10},
    'total_score': 100,
})
d9 = get_json(r9)
test('No difficulty -> 200', r9.status_code == 200,
     f'status={r9.status_code}, msg={d9.get("message")}')

# 10. total_score as string "150" (type coercion)
print('\n--- 10. total_score as string "150" ---')
r10 = call_view({
    'subject_id': 'subj_008',
    'type_dist': {'single': 10},
    'difficulty': {'easy': 100},
    'total_score': '150',
})
d10 = get_json(r10)
test('total_score="150" coerced -> 200', r10.status_code == 200,
     f'status={r10.status_code}, msg={d10.get("message")}')

# 11. Mix: examid + type_dist (cross naming)
print('\n--- 11. Mixed naming: examid + type_dist + difficulty ---')
r11 = call_view({
    'examid': 'exam_mix',
    'type_dist': {'single': 10},
    'difficulty': {'easy': 100},
    'total_score': 100,
})
d11 = get_json(r11)
test('Mixed naming -> 200', r11.status_code == 200,
     f'status={r11.status_code}, msg={d11.get("message")}')

# 12. Empty body -> should still return 400 (examid missing)
print('\n--- 12. Empty body {} ---')
r12 = call_view({})
d12 = get_json(r12)
test('Empty body -> 400', r12.status_code == 400,
     f'status={r12.status_code}, msg={d12.get("message")}')

# 13. knowledge_tags with values
print('\n--- 13. knowledge_tags with values ---')
r13 = call_view({
    'subject_id': 'subj_009',
    'type_dist': {'single': 10},
    'difficulty': {'easy': 100},
    'total_score': 100,
    'knowledge_tags': ['tag_a', 'tag_b'],
})
d13 = get_json(r13)
test('knowledge_tags -> 200', r13.status_code == 200,
     f'status={r13.status_code}, msg={d13.get("message")}')

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
