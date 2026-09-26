const api = require('../../utils/api.js');

Page({
  data: {
    // 6 位激活码输入（独立 6 格）
    codeDigits: ['', '', '', '', '', ''],
    activeIndex: 0,
    submitting: false,
    isVip: false,
    vipExpireAt: '',
    resultMsg: '',
    resultType: ''  // 'success' | 'error' | ''
  },

  onLoad: function () {
    this.checkVipStatus();
  },

  onShow: function () {
    this.checkVipStatus();
  },

  noop: function () {},

  // 查询当前 VIP 状态
  checkVipStatus: function () {
    var that = this;
    api.getVipStatus().then(function (res) {
      that.setData({
        isVip: !!res.isVip,
        vipExpireAt: res.vipExpireAt || ''
      });
    }).catch(function () {});
  },

  // 点击某个输入格 → 聚焦隐藏的 input
  onDigitTap: function (e) {
    var index = e.currentTarget.dataset.index;
    this.setData({ activeIndex: index });
  },

  // 输入事件（单一隐藏 input 统一接收）
  onCodeInput: function (e) {
    var value = (e.detail.value || '').replace(/\D/g, ''); // 只保留数字
    var digits = value.split('');
    var newCodeDigits = ['', '', '', '', '', ''];
    for (var i = 0; i < Math.min(digits.length, 6); i++) {
      newCodeDigits[i] = digits[i];
    }
    var nextActive = Math.min(digits.length, 5);
    this.setData({
      codeDigits: newCodeDigits,
      activeIndex: nextActive,
      resultMsg: '',
      resultType: ''
    });
  },

  // 获取当前完整激活码
  getFullCode: function () {
    return this.data.codeDigits.join('');
  },

  // 提交激活
  onActivate: function () {
    if (this.data.submitting) return;

    var code = this.getFullCode();
    if (code.length !== 6) {
      this.setData({ resultMsg: '请输入完整的 6 位激活码', resultType: 'error' });
      return;
    }

    this.setData({ submitting: true, resultMsg: '', resultType: '' });

    var that = this;
    api.redeemActivationCode(code).then(function (res) {
      that.setData({
        submitting: false,
        isVip: true,
        vipExpireAt: res.vipExpireAt || '',
        resultMsg: '激活成功！您已获得 VIP 权限',
        resultType: 'success',
        codeDigits: ['', '', '', '', '', '']
      });
      // 延迟跳回首页
      setTimeout(function () {
        wx.showToast({ title: '激活成功', icon: 'success', duration: 1500 });
      }, 100);
    }).catch(function (err) {
      var msg = '激活失败，请稍后重试';
      if (err && err.message) {
        msg = err.message;
      } else if (err && err.data && err.data.message) {
        msg = err.data.message;
      } else if (typeof err === 'string') {
        msg = err;
      }
      that.setData({
        submitting: false,
        resultMsg: msg,
        resultType: 'error'
      });
    });
  },

  // 清空输入
  onClear: function () {
    this.setData({
      codeDigits: ['', '', '', '', '', ''],
      activeIndex: 0,
      resultMsg: '',
      resultType: ''
    });
  },

  goHome: function () {
    wx.switchTab({ url: '/pages/home/index' });
  },

  onShareAppMessage: function () {
    return { title: '考试助手', path: '/pages/home/index' };
  }
});
