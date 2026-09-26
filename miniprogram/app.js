//app.js
const api = require('./utils/api.js')

App({
  onLaunch: function () {
    this.globalData = {};

    // 登录：从 Django 后端获取 openid（本地开发返回演示账号，
    // 该账号在数据库中有答题记录，便于查看「答题记录/错题本」演示数据）
    api.callFunction({
      name: 'login',
      data: {},
      success: function (res) {
        console.log('[login] 成功: ', res.result)
      },
      fail: function (err) {
        console.error('[login] 失败，请确认 Django 后端已启动: http://127.0.0.1:8000', err)
      }
    })
  }
})
