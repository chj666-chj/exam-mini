// utils/judge.js —— 判题唯一实现（Single Source of Truth）
//
// 为什么单独抽出来：
//   1) 原实现散落在 exam.js / question/index.js 中，各页面比对方式不一致；
//   2) 原 exam.js 的 checkAnswer 直接读 this.data，调用方若在 setData 之前调用，
//      会读到「上一次」的作答，导致首答必判错（见本次修复）；
//   3) code 可能是 String / Number，value 可能是 1 / '1' / true，必须统一归一化。
//
// 设计原则：
//   · 纯函数：只依赖入参 question / userAnswer，绝不读 this.data（可从任意时序安全调用）
//   · 类型归一：code 一律 String().trim().toUpperCase()；value 走白名单真值判断
//   · 双层答案源：优先 options[].value，缺失时回退 question.answer 字段
//   · 容错优先：无标准答案时不武断判错（与填空/问答分支既有约定保持一致）

/** 判断单个选项是否为正确项：兼容 1 / '1' / ' 1 ' / true / isCorrect 标记 */
function isCorrectOption(opt) {
  if (!opt) return false;
  if (opt.isCorrect === true) return true;
  var v = opt.value;
  if (v === true) return true;
  if (typeof v === 'number') return v === 1;
  if (typeof v === 'string') return v.trim() === '1';
  return false;
}

/** 归一化选项编号：'b ' / 'B' / 2 -> 'B' / '2' */
function normalizeCode(code) {
  if (code === null || code === undefined) return '';
  return String(code).trim().toUpperCase();
}

/** 归一化作答数组：去空、去重、排序 */
function normalizeCodes(arr) {
  if (!Array.isArray(arr)) {
    if (arr === null || arr === undefined || arr === '') return [];
    arr = [arr];
  }
  var out = [];
  for (var i = 0; i < arr.length; i++) {
    var c = normalizeCode(arr[i]);
    if (c && out.indexOf(c) === -1) out.push(c);
  }
  return out.sort();
}

/**
 * 取题目的标准答案编号列表
 * 第一答案源：options 中 value == 1 的项
 * 第二答案源：question.answer 字段（兼容 'B' / 'ABC' / 'A,B' 等写法）
 */
function getCorrectCodes(question) {
  question = question || {};
  var options = question.options || [];
  var codes = [];
  for (var i = 0; i < options.length; i++) {
    var opt = options[i];
    if (isCorrectOption(opt)) {
      var c = normalizeCode(opt.code);
      if (c && codes.indexOf(c) === -1) codes.push(c);
    }
  }
  if (codes.length > 0) return codes.sort();

  // 回退：options 未标注正确项时，从 answer 字段解析
  var ans = (question.answer === null || question.answer === undefined) ? '' : String(question.answer).trim();
  if (!ans) return [];

  var optCodes = [];
  for (var j = 0; j < options.length; j++) {
    var oc = normalizeCode(options[j] && options[j].code);
    if (oc && optCodes.indexOf(oc) === -1) optCodes.push(oc);
  }
  if (optCodes.length === 0) return [];

  var upper = ans.toUpperCase();
  if (optCodes.indexOf(upper) > -1) return [upper];      // answer === 'B'

  var letters = upper.match(/[A-Z]/g) || [];             // answer === 'ABC'
  var picked = [];
  for (var k = 0; k < letters.length; k++) {
    if (optCodes.indexOf(letters[k]) > -1 && picked.indexOf(letters[k]) === -1) {
      picked.push(letters[k]);
    }
  }
  return picked.sort();
}

/** 判断题：把「正确/错误」「对/错」「T/F」「√/×」等文本归一为布尔 */
function normalizeJudgeText(text) {
  var t = String(text === null || text === undefined ? '' : text).trim().toLowerCase();
  if (!t) return null;
  if (['正确', '对', '是', '真', 't', 'true', 'y', 'yes', '√', '1', 'a'].indexOf(t) > -1) return true;
  if (['错误', '错', '否', '假', 'f', 'false', 'n', 'no', '×', 'x', '0', 'b'].indexOf(t) > -1) return false;
  return null;
}

/**
 * 核心判题（纯函数）
 * @param {Object} question  题目对象（含 options / qtype / blanks / answer）
 * @param {Array}  userAnswer 用户作答（选项题为编号数组；填空题为各空文本数组）
 * @returns {Boolean}
 */
function judgeAnswer(question, userAnswer) {
  if (!question) return false;
  userAnswer = userAnswer || [];
  if (userAnswer.length === 0) return false;

  var qtype = question.qtype || question.type || 'single';

  // ---- 填空题：逐空比对可接受答案列表 ----
  if (qtype === 'fill') {
    var blanks = question.blanks || [];
    if (blanks.length === 0) return true;              // 无标准答案，视为正确
    if (userAnswer.length !== blanks.length) return false;
    for (var i = 0; i < blanks.length; i++) {
      var userText = String(userAnswer[i] === null || userAnswer[i] === undefined ? '' : userAnswer[i]).trim().toLowerCase();
      if (!userText) return false;
      var acceptable = blanks[i] || [];
      var matched = false;
      for (var j = 0; j < acceptable.length; j++) {
        if (String(acceptable[j]).trim().toLowerCase() === userText) { matched = true; break; }
      }
      if (!matched) return false;
    }
    return true;
  }

  // ---- 问答题：关键词覆盖度 >= 60% 判正确 ----
  if (qtype === 'qa') {
    var refAnswer = question.answer_md || question.answer || '';
    if (!String(refAnswer).trim()) return true;        // 无参考答案，视为正确
    var uText = String(userAnswer[0] === null || userAnswer[0] === undefined ? '' : userAnswer[0]).trim();
    if (!uText) return false;
    var keywords = String(refAnswer)
      .replace(/[\s\n，。、；：""''（）()【】\[\]{}]/g, ' ')
      .split(/\s+/)
      .filter(function (kw) { return kw.length >= 2; });
    if (keywords.length === 0) return uText.length >= 5;
    var lowerUser = uText.toLowerCase();
    var hit = 0;
    keywords.forEach(function (kw) {
      if (lowerUser.indexOf(kw.toLowerCase()) !== -1) hit++;
    });
    return (hit / keywords.length) >= 0.6;
  }

  // ---- 选项题（single / multiple / judge）：集合比对 ----
  var correct = getCorrectCodes(question);
  if (correct.length === 0) {
    // 无任何正确项（脏数据）→ 不武断判错，避免「答对却判错」，同时留下可观测日志
    console.warn('[judge] 题目无标准答案，判定为正确（请检查题目数据）:', question._id || question.title);
    return true;
  }
  var mine = normalizeCodes(userAnswer);
  if (mine.length !== correct.length) return false;
  for (var m = 0; m < mine.length; m++) {
    if (correct.indexOf(mine[m]) === -1) return false;
  }
  return true;
}

/**
 * 归一化题目对象：把 options 的 code/value 统一成稳定类型
 * 建议在题目加载后调用一次，避免下游各页面重复处理
 */
function normalizeQuestion(q) {
  if (!q) return q;
  var options = q.options;
  if (typeof options === 'string') {
    try { options = JSON.parse(options); } catch (e) { options = []; }
  } else if (!Array.isArray(options)) {
    options = [];
  }
  q.options = options.map(function (opt) {
    opt = opt || {};
    // 浅拷贝保留选项上的其它自定义字段，仅覆写 code / content / value / selected
    var out = {};
    for (var k in opt) {
      if (Object.prototype.hasOwnProperty.call(opt, k)) out[k] = opt[k];
    }
    out.code = normalizeCode(opt.code);
    if (out.content === undefined || out.content === null || out.content === '') {
      out.content = opt.content || opt.text || '';
    }
    out.value = isCorrectOption(opt) ? 1 : 0;
    out.selected = !!opt.selected;
    return out;
  });
  q.qtype = q.qtype || q.type || 'single';
  q.type = q.type || q.qtype;
  return q;
}

/**
 * 判定单题的作答状态（答题卡标识用，纯函数）
 *
 * 四种状态，与「能否揭示对错」解耦：
 *   · 'unanswered' —— 未作答
 *   · 'answered'   —— 已作答但结果未知（模拟考试/测评交卷前，不应泄漏对错）
 *   · 'correct'    —— 已作答且判定正确
 *   · 'wrong'      —— 已作答且判定错误
 *
 * @param {Object}  question   题目对象
 * @param {Array}   userAnswer 用户作答
 * @param {Boolean} reveal     是否允许揭示对错（答题模式即时反馈 / 已交卷）
 */
function resolveStatus(question, userAnswer, reveal) {
  var ans = normalizeCodes(userAnswer);
  if (ans.length === 0) return 'unanswered';
  if (!reveal) return 'answered';
  return judgeAnswer(question, ans) ? 'correct' : 'wrong';
}

/** 状态 → 角标字符（未作答题号不显示角标） */
function statusMark(status) {
  if (status === 'correct') return '\u2713';
  if (status === 'wrong') return '\u2717';
  return '';
}

/** 生成答案展示文本（选项题显示编号，填空题显示作答内容） */
function describeAnswer(question, answerArr) {
  answerArr = answerArr || [];
  if (answerArr.length === 0) return '未作答';
  var qtype = (question && (question.qtype || question.type)) || 'single';
  if (qtype === 'fill' || qtype === 'qa') {
    return answerArr.map(function (t) { return String(t || '').trim() || '（空）'; }).join('、');
  }
  return normalizeCodes(answerArr).join('、');
}

module.exports = {
  judgeAnswer: judgeAnswer,
  getCorrectCodes: getCorrectCodes,
  isCorrectOption: isCorrectOption,
  normalizeCode: normalizeCode,
  normalizeCodes: normalizeCodes,
  normalizeQuestion: normalizeQuestion,
  normalizeJudgeText: normalizeJudgeText,
  describeAnswer: describeAnswer,
  resolveStatus: resolveStatus,
  statusMark: statusMark
};
