const api = require('../../utils/api.js');
const util = require('../../utils/util.js');
const judge = require('../../utils/judge.js');

Page({
  data: {
    subjectId: '',
    mode: 'answer',
    undone: false,
    undoneSkipped: 0,
    totalBeforeFilter: 0,
    questions: [],
    total: 0,
    userAnswers: [],
    loading: true,
    error: '',
    showAnswers: false,
    allAnswered: false
  },

  onLoad: function (options) {
    var id = options.id || '';
    var mode = options.mode || 'answer';
    var undone = options.undone === 'true';
    this.setData({
      subjectId: id,
      mode: mode,
      undone: undone,
      showAnswers: mode === 'memorize'
    });
    this.loadQuestions();
  },

  loadQuestions: function () {
    var that = this;
    var questions = wx.getStorageSync('quiz_questions');

    if (questions && questions.length > 0) {
      that.processQuestions(questions);
      return;
    }

    if (!that.data.subjectId) {
      that.setData({ loading: false, error: '缺少科目参数' });
      return;
    }

    var db = api.database();
    db.collection('questions').where({ examid: that.data.subjectId }).get({
      success: function (res) {
        var list = (res.data || []).map(function (q) {
          // 统一归一化：code -> String、value -> 0/1，避免类型混用导致判题/展示不一致
          q = judge.normalizeQuestion(q);
          q.options.forEach(function (opt) {
            opt.isCorrect = judge.isCorrectOption(opt);
            opt.selected = false;
          });
          return q;
        });
        if (list.length === 0) {
          that.setData({ loading: false, error: '该科目暂无题目' });
          return;
        }
        that.processQuestions(list);
      },
      fail: function (err) {
        console.error('[question] loadQuestions fail', err);
        that.setData({ loading: false, error: '题目加载失败' });
      }
    });
  },

  // 处理题目列表：undone 模式下过滤已答题目
  processQuestions: function (questions) {
    var that = this;
    that.setData({ totalBeforeFilter: questions.length });

    if (!that.data.undone) {
      that.initQuestions(questions);
      return;
    }

    // undone 模式：查询 historys 提取已答题目 ID
    var openid = wx.getStorageSync('openid');
    if (!openid) {
      // 未登录无法判断已答，降级展示全部
      that.initQuestions(questions);
      return;
    }

    var db = api.database();
    db.collection('historys').where({ _openid: openid }).get({
      success: function (res) {
        var histories = res.data || [];
        var answeredSet = {};
        histories.forEach(function (h) {
          var items = h.items || [];
          items.forEach(function (qid) {
            answeredSet[qid] = true;
          });
        });

        var unanswered = questions.filter(function (q) {
          return !answeredSet[q._id];
        });

        var skipped = questions.length - unanswered.length;
        that.setData({ undoneSkipped: skipped });

        if (unanswered.length === 0) {
          that.setData({
            loading: false,
            allAnswered: true,
            total: 0,
            questions: []
          });
          return;
        }

        that.initQuestions(unanswered);
      },
      fail: function (err) {
        console.error('[question] loadHistorys fail', err);
        that.initQuestions(questions);
      }
    });
  },

  initQuestions: function (questions) {
    var userAnswers = questions.map(function () { return []; });
    this.setData({
      questions: questions,
      total: questions.length,
      userAnswers: userAnswers,
      loading: false
    });
  },

  selectOption: function (e) {
    if (this.data.mode === 'memorize') return;

    var qIdx = e.currentTarget.dataset.qidx;
    var code = judge.normalizeCode(e.currentTarget.dataset.code);
    var questions = this.data.questions.slice();
    var question = questions[qIdx];
    var qtype = question.qtype || 'single';

    if (qtype === 'multiple') {
      question.options.forEach(function (opt) {
        if (opt.code === code) {
          opt.selected = !opt.selected;
        }
      });
    } else {
      question.options.forEach(function (opt) {
        opt.selected = (opt.code === code);
      });
    }

    var userAnswer = judge.normalizeCodes(question.options.filter(function (opt) { return opt.selected; }).map(function (opt) { return opt.code; }));
    var userAnswers = this.data.userAnswers.slice();
    userAnswers[qIdx] = userAnswer;

    this.setData({ questions: questions, userAnswers: userAnswers });
  },

  submitAnswers: function () {
    var that = this;
    var rightNum = 0;
    var errNum = 0;
    var ordernum = util.formatTime(new Date());

    this.data.questions.forEach(function (question, index) {
      var isRight = that.checkAnswer(index);
      if (isRight) {
        rightNum++;
      } else {
        errNum++;
        that.addNote(index, ordernum);
      }
    });

    this.setData({ rightNum: rightNum, errNum: errNum, ordernum: ordernum });
    this.addHistory(ordernum, rightNum, errNum);

    wx.showModal({
      showCancel: false,
      title: '答题完成',
      content: '共 ' + this.data.total + ' 题\n答对 ' + rightNum + ' 题，答错 ' + errNum + ' 题',
      success: function () {
        that.goResult(rightNum, errNum, ordernum);
      }
    });
  },

  // 判题：统一委托 utils/judge.js（唯一实现），
  // 避免与 exam.js 各写一份导致比对规则漂移（历史事故：code 类型 / value 类型不一致）
  checkAnswer: function (index) {
    var question = this.data.questions[index];
    var userAnswer = this.data.userAnswers[index] || [];
    return judge.judgeAnswer(question, userAnswer);
  },

  addNote: function (index, ordernum) {
    var that = this;
    var question = this.data.questions[index];
    var openid = wx.getStorageSync('openid');
    if (!openid) return;

    var db = api.database();
    var questionId = question._id;

    // 去重: 先查询是否已有同 questionId 的未解决记录
    db.collection('notes').where({ _openid: openid, questionId: questionId, resolved: false }).get({
      success: function (res) {
        var existing = res.data || [];
        if (existing.length > 0) {
          var existingNote = existing[0];
          var retryCount = (existingNote.retryCount || 0) + 1;
          wx.request({
            url: api.API_BASE + '/collections/notes/' + existingNote._id + '/',
            method: 'PUT',
            header: { 'Content-Type': 'application/json', 'X-Openid': openid },
            data: {
              retryCount: retryCount,
              lastRetryTime: util.getTime(new Date()),
              userAnswer: that.data.userAnswers[index],
              ordernum: ordernum
            },
            success: function () { console.log('[question] addNote dedup update success'); },
            fail: function (err) { console.error('[question] addNote dedup update fail', err); }
          });
        } else {
          db.collection('notes').add({
            data: {
              ordernum: ordernum,
              questionId: questionId,
              question: question,
              options: question.options,
              userAnswer: that.data.userAnswers[index],
              resolved: false,
              retryCount: 0,
              createTime: util.getTime(new Date())
            },
            success: function (res) { console.log('[question] addNote new success', res._id); },
            fail: function (err) { console.error('[question] addNote new fail', err); }
          });
        }
      },
      fail: function (err) {
        console.error('[question] addNote query fail', err);
        db.collection('notes').add({
          data: {
            ordernum: ordernum,
            questionId: questionId,
            question: question,
            options: question.options,
            userAnswer: that.data.userAnswers[index],
            resolved: false,
            retryCount: 0,
            createTime: util.getTime(new Date())
          }
        });
      }
    });
  },

  addHistory: function (ordernum, rightNum, errNum) {
    var subject = wx.getStorageSync('subject') || {};
    var db = api.database();
    var items = this.data.questions.map(function (q) { return q._id; });

    db.collection('historys').add({
      data: {
        _id: ordernum,
        subject: subject,
        items: items,
        rightNum: rightNum,
        nums: this.data.total,
        score_arr: this.data.userAnswers,
        createTime: util.getTime(new Date())
      },
      success: function (res) { console.log('[question] addHistory success', res._id); },
      fail: function (err) { console.error('[question] addHistory fail', err); }
    });
  },

  goResult: function (rightNum, errNum, ordernum) {
    wx.redirectTo({
      url: '/pages/examresult/examresult?length=' + this.data.total +
        '&errNum=' + errNum + '&rightNum=' + rightNum + '&ordernum=' + ordernum
    });
  },

  goHome: function () {
    wx.switchTab({ url: '/pages/home/index' });
  },

  onShareAppMessage: function () {
    return { title: '考试助手', path: '/pages/home/index' };
  }
});
