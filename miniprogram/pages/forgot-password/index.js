const api = require('../../utils/api.js');

Page({
  data: {
    step: 1,          // 1=输入用户名+选择渠道, 2=输入验证码+新密码
    account: '',
    channel: 'email', // email | phone
    targetHint: '',   // 遮罩后的发送目标
    devCode: '',      // 开发环境返回的验证码
    code: '',
    newPassword: '',
    confirmPassword: '',
    errors: { account: '', code: '', new: '', confirm: '' },
    globalError: '',
    sending: false,
    resetting: false,
    countdown: 0
  },

  onLoad: function (options) {
    if (options && options.account) {
      this.setData({ account: options.account });
    }
  },

  // ===== Step 1 =====
  onAccountInput: function (e) {
    this.setData({ account: e.detail.value || '', 'errors.account': '' });
  },

  selectChannel: function (e) {
    this.setData({ channel: e.currentTarget.dataset.channel });
  },

  handleSendCode: function () {
    if (this.data.sending) return;
    if (!this.data.account) {
      this.setData({ 'errors.account': '请输入用户名' });
      return;
    }

    var that = this;
    this.setData({ sending: true, globalError: '' });

    api.forgotPassword({
      account: this.data.account,
      channel: this.data.channel
    }).then(function (info) {
      that.setData({ sending: false });
      if (info.devCode) {
        that.setData({
          devCode: info.devCode,
          targetHint: info.target || '',
          step: 2
        });
        wx.showToast({
          title: '验证码已发送',
          icon: 'success',
          duration: 1500
        });
      } else {
        that.setData({
          targetHint: info.target || '',
          step: 2
        });
        wx.showToast({
          title: '验证码已发送至绑定' + (that.data.channel === 'email' ? '邮箱' : '手机号'),
          icon: 'none',
          duration: 2000
        });
      }
      // 开始倒计时
      that._startCountdown();
    }).catch(function (err) {
      that.setData({
        sending: false,
        globalError: (err && err.message) || '发送验证码失败'
      });
    });
  },

  _startCountdown: function () {
    var that = this;
    this.setData({ countdown: 60 });
    var timer = setInterval(function () {
      var cd = that.data.countdown - 1;
      that.setData({ countdown: cd });
      if (cd <= 0) clearInterval(timer);
    }, 1000);
  },

  // ===== Step 2 =====
  onCodeInput: function (e) {
    this.setData({ code: e.detail.value || '', 'errors.code': '' });
  },
  onNewInput: function (e) {
    this.setData({ newPassword: e.detail.value || '', 'errors.new': '' });
  },
  onConfirmInput: function (e) {
    this.setData({ confirmPassword: e.detail.value || '', 'errors.confirm': '' });
  },

  handleReset: function () {
    if (this.data.resetting) return;

    var errors = { account: '', code: '', new: '', confirm: '' };
    var valid = true;

    if (!this.data.code) {
      errors.code = '请输入验证码';
      valid = false;
    }
    if (!this.data.newPassword) {
      errors.new = '请输入新密码';
      valid = false;
    } else if (this.data.newPassword.length < 6 || this.data.newPassword.length > 32) {
      errors.new = '密码长度需 6-32 位';
      valid = false;
    } else if (!/(?=.*[a-zA-Z])(?=.*\d)/.test(this.data.newPassword)) {
      errors.new = '密码需包含字母和数字';
      valid = false;
    }
    if (!this.data.confirmPassword) {
      errors.confirm = '请再次输入新密码';
      valid = false;
    } else if (this.data.confirmPassword !== this.data.newPassword) {
      errors.confirm = '两次输入的密码不一致';
      valid = false;
    }

    this.setData({ errors: errors });
    if (!valid) return;

    var that = this;
    this.setData({ resetting: true, globalError: '' });

    api.resetPassword({
      account: this.data.account,
      code: this.data.code,
      newPassword: this.data.newPassword
    }).then(function () {
      that.setData({ resetting: false });
      wx.showToast({ title: '密码重置成功', icon: 'success', duration: 1500 });
      setTimeout(function () {
        wx.navigateBack({ delta: 1 });
      }, 1200);
    }).catch(function (err) {
      that.setData({
        resetting: false,
        globalError: (err && err.message) || '密码重置失败，请重试'
      });
    });
  },

  backToStep1: function () {
    this.setData({ step: 1, code: '', newPassword: '', confirmPassword: '', globalError: '' });
  }
});
