const app = getApp();
Page({

  /**
   * 页面的初始数据
   */
  data: {
    openid: '',
    nickName: '',
    avatarUrl: '',
    userInfo: {
      nickName: '',
      avatarUrl: '',
    }
  },

  /**
   * 生命周期函数--监听页面加载
   * 说明：原版本会请求外部服务(xiaomutong.com.cn)获取用户信息，
   * 本地化改造后直接使用 app.js 启动时从 Django 后端获取的 openid。
   */
  onLoad: function (options) {
    let openid = wx.getStorageSync('openid') || app.globalData.openid || '';
    this.setData({
      openid: openid
    })
  },
  bindMyHistory: function(){
    let url = '/pages/history/index';
    wx.navigateTo({
      url: url
    })
  },
  bindMyStudy: function(){
    let url = '/pages/study/index';
    wx.navigateTo({
      url: url
    })
  },
  bindgopay: function(){
    let url = '/pages/pay/index';
    wx.navigateTo({
      url: url
    })
  },
  bindgoabout: function(){
    let url = '/pages/about/index';
    wx.navigateTo({
      url: url
    })
  },
  bindgorule: function(){
    let url = '/pages/rule/index';
    wx.navigateTo({
      url: url
    })
  },
  /**
   * 生命周期函数--监听页面初次渲染完成
   */
  onReady: function () {

  },

  /**
   * 生命周期函数--监听页面显示
   */
  onShow: function () {

  },

  /**
   * 生命周期函数--监听页面隐藏
   */
  onHide: function () {

  },

  /**
   * 生命周期函数--监听页面卸载
   */
  onUnload: function () {

  },

  /**
   * 页面相关事件处理函数--监听用户下拉动作
   */
  onPullDownRefresh: function () {

  },

  /**
   * 页面上拉触底的处理函数
   */
  onReachBottom: function () {

  },

  /**
   * 用户点击右上角分享
   */
  onShareAppMessage: function () {

  }
})
