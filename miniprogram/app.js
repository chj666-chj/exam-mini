//app.js
const api = require('./utils/api.js')

App({
  onLaunch: function () {
    this.globalData = {};

    // 游客模式自动登录：仅在本地无 openid 时触发（首次启动）。
    // 如果用户已主动退出登录（openid 已清除），此处会重新以游客身份登录；
    // 如果用户已通过账号登录（openid 存在），则跳过，不覆盖已有登录态。
    var existingOpenid = wx.getStorageSync('openid') || '';
    if (existingOpenid) {
      console.log('[app] 已有登录态，跳过自动登录, openid:', existingOpenid);
      this.globalData.openid = existingOpenid;
      return;
    }

    api.callFunction({
      name: 'login',
      data: {},
      success: function (res) {
        console.log('[app] 游客自动登录成功: ', res.result)
      },
      fail: function (err) {
        console.error('[app] 游客自动登录失败，请确认 Django 后端已启动: http://127.0.0.1:8000', err)
      }
    })
  }
})
