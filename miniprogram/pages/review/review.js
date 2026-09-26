const api = require('../../utils/api.js');

Page({
  data: {
    ordernum: '',
    history: {},
    items: [],
    currentIndex: 0,
    total: 0,
    question: {},
    options: [],
    percent: 0,
    btnText: '下一题',
    loading: true,
    error: ''
  },

  onLoad: function (options) {
    var id = options.id || '';
    if (!id) {
      this.setData({ loading: false, error: '缺少记录参数' });
      return;
    }
    this.setData({ ordernum: id });
    this.loadHistory(id);
  },

  loadHistory: function (ordernum) {
    var that = this;
    var db = api.database();
    db.collection('historys').doc(ordernum).get({
      success: function (res) {
        var history = res.data || {};
        var items = history.items || [];
        if (items.length === 0) {
          that.setData({ loading: false, error: '该记录无题目数据' });
          return;
        }
        that.setData({
          history: history,
          items: items,
          total: items.length,
          loading: false
        });
        that.loadQuestion(items[0]);
      },
      fail: function (err) {
        console.error('[review] loadHistory fail', err);
        that.setData({ loading: false, error: '记录加载失败' });
      }
    });
  },

  loadQuestion: function (qid) {
    var that = this;
    var db = api.database();
    db.collection('questions').doc(qid).get({
      success: function (res) {
        var question = res.data || {};
        if (typeof question.options === 'string') {
          try { question.options = JSON.parse(question.options); } catch (e) { question.options = []; }
        }
        question.options = question.options || [];
        var options = question.options.map(function (opt) {
          return {
            code: opt.code,
            content: opt.content || opt.text || '',
            value: opt.value,
            isCorrect: opt.value == 1
          };
        });
        that.setData({ question: question, options: options });
      },
      fail: function (err) {
        console.error('[review] loadQuestion fail', err);
        that.setData({ error: '题目加载失败' });
      }
    });
  },

  goPrev: function () {
    if (this.data.currentIndex === 0) {
      wx.showToast({ icon: 'none', title: '已经是第一题' });
      return;
    }
    var prevIndex = this.data.currentIndex - 1;
    this.setData({ currentIndex: prevIndex });
    this.loadQuestion(this.data.items[prevIndex]);
    this.updateProgress(prevIndex);
  },

  goNext: function () {
    var index = this.data.currentIndex;
    if (index >= this.data.total - 1) {
      wx.navigateBack();
      return;
    }
    var nextIndex = index + 1;
    this.setData({ currentIndex: nextIndex });
    this.loadQuestion(this.data.items[nextIndex]);
    this.updateProgress(nextIndex);
  },

  updateProgress: function (index) {
    var percent = Math.round(((index + 1) / this.data.total) * 100);
    var btnText = '下一题';
    if (index === this.data.total - 1) {
      btnText = '完成';
    }
    this.setData({ percent: percent, btnText: btnText });
  },

  goHome: function () {
    wx.switchTab({ url: '/pages/home/index' });
  },

  onShareAppMessage: function () {
    return { title: '考试助手 - 答题回顾', path: '/pages/home/index' };
  }
});
