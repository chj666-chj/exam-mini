const api = require('../../utils/api.js');
const app = getApp();

Page({
  data: {
    score: 0,
    nickname: '',
    avatar: '',
    useTime: '-',
    resultText: '加油',
    accuracy: 0,
    rank: '-',
    ordernum: ''
  },

  onLoad: function (options) {
    const score = parseInt(options.score) || 0;
    const rightNum = parseInt(options.rightNum) || 0;
    const length = parseInt(options.length) || 0;
    const ordernum = options.ordernum || '';
    const accuracy = length ? Math.round(rightNum / length * 100) : 0;

    this.setData({
      score,
      accuracy,
      ordernum,
      useTime: this.calcUseTime(ordernum),
      resultText: score >= 60 ? '及格' : '加油'
    });

    this.loadUserInfo();
    this.calcRank(score);
  },

  /** ordernum 前 14 位为考试开始时间（yyyyMMddHHmmss），计算用时 */
  calcUseTime: function (ordernum) {
    if (!ordernum || !/^\d{14}/.test(ordernum)) return '-';
    var ts = ordernum.slice(0, 14);
    var y = ts.slice(0, 4), mo = ts.slice(4, 6), d = ts.slice(6, 8);
    var h = ts.slice(8, 10), mi = ts.slice(10, 12), s = ts.slice(12, 14);
    var start = new Date(+y, +mo - 1, +d, +h, +mi, +s).getTime();
    var diff = Math.max(0, Math.round((Date.now() - start) / 1000));
    var m = Math.floor(diff / 60), sec = diff % 60;
    return (m < 10 ? '0' + m : m) + ':' + (sec < 10 ? '0' + sec : sec);
  },

  loadUserInfo: function () {
    const openid = wx.getStorageSync('openid') || '';
    const that = this;
    const db = api.database();
    db.collection('profiles').where({ _openid: openid }).get({
      success: res => {
        const list = res.data || [];
        if (list.length && list[0].userInfo) {
          that.setData({
            nickname: list[0].userInfo.nickName || '考试用户',
            avatar: list[0].userInfo.avatarUrl || ''
          });
        } else {
          that.fallbackUser(openid);
        }
      },
      fail: () => that.fallbackUser(openid)
    });
  },

  fallbackUser: function (openid) {
    const db = api.database();
    db.collection('historys').where({ _openid: openid }).get({
      success: res => {
        const rec = (res.data || []).find(h => h.userInfo && h.userInfo.nickName);
        if (rec) {
          this.setData({
            nickname: rec.userInfo.nickName,
            avatar: rec.userInfo.avatarUrl || ''
          });
        } else {
          this.setData({ nickname: '考试用户' });
        }
      },
      fail: () => this.setData({ nickname: '考试用户' })
    });
  },

  /** 考试排名：历史成绩中高于本次的正确率人数 + 1 */
  calcRank: function (score) {
    const db = api.database();
    const that = this;
    db.collection('historys').get({
      success: res => {
        const all = res.data || [];
        // 每个用户的最佳成绩
        const best = {};
        all.forEach(h => {
          // 兼容 nums 字段或 items 数组长度
          var nums = Number(h.nums) || 0;
          if (!nums && h.items) {
            nums = Array.isArray(h.items) ? h.items.length : 0;
          }
          if (!nums) return;
          const acc = Math.round((Number(h.rightNum) || 0) / nums * 100);
          if (!best[h._openid] || acc > best[h._openid]) best[h._openid] = acc;
        });
        let higher = 0;
        Object.keys(best).forEach(oid => {
          if (best[oid] > score) higher += 1;
        });
        that.setData({ rank: higher + 1 });
      },
      fail: () => that.setData({ rank: '-' })
    });
  },

  /** 查看答案：去错题重做页 */
  bindgoview: function () {
    const ordernum = this.data.ordernum;
    if (ordernum) {
      wx.navigateTo({ url: '/pages/note/note?ordernum=' + ordernum });
    } else {
      wx.showToast({ icon: 'none', title: '无本次作答记录' });
    }
  },

  onGetOpenid: function () {
    api.callFunction({
      name: 'login',
      data: {},
      success: res => { app.globalData.openid = res.result.openid; },
      fail: err => console.error('[login] 失败', err)
    });
  },

  onShareAppMessage: function () {
    return {
      title: '我在考试助手取得了 ' + this.data.score + ' 分，来挑战吧！',
      path: '/pages/home/index'
    };
  }
});
