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
      // 未登录：重置用户信息为默认值，避免残留上次登录的数据
      this.setData({
        nickname: '未登录用户',
        avatar: '',
        openidShort: '',
        solvedCount: 0,
        accuracy: 0,
        persistDays: 0
      });
    }
    this.loadSettings();
  },

  onAvatarError: function () {
    this.setData({ avatar: '/images/header.png' });
  },

  goLogin: function () {
    wx.navigateTo({ url: '/pages/info/index' });
  },

  // 未登录时点击用户卡片 → 直接跳转登录页（无需二次确认，卡片本身就是登录引导）
  // 已登录时点击用户卡片 → 打开详情弹窗
  // showUserDetail 的未登录分支已在 wxml 中通过 wx:if 隔离，此处不会在未登录时被触发

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

  // 关闭用户详情弹窗
  // 注意：不可用 e.target !== e.currentTarget 判断——微信小程序中
  // e.target 与 e.currentTarget 始终是不同的对象引用，该比较恒为 true，
  // 会导致关闭逻辑永远提前 return，弹窗无法关闭。
  // 正确做法：面板用 catchtap="noop" 阻止内部点击冒泡到遮罩，
  // 关闭按钮直接绑定 closeUserDetail，此处无需额外判断。
  closeUserDetail: function () {
    this.setData({ showDetail: false });
  },

  noop: function () {},

  _requireLogin: function () {
    var openid = wx.getStorageSync('openid');
    if (!openid) {
      wx.showModal({
        title: '需要登录',
        content: '该功能需要登录后才能使用，是否前往登录？',
        confirmText: '去登录',
        cancelText: '暂不',
        confirmColor: '#4A90F3',
        success: function (res) {
          if (res.confirm) {
            wx.navigateTo({ url: '/pages/info/index' });
          }
        }
      });
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
  goAIService: function () { wx.navigateTo({ url: '/pages/ai-service/index' }); },

  // ===== 账号管理 =====
  goProfileEdit: function () {
    if (!this._requireLogin()) return;
    wx.navigateTo({ url: '/pages/profile-edit/index' });
  },
  goChangePassword: function () {
    if (!this._requireLogin()) return;
    wx.navigateTo({ url: '/pages/change-password/index' });
  },

  // ===== 退出登录 =====
  handleLogout: function () {
    var that = this;
    wx.showModal({
      title: '退出登录',
      content: '确认退出当前账号？退出后将清除本地登录信息，需要重新登录。',
      confirmText: '退出',
      cancelText: '取消',
      confirmColor: '#e64340',
      success: function (res) {
        if (res.confirm) {
          that._doLogout();
        }
        // 取消则关闭提示框，保持在设置页面，无需处理
      }
    });
  },

  _doLogout: function () {
    // 1. 清除本地登录状态
    wx.removeStorageSync('openid');

    // 2. 清除 app.globalData 中的 openid
    var app = getApp();
    if (app && app.globalData) {
      app.globalData.openid = '';
    }

    // 3. 重置页面数据为未登录状态
    this.setData({
      isLoggedIn: false,
      nickname: '未登录用户',
      avatar: '',
      openidShort: '',
      solvedCount: 0,
      accuracy: 0,
      persistDays: 0,
      showDetail: false
    });

    // 4. 提示并跳转登录页
    wx.showToast({
      title: '已退出登录',
      icon: 'success',
      duration: 1200
    });
    setTimeout(function () {
      wx.navigateTo({ url: '/pages/info/index' });
    }, 1000);
  }
});
