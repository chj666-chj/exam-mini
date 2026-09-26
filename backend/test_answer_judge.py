#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""答案判定逻辑 + 全站题目统计接口 回归测试。

背景（本次修复的 Bug）：
  小程序答题页「我的答案 B / 正确答案 B / 判定 错误」——用户答对却被判错。
  根因：exam.js 的 selectOption 在 setData 之前调用 checkAnswer，
       而 checkAnswer 读取 this.data.userAnswers（尚未写入新值），
       导致首答必判错、改答后结果滞后一轮。
  修复：抽出 utils/judge.js 纯函数，交互链路传入「新算出的作答」，
       并补齐后端 /api/question-stats/ 接口（全站统计原先走私有集合，恒为 0）。

测试范围：
  1. 标准答案解析 _correct_codes_of（value 类型兼容 / answer 字段回退）
  2. 作答归一化 _normalize_codes（去空、去重、排序、大小写）
  3. 集合比对规则（与 JS 端 judge.js 语义对齐）
  4. 全库题目数据完整性（不得存在「无正确项」的脏数据）
  5. /api/question-stats/ 路由注册与可达性
  6. 接口参数校验 / 方法校验
  7. 接口统计结果与独立实现交叉核对
  8. 架构回归：私有集合接口无法替代全站统计

运行方式：
  cd backend
  python test_answer_judge.py
"""
import os
import sys
import traceback
from collections import Counter

# ---- Django 初始化 ----
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django  # noqa: E402
django.setup()

from django.test import Client  # noqa: E402
from django.urls import reverse  # noqa: E402

from core.models import Document  # noqa: E402
from core.views import _correct_codes_of, _is_correct_value, _normalize_codes  # noqa: E402

# ---- 测试框架 ----
_results = []


def assert_true(name, condition, detail=''):
    passed = bool(condition)
    _results.append((name, passed, detail if not passed else ''))
    print('  [%s] %s%s' % ('PASS' if passed else 'FAIL', name, '' if passed else (' -- ' + str(detail))))
    return passed


def assert_equal(name, actual, expected, detail=''):
    passed = actual == expected
    msg = '' if passed else (detail or ('expected %r, got %r' % (expected, actual)))
    _results.append((name, passed, msg))
    print('  [%s] %s%s' % ('PASS' if passed else 'FAIL', name, '' if passed else (' -- ' + str(msg))))
    return passed


# ---- 与小程序端 judge.js 语义对齐的集合比对 ----
def compare_option_answer(correct_codes, user_codes):
    """对齐 judge.judgeAnswer 的选项题分支：集合相等（顺序无关、去重）。"""
    c = sorted(set(correct_codes))
    u = sorted(set(user_codes))
    if not c:
        return True          # 无标准答案 -> 不武断判错
    if len(c) != len(u):
        return False
    return all(x in u for x in c)


# ==================== 1. 标准答案解析 ====================
def test_correct_codes_of():
    print('\n--- 1. 标准答案解析 _correct_codes_of ---')
    q = {
        'options': [
            {'code': 'A', 'value': 0},
            {'code': 'B', 'value': 1},
            {'code': 'C', 'value': 0},
            {'code': 'D', 'value': 0},
        ]
    }
    assert_equal('value=1(int) 正确项', _correct_codes_of(q), ['B'])

    q_str = {'options': [{'code': 'A', 'value': '0'}, {'code': 'B', 'value': '1'}]}
    assert_equal("value='1'(str) 正确项", _correct_codes_of(q_str), ['B'])

    q_bool = {'options': [{'code': 'A', 'value': False}, {'code': 'B', 'value': True}]}
    assert_equal('value=True(bool) 正确项', _correct_codes_of(q_bool), ['B'])

    q_space = {'options': [{'code': ' a ', 'value': 0}, {'code': ' b ', 'value': ' 1 '}]}
    assert_equal('code 带空格归一化', _correct_codes_of(q_space), ['B'])

    q_multi = {
        'options': [
            {'code': 'A', 'value': 1}, {'code': 'B', 'value': 1},
            {'code': 'C', 'value': 0}, {'code': 'D', 'value': 0},
        ]
    }
    assert_equal('多选正确项', _correct_codes_of(q_multi), ['A', 'B'])

    # 回退：options 未标注正确项 -> 用 answer 字段
    q_fb = {'answer': 'C', 'options': [{'code': 'A', 'value': 0}, {'code': 'B', 'value': 0}, {'code': 'C', 'value': 0}]}
    assert_equal("回退 answer='C'", _correct_codes_of(q_fb), ['C'])

    q_fb2 = {'answer': 'AC', 'options': [{'code': 'A', 'value': 0}, {'code': 'B', 'value': 0}, {'code': 'C', 'value': 0}]}
    assert_equal("回退 answer='AC' 多选", _correct_codes_of(q_fb2), ['A', 'C'])

    assert_equal('无答案无选项 -> 空', _correct_codes_of({}), [])
    assert_equal('选项非列表 -> 空', _correct_codes_of({'options': 'bad'}), [])

    # isCorrect 标记兼容
    q_mark = {'options': [{'code': 'A', 'isCorrect': True}, {'code': 'B', 'isCorrect': False}]}
    assert_equal('isCorrect 标记兼容', _correct_codes_of(q_mark), ['A'])


# ==================== 2. 作答归一化 ====================
def test_normalize_codes():
    print('\n--- 2. 作答归一化 _normalize_codes ---')
    assert_equal('去空/null/去重/排序', _normalize_codes(['b', 'A', 'b', '', None]), ['A', 'B'])
    assert_equal('小写转大写', _normalize_codes(['c']), ['C'])
    assert_equal('去首尾空格', _normalize_codes([' b ']), ['B'])
    assert_equal('非列表 -> 空', _normalize_codes('B'), [])
    assert_equal('空列表', _normalize_codes([]), [])


# ==================== 3. 集合比对规则 ====================
def test_compare_rule():
    print('\n--- 3. 选项集合比对规则（对齐 judge.js）---')
    assert_true('单选正确', compare_option_answer(['B'], ['B']) is True)
    assert_true('单选错误', compare_option_answer(['B'], ['A']) is False)
    assert_true('多选顺序无关', compare_option_answer(['A', 'B'], ['B', 'A']) is True)
    assert_true('多选漏选判错', compare_option_answer(['A', 'B'], ['A']) is False)
    assert_true('多选多选判错', compare_option_answer(['A', 'B'], ['A', 'B', 'C']) is False)
    assert_true('重复作答去重后正确', compare_option_answer(['B'], ['B', 'B']) is True)
    assert_true('未作答判错', compare_option_answer(['B'], []) is False)
    assert_true('无标准答案不判错', compare_option_answer([], ['A']) is True)


# ==================== 4. 全库数据完整性 ====================
def test_data_integrity():
    print('\n--- 4. 全库题目数据完整性 ---')
    total = 0
    dirty = []
    qtype_counter = Counter()
    for doc in Document.objects.filter(collection='questions'):
        data = doc.data or {}
        total += 1
        qtype_counter[data.get('qtype') or data.get('type')] += 1
        if (data.get('qtype') or data.get('type')) in ('fill', 'qa'):
            continue
        if not _correct_codes_of(data):
            dirty.append(doc.doc_id)

    assert_true('题目总数 > 0', total > 0, 'total=%d' % total)
    print('      题目分布:', dict(qtype_counter))
    assert_equal('无「缺少正确项」的脏数据题目', dirty, [])


# ==================== 5. 路由注册 ====================
def test_url_route():
    print('\n--- 5. /api/question-stats/ 路由注册 ---')
    try:
        url = reverse('question-stats')
        assert_equal('reverse(question-stats)', url, '/api/question-stats/')
    except Exception as e:
        assert_true('reverse(question-stats) 路由存在', False, str(e))


# ==================== 6/7. 接口行为 ====================
_client = Client()


def _get(path, openid=None):
    headers = {'HTTP_X_OPENID': openid} if openid else {}
    resp = _client.get(path, **headers)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, None


def test_api_validation():
    print('\n--- 6. 接口参数 / 方法校验 ---')
    st, body = _get('/api/question-stats/?id=RK_RJJS_CH01_QS001')
    assert_equal('正常请求 status', st, 200)
    assert_true('返回 data 段', isinstance(body, dict) and 'data' in body, body)
    d = body['data']
    for k in ('totalAttempts', 'correctCount', 'correctRate', 'correctCodes'):
        assert_true('返回字段 %s' % k, k in d, d)

    st, body = _get('/api/question-stats/')
    assert_equal('缺 id -> 400', st, 400)

    resp = _client.post('/api/question-stats/', data='{}', content_type='application/json')
    assert_equal('POST -> 405', resp.status_code, 405)


def test_api_consistency():
    print('\n--- 7. 接口统计与独立实现交叉核对 ---')
    # 找出在 historys 中出现最多的题目
    cnt = Counter()
    for doc in Document.objects.filter(collection='historys'):
        items = (doc.data or {}).get('items') or []
        if isinstance(items, list):
            for i in items:
                cnt[i] += 1
    assert_true('historys 中存在可统计的题目', len(cnt) > 0, 'len=%d' % len(cnt))

    checked = 0
    for qid, _n in cnt.most_common(5):
        qdoc = Document.objects.filter(collection='questions', doc_id=qid).first()
        cc = _correct_codes_of(qdoc.data) if qdoc else []

        total, correct = 0, 0
        for doc in Document.objects.filter(collection='historys'):
            d = doc.data or {}
            items, sa = d.get('items') or [], d.get('score_arr') or []
            if not isinstance(items, list) or not isinstance(sa, list) or qid not in items:
                continue
            idx = items.index(qid)
            if idx >= len(sa):
                continue
            ua = _normalize_codes(sa[idx])
            if not ua:
                continue
            total += 1
            if cc and ua == cc:
                correct += 1

        st, body = _get('/api/question-stats/?id=' + qid)
        d = body.get('data') if isinstance(body, dict) else None
        ok = bool(d) and d.get('totalAttempts') == total and d.get('correctCount') == correct
        assert_true('题目 %s 统计一致 (total=%d, correct=%d)' % (qid, total, correct), ok, d)
        assert_equal('题目 %s correctCodes 一致' % qid,
                     d.get('correctCodes') if d else None, cc or [])
        checked += 1
    assert_true('至少校验 1 道题', checked > 0)


def test_architecture_regression():
    print('\n--- 8. 架构回归：私有集合接口 ≠ 全站统计 ---')
    # 找一个在 historys 中真实存在的题目
    qid = None
    for doc in Document.objects.filter(collection='historys'):
        items = (doc.data or {}).get('items') or []
        if isinstance(items, list) and items:
            qid = items[0]
            break
    assert_true('找到样本题目', bool(qid), '')

    # 私有集合：带任意 openid 只能看到本人数据
    st1, body1 = _get('/api/collections/historys/?items__contains=' + qid, 'oDWYj0User000abcdef1234567890')
    n_private = len(body1.get('data', [])) if isinstance(body1, dict) else -1
    # 私有集合：不带 openid 直接返回空
    st2, body2 = _get('/api/collections/historys/?items__contains=' + qid)
    n_anon = len(body2.get('data', [])) if isinstance(body2, dict) else -1
    # 全站接口：无需 openid 即可拿到全量
    st3, body3 = _get('/api/question-stats/?id=' + qid)
    n_all = body3['data']['totalAttempts']

    print('      题目 %s: 私有集合(带openid)=%d 条, 私有集合(匿名)=%d 条, 全站接口=%d 次'
          % (qid, n_private, n_anon, n_all))
    assert_equal('私有集合匿名访问返回空（数据隔离生效）', n_anon, 0)
    assert_true('全站接口不得受 openid 隔离影响', n_all >= n_private,
                'all=%s private=%s' % (n_all, n_private))
    assert_true('全站接口返回非负整数', isinstance(n_all, int) and n_all >= 0, n_all)


# ==================== 汇总 ====================
def main():
    print('=' * 72)
    print('考试宝 —— 答案判定逻辑 & 全站题目统计 回归测试')
    print('=' * 72)

    tests = [
        test_correct_codes_of,
        test_normalize_codes,
        test_compare_rule,
        test_data_integrity,
        test_url_route,
        test_api_validation,
        test_api_consistency,
        test_architecture_regression,
    ]

    for t in tests:
        try:
            t()
        except Exception as e:
            print('  [ERROR] %s 异常: %s' % (t.__name__, e))
            traceback.print_exc()
            _results.append((t.__name__, False, str(e)))

    print('\n' + '=' * 72)
    print('测试汇总')
    print('=' * 72)
    total = len(_results)
    passed = sum(1 for _, p, _ in _results if p)
    failed = total - passed
    print('总测试数: %d | 通过: %d | 失败: %d' % (total, passed, failed))
    if failed:
        print('\n--- 失败用例详情 ---')
        for name, p, detail in _results:
            if not p:
                print('  FAIL: %s' % name)
                if detail:
                    print('        %s' % detail)
    print('\nRouting Decision: %s' % (
        'NoOne (全部通过)' if failed == 0 else '需分析失败原因（源码 Bug 或测试 Bug）'))
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
