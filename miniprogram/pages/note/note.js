const api = require('../../utils/api.js');
const util = require('../../utils/util.js');

Page({
  data: {
    ordernum: '',
    notes: [],
    currentIndex: 0,
    total: 0,
    question: {},
    options: [],
    userAnswer: [],
    correctAnswer: [],
    percent: 0,
    btnText: '下一题',
    loading: true,
    error: '',
    empty: false,
    // 重做模式
    retryMode: false,
    retryResult: false,
    retryCorrect: false,
    // 已掌握标记
    resolvedMap: {},
    currentResolved: false
  },

  onLoad: function (options) {
    var ordernum = options.ordernum || '';
    if (!ordernum) {
      this.setData({ loading: false, error: '缺少场次参数' });
      return;
    }
    this.setData({ ordernum: ordernum });
    this.loadNotes(ordernum);
  },

  loadNotes: function (ordernum) {
    var that = this;
    var db = api.database();
    db.collection('notes').where({ ordernum: ordernum }).get({
      success: function (res) {
        var notes = res.data || [];
        if (notes.length === 0) {
          that.setData({ loading: false, empty: true });
          return;
        }

        var resolvedMap = {};
        notes.forEach(function (n) {
          resolvedMap[n._id] = n.resolved || false;
        });

        that.setData({
          notes: notes,
          total: notes.length,
          loading: false,
          resolvedMap: resolvedMap
        });
        that.showNote(0);
      },
      fail: function (err) {
        console.error('[note] loadNotes fail', err);
        that.setData({ loading: false, error: '错题加载失败' });
      }
    });
  },

  showNote: function (index) {
    var notes = this.data.notes;
    if (index < 0 || index >= notes.length) return;

    var note = notes[index];
    var question = note.question || {};
    var rawOptions = note.options || question.options || [];

    if (typeof rawOptions === 'string') {
      try { rawOptions = JSON.parse(rawOptions); } catch (e) { rawOptions = []; }
    }

    var userAnswer = note.userAnswer || [];
    if (typeof userAnswer === 'string') {
      try { userAnswer = JSON.parse(userAnswer); } catch (e) { userAnswer = [userAnswer]; }
    }

    var correctAnswer = rawOptions.filter(function (opt) { return opt.value == 1; }).map(function (opt) { return opt.code; });

    var options = rawOptions.map(function (opt) {
      return {
        code: opt.code,
        content: opt.content || opt.text || '',
        value: opt.value,
        isCorrect: opt.value == 1,
        isUserChoice: userAnswer.indexOf(opt.code) > -1,
        retrySelected: false
      };
    });

    var percent = Math.round(((index + 1) / notes.length) * 100);
    var btnText = '下一题';
    if (index === notes.length - 1) {
      btnText = '完成';
    }

    var noteId = note._id;
    var currentResolved = this.data.resolvedMap[noteId] || false;

    this.setData({
      currentIndex: index,
      question: question,
      options: options,
      userAnswer: userAnswer,
      correctAnswer: correctAnswer,
      percent: percent,
      btnText: btnText,
      retryResult: false,
      retryCorrect: false,
      retryMode: false,
      currentResolved: currentResolved
    });
  },

  // ===== 重做模式 =====
  toggleRetry: function () {
    var newMode = !this.data.retryMode;
    this.setData({
      retryMode: newMode,
      retryResult: false,
      retryCorrect: false
    });

    if (newMode) {
      var options = this.data.options.map(function (opt) {
        opt.retrySelected = false;
        return opt;
      });
      this.setData({ options: options });
    }
  },

  selectRetryOption: function (e) {
    if (this.data.retryResult) return;

    var code = e.currentTarget.dataset.code;
    var qtype = this.data.question.qtype || 'single';
    var options = this.data.options.slice();

    if (qtype === 'multiple') {
      options.forEach(function (opt) {
        if (opt.code === code) {
          opt.retrySelected = !opt.retrySelected;
        }
      });
    } else {
      options.forEach(function (opt) {
        opt.retrySelected = (opt.code === code);
      });
    }

    this.setData({ options: options });
  },

  submitRetry: function () {
    var that = this;
    var selectedCodes = this.data.options.filter(function (opt) { return opt.retrySelected; }).map(function (opt) { return opt.code; });

    if (selectedCodes.length === 0) {
      wx.showToast({ icon: 'none', title: '请选择答案' });
      return;
    }

    var isCorrect = this.checkRetryAnswer(selectedCodes);

    this.setData({
      retryResult: true,
      retryCorrect: isCorrect
    });

    if (isCorrect) {
      this.markResolved(this.data.notes[this.data.currentIndex]._id, true, true);
    }

    wx.showToast({
      icon: isCorrect ? 'success' : 'none',
      title: isCorrect ? '回答正确！已标记为已掌握' : '回答错误，继续加油'
    });
  },

  checkRetryAnswer: function (selectedCodes) {
    var correctCodes = this.data.correctAnswer;
    if (selectedCodes.length !== correctCodes.length) return false;
    var allMatch = true;
    selectedCodes.forEach(function (code) {
      if (correctCodes.indexOf(code) === -1) allMatch = false;
    });
    return allMatch;
  },

  // ===== 已掌握标记 =====
  markResolved: function (noteId, resolved, silent) {
    var that = this;
    var openid = wx.getStorageSync('openid');
    if (!openid || !noteId) return;

    wx.request({
      url: api.API_BASE + '/collections/notes/' + noteId + '/',
      method: 'PUT',
      header: { 'Content-Type': 'application/json', 'X-Openid': openid },
      data: {
        resolved: resolved,
        resolvedTime: resolved ? util.getTime(new Date()) : ''
      },
      success: function () {
        var resolvedMap = that.data.resolvedMap;
        resolvedMap[noteId] = resolved;
        that.setData({
          resolvedMap: resolvedMap,
          currentResolved: resolved
        });
        if (!silent) {
          wx.showToast({
            icon: 'none',
            title: resolved ? '已标记为已掌握' : '已取消标记'
          });
        }
      },
      fail: function () {
        if (!silent) {
          wx.showToast({ icon: 'none', title: '操作失败' });
        }
      }
    });
  },

  toggleResolved: function () {
    var noteId = this.data.notes[this.data.currentIndex]._id;
    var currentResolved = this.data.currentResolved || false;
    this.markResolved(noteId, !currentResolved);
  },

  // ===== 导航 =====
  goPrev: function () {
    if (this.data.currentIndex === 0) {
      wx.showToast({ icon: 'none', title: '已经是第一题' });
      return;
    }
    this.showNote(this.data.currentIndex - 1);
  },

  goNext: function () {
    if (this.data.currentIndex >= this.data.total - 1) {
      wx.navigateBack();
      return;
    }
    this.showNote(this.data.currentIndex + 1);
  },

  goHome: function () {
    wx.switchTab({ url: '/pages/home/index' });
  },

  onShareAppMessage: function () {
    return { title: '考试助手 - 错题回顾', path: '/pages/home/index' };
  }
});
