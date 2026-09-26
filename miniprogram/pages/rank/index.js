var api = require('../../utils/api.js');

Page({
  data: {
    tab: 'rank',
    myOpenid: '',
    latestScore: 0,
    myRank: '-',
    passCount: 0,
    examCount: 0,
    predictScore: 0,
    solvedCount: 0,
    accuracy: 0,
    accuracyRank: 0,
    persistDays: 0,
    persistRank: 0,
    unsolvedCount: 0,
    weekDays: [],
    weekPass: 0,
    totalPassDays: 0,
    board: []
  },

  onShow: function () {
    this.setData({ myOpenid: wx.getStorageSync('openid') || '' });
    this.load();
  },

  onPullDownRefresh: function () {
    this.load(function () { wx.stopPullDownRefresh(); });
  },

  switchTab: function (e) {
    this.setData({ tab: e.currentTarget.dataset.tab });
  },

  load: function (done) {
    var that = this;
    api.getRanking().then(function (res) {
      var s = res.myStats || {};
      that.setData({
        board: res.board || [],
        myRank: res.myRank || '-',
        latestScore: s.latestScore || 0,
        passCount: s.passCount || 0,
        examCount: s.examCount || 0,
        predictScore: s.predictScore || 0,
        solvedCount: s.solvedCount || 0,
        accuracy: s.accuracy || 0,
        accuracyRank: s.accuracyRank || 0,
        persistDays: s.persistDays || 0,
        persistRank: s.persistRank || 0,
        unsolvedCount: s.unsolvedCount || 0,
        totalPassDays: s.totalPassDays || 0,
        weekDays: s.weekDays || [],
        weekPass: s.weekPass || 0
      });
      if (done) done();
    }).catch(function (err) {
      console.error('[排行] 加载失败', err);
      wx.showToast({ icon: 'none', title: '排行数据加载失败' });
      if (done) done();
    });
  }
});
