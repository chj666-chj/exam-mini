# 小程序「答对却判错」问题 —— 根因分析与修复方案

> 现象截图：`我的答案 B` / `正确答案 B` / `判定 错误`
> 结论：**不是答案比对规则写错，而是判题时机（setData 时序）错误** —— 判题读到了上一次的作答。
> 附带修复：`全站作答 0 次 / 全站正确率 0%`（架构缺陷，私有集合无法替代全站统计）。

---

## 一、问题现象

答题页顶部出现「回答错误」横幅，下方「回答结果」区块中：

| 字段 | 值 |
| --- | --- |
| 我的答案 | B |
| 正确答案 | B |
| 判定 | **错误** |

「我的答案」与「正确答案」都是 B，判定却是「错误」——**展示数据正确、判题结论错误**，这是典型的「两处取数来源不一致」特征。

---

## 二、排查过程与证据

### 2.1 先排除数据层（结论：数据完全正常）

对 SQLite `backend/db.sqlite3` 中 1910 道题做全量普查（脚本 `tools/diag_answer_judge*.py`，结果 `outputs/diag_result*.txt`）：

```
题目总数: 1910
题型分布: single=726, multiple=476, judge=708
选项 code 类型分布: {'str': 7153}        ← 全部字符串，无数字型编号
选项 value 类型分布: {'int': 7101, 'str': 52}
无「缺少正确项」的脏数据题目: 0          ← 关键：不存在标准答案缺失的题
```

以截图中的题为样本（`RK_RJJS_CH01_QS001`，二进制 10110）：

```json
{
  "title": "二进制数 10110 转换为十进制数是？",
  "qtype": "single",
  "answer": "B",
  "options": [
    {"code":"A","value":0,"text":"23"},
    {"code":"B","value":1,"text":"22"},   ← 正确项标注正确
    {"code":"C","value":0,"text":"21"},
    {"code":"D","value":0,"text":"24"}
  ]
}
```

**结论**：`code` 是字符串 `'B'`、`value` 是整数 `1`，与前端 `opt.value == 1` 的判定方式完全匹配。数据格式、类型、正确答案标注**全部正确**，数据层不是根因。

> 补充：另有 52 个选项的 `value` 存成了字符串 `'1'`/`'0'`（涉及 13 道题）。JS 的 `==` 松散比较能正确处理，属于**潜在隐患**而非本次根因，本次一并做了类型归一化加固。

### 2.2 定位到前端判题代码

`miniprogram/pages/exam/exam.js` 的 `selectOption`（用户点击选项时执行）：

```js
var userAnswers = this.data.userAnswers.slice();
userAnswers[this.data.currentIndex] = userAnswer;   // ① 先把新作答写入「副本」

// ...
if (this.data.mode === 'answer' && userAnswer.length > 0 && !this.data.unifiedMode) {
  instantResult = true;
  instantCorrect = this.checkAnswer(this.data.currentIndex);   // ② ⚠️ 判题
  // ...
}

this.setData({ userAnswers: userAnswers, /* ... */ });          // ③ 最后才提交
```

而 `checkAnswer` 的实现是：

```js
checkAnswer: function (index) {
  var question = this.data.questions[index];
  var userAnswer = this.data.userAnswers[index] || [];   // ← 读的是 this.data，不是刚算出的新值
  if (userAnswer.length === 0) return false;             // ← 首次作答必然命中这里
  // ...
}
```

### 2.3 根因（Root Cause）

**步骤 ② 在步骤 ③ 之前执行，而 ② 读取的 `this.data.userAnswers` 尚未被 ③ 写入。**

由此产生两种错误表现：

| 场景 | `this.data.userAnswers[idx]` 实际值 | 判题结果 |
| --- | --- | --- |
| 首次作答该题 | `undefined` → `[]`（空数组） | 命中 `if (userAnswer.length === 0) return false` → **一律判「错误」** |
| 修改答案 | 上一次的选择 | 用旧答案判题 → **判定滞后一轮** |

而同一段代码里，展示用的 `myAnswerText` 是由**局部变量 `userAnswer`（新值）**拼出来的：

```js
var myAnswerText = userAnswer.length > 0 ? userAnswer.join('、') : '未作答';   // 用的是新值
```

**「展示用新值、判题用旧值」→ 屏幕上出现「我的答案 B / 正确答案 B / 判定错误」。** 与截图现象完全吻合。

> 验证：页面顶部「回答错误」横幅的显示条件是 `{{instantResult && !instantCorrect}}`（`exam.wxml:68`），
> 即横幅本身就来源于这个错误的 `instantCorrect`，与「判定」行同源。

### 2.4 为什么最终成绩是对的（重要旁证）

`goNext` 中的统分/错题记录发生在 `setData` 之后：

```js
var isRight = this.checkAnswer(index);   // 此时 this.data.userAnswers 已提交 → 结果正确
if (isRight) { rightNum++; } else { errNum++; this.addNote(index); }
```

**所以「即时反馈是错的、最终得分是对的」** —— 这一自相矛盾的现象正是时序 Bug 的专属指纹，也说明问题不在比对规则，而在取值时机。

---

## 三、附带发现的第 2 个缺陷：全站统计恒为 0

`exam.js` 的 `loadQuestionStats` 原实现：

```js
db.collection('historys').where({ items__contains: questionId }).get({ ... });
```

但 `historys` 属于后端 `PRIVATE_COLLECTIONS`（`core/views.py:36`），GET 时按 `X-Openid` 过滤：

```python
if name in PRIVATE_COLLECTIONS:
    openid = request.headers.get('X-Openid') or ''
    if not openid:
        return JsonResponse({'data': []})      # 匿名直接返回空
    qs = qs.filter(data___openid=openid)       # 只返回本人数据
```

**用「只看得到自己」的接口去算「全站」统计，逻辑上不可能成立。** 实测数据（`outputs/test_answer_judge_console.txt`）：

```
题目 RK_RJJS_CH03_Q02:
  私有集合(带某用户 openid) = 7 条
  私有集合(匿名)            = 0 条
  全站专用接口              = 33 次      ← 真实全站值
```

这正是截图中「全站作答 0 次 / 全站正确率 0%」的原因。本问题与判题 Bug **互相独立**。

---

## 四、修复方案与实施

### 4.1 新增判题唯一实现 `miniprogram/utils/judge.js`

把判题从页面中抽出为**纯函数**，从设计上消除「时序」「类型」两类问题：

| 设计原则 | 解决的问题 |
| --- | --- |
| 纯函数，只依赖入参 `question` / `userAnswer`，不读 `this.data` | 任意时序调用都安全（本次根因） |
| `code` 统一 `String().trim().toUpperCase()` | 数字编号 / 空格 / 大小写不一致 |
| `value` 走白名单真值判断（`1` / `'1'` / `' 1 '` / `true` / `isCorrect`） | `'1'` vs `1` 类型混用 |
| 作答数组去空、去重、排序 | 脏数据导致长度比对失败 |
| 双层答案源：`options[].value` → 回退 `question.answer` | 题目数据未标注正确项时仍可判题 |
| 无标准答案时**不判错**（与既有填空/问答分支约定一致） | 脏数据导致「答对判错」 |

### 4.2 修复 `exam.js` 判题时序（核心修复）

```js
// 修复前（读 this.data，尚未提交 → 旧值）
instantCorrect = this.checkAnswer(this.data.currentIndex);

// 修复后（传入刚算出的新作答，纯函数）
instantCorrect = judge.judgeAnswer(this.data.questions[this.data.currentIndex], userAnswer);
```

同一处展示也改为同源取值，保证「我的答案」「正确答案」「判定」三者永不矛盾：

```js
var correctAnswerText = judge.getCorrectCodes(question).join('、');
var myAnswerText = judge.describeAnswer(question, userAnswer);
var isRight = judge.judgeAnswer(question, userAnswer);
```

### 4.3 数据入口统一归一化

`exam.js#initQuestions` / `question/index.js#loadQuestions` 在题目加载后统一调用
`judge.normalizeQuestion(q)`：`code` → 字符串、`value` → 0/1、兼容 `options` 为 JSON 字符串的情况。

另外对 `data-code` 取值做兜底（`judge.normalizeCode(e.currentTarget.dataset.code)`）：
WXML 的 `data-*` 在值形如 `"1"` 时会被微信转成 Number，与字符串 `code` 严格比较会失败，导致点击无响应。

### 4.4 新增后端全站统计接口

* `GET /api/question-stats/?id=<题目id>` → `{data:{totalAttempts, correctCount, correctRate, correctCodes}}`
* 位置：`backend/core/views.py`（`question_stats`）、`backend/core/urls.py`、`miniprogram/utils/api.js`（`api.getQuestionStats`）
* 与既有 `/api/ranking/` 同属「需跨用户聚合」的专用接口，**刻意不做 `_openid` 过滤**
* 与小程序端同口径：`value` 类型兼容 + `answer` 字段回退 + 作答归一化

### 4.5 统一 `question/index.js` 判题

删除该页重复的判题实现，改为委托 `judge.judgeAnswer`，避免两处规则再次漂移。
（该页原实现因在 `setData` 之后判题，本身没有时序 Bug，属一致性加固。）

---

## 五、验证结果

### 5.1 前端运行时验证（真实驱动 `exam.js` 页面逻辑）

`tools/test_judge_fix.js` —— 为小程序提供 `Page` / `wx` / `getApp` 桩，加载真实页面代码，
构造页面实例后直接调用 `selectOption`，断言判题结果：

```
通过 51 项，失败 0 项
```

覆盖：
* 复现截图场景（正确答案 B、选 B → 判定「正确」），并**对照复刻旧实现证明确实返回 false**
* 改答案后判定实时跟随（旧实现会滞后一轮）
* 错选仍能正确判错（防止「一律判对」的反向回归）
* `value='1'`（字符串）/ `code=2`（数字）/ `code=' b '`（空格小写）
* 多选题顺序无关 / 漏选 / 多选；判断题
* 无标准答案脏数据不判错；归一化不破坏自定义字段

### 5.2 后端回归测试

`backend/test_answer_judge.py`（项目既有测试风格）：

```
总测试数: 50 | 通过: 50 | 失败: 0
Routing Decision: NoOne (全部通过)
```

其中第 7 项用**独立实现**重新聚合 `historys` 并与接口返回值逐题比对，5 道题全部一致；
第 8 项量化验证了「私有集合 ≠ 全站统计」的架构回归。

> 测试还捕获到 1 个新引入的缺陷并已修复：Python 的 `str(None)` 会得到 `'None'`，
> 使 `_normalize_codes` 把 `None` 当成合法选项编号（JS 端无此问题，已保持两端语义一致）。

### 5.3 语法与路由

* `node --check` 对 4 个改动文件全部通过
* `/api/question-stats/` 路由可达（200）、缺参 400、错误方法 405

---

## 六、改动清单

| 文件 | 变更 |
| --- | --- |
| `miniprogram/utils/judge.js` | **新增** 判题唯一实现（纯函数 + 类型归一 + 双层答案源） |
| `miniprogram/pages/exam/exam.js` | 修复判题时序（P0）；统一取数来源；题目归一化；`dataset` 兜底；统计改走后端接口 |
| `miniprogram/pages/question/index.js` | 判题委托 `judge`；题目归一化；`dataset` 兜底 |
| `miniprogram/utils/api.js` | **新增** `getQuestionStats()` |
| `backend/core/views.py` | **新增** `question_stats` 视图及 `_correct_codes_of` / `_normalize_codes` / `_is_correct_value` |
| `backend/core/urls.py` | **新增** 路由 `question-stats/` |
| `backend/test_answer_judge.py` | **新增** 后端回归测试（50 项） |
| `tools/test_judge_fix.js` | **新增** 前端运行时验证（51 项） |
| `tools/diag_answer_judge*.py` | **新增** 数据层诊断脚本（4 个） |

---

## 七、遗留建议（未在本次改动）

1. **`value` 存储类型统一**：13 道题的选项 `value` 存成了字符串 `'1'`。前端已兼容，建议在导入/管理端录入时统一写入整数，避免其他消费方（如 Excel 导出、报表）按严格类型比较时出错。
2. **`review.js` 展示一致性**：错题回顾页仍在用 `opt.value == 1` 自行判断（功能正常）。建议后续也切到 `judge.isCorrectOption`，形成单一事实来源。
3. **`exam.js` 其余 `checkAnswer` 调用点**：`goNext` / `submitExam` 中仍调用 `this.checkAnswer(index)`。这些位置在 `setData` 之后执行，当前正确；但建议后续统一改为 `judge.judgeAnswer(question, this.data.userAnswers[index])`，彻底消除「依赖调用时机」的隐性约定。
