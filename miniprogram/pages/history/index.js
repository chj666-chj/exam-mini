const api = require('../../utils/api.js');
const app = getApp();

Page({
  data: {
    items: [],
    loading: true
  },

  onLoad: function (options) {
    this.loadData();
  },

  onShow: function () {
    this.loadData();
  },

  onPullDownRefresh: function () {
    this.loadData(function () {
      wx.stopPullDownRefresh();
    });
  },

  loadData: function (done) {
    var that = this;
    var openid = wx.getStorageSync('openid');
    if (!openid) {
      // 尝试调用登录
      api.callFunction({
        name: 'login',
        data: {},
        success: res => {
          app.globalData.openid = res.result.openid;
          wx.setStorageSync('openid', res.result.openid);
          that.query(res.result.openid, done);
        },
        fail: err => {
          console.error('[history] login fail', err);
          that.setData({ loading: false, items: [] });
          wx.showToast({ icon: 'none', title: '后端未启动或网络异常' });
          if (done) done();
        }
      });
      return;
    }
    this.query(openid, done);
  },

  query: function (openid, done) {
    var that = this;
    var db = api.database();
    db.collection('historys').where({ _openid: openid }).get({
      success: res => {
        var arrayObject = res.data || [];
        var items = arrayObject.slice(0, 50);
        items.map(function (item) {
          var ct = item.createTime || item.time || '';
          item.createTime = ct.substr ? ct.substr(0, 10) : '';
          if (!item.subject) item.subject = { name: '未知科目' };
          if (!item.subject.name) item.subject.name = '未知科目';
          return item;
        });
        that.setData({ items: items, loading: false });
        if (done) done();
      },
      fail: err => {
        console.error('[history] query fail', err);
        that.setData({ loading: false });
        wx.showToast({ icon: 'none', title: '查询记录失败' });
        if (done) done();
      }
    });
  },

  toReviewPage: function (e) {
    var id = e.currentTarget.dataset.id;
    if (!id) return;
    wx.navigateTo({ url: '/pages/review/review?id=' + id });
  },

  onShareAppMessage: function () {
    return { title: '考试助手 - 答题记录', path: '/pages/home/index' };
  }
});