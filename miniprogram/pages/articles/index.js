var api = require('../../utils/api.js');

Page({
  data: {
    list: [],
    favIds: {}
  },

  onShow: function () {
    this.load();
  },

  onPullDownRefresh: function () {
    var that = this;
    this.load(function () {
      that.loadFavorites(function () {
        wx.stopPullDownRefresh();
      });
    });
  },

  load: function (done) {
    var that = this;
    var db = api.database();
    db.collection('articles').get({
      success: function (res) {
        var list = (res.data || []).map(function (item) {
          var images = item.images || [];
          var tags = item.tags || [];
          return Object.assign({}, item, {
            displayImages: images.slice(0, 3),
            displayTags: tags.slice(0, 3),
            isHot: (item.views || 0) > 1000,
            imageCount: Math.min(images.length, 3)
          });
        });
        // 按 views 降序排序
        list.sort(function (a, b) { return (b.views || 0) - (a.views || 0); });
        that.setData({ list: list });
        // 加载完文章后加载收藏状态
        that.loadFavorites(done);
      },
      fail: function (err) {
        console.error('[文章] 查询失败', err);
        wx.showToast({ icon: 'none', title: '文章加载失败' });
        if (done) done();
      }
    });
  },

  // ===== 收藏 =====
  loadFavorites: function (done) {
    var that = this;
    api.getFavorites('article').then(function (favs) {
      var favIds = {};
      favs.forEach(function (f) {
        if (f.articleId) favIds[f.articleId] = f._id;
      });
      that.setData({ favIds: favIds });
      if (done) done();
    }).catch(function (err) {
      console.error('[文章] 加载收藏状态失败', err);
      if (done) done();
    });
  },

  toggleFav: function (e) {
    var that = this;
    var id = e.currentTarget.dataset.id;

    // 防重锁：阻止重复点击
    if (this._favLock) return;
    this._favLock = true;

    var openid = wx.getStorageSync('openid');
    if (!openid) {
      wx.showToast({ icon: 'none', title: '请先登录' });
      this._favLock = false;
      return;
    }

    var article = this.data.list.find(function (a) { return a._id === id; });
    if (!article) {
      this._favLock = false;
      return;
    }

    var isFav = !!this.data.favIds[id];
    var favIds = this.data.favIds;

    if (isFav) {
      // 取消收藏
      var favId = favIds[id];
      api.removeFavorite(favId).then(function () {
        delete favIds[id];
        that.setData({ favIds: favIds });
        wx.showToast({ icon: 'none', title: '已取消收藏' });
        that._favLock = false;
      }).catch(function (err) {
        console.error('[文章] 取消收藏失败', err);
        wx.showToast({ icon: 'none', title: '操作失败，请重试' });
        that._favLock = false;
      });
    } else {
      // 添加收藏
      api.addFavorite('article', {
        articleId: article._id,
        articleTitle: article.title || '',
        articleSummary: article.summary || '',
        articleAuthor: article.author || '',
        createTime: require('../../utils/util.js').getTime(new Date())
      }).then(function () {
        // 重新加载收藏列表以获取新的 _id
        that.loadFavorites(function () {
          wx.showToast({ icon: 'none', title: '已收藏' });
          that._favLock = false;
        });
      }).catch(function (err) {
        console.error('[文章] 收藏失败', err);
        wx.showToast({ icon: 'none', title: '收藏失败，请重试' });
        that._favLock = false;
      });
    }
  },

  openDetail: function (e) {
    var id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: '/pages/article/detail?id=' + id });
  },

  openCreate: function () {
    wx.navigateTo({ url: '/pages/article/create' });
  }
});
