const api = require('../../utils/api.js');
const util = require('../../utils/util.js');
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
    btnText: '下一题',
    ordernum: '',
    loading: true,
    error: '',
    answered: false,
    showAnswer: false
  },

  onLoad: function (options) {
    var id = options.id || '';
    var mode = options.mode || 'answer';
    var ordernum = util.formatTime(new Date());
    this.setData({ subjectId: id, mode: mode, ordernum: ordernum });
    this.loadQuestions();
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
    db.collection('questions').where({ examid: that.data.subjectId }).get({
      success: function (res) {
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
      },
      fail: function (err) {
        console.error('[simple] loadQuestions fail', err);
        that.setData({ loading: false, error: '题目加载失败' });
      }
    });
  },

  initQuestions: function (questions) {
    var userAnswers = questions.map(function () { return []; });
    var isMemorize = this.data.mode === 'memorize';
    this.setData({
      questions: questions,
      total: questions.length,
      userAnswers: userAnswers,
      loading: false,
      showAnswer: isMemorize
    });
    this.showQuestion(0);
  },

  showQuestion: function (index) {
    var questions = this.data.questions;
    if (index < 0 || index >= questions.length) return;

    var question = questions[index];
    var options = (question.options || []).map(function (opt) {
      return {
        code: opt.code,
        content: opt.content || opt.text || '',
        value: opt.value,
        selected: false,
        isCorrect: opt.value == 1
      };
    });

    var userAnswer = this.data.userAnswers[index] || [];
    if (userAnswer.length > 0) {
      options.forEach(function (opt) {
        if (userAnswer.indexOf(opt.code) > -1) {
          opt.selected = true;
        }
      });
    }

    var percent = Math.round(((index + 1) / questions.length) * 100);
    var btnText = '下一题';
    if (index === questions.length - 1) {
      btnText = this.data.mode === 'memorize' ? '完成' : '提交';
    }

    this.setData({
      currentIndex: index,
      question: question,
      options: options,
      percent: percent,
      btnText: btnText,
      answered: userAnswer.length > 0
    });
  },

  selectOption: function (e) {
    if (this.data.mode === 'memorize') return;

    var code = e.currentTarget.dataset.code;
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

    var userAnswer = options.filter(function (opt) { return opt.selected; }).map(function (opt) { return opt.code; });
    var userAnswers = this.data.userAnswers.slice();
    userAnswers[this.data.currentIndex] = userAnswer;

    this.setData({
      options: options,
      userAnswers: userAnswers,
      answered: userAnswer.length > 0
    });
  },

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
        wx.navigateBack();
        return;
      }
      this.showQuestion(index + 1);
      return;
    }

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
        that.addHistory();
        that.goResult();
      });
      return;
    }

    this.setData({ rightNum: rightNum, errNum: errNum });
    this.showQuestion(index + 1);
  },

  checkAnswer: function (index) {
    var question = this.data.questions[index];
    var options = question.options || [];
    var correctCodes = options.filter(function (opt) { return opt.value == 1; }).map(function (opt) { return opt.code; });
    var userAnswer = this.data.userAnswers[index] || [];

    if (userAnswer.length === 0) return false;
    if (userAnswer.length !== correctCodes.length) return false;

    var allMatch = true;
    userAnswer.forEach(function (code) {
      if (correctCodes.indexOf(code) === -1) allMatch = false;
    });
    return allMatch;
  },

  addNote: function (index) {
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
              ordernum: that.data.ordernum
            },
            success: function () { console.log('[simple] addNote dedup update success'); },
            fail: function (err) { console.error('[simple] addNote dedup update fail', err); }
          });
        } else {
          db.collection('notes').add({
            data: {
              ordernum: that.data.ordernum,
              questionId: questionId,
              question: question,
              options: question.options,
              userAnswer: that.data.userAnswers[index],
              resolved: false,
              retryCount: 0,
              createTime: util.getTime(new Date())
            },
            success: function (res) { console.log('[simple] addNote new success', res._id); },
            fail: function (err) { console.error('[simple] addNote new fail', err); }
          });
        }
      },
      fail: function (err) {
        console.error('[simple] addNote query fail', err);
        db.collection('notes').add({
          data: {
            ordernum: that.data.ordernum,
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

  addHistory: function () {
    var subject = wx.getStorageSync('subject') || {};
    var db = api.database();
    var items = this.data.questions.map(function (q) { return q._id; });

    db.collection('historys').add({
      data: {
        _id: this.data.ordernum,
        subject: subject,
        items: items,
        rightNum: this.data.rightNum,
        nums: this.data.total,
        score_arr: this.data.userAnswers,
        createTime: util.getTime(new Date())
      },
      success: function (res) { console.log('[simple] addHistory success', res._id); },
      fail: function (err) { console.error('[simple] addHistory fail', err); }
    });
  },

  goResult: function () {
    var url = '/pages/examresult/examresult?length=' + this.data.total +
      '&errNum=' + this.data.errNum +
      '&rightNum=' + this.data.rightNum +
      '&ordernum=' + this.data.ordernum;
    wx.redirectTo({ url: url });
  },

  onShareAppMessage: function () {
    return { title: '考试助手 - 来刷题吧', path: '/pages/home/index' };
  }
});
