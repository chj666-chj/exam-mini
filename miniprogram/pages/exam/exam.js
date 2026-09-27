const api = require('../../utils/api.js');
const util = require('../../utils/util.js');
const judge = require('../../utils/judge.js');
const md = require('../../utils/markdown.js');
var app = getApp();

Page({
  data: {
    subjectId: '',
    mode: 'answer',
    questions: [],
    currentIndex: 0,
    total: 0,
    question: {},
    options: [],
    userAnswers: [],
    rightNum: 0,
    errNum: 0,
    percent: 0,
    answeredCount: 0,
    btnText: '下一题',
    ordernum: '',
    loading: true,
    error: '',
    answered: false,
    showAnswer: false,
    // ===== 功能1: 解析展开/收起 =====
    showExplanation: false,
    // ===== 功能2: 收藏 =====
    isFavorited: false,
    // ===== 功能3: 答题卡 =====
    showCard: false,
    answerCard: [],
    cardLegend: [],        // 图例（随模式变化：正确/错误/未答 或 已答/未答）
    correctCount: 0,       // 答题卡：正确题数
    wrongCount: 0,         // 答题卡：错误题数
    cardRevealed: false,   // 是否已揭示对错（交卷后置 true；答题模式天然为 true）
    // ===== 功能4: 断点续答 =====
    resumeKey: '',
    // ===== 功能6: 题目反馈 =====
    showFeedback: false,
    feedbackText: '',
    // ===== 功能7: 题目标签 =====
    difficultyLabel: '',
    qtypeLabel: '',
    // ===== 配置: 答对自动跳转 =====
    autoNext: false,
    // ===== 答题模式即时反馈 =====
    instantResult: false,
    instantCorrect: false,
    // ===== 模拟考试模式 =====
    examMode: false,
    timeLimit: 0,
    remainingSeconds: 0,
    timeDisplay: '',
    startTime: 0,
    // ===== 自我测评模式 =====
    assessmentMode: false,
    feedbackMode: 'unified',
    unifiedMode: false,
    // ===== 回答结果展示 =====
    questionStats: { totalAttempts: 0, correctRate: 0 },
    myAnswerText: '',
    correctAnswerText: '',
    resultLabel: '',
    resultClass: '',
    kpTags: [],
    // ===== 字体大小偏好 =====
    fontSizeClass: 'fs-medium',
    // ===== AI 解析（VIP 专用）=====
    isVip: false,                  // VIP 状态（页面加载时查询）
    vipChecked: false,             // VIP 状态是否已查询完成
    aiAnalysisData: null,          // 当前题的 AI 解析原始数据
    aiAnalysisNodes: [],           // AI 解析 Markdown → rich-text nodes
    aiAnalysisLoading: false,      // AI 解析加载中
    aiAnalysisError: '',           // AI 解析错误信息
    showAiAnalysis: false,         // 是否展开 AI 解析面板
    aiAnalysisCached: false,       // 本次解析是否命中缓存
    // ===== AI 答题分析总结（VIP 专用）=====
    examSummaryData: null,         // 整份作答分析总结原始数据
    examSummaryNodes: [],          // 分析总结 Markdown → rich-text nodes
    examSummaryLoading: false,     // 分析总结加载中
    examSummaryError: '',          // 分析总结错误信息
    showExamSummary: false,        // 是否展示分析总结弹层
    // ===== VIP 升级引导 =====
    showVipUpgrade: false          // 非 VIP 点击 AI 入口时弹出升级引导
  },

  onLoad: function (options) {
    var id = options.id || '';
    var mode = options.mode || 'answer';
    var ordernum = util.formatTime(new Date()) + Math.random().toString(36).substr(2, 4);
    var settings = wx.getStorageSync('quiz_settings') || {};
    var fontSizeMap = { small: 'fs-small', medium: 'fs-medium', large: 'fs-large' };
    var fontSizeClass = fontSizeMap[settings.fontSize] || 'fs-medium';

    var examMode = options.examMode === 'true' || wx.getStorageSync('quiz_exam_mode') === 'true';
    var timeLimit = parseInt(options.timeLimit, 10) || 0;
    var assessmentMode = options.assessmentMode === 'true' || false;
    var feedbackMode = options.feedbackMode || 'unified';
    var unifiedMode = examMode || (assessmentMode && feedbackMode === 'unified');

    this.setData({
      subjectId: id,
      mode: mode,
      ordernum: ordernum,
      autoNext: settings.autoNext || false,
      resumeKey: 'quiz_resume_' + id,
      examMode: examMode,
      timeLimit: timeLimit,
      startTime: Date.now(),
      assessmentMode: assessmentMode,
      feedbackMode: feedbackMode,
      unifiedMode: unifiedMode,
      fontSizeClass: fontSizeClass
    });

    this.ensureOpenid();
    this.loadQuestions();
    this.loadVipStatus();
  },

  onHide: function () {
    // ⚠️ 交卷后不再保存续答：submitExam 已调用 clearResumePosition，
    //    若 onUnload 再 saveResumePosition 会把过期的 startTime 写回 storage，
    //    导致下次同科目考试进入即提示"考试时间已结束"。
    if (!this._examSubmitted) {
      this.saveResumePosition();
    }
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  },

  onUnload: function () {
    if (!this._examSubmitted) {
      this.saveResumePosition();
    }
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  },

  ensureOpenid: function () {
    var openid = wx.getStorageSync('openid');
    if (!openid) {
      api.callFunction({
        name: 'login',
        data: {},
        success: function (res) {
          if (res.result && res.result.openid) {
            wx.setStorageSync('openid', res.result.openid);
            app.globalData.openid = res.result.openid;
          }
        },
        fail: function (err) {
          console.error('[exam] login fail', err);
        }
      });
    }
  },

  loadQuestions: function () {
    var that = this;
    var questions = wx.getStorageSync('quiz_questions');

    if (questions && questions.length > 0) {
      that.initQuestions(questions);
      return;
    }

    if (!that.data.subjectId) {
      that.setData({ loading: false, error: '缺少科目参数' });
      return;
    }

    var db = api.database();
    // subjectId 可能是章节 _id（如 RK_RJJS_CH01，来自 entry）或考试 _id（如 RK_RJJS，来自 examsetup/assessment）。
    // 题目数据中 chapter 存章节 id、examid 存考试 id，先按 chapter 查，空则回退 examid 查。
    function handleQuestions(res) {
      var list = (res.data || []).map(function (q) {
        if (typeof q.options === 'string') {
          try { q.options = JSON.parse(q.options); } catch (e) { q.options = []; }
        }
        q.options = q.options || [];
        q.qtype = q.qtype || q.type || 'single';
        return q;
      });
      if (list.length === 0) {
        that.setData({ loading: false, error: '该科目暂无题目' });
        return;
      }
      that.initQuestions(list);
    }
    db.collection('questions').where({ chapter: that.data.subjectId }).get({
      success: function (res) {
        if ((res.data || []).length > 0) { handleQuestions(res); return; }
        // chapter 查询为空，回退用 examid 查（subjectId 可能是考试级 id）
        db.collection('questions').where({ examid: that.data.subjectId }).get({
          success: handleQuestions,
          fail: function (err) {
            console.error('[exam] loadQuestions fallback fail', err);
            that.setData({ loading: false, error: '题目加载失败，请检查网络' });
          }
        });
      },
      fail: function (err) {
        console.error('[exam] loadQuestions fail', err);
        that.setData({ loading: false, error: '题目加载失败，请检查网络' });
      }
    });
  },

  initQuestions: function (questions) {
    var isMemorize = this.data.mode === 'memorize';
    // 题目归一化（数据入口统一处理一次）：
    //   · options 若是 JSON 字符串则解析
    //   · code 统一为 String（trim + 大写），避免 dataset 取到 Number 后与字符串 code 严格比较失败
    //   · value 统一为 0/1，兼容 '1'(str) / 1(int) / true(boolean) 三种历史写法
    questions = (questions || []).map(function (q) { return judge.normalizeQuestion(q); });
    var userAnswers = questions.map(function () { return []; });
    var resume = wx.getStorageSync(this.data.resumeKey);
    var resumeIndex = 0;
    var resumeStartTime = 0;
    if (resume && resume.answers && resume.answers.length === questions.length) {
      // ⚠️ 考试/测评模式下增加续答时效校验：
      //    即使有匹配的 resume 数据，如果距上次保存已超过考试总时长 + 10 分钟缓冲，
      //    视为过期数据（上次考试已结束但 resume 未清理），不恢复 startTime。
      var isTimedMode = this.data.examMode || this.data.assessmentMode;
      var isStale = false;
      if (isTimedMode && this.data.timeLimit > 0) {
        var maxAgeMs = (this.data.timeLimit * 60 + 600) * 1000; // 总时长 + 10分钟
        isStale = resume.startTime && (Date.now() - resume.startTime > maxAgeMs);
      }
      if (!isStale) {
        userAnswers = resume.answers;
        resumeIndex = resume.currentIndex || 0;
        resumeStartTime = resume.startTime || 0;
      } else {
        // 过期续答数据：清除并重新开始
        this.clearResumePosition();
      }
    }

    // ⚠️ 修复：初始进度基于已答题数，而非题目序号
    var initAnswered = 0;
    for (var ai2 = 0; ai2 < userAnswers.length; ai2++) {
      if ((userAnswers[ai2] || []).length > 0) initAnswered++;
    }
    var percent = questions.length > 0 ? Math.round((initAnswered / questions.length) * 100) : 0;

    this.setData({
      questions: questions,
      total: questions.length,
      userAnswers: userAnswers,
      loading: false,
      showAnswer: isMemorize,
      percent: percent,
      cardRevealed: false,
      // 续考时回写原始 startTime，保证交卷时 duration 准确
      startTime: resumeStartTime || this.data.startTime
    });
    // 答题卡全量构建：断点续答后的「已答/未答（及对错）」状态与图例计数一并还原
    this.setData(this.buildAnswerCard(userAnswers, resumeIndex, questions));
    this.showQuestion(resumeIndex);

    if ((this.data.examMode || this.data.assessmentMode) && this.data.timeLimit > 0) {
      var totalSeconds = this.data.timeLimit * 60;
      // ⚠️ P0 修复（倒计时 1 秒归零 Bug）：
      //    原实现 `resume ? Math.floor((Date.now() - resume.startTime) / 1000) : 0`
      //    直接读原始 resume 对象 —— 但 resume 可能是【上一次同科目考试】的残留数据，
      //    其 startTime 远早于本次考试（几小时甚至几天前）→ elapsed 巨大 → remaining=0
      //    → 定时器第一次 tick(1秒后) 即触发 remaining<=0 → 自动交卷。
      //
      //    正确做法：用上方 setData 已正确设置的 this.data.startTime —— 它只在
      //    resume.answers.length === questions.length（本次题目数匹配）时才采用 resume.startTime，
      //    否则保持 onLoad 的 Date.now()，杜绝跨场次串扰。
      var elapsed = Math.floor((Date.now() - this.data.startTime) / 1000);
      var remaining = Math.max(0, totalSeconds - elapsed);
      this.setData({ remainingSeconds: remaining });
      this.updateTimeDisplay();
      if (remaining > 0) {
        this.startTimer();
      } else {
        // 续考场景：上次离开时时间已耗尽，直接交卷（不再等 1 秒定时器）
        var that = this;
        wx.showModal({
          title: '时间到',
          content: '考试时间已结束，系统将自动交卷',
          showCancel: false,
          success: function () { that.submitExam(); }
        });
      }
    }
  },

  // ===== 模拟考试倒计时 =====
  startTimer: function () {
    var that = this;
    if (this._timer) {
      clearInterval(this._timer);
    }
    this._timer = setInterval(function () {
      var remaining = that.data.remainingSeconds - 1;
      if (remaining < 0) {
        // remaining 已到 0 并显示了 00:00，再 tick 一次才触发交卷
        clearInterval(that._timer);
        that._timer = null;
        that.setData({ remainingSeconds: 0 });
        that.updateTimeDisplay();
        wx.showModal({
          title: '时间到',
          content: '考试时间已结束，系统将自动交卷',
          showCancel: false,
          success: function () {
            that.submitExam();
          }
        });
        return;
      }
      that.setData({ remainingSeconds: remaining });
      that.updateTimeDisplay();
    }, 1000);
  },

  updateTimeDisplay: function () {
    var sec = this.data.remainingSeconds;
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    var s = sec % 60;
    var display = '';
    if (h > 0) {
      display = h + ':' + this.pad(m) + ':' + this.pad(s);
    } else {
      display = this.pad(m) + ':' + this.pad(s);
    }
    this.setData({ timeDisplay: display });
  },

  pad: function (n) {
    return n < 10 ? '0' + n : '' + n;
  },

  showQuestion: function (index) {
    var questions = this.data.questions;
    if (index < 0 || index >= questions.length) return;

    var question = questions[index];
    var that = this;

    var options = (question.options || []).map(function (opt) {
      return {
        code: judge.normalizeCode(opt.code),
        content: opt.content || opt.text || '',
        value: judge.isCorrectOption(opt) ? 1 : 0,
        selected: false,
        isCorrect: judge.isCorrectOption(opt)
      };
    });

    var userAnswer = this.data.userAnswers[index] || [];
    var hasAnswered = userAnswer.length > 0;
    if (hasAnswered) {
      var myCodes = judge.normalizeCodes(userAnswer);
      options.forEach(function (opt) {
        if (myCodes.indexOf(opt.code) > -1) {
          opt.selected = true;
        }
      });
    }

    // ⚠️ 修复：进度条百分比基于「已答题数」而非「当前题号」，确保单调递增
    //    原实现 `(index + 1) / total * 100` —— 返回上一题时 percent 回退（如 80%→10%）
    //    正确做法：已答题数 / 总题数，仅回答新题时增长，翻页不回退
    var answeredNum = 0;
    for (var ai = 0; ai < questions.length; ai++) {
      if ((this.data.userAnswers[ai] || []).length > 0) answeredNum++;
    }
    var percent = Math.round((answeredNum / questions.length) * 100);

    var btnText = '下一题';
    if (index === questions.length - 1) {
      btnText = this.data.unifiedMode ? '交卷' : (this.data.mode === 'memorize' ? '完成' : '提交');
    }

    var diffMap = { 1: '简单', 2: '中等', 3: '困难' };
    var qtypeMap = { single: '单选题', multiple: '多选题', judge: '判断题', fill: '填空题', qa: '问答题' };
    var difficultyLabel = diffMap[question.difficulty] || '普通';
    var qtypeLabel = qtypeMap[question.qtype] || qtypeMap[question.type] || '单选题';

    // 普通答题模式才显示即时反馈，考试模式不显示
    var instantResult = false;
    var instantCorrect = false;
    if (this.data.mode === 'answer' && hasAnswered && !this.data.unifiedMode) {
      instantResult = true;
      instantCorrect = judge.judgeAnswer(question, userAnswer);
    }

    // ===== 计算回答结果展示信息 =====
    // 统一走 judge 模块：标准答案、用户作答、判定结论三者同源，杜绝展示与判定不一致
    var correctAnswerText = judge.getCorrectCodes(question).join('、');
    var myAnswerText = judge.describeAnswer(question, userAnswer);
    var resultLabel = '';
    var resultClass = '';
    if (hasAnswered) {
      var isRight = judge.judgeAnswer(question, userAnswer);
      resultLabel = isRight ? '正确' : '错误';
      resultClass = isRight ? 'result-right' : 'result-wrong';
    }
    var kpTags = question.knowledgePointNames || [];

    // ⚠️ 优化：进度条数据单独 setData，与题目内容解耦
    //    避免进度条随 showQuestion 的大 setData 一起重渲染（20+ 字段）
    this.setData({ percent: percent });

    this.setData({
      currentIndex: index,
      question: question,
      options: options,
      btnText: btnText,
      answered: hasAnswered,
      showExplanation: this.data.mode === 'memorize' ? true : (instantResult ? true : false),
      isFavorited: false,
      showFeedback: false,
      feedbackText: '',
      instantResult: instantResult,
      instantCorrect: instantCorrect,
      myAnswerText: myAnswerText,
      correctAnswerText: correctAnswerText,
      resultLabel: resultLabel,
      resultClass: resultClass,
      qtypeLabel: qtypeLabel,
      difficultyLabel: difficultyLabel,
      kpTags: kpTags,
      questionStats: { totalAttempts: 0, correctRate: 0 },
      // 切题时重置 AI 解析状态（新题需重新加载）
      aiAnalysisData: null,
      aiAnalysisNodes: [],
      aiAnalysisDisplay: null,
      aiAnalysisLoading: false,
      aiAnalysisError: '',
      showAiAnalysis: false,
      aiAnalysisCached: false
    });
    // 答题卡：全量重建（当前题高亮 + 各题 正确/错误/未答 标识 + 图例计数一次算齐）
    this.setData(this.buildAnswerCard(this.data.userAnswers, index));

    this.checkFavorite(question._id);
    this.loadQuestionStats(question._id);
  },

  toggleExplanation: function () {
    this.setData({ showExplanation: !this.data.showExplanation });
  },

  // ===== 全站题目统计（作答次数 + 正确率） =====
  // ⚠️ 修复：原实现走 db.collection('historys')，但 historys 属于服务端 PRIVATE_COLLECTIONS，
  //    GET 时按 X-Openid 过滤，只能拿到「本人」的记录，永远统计不出「全站」数据
  //    （新用户更是恒为 0 次 / 0%）。改为调用全量聚合接口 /api/question-stats/，
  //    与 /api/ranking/ 同属需跨用户聚合的专用接口。
  loadQuestionStats: function (questionId) {
    var that = this;
    if (!questionId) return;

    api.getQuestionStats(questionId).then(function (res) {
      var data = (res && res.data) ? res.data : (res || {});
      if (that.data.question && that.data.question._id === questionId) {
        that.setData({
          questionStats: {
            totalAttempts: data.totalAttempts || 0,
            correctRate: data.correctRate || 0
          }
        });
      }
    }, function (err) {
      console.error('[exam] loadQuestionStats fail', err);
      if (that.data.question && that.data.question._id === questionId) {
        that.setData({ questionStats: { totalAttempts: 0, correctRate: 0 } });
      }
    });
  },

  // ===== 收藏 =====
  checkFavorite: function (questionId) {
    var that = this;
    var openid = wx.getStorageSync('openid');
    if (!openid || !questionId) return;

    var db = api.database();
    db.collection('favorites').where({ _openid: openid, questionId: questionId }).get({
      success: function (res) {
        var isFav = (res.data || []).length > 0;
        that.setData({ isFavorited: isFav });
      },
      fail: function () {
        that.setData({ isFavorited: false });
      }
    });
  },

  toggleFavorite: function () {
    var that = this;
    var openid = wx.getStorageSync('openid');
    var question = this.data.question;
    if (!openid) {
      wx.showToast({ icon: 'none', title: '请先登录' });
      return;
    }

    var db = api.database();
    if (this.data.isFavorited) {
      db.collection('favorites').where({ _openid: openid, questionId: question._id }).get({
        success: function (res) {
          var docs = res.data || [];
          if (docs.length > 0) {
            wx.request({
              url: api.API_BASE + '/collections/favorites/' + docs[0]._id + '/',
              method: 'DELETE',
              header: { 'Content-Type': 'application/json', 'X-Openid': openid },
              success: function () {
                that.setData({ isFavorited: false });
                wx.showToast({ icon: 'none', title: '已取消收藏' });
              },
              fail: function () {
                wx.showToast({ icon: 'none', title: '操作失败' });
              }
            });
          } else {
            that.setData({ isFavorited: false });
          }
        }
      });
    } else {
      db.collection('favorites').add({
        data: {
          favType: 'question',
          questionId: question._id,
          questionTitle: question.title,
          examid: question.examid,
          qtype: question.qtype,
          difficulty: question.difficulty,
          createTime: util.getTime(new Date())
        },
        success: function () {
          that.setData({ isFavorited: true });
          wx.showToast({ icon: 'none', title: '已收藏' });
        },
        fail: function () {
          wx.showToast({ icon: 'none', title: '收藏失败' });
        }
      });
    }
  },

  // ===== 答题卡 =====
  // 是否允许在答题卡上揭示「正确/错误」：
  //   · 答题模式(answer)非统一交卷 → 逐题即时判分，天然可揭示
  //   · 模拟考试 / 统一交卷测评 → 交卷前只显示「已答/未答」，避免泄漏答案
  canRevealResult: function () {
    if (this.data.cardRevealed) return true;
    return this.data.mode === 'answer' && !this.data.unifiedMode;
  },

  /**
   * 构建答题卡数据（唯一实现）
   *
   * ⚠️ 采用「全量重建」而非「就地改一格」：
   *    原实现 `this.data.answerCard.slice()` 是浅拷贝，随后 `card.status = 'answered'`
   *    实际改的是 this.data 里的同一个对象（setData 前就先污染了状态），且无法表达
   *    「由答对改答错」这类状态回退。全量重建既杜绝状态漂移，又顺带算出图例计数。
   *
   * @param {Array}   userAnswers    作答数组（默认取 this.data.userAnswers）
   * @param {Number}  currentIndex   当前题下标
   * @param {Array}   questions      题目数组（默认取 this.data.questions）
   * @param {Boolean} reveal         是否揭示对错（默认按 canRevealResult 推断）
   * @returns {Object} 可直接并入 setData 的补丁对象
   */
  buildAnswerCard: function (userAnswers, currentIndex, questions, reveal) {
    var answers = userAnswers || this.data.userAnswers || [];
    var qs = questions || this.data.questions || [];
    var cur = (currentIndex === undefined || currentIndex === null) ? this.data.currentIndex : currentIndex;
    var canReveal = (reveal === undefined || reveal === null) ? this.canRevealResult() : !!reveal;

    var correctCount = 0;
    var wrongCount = 0;
    var answeredCount = 0;
    var card = qs.map(function (q, i) {
      var ans = answers[i] || [];
      var status = judge.resolveStatus(q, ans, canReveal);
      if (status === 'correct') correctCount++;
      else if (status === 'wrong') wrongCount++;
      if (ans.length > 0) answeredCount++;
      return {
        index: i,
        qid: q._id,
        status: status,
        mark: judge.statusMark(status),
        isCurrent: i === cur
      };
    });

    return {
      answerCard: card,
      correctCount: correctCount,
      wrongCount: wrongCount,
      answeredCount: answeredCount,
      // 图例沿用同一个 canReveal，避免格子与图例对"是否揭示对错"判断不一致
      cardLegend: this.buildCardLegend(answeredCount, correctCount, wrongCount, canReveal)
    };
  },

  /**
   * 图例：与格子配色同源，避免「图例说蓝=已答、单元格却用蓝表示对」这类不一致
   * 未揭示对错时不展示「正确/错误」图例，否则会误导用户
   */
  buildCardLegend: function (answeredCount, correctCount, wrongCount, reveal) {
    var total = this.data.total || 0;
    var unanswered = Math.max(0, total - answeredCount);
    var canReveal = (reveal === undefined || reveal === null) ? this.canRevealResult() : !!reveal;
    if (canReveal) {
      return [
        { type: 'correct', label: '正确', count: correctCount },
        { type: 'wrong', label: '错误', count: wrongCount },
        { type: 'unanswered', label: '未答', count: unanswered }
      ];
    }
    return [
      { type: 'answered', label: '已答', count: answeredCount },
      { type: 'unanswered', label: '未答', count: unanswered }
    ];
  },

  toggleAnswerCard: function () {
    if (this.data.showCard) {
      this.setData({ showCard: false });
      return;
    }
    // 打开时刷新一次，防止与最新作答状态脱节
    var patch = this.buildAnswerCard();
    patch.showCard = true;
    this.setData(patch);
  },

  closeAnswerCard: function (e) {
    if (e && e.target && e.currentTarget && e.target !== e.currentTarget) return;
    this.setData({ showCard: false });
  },

  cardJump: function (e) {
    var index = e.currentTarget.dataset.index;
    if (index === undefined) return;
    this.setData({ showCard: false });
    this.showQuestion(parseInt(index));
  },

  // ===== 断点续答 =====
  saveResumePosition: function () {
    // ⚠️ 交卷后不再保存续答数据（双重保险）
    if (this._examSubmitted) return;
    if (this.data.total === 0) return;
    var resume = {
      currentIndex: this.data.currentIndex,
      answers: this.data.userAnswers,
      mode: this.data.mode,
      subjectId: this.data.subjectId,
      startTime: this.data.startTime
    };
    wx.setStorageSync(this.data.resumeKey, resume);
  },

  clearResumePosition: function () {
    wx.removeStorageSync(this.data.resumeKey);
  },

  // ===== 选项选择 =====
  selectOption: function (e) {
    if (this.data.mode === 'memorize') return;

    // ⚠️ dataset 取值兜底：WXML 的 data-code 若形如 "1"/"2"（纯数字编号），
    //    微信会把 dataset 值转成 Number，而 opt.code 是 String，
    //    严格比较 `opt.code === code` 会失败 → 点击无反应/选项选不中。此处统一转字符串。
    var code = judge.normalizeCode(e.currentTarget.dataset.code);
    var qtype = this.data.question.qtype || 'single';
    var options = this.data.options.slice();

    if (qtype === 'multiple') {
      options.forEach(function (opt) {
        if (opt.code === code) {
          opt.selected = !opt.selected;
        }
      });
    } else {
      options.forEach(function (opt) {
        opt.selected = (opt.code === code);
      });
    }

    var userAnswer = judge.normalizeCodes(options.filter(function (opt) { return opt.selected; }).map(function (opt) { return opt.code; }));
    var userAnswers = this.data.userAnswers.slice();
    userAnswers[this.data.currentIndex] = userAnswer;

    // 答题卡：本次作答后立即重建 → 题号颜色与角标实时跟随（含「答对改答错」的状态回退）
    var cardPatch = this.buildAnswerCard(userAnswers, this.data.currentIndex);

    // 普通答题模式: 即时反馈；考试模式: 仅记录，不显示对错
    // ⚠️ P0 修复（判题时序 Bug）：
    //    旧实现此处调用 this.checkAnswer(this.data.currentIndex)，而 checkAnswer 读取的是
    //    this.data.userAnswers —— 该值需等下方 setData 才会写入，因此判题读到的是「上一次」的作答：
    //      · 首次作答该题 → this.data.userAnswers[idx] 为 undefined → 一律判「错误」
    //      · 再次作答      → 用上一次的选择判题 → 判定结果整体滞后一轮
    //    这正是「我的答案 B / 正确答案 B / 判定错误」的根因（展示用的是新值，判题用的是旧值）。
    //    修复：判题改用上面刚算出的 userAnswer 局部变量，纯函数、不依赖 this.data。
    var instantResult = false;
    var instantCorrect = false;
    var showExplanation = false;
    if (this.data.mode === 'answer' && userAnswer.length > 0 && !this.data.unifiedMode) {
      instantResult = true;
      instantCorrect = judge.judgeAnswer(this.data.questions[this.data.currentIndex], userAnswer);
      showExplanation = true;
      if (this.data.autoNext && instantCorrect) {
        var that = this;
        setTimeout(function () {
          that.goNext();
        }, 800);
      }
    }

    // 更新回答结果展示（与判题共用同一份 userAnswer，保证两者永不矛盾）
    var myAnswerText = judge.describeAnswer(this.data.question, userAnswer);
    var resultLabel = '';
    var resultClass = '';
    if (instantResult) {
      resultLabel = instantCorrect ? '正确' : '错误';
      resultClass = instantCorrect ? 'result-right' : 'result-wrong';
    }

    cardPatch.options = options;
    cardPatch.userAnswers = userAnswers;
    cardPatch.answered = userAnswer.length > 0;
    cardPatch.instantResult = instantResult;
    cardPatch.instantCorrect = instantCorrect;
    cardPatch.showExplanation = showExplanation;
    cardPatch.myAnswerText = myAnswerText;
    cardPatch.resultLabel = resultLabel;
    cardPatch.resultClass = resultClass;
    // ⚠️ 修复：答题后同步更新进度条百分比（基于已答题数）
    //    buildAnswerCard 返回的 cardPatch 已含 answeredCount，据此更新 percent
    var newAnswered = cardPatch.answeredCount || 0;
    var newTotal = this.data.total || 1;
    cardPatch.percent = Math.round((newAnswered / newTotal) * 100);
    this.setData(cardPatch);

    this.saveResumePosition();
  },

  // ===== 导航 =====
  goPrev: function () {
    if (this.data.currentIndex === 0) {
      wx.showToast({ icon: 'none', title: '已经是第一题' });
      return;
    }
    this.showQuestion(this.data.currentIndex - 1);
  },

  goNext: function () {
    var that = this;
    var index = this.data.currentIndex;
    var total = this.data.total;

    if (this.data.mode === 'memorize') {
      if (index >= total - 1) {
        this.clearResumePosition();
        wx.navigateBack();
        return;
      }
      this.showQuestion(index + 1);
      return;
    }

    // 统一交卷模式(examMode 或 assessmentMode+unified): 仅翻页，不逐题判分
    if (this.data.unifiedMode) {
      if (index >= total - 1) {
        this.confirmSubmitExam();
        return;
      }
      this.showQuestion(index + 1);
      return;
    }

    // 普通答题模式: 逐题判分
    if (!this.data.answered) {
      wx.showToast({ icon: 'none', title: '请先选择答案' });
      return;
    }

    var isRight = this.checkAnswer(index);
    var rightNum = this.data.rightNum;
    var errNum = this.data.errNum;

    if (isRight) {
      rightNum++;
    } else {
      errNum++;
      this.addNote(index);
    }

    if (index >= total - 1) {
      this.setData({ rightNum: rightNum, errNum: errNum }, function () {
        that._examSubmitted = true;  // 阻止 onUnload 再次保存续答
        that.clearResumePosition();
        if (that.data.assessmentMode) {
          var duration = Math.floor((Date.now() - that.data.startTime) / 1000);
          var score = that.data.total ? Math.round(rightNum / that.data.total * 100) : 0;
          that.saveAssessment(rightNum, errNum, duration, score);
          that.addHistory(false, duration, score, true);
          var url = '/pages/examresult/examresult?length=' + that.data.total +
            '&errNum=' + errNum + '&rightNum=' + rightNum +
            '&ordernum=' + that.data.ordernum +
            '&assessmentMode=true&duration=' + duration + '&score=' + score;
          wx.redirectTo({ url: url });
        } else {
          that.addHistory();
          that.goResult();
        }
      });
      return;
    }

    this.setData({ rightNum: rightNum, errNum: errNum });
    this.showQuestion(index + 1);
  },

  // ===== 模拟考试: 统一交卷 =====
  confirmSubmitExam: function () {
    var that = this;
    var unanswered = this.data.total - this.data.answeredCount;
    var content = '共 ' + this.data.total + ' 题，已答 ' + this.data.answeredCount + ' 题';
    if (unanswered > 0) {
      content += '，未答 ' + unanswered + ' 题将计为错误';
    }
    content += '。确认交卷吗？';

    wx.showModal({
      title: '确认交卷',
      content: content,
      success: function (res) {
        if (res.confirm) {
          that.submitExam();
        }
      }
    });
  },

  submitExam: function () {
    var that = this;

    // ⚠️ 标记已交卷，阻止 onHide/onUnload 再次 saveResumePosition
    //    （否则 clearResumePosition 后 onUnload 又把过期 startTime 写回 storage）
    this._examSubmitted = true;

    // 停止计时器
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }

    // 统一判分
    var rightNum = 0;
    var errNum = 0;
    var wrongIndices = [];
    this.data.questions.forEach(function (question, index) {
      var isRight = that.checkAnswer(index);
      if (isRight) {
        rightNum++;
      } else {
        errNum++;
        wrongIndices.push(index);
      }
    });

    // 串行保存错题笔记（错峰写入，避免并发 POST 导致 SQLite database is locked）
    // 每条笔记间隔 150ms，配合后端 WAL + busy_timeout 双重保险
    wrongIndices.forEach(function (idx, i) {
      setTimeout(function () {
        that.addNote(idx);
      }, i * 150);
    });

    var duration = Math.floor((Date.now() - this.data.startTime) / 1000);
    var score = this.data.total ? Math.round(rightNum / this.data.total * 100) : 0;

    // 交卷后揭示对错 → 答题卡同步由「已答/未答」切换为「正确/错误」标识
    this.setData({ rightNum: rightNum, errNum: errNum, cardRevealed: true, percent: 100 });
    this.setData(this.buildAnswerCard());
    this.clearResumePosition();

    // 清除考试模式标记
    wx.removeStorageSync('quiz_exam_mode');
    wx.removeStorageSync('quiz_time_limit');

    // 保存历史记录
    if (this.data.assessmentMode) {
      this.saveAssessment(rightNum, errNum, duration, score);
      this.addHistory(false, duration, score, true);
    } else {
      this.addHistory(true, duration, score);
    }

    // 跳转成绩页
    var url = '/pages/examresult/examresult?length=' + this.data.total +
      '&errNum=' + errNum +
      '&rightNum=' + rightNum +
      '&ordernum=' + this.data.ordernum;
    if (this.data.assessmentMode) {
      url += '&assessmentMode=true&duration=' + duration + '&score=' + score;
    } else {
      url += '&examMode=true&duration=' + duration + '&score=' + score;
    }
    wx.redirectTo({ url: url });
  },

  // 判题：读取已提交的作答结果（index 题的 this.data.userAnswers）
  // 注意：本方法依赖 this.data，必须在 setData 之后调用；
  //       答题交互链路请改用 judge.judgeAnswer(question, userAnswer) 传入新值，避免时序问题。
  checkAnswer: function (index) {
    var question = this.data.questions[index];
    var userAnswer = this.data.userAnswers[index] || [];
    return judge.judgeAnswer(question, userAnswer);
  },

  addNote: function (index, _retryCount) {
    var that = this;
    var question = this.data.questions[index];
    var openid = wx.getStorageSync('openid');
    if (!openid) return;

    var db = api.database();
    var questionId = question._id;
    var retryCount = _retryCount || 0;
    var MAX_RETRY = 2;

    // 去重: 先查询是否已有同 questionId 的未解决记录
    db.collection('notes').where({ _openid: openid, questionId: questionId, resolved: false }).get({
      success: function (res) {
        var existing = res.data || [];
        if (existing.length > 0) {
          // 已有未解决记录: 更新 retryCount（走 api 层，带 ensureOpenid）
          var existingNote = existing[0];
          var retryCountVal = (existingNote.retryCount || 0) + 1;
          var updateData = {
            retryCount: retryCountVal,
            lastRetryTime: util.getTime(new Date()),
            userAnswer: that.data.userAnswers[index],
            ordernum: that.data.ordernum
          };
          db.collection('notes').doc(existingNote._id).update({
            data: updateData,
            success: function () {
              console.log('[exam] addNote dedup update success');
            },
            fail: function (err) {
              console.error('[exam] addNote dedup update fail', err);
              // 服务器错误(500)时重试一次，不阻断考试流程
              if (retryCount < MAX_RETRY && err && err.statusCode >= 500) {
                setTimeout(function () {
                  that.addNote(index, retryCount + 1);
                }, 300 * (retryCount + 1));
              }
            }
          });
        } else {
          // 无未解决记录: 新增
          // ⚠️ 必须传唯一 _id：后端 update_or_create 按 (collection, doc_id) 查重，
          //    若 _id 缺失 → doc_id=None → 多条 note 覆写同一条（只剩 1 条错题）
          var noteId = 'NOTE_' + util.formatTime(new Date()) + '_' + String(questionId).replace(/[^a-zA-Z0-9]/g, '') + '_' + Math.random().toString(36).substr(2, 6);
          db.collection('notes').add({
            data: {
              _id: noteId,
              ordernum: that.data.ordernum,
              questionId: questionId,
              question: question,
              options: question.options,
              userAnswer: that.data.userAnswers[index],
              resolved: false,
              retryCount: 0,
              createTime: util.getTime(new Date())
            },
            success: function (res) {
              console.log('[exam] addNote new success', res._id);
            },
            fail: function (err) {
              console.error('[exam] addNote new fail', err);
              // 服务器错误(500)时重试，不阻断考试流程
              if (retryCount < MAX_RETRY && err && err.statusCode >= 500) {
                setTimeout(function () {
                  that.addNote(index, retryCount + 1);
                }, 300 * (retryCount + 1));
              }
            }
          });
        }
      },
      fail: function (err) {
        console.error('[exam] addNote query fail', err);
        // 查询失败降级: 直接新增（同样需要唯一 _id）
        var noteId = 'NOTE_' + util.formatTime(new Date()) + '_' + String(questionId).replace(/[^a-zA-Z0-9]/g, '') + '_' + Math.random().toString(36).substr(2, 6);
        db.collection('notes').add({
          data: {
            _id: noteId,
            ordernum: that.data.ordernum,
            questionId: questionId,
            question: question,
            options: question.options,
            userAnswer: that.data.userAnswers[index],
            resolved: false,
            retryCount: 0,
            createTime: util.getTime(new Date())
          },
          success: function () {
            console.log('[exam] addNote fallback new success');
          },
          fail: function (err2) {
            console.error('[exam] addNote fallback new fail', err2);
            // 最终失败不阻断考试流程，仅记录日志
          }
        });
      }
    });
  },

  addHistory: function (isExam, duration, score, isAssessment) {
    var subject = wx.getStorageSync('subject') || {};
    var db = api.database();
    var items = this.data.questions.map(function (q) { return q._id; });

    var data = {
      _id: this.data.ordernum,
      subject: subject,
      items: items,
      rightNum: this.data.rightNum,
      nums: this.data.total,
      score_arr: this.data.userAnswers,
      createTime: util.getTime(new Date())
    };

    if (isExam) {
      data.examMode = true;
      data.duration = duration || 0;
      data.score = score || 0;
    }

    if (isAssessment) {
      data.assessmentMode = true;
      data.assessmentId = this.data.ordernum;
      data.duration = duration || 0;
      data.score = score || 0;
      var config = wx.getStorageSync('quiz_assessment_config');
      if (config) {
        data.assessmentConfig = config;
      }
    }

    db.collection('historys').add({
      data: data,
      success: function (res) {
        console.log('[exam] addHistory success', res._id);
      },
      fail: function (err) {
        console.error('[exam] addHistory fail', err);
        // 服务器错误(500)时延迟重试一次，不阻断交卷跳转
        if (err && err.statusCode >= 500) {
          setTimeout(function () {
            db.collection('historys').add({
              data: data,
              success: function () { console.log('[exam] addHistory retry success'); },
              fail: function (err2) { console.error('[exam] addHistory retry fail', err2); }
            });
          }, 500);
        }
      }
    });
  },

  // ===== 自我测评: 多维度统计与保存 =====
  saveAssessment: function (rightNum, errNum, duration, score) {
    var that = this;
    var db = api.database();
    var questions = this.data.questions;
    var total = questions.length;

    // 按题型统计
    var byQtype = {};
    // 按难度统计
    var byDifficulty = {};
    // 按章节统计
    var byChapterMap = {};
    // 按知识点统计
    var byKpMap = {};

    questions.forEach(function (q, index) {
      var isRight = that.checkAnswer(index);
      var qt = q.qtype || q.type || 'single';
      var diff = String(q.difficulty || 2);
      var chId = q.examid || q.chapter || '';
      var kpIds = q.knowledgePointIds || [];
      var kpNames = q.knowledgePointNames || [];

      // byQtype
      if (!byQtype[qt]) byQtype[qt] = { total: 0, right: 0 };
      byQtype[qt].total++;
      if (isRight) byQtype[qt].right++;

      // byDifficulty
      if (!byDifficulty[diff]) byDifficulty[diff] = { total: 0, right: 0 };
      byDifficulty[diff].total++;
      if (isRight) byDifficulty[diff].right++;

      // byChapter
      if (!byChapterMap[chId]) byChapterMap[chId] = { total: 0, right: 0, name: '' };
      byChapterMap[chId].total++;
      if (isRight) byChapterMap[chId].right++;

      // byKnowledgePoint
      kpIds.forEach(function (kpId, kpIdx) {
        var kpName = kpNames[kpIdx] || '';
        if (!byKpMap[kpId]) byKpMap[kpId] = { total: 0, right: 0, name: kpName };
        byKpMap[kpId].total++;
        if (isRight) byKpMap[kpId].right++;
      });
    });

    // 格式化统计结果
    var byQtypeResult = {};
    Object.keys(byQtype).forEach(function (qt) {
      var s = byQtype[qt];
      byQtypeResult[qt] = { total: s.total, right: s.right, rate: s.total ? Math.round(s.right / s.total * 100) : 0 };
    });

    var byDifficultyResult = {};
    Object.keys(byDifficulty).forEach(function (d) {
      var s = byDifficulty[d];
      byDifficultyResult[d] = { total: s.total, right: s.right, rate: s.total ? Math.round(s.right / s.total * 100) : 0 };
    });

    var byChapterResult = Object.keys(byChapterMap).map(function (chId) {
      var s = byChapterMap[chId];
      return { chapterId: chId, total: s.total, right: s.right, rate: s.total ? Math.round(s.right / s.total * 100) : 0 };
    });

    var byKpResult = Object.keys(byKpMap).map(function (kpId) {
      var s = byKpMap[kpId];
      var rate = s.total ? Math.round(s.right / s.total * 100) : 0;
      return { kpId: kpId, kpName: s.name, total: s.total, right: s.right, rate: rate };
    });

    // 薄弱知识点: 答对率 < 60%
    var weakPoints = byKpResult.filter(function (kp) { return kp.rate < 60; }).map(function (kp) { return kp.kpId; });

    // 生成建议
    var suggestion = '';
    if (weakPoints.length > 0) {
      var weakNames = byKpResult.filter(function (kp) { return kp.rate < 60; }).map(function (kp) { return kp.kpName; });
      suggestion = '建议重点复习「' + weakNames.join('、') + '」相关知识点，可使用刷知识点功能针对性练习。';
    } else if (score >= 85) {
      suggestion = '整体掌握度优秀，建议尝试更高难度的测评或进行模拟考试。';
    } else {
      suggestion = '整体掌握度良好，建议继续练习巩固薄弱环节。';
    }

    var config = wx.getStorageSync('quiz_assessment_config') || {};
    var examId = this.data.subjectId || '';
    var examName = '';
    var examList = wx.getStorageSync('home_exam_list') || [];
    examList.forEach(function (e) { if (e._id === examId) examName = e.name; });

    var assessmentData = {
      _id: this.data.ordernum,
      _openid: wx.getStorageSync('openid') || '',
      examId: examId,
      examName: examName,
      config: config,
      questionIds: questions.map(function (q) { return q._id; }),
      answers: {},
      results: {
        total: total,
        rightNum: rightNum,
        errNum: errNum,
        score: score,
        duration: duration,
        byQtype: byQtypeResult,
        byDifficulty: byDifficultyResult,
        byChapter: byChapterResult,
        byKnowledgePoint: byKpResult,
        weakPoints: weakPoints,
        suggestion: suggestion
      },
      createTime: util.getTime(new Date())
    };

    // 填充 answers
    var answers = {};
    questions.forEach(function (q, index) {
      answers[q._id] = that.data.userAnswers[index] || [];
    });
    assessmentData.answers = answers;

    db.collection('assessments').add({
      data: assessmentData,
      success: function (res) {
        console.log('[exam] saveAssessment success', res._id);
        wx.removeStorageSync('quiz_assessment_config');
      },
      fail: function (err) {
        console.error('[exam] saveAssessment fail', err);
      }
    });
  },

  goResult: function () {
    var url = '/pages/examresult/examresult?length=' + this.data.total +
      '&errNum=' + this.data.errNum +
      '&rightNum=' + this.data.rightNum +
      '&ordernum=' + this.data.ordernum;
    wx.redirectTo({ url: url });
  },

  // ===== 题目反馈 =====
  toggleFeedback: function () {
    this.setData({ showFeedback: !this.data.showFeedback });
  },

  onFeedbackInput: function (e) {
    this.setData({ feedbackText: e.detail.value });
  },

  submitFeedback: function () {
    var that = this;
    var text = this.data.feedbackText.trim();
    if (!text) {
      wx.showToast({ icon: 'none', title: '请输入反馈内容' });
      return;
    }
    if (text.length > 500) {
      wx.showToast({ icon: 'none', title: '反馈内容不能超过500字' });
      return;
    }

    var openid = wx.getStorageSync('openid');
    var question = this.data.question;
    var db = api.database();

    db.collection('feedback').add({
      data: {
        questionId: question._id,
        questionTitle: question.title,
        examid: question.examid,
        content: text,
        createTime: util.getTime(new Date())
      },
      success: function () {
        wx.showToast({ icon: 'success', title: '反馈已提交' });
        that.setData({ showFeedback: false, feedbackText: '' });
      },
      fail: function () {
        wx.showToast({ icon: 'none', title: '提交失败，请重试' });
      }
    });
  },

  toggleAutoNext: function () {
    var newVal = !this.data.autoNext;
    this.setData({ autoNext: newVal });
    var settings = wx.getStorageSync('quiz_settings') || {};
    settings.autoNext = newVal;
    wx.setStorageSync('quiz_settings', settings);
    wx.showToast({
      icon: 'none',
      title: newVal ? '已开启答对自动跳转' : '已关闭答对自动跳转'
    });
  },

  // ===== AI 解析功能（VIP 专用）=====

  /**
   * 预处理 LaTeX / 特殊符号，转为小程序可读文本
   * AI 返回的 Markdown 常含 $...$ 数学公式，markdown.js 不支持 LaTeX，
   * 这里做轻量转换：
   *   $...$  → 去掉美元符号，保留内容
   *   2^4    → 2⁴ （Unicode 上标）
   *   2_0    → 2₀ （Unicode 下标）
   *   \\( ... \\) / \\[ ... \\] → 去掉定界符
   */
  _preprocessMath: function (text) {
    if (!text || typeof text !== 'string') return '';
    var s = text;
    // 去掉行内 LaTeX 定界符 $...$ 和 \(...\)
    s = s.replace(/\$([^$]+)\$/g, function (_, inner) {
      return inner;
    });
    s = s.replace(/\\\(([^)]+)\\\)/g, function (_, inner) {
      return inner;
    });
    // 去掉块级 LaTeX 定界符 $$...$$ 和 \[...\]
    s = s.replace(/\$\$([^$]+)\$\$/g, function (_, inner) {
      return inner;
    });
    s = s.replace(/\\\[([^\]]+)\\\]/g, function (_, inner) {
      return inner;
    });
    // 上标转换：x^{n} → xⁿ，x^n → xⁿ
    var supMap = { '0': '\u2070', '1': '\u00B9', '2': '\u00B2', '3': '\u00B3', '4': '\u2074', '5': '\u2075', '6': '\u2076', '7': '\u2077', '8': '\u2078', '9': '\u2079', '+': '\u207A', '-': '\u207B', '=': '\u207C', '(': '\u207D', ')': '\u207E' };
    s = s.replace(/\^{([^}]+)}/g, function (_, inner) {
      return inner.split('').map(function (c) { return supMap[c] || c; }).join('');
    });
    s = s.replace(/\^(\d)/g, function (_, d) {
      return supMap[d] || ('^' + d);
    });
    // 下标转换：x_{n} → xₙ
    var subMap = { '0': '\u2080', '1': '\u2081', '2': '\u2082', '3': '\u2083', '4': '\u2084', '5': '\u2085', '6': '\u2086', '7': '\u2087', '8': '\u2088', '9': '\u2089' };
    s = s.replace(/_{([^}]+)}/g, function (_, inner) {
      return inner.split('').map(function (c) { return subMap[c] || c; }).join('');
    });
    s = s.replace(/_(\d)/g, function (_, d) {
      return subMap[d] || ('_' + d);
    });
    // \times → ×，\div → ÷，\leq → ≤，\geq → ≥，\neq → ≠
    s = s.replace(/\\times/g, '\u00D7').replace(/\\div/g, '\u00F7');
    s = s.replace(/\\leq/g, '\u2264').replace(/\\geq/g, '\u2265').replace(/\\neq/g, '\u2260');
    // \frac{a}{b} → a/b
    s = s.replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, function (_, a, b) {
      return a + '/' + b;
    });
    // \sqrt{x} → √x
    s = s.replace(/\\sqrt\{([^}]+)\}/g, function (_, x) {
      return '\u221A' + x;
    });
    return s;
  },

  /**
   * 将 AI 解析结果转为前端展示用的结构化数据 + rich-text nodes
   * 适配后端 QuestionAnalysisService 返回的字段：
   *   knowledge_points[]  → 知识点标签列表
   *   difficulty / difficulty_score → 难度信息
   *   qtype_detected      → 识别题型
   *   answer_analysis_md  → Markdown 答案解析（主内容，需 rich-text 渲染）
   *   key_concepts[]      → 核心概念列表
   *   common_mistakes[]   → 常见错误列表
   *   suggested_tags[]    → 推荐标签列表
   */
  _buildAiDisplayData: function (raw) {
    if (!raw || typeof raw !== 'object') return { nodes: [], display: null };
    // 预处理 LaTeX 并解析 Markdown
    var analysisMd = raw.answer_analysis_md || raw.answer_analysis || raw.explanation || raw.content || '';
    analysisMd = this._preprocessMath(analysisMd);
    var nodes = md.parse(analysisMd);

    // 知识点：[{name, confidence}] → 字符串数组
    var knowledgePoints = [];
    if (Array.isArray(raw.knowledge_points)) {
      knowledgePoints = raw.knowledge_points.map(function (kp) {
        return kp.name || kp;
      }).filter(function (n) { return n; });
    }

    // 核心概念
    var keyConcepts = [];
    if (Array.isArray(raw.key_concepts)) {
      keyConcepts = raw.key_concepts.filter(function (c) { return c; });
    }

    // 常见错误
    var commonMistakes = [];
    if (Array.isArray(raw.common_mistakes)) {
      commonMistakes = raw.common_mistakes.filter(function (m) { return m; });
    }

    // 推荐标签
    var suggestedTags = [];
    if (Array.isArray(raw.suggested_tags)) {
      suggestedTags = raw.suggested_tags.map(function (t) {
        return t.name || t;
      }).filter(function (n) { return n; });
    }

    // 难度
    var diffMap = { easy: '简单', medium: '中等', hard: '困难' };
    var difficultyLabel = diffMap[raw.difficulty] || raw.difficulty || '';
    if (raw.difficulty_score) {
      difficultyLabel += ' (' + raw.difficulty_score + '/10)';
    }

    // 识别题型
    var qtypeMap = { single: '单选题', multiple: '多选题', judge: '判断题', fill: '填空题', qa: '问答题', multi_part: '综合题' };
    var qtypeLabel = qtypeMap[raw.qtype_detected] || raw.qtype_detected || '';

    return {
      nodes: nodes,
      display: {
        knowledgePoints: knowledgePoints,
        keyConcepts: keyConcepts,
        commonMistakes: commonMistakes,
        suggestedTags: suggestedTags,
        difficultyLabel: difficultyLabel,
        qtypeLabel: qtypeLabel,
        analysisMd: analysisMd,
        model: raw.model || '',
        analyzedAt: raw.analyzed_at || ''
      }
    };
  },

  /**
   * 加载 VIP 状态
   * 页面初始化时调用，决定 AI 入口的显隐与可用性。
   * 后端通过 profiles 集合的 vip / roles 字段判定。
   */
  loadVipStatus: function () {
    var that = this;
    api.getVipStatus().then(function (res) {
      that.setData({
        isVip: !!(res && res.isVip),
        vipChecked: true
      });
    }, function (err) {
      console.error('[exam] loadVipStatus fail', err);
      // 查询失败默认非 VIP，不阻断答题流程
      that.setData({ isVip: false, vipChecked: true });
    });
  },

  /**
   * 点击「AI解析」入口
   * 非 VIP → 弹出升级引导；VIP → 展开 AI 解析面板并加载/触发解析
   */
  tapAiAnalysis: function () {
    if (!this.data.vipChecked) {
      wx.showToast({ icon: 'none', title: '正在验证权限，请稍候' });
      return;
    }
    if (!this.data.isVip) {
      this.setData({ showVipUpgrade: true });
      return;
    }
    // VIP 用户：切换面板显隐
    if (this.data.showAiAnalysis) {
      this.setData({ showAiAnalysis: false });
      return;
    }
    this.setData({ showAiAnalysis: true });
    // 若已有解析数据且属于当前题，直接展示；否则发起请求
    var qid = this.data.question._id;
    if (this.data.aiAnalysisData && this.data.aiAnalysisData._qid === qid) {
      return;
    }
    this.loadAiAnalysis(qid);
  },

  /**
   * 加载单题 AI 解析（缓存优先策略）
   * 1. 先 GET 查询是否已有缓存解析 → 有则直接展示
   * 2. 无缓存 → POST 触发 AI 生成（后端生成后写入数据库，下次直接复用）
   */
  loadAiAnalysis: function (questionId) {
    var that = this;
    if (!questionId) return;

    this.setData({ aiAnalysisLoading: true, aiAnalysisError: '', aiAnalysisData: null, aiAnalysisNodes: [] });

    // 第一步：查询缓存
    api.aiQuestionAnalysis(questionId).then(function (res) {
      if (res && res.hasAnalysis && res.analysis) {
        // 缓存命中，直接展示
        res.analysis._qid = questionId;
        var built = that._buildAiDisplayData(res.analysis);
        that.setData({
          aiAnalysisData: res.analysis,
          aiAnalysisNodes: built.nodes,
          aiAnalysisDisplay: built.display,
          aiAnalysisLoading: false,
          aiAnalysisCached: true,
          aiAnalysisError: ''
        });
        return;
      }
      // 无缓存，触发 AI 生成
      that.triggerAiAnalysis(questionId);
    }, function (err) {
      console.error('[exam] aiQuestionAnalysis GET fail', err);
      // GET 失败时直接尝试 POST（降级策略，保证可用性）
      that.triggerAiAnalysis(questionId);
    });
  },

  /**
   * 触发单题 AI 解析（POST，后端缓存优先 + LLM 生成）
   */
  triggerAiAnalysis: function (questionId) {
    var that = this;
    this.setData({ aiAnalysisLoading: true, aiAnalysisError: '' });

    api.aiQuestionAnalysisTrigger(questionId).then(function (res) {
      if (res && res.analysis) {
        res.analysis._qid = questionId;
        var built = that._buildAiDisplayData(res.analysis);
        that.setData({
          aiAnalysisData: res.analysis,
          aiAnalysisNodes: built.nodes,
          aiAnalysisDisplay: built.display,
          aiAnalysisLoading: false,
          aiAnalysisCached: !!res.cached,
          aiAnalysisError: ''
        });
      } else {
        that.setData({
          aiAnalysisLoading: false,
          aiAnalysisError: 'AI 解析返回空结果，请稍后重试'
        });
      }
    }, function (err) {
      var msg = 'AI 解析失败，请稍后重试';
      if (err && err.data && err.data.message) {
        msg = err.data.message;
      } else if (err && err.message) {
        msg = err.message;
      }
      // 403 权限不足单独处理
      if (err && err.statusCode === 403) {
        msg = '该功能仅对 VIP 用户开放';
        that.setData({ isVip: false });
      }
      that.setData({
        aiAnalysisLoading: false,
        aiAnalysisError: msg
      });
    });
  },

  /**
   * 重试 AI 解析（解析失败后用户可点击重试）
   */
  retryAiAnalysis: function () {
    var qid = this.data.question._id;
    if (qid) {
      this.triggerAiAnalysis(qid);
    }
  },

  /**
   * 关闭 AI 解析面板
   */
  closeAiAnalysis: function () {
    this.setData({ showAiAnalysis: false });
  },

  // ===== AI 答题分析总结（VIP 专用）=====

  /**
   * 点击「AI分析」入口
   * 非 VIP → 弹出升级引导；VIP → 发起整份作答分析
   */
  tapExamSummary: function () {
    if (!this.data.vipChecked) {
      wx.showToast({ icon: 'none', title: '正在验证权限，请稍候' });
      return;
    }
    if (!this.data.isVip) {
      this.setData({ showVipUpgrade: true });
      return;
    }
    // 至少答 1 题才允许分析
    if (this.data.answeredCount === 0) {
      wx.showToast({ icon: 'none', title: '请先至少作答 1 题再使用分析功能' });
      return;
    }
    this.setData({ showExamSummary: true });
    this.loadExamSummary();
  },

  /**
   * 加载整份作答的 AI 分析总结
   * 将当前答题场的题目 + 作答发送后端，后端按 (openid + 题目集 + 作答) 哈希缓存。
   */
  loadExamSummary: function () {
    var that = this;
    var questions = this.data.questions;
    var answers = this.data.userAnswers;

    // 精简题目数据（只发送必要字段，控制请求体大小）
    var simplifiedQuestions = questions.map(function (q) {
      return {
        _id: q._id,
        title: q.title,
        qtype: q.qtype || q.type || 'single',
        options: q.options,
        difficulty: q.difficulty,
        answer: q.answer
      };
    });

    this.setData({ examSummaryLoading: true, examSummaryError: '', examSummaryData: null, examSummaryNodes: [] });

    api.aiExamSummaryAnalysis(simplifiedQuestions, answers).then(function (res) {
      if (res && res.summary) {
        // 预处理 LaTeX 并解析 Markdown
        var summaryMd = that._preprocessMath(res.summary.content || '');
        var summaryNodes = md.parse(summaryMd);
        that.setData({
          examSummaryData: res.summary,
          examSummaryNodes: summaryNodes,
          examSummaryLoading: false,
          examSummaryError: ''
        });
      } else {
        that.setData({
          examSummaryLoading: false,
          examSummaryError: '分析总结返回空结果，请稍后重试'
        });
      }
    }, function (err) {
      var msg = 'AI 分析失败，请稍后重试';
      if (err && err.data && err.data.message) {
        msg = err.data.message;
      } else if (err && err.message) {
        msg = err.message;
      }
      if (err && err.statusCode === 403) {
        msg = '该功能仅对 VIP 用户开放';
        that.setData({ isVip: false });
      }
      that.setData({
        examSummaryLoading: false,
        examSummaryError: msg
      });
    });
  },

  /**
   * 重试答题分析总结
   */
  retryExamSummary: function () {
    this.loadExamSummary();
  },

  /**
   * 关闭分析总结弹层
   */
  closeExamSummary: function (e) {
    if (e && e.target && e.currentTarget && e.target !== e.currentTarget) return;
    this.setData({ showExamSummary: false });
  },

  // ===== VIP 升级引导 =====

  closeVipUpgrade: function (e) {
    if (e && e.target && e.currentTarget && e.target !== e.currentTarget) return;
    this.setData({ showVipUpgrade: false });
  },

  noop: function () {},

  onShareAppMessage: function () {
    return {
      title: '考试助手 - 来刷题吧',
      path: '/pages/home/index'
    };
  }
});
