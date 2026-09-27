const api = require('../../utils/api.js');

Page({
  data: {
    account: '',
    nickname: '',
    avatarUrl: '',
    email: '',
    phone: '',
    address: '',
    createdAt: '',
    // 错误提示
    errors: { nickname: '', email: '', phone: '', address: '' },
    globalError: '',
    saving: false
  },

  onLoad: function () {
    this.loadProfile();
  },

  loadProfile: function () {
    var that = this;
    wx.showLoading({ title: '加载中...' });
    api.getProfile().then(function (info) {
      wx.hideLoading();
      that.setData({
        account: info.account || '',
        nickname: info.nickname || '',
        avatarUrl: info.avatarUrl || '',
        email: info.email || '',
        phone: info.phone || '',
        address: info.address || '',
        createdAt: info.createdAt || ''
      });
    }).catch(function (err) {
      wx.hideLoading();
      that.setData({
        globalError: (err && err.message) || '加载资料失败'
      });
    });
  },

  // ===== 头像上传 =====
  chooseAvatar: function () {
    var that = this;
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      sizeType: ['compressed'],
      success: function (res) {
        var tempPath = res.tempFiles[0].tempFilePath;
        // 先本地预览
        that.setData({ avatarUrl: tempPath });
        // 上传到后端
        wx.showLoading({ title: '上传中...' });
        api.uploadImage(tempPath).then(function (result) {
          wx.hideLoading();
          if (result && result.url) {
            // 拼接完整 URL（后端返回的是相对路径）
            var fullUrl = result.url;
            if (fullUrl.indexOf('http') !== 0) {
              fullUrl = api.API_BASE.replace('/api', '') + fullUrl;
            }
            that.setData({ avatarUrl: fullUrl });
            wx.showToast({ title: '头像上传成功', icon: 'success' });
          }
        }).catch(function (err) {
          wx.hideLoading();
          wx.showToast({ title: '头像上传失败', icon: 'none' });
          // 上传失败保持本地预览，用户保存时后端会收到本地路径（会被忽略）
        });
      }
    });
  },

  // ===== 输入处理 =====
  onNicknameInput: function (e) {
    this.setData({ nickname: e.detail.value || '', 'errors.nickname': '' });
  },
  onEmailInput: function (e) {
    this.setData({ email: e.detail.value || '', 'errors.email': '' });
  },
  onPhoneInput: function (e) {
    this.setData({ phone: e.detail.value || '', 'errors.phone': '' });
  },
  onAddressInput: function (e) {
    this.setData({ address: e.detail.value || '', 'errors.address': '' });
  },

  // ===== 校验 =====
  validate: function () {
    var errors = { nickname: '', email: '', phone: '', address: '' };
    var valid = true;

    if (this.data.nickname && this.data.nickname.length > 20) {
      errors.nickname = '昵称长度不能超过 20 位';
      valid = false;
    }
    if (this.data.email && !/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(this.data.email)) {
      errors.email = '邮箱格式不正确';
      valid = false;
    }
    if (this.data.phone && !/^1[3-9]\d{9}$/.test(this.data.phone)) {
      errors.phone = '手机号格式不正确（需 11 位数字）';
      valid = false;
    }
    if (this.data.address && this.data.address.length > 200) {
      errors.address = '地址长度不能超过 200 位';
      valid = false;
    }

    this.setData({ errors: errors });
    return valid;
  },

  // ===== 保存 =====
  handleSave: function () {
    if (this.data.saving) return;
    if (!this.validate()) return;

    var that = this;
    this.setData({ saving: true, globalError: '' });

    api.updateProfile({
      nickname: this.data.nickname,
      avatarUrl: this.data.avatarUrl,
      email: this.data.email,
      phone: this.data.phone,
      address: this.data.address
    }).then(function (info) {
      that.setData({ saving: false });
      wx.showToast({ title: '保存成功', icon: 'success', duration: 1500 });
      setTimeout(function () {
        wx.navigateBack({ delta: 1 });
      }, 1200);
    }).catch(function (err) {
      that.setData({
        saving: false,
        globalError: (err && err.message) || '保存失败，请重试'
      });
    });
  }
});
