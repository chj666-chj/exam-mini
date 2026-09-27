const api = require('../../utils/api.js');

Page({
  data: {
    oldPassword: '',
    newPassword: '',
    confirmPassword: '',
    errors: { old: '', new: '', confirm: '' },
    globalError: '',
    saving: false,
    showOld: false,
    showNew: false,
    showConfirm: false,
    // 强度提示
    strengthLevel: 0,
    strengthText: '',
    // 强制改密模式（管理员重置后首次登录）
    forceReset: false
  },

  onLoad: function (options) {
    if (options && options.force === '1') {
      this.setData({ forceReset: true });
    }
  },

  // ===== 输入处理 =====
  onOldInput: function (e) {
    this.setData({ oldPassword: e.detail.value || '', 'errors.old': '', globalError: '' });
  },
  onNewInput: function (e) {
    var pwd = e.detail.value || '';
    var level = this._checkStrength(pwd);
    this.setData({
      newPassword: pwd,
      'errors.new': '',
      globalError: '',
      strengthLevel: level,
      strengthText: ['弱', '中', '强', '很强'][level - 1] || ''
    });
  },
  onConfirmInput: function (e) {
    this.setData({ confirmPassword: e.detail.value || '', 'errors.confirm': '', globalError: '' });
  },

  toggleOld: function () { this.setData({ showOld: !this.data.showOld }); },
  toggleNew: function () { this.setData({ showNew: !this.data.showNew }); },
  toggleConfirm: function () { this.setData({ showConfirm: !this.data.showConfirm }); },

  // ===== 密码强度检测 =====
  _checkStrength: function (pwd) {
    if (!pwd) return 0;
    var score = 0;
    if (pwd.length >= 6) score++;
    if (pwd.length >= 10) score++;
    if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) score++;
    if (/\d/.test(pwd) && /[a-zA-Z]/.test(pwd)) score++;
    if (/[^a-zA-Z0-9]/.test(pwd)) score++;
    if (score >= 4) return 4;
    if (score >= 3) return 3;
    if (score >= 2) return 2;
    return 1;
  },

  // ===== 校验 =====
  validate: function () {
    var errors = { old: '', new: '', confirm: '' };
    var valid = true;

    if (!this.data.oldPassword) {
      errors.old = '请输入原密码';
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
    if (this.data.oldPassword && this.data.newPassword === this.data.oldPassword) {
      errors.new = '新密码不能与原密码相同';
      valid = false;
    }

    this.setData({ errors: errors });
    return valid;
  },

  // ===== 提交 =====
  handleSubmit: function () {
    if (this.data.saving) return;
    if (!this.validate()) return;

    var that = this;
    this.setData({ saving: true, globalError: '' });

    api.changePassword({
      oldPassword: this.data.oldPassword,
      newPassword: this.data.newPassword
    }).then(function () {
      that.setData({ saving: false });
      wx.showToast({ title: '密码修改成功', icon: 'success', duration: 1500 });
      setTimeout(function () {
        wx.navigateBack({ delta: 1 });
      }, 1200);
    }).catch(function (err) {
      that.setData({
        saving: false,
        globalError: (err && err.message) || '密码修改失败，请重试'
      });
    });
  }
});
