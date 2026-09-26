const api = require('../../utils/api.js');

Page({
  data: {
    avatar: '',
    nickname: '未登录用户',
    openidShort: '',
    isLoggedIn: false,
    solvedCount: 0,
    accuracy: 0,
    persistDays: 0,
    settings: { autoNext: false, fontSize: 'medium' },
    fontSizeClass: 'fs-medium',
    showDetail: false
  },

  onShow: function () {
    var openid = wx.getStorageSync('openid') || '';
    this.setData({ isLoggedIn: !!openid });
    if (openid) {
      this.loadProfile();
      this.loadStats();
    } else {
      this.setData({ solvedCount: 0, accuracy: 0, persistDays: 0 });
    }
    this.loadSettings();
  },

  onAvatarError: function () {
    this.setData({ avatar: '/images/header.png' });
  },

  goLogin: function () {
    wx.navigateTo({ url: '/pages/info/index' });
  },

  loadProfile: function () {
    const openid = wx.getStorageSync('openid') || '';
    const that = this;
    this.setData({ openidShort: openid ? openid.slice(-8) : '-' });
    const db = api.database();
    db.collection('profiles').where({ _openid: openid }).get({
      success: res => {
        const list = res.data || [];
        if (list.length && list[0].userInfo) {
          that.setData({
            nickname: list[0].userInfo.nickName || '考试用户',
            avatar: list[0].userInfo.avatarUrl || '/images/header.png'
          });
        } else {
          that.setData({ avatar: '/images/header.png' });
        }
      },
      fail: () => {
        that.setData({ avatar: '/images/header.png' });
        db.collection('historys').where({ _openid: openid }).get({
          success: res2 => {
            const rec = (res2.data || []).find(h => h.userInfo && h.userInfo.nickName);
            if (rec) {
              that.setData({
                nickname: rec.userInfo.nickName,
                avatar: rec.userInfo.avatarUrl || '/images/header.png'
              });
            }
          }
        });
      }
    });
  },

  loadStats: function () {
    const openid = wx.getStorageSync('openid');
    if (!openid) return;
    const db = api.database();
    const that = this;
    db.collection('historys').where({ _openid: openid }).get({
      success: res => {
        const mine = res.data || [];
        let solved = 0, right = 0;
        const days = {};
        mine.forEach(h => {
          solved += Number(h.nums) || 0;
          right += Number(h.rightNum) || 0;
          const d = (h.createTime || '').split(' ')[0];
          if (d) days[d] = true;
        });
        that.setData({
          solvedCount: solved,
          accuracy: solved ? Math.round(right / solved * 100) : 0,
          persistDays: Object.keys(days).length
        });
      },
      fail: err => {
        console.error('[mine] loadStats fail', err);
      }
    });
  },

  // ===== 答题设置 =====
  loadSettings: function () {
    var settings = wx.getStorageSync('quiz_settings') || {};
    var fontSizeMap = { small: 'fs-small', medium: 'fs-medium', large: 'fs-large' };
    var fs = settings.fontSize || 'medium';
    this.setData({
      settings: {
        autoNext: settings.autoNext || false,
        fontSize: fs
      },
      fontSizeClass: fontSizeMap[fs] || 'fs-medium'
    });
  },

  toggleAutoNextSetting: function (e) {
    var newVal = e.detail.value;
    var settings = wx.getStorageSync('quiz_settings') || {};
    settings.autoNext = newVal;
    wx.setStorageSync('quiz_settings', settings);
    this.setData({ 'settings.autoNext': newVal });
    wx.showToast({
      icon: 'none',
      title: newVal ? '已开启答对自动跳转' : '已关闭答对自动跳转'
    });
  },

  changeFontSize: function (e) {
    var size = e.currentTarget.dataset.size;
    var fontSizeMap = { small: 'fs-small', medium: 'fs-medium', large: 'fs-large' };
    var sizeLabel = { small: '小', medium: '标准', large: '大' };
    var settings = wx.getStorageSync('quiz_settings') || {};
    settings.fontSize = size;
    wx.setStorageSync('quiz_settings', settings);
    this.setData({
      'settings.fontSize': size,
      fontSizeClass: fontSizeMap[size] || 'fs-medium'
    });
    wx.showToast({ icon: 'none', title: '字体已切换为' + (sizeLabel[size] || '标准') + '，答题页生效' });
  },

  // ===== 用户详情弹窗 =====
  showUserDetail: function () {
    if (!this.data.isLoggedIn) {
      this.goLogin();
      return;
    }
    this.setData({ showDetail: true });
  },

  closeUserDetail: function (e) {
    if (e && e.target && e.currentTarget && e.target !== e.currentTarget) return;
    this.setData({ showDetail: false });
  },

  noop: function () {},

  _requireLogin: function () {
    var openid = wx.getStorageSync('openid');
    if (!openid) {
      wx.showToast({ icon: 'none', title: '请先登录' });
      return false;
    }
    return true;
  },

  goHistory: function () {
    if (!this._requireLogin()) return;
    wx.navigateTo({ url: '/pages/history/index' });
  },
  goWrong: function () {
    if (!this._requireLogin()) return;
    wx.navigateTo({ url: '/pages/wrong/index' });
  },
  goRank: function () { wx.switchTab({ url: '/pages/rank/index' }); },
  goStudy: function () {
    if (!this._requireLogin()) return;
    wx.navigateTo({ url: '/pages/study/index' });
  },
  goAIConfig: function () { wx.navigateTo({ url: '/pages/ai-config/index' }); },
  goPay: function () { wx.navigateTo({ url: '/pages/pay/index' }); },
  goAbout: function () { wx.navigateTo({ url: '/pages/about/index' }); },
  goRule: function () { wx.navigateTo({ url: '/pages/rule/index' }); },
  goAIQA: function () { wx.navigateTo({ url: '/pages/ai-qa/index' }); },
  goAIReport: function () { wx.navigateTo({ url: '/pages/ai-report/index' }); },
  goAIService: function () { wx.navigateTo({ url: '/pages/ai-service/index' }); }
});
