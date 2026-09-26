var api = require('../../utils/api.js');
var md = require('../../utils/markdown.js');

Page({
  data: {
    article: {},
    contentNodes: [],
    images: [],
    isFavorited: false
  },

  onLoad: function (options) {
    var that = this;
    var id = options.id;
    this._articleId = id;
    var db = api.database();
    db.collection('articles').doc(id).get({
      success: function (res) {
        var article = res.data || {};
        var contentNodes = [];
        if (article.content) {
          contentNodes = md.parse(article.content);
        }
        var images = article.images || [];
        wx.setNavigationBarTitle({ title: article.title || '文章详情' });
        that.setData({
          article: article,
          contentNodes: contentNodes,
          images: images
        });
        // 加载收藏状态
        that.checkFavorite(id);
      },
      fail: function (err) {
        console.error('[文章详情] 查询失败', err);
        wx.showToast({ icon: 'none', title: '文章不存在' });
      }
    });
  },

  onShow: function () {
    // 从收藏列表取消收藏后返回时刷新状态
    if (this._articleId && this.data.article._id) {
      this.checkFavorite(this._articleId);
    }
  },

  // ===== 收藏 =====
  checkFavorite: function (articleId) {
    var that = this;
    api.isFavorited('article', articleId).then(function (isFav) {
      that.setData({ isFavorited: isFav });
    }).catch(function () {
      that.setData({ isFavorited: false });
    });
  },

  toggleFavorite: function () {
    var that = this;
    var article = this.data.article;

    // 防重锁
    if (this._favLock) return;
    this._favLock = true;

    var openid = wx.getStorageSync('openid');
    if (!openid) {
      wx.showToast({ icon: 'none', title: '请先登录' });
      this._favLock = false;
      return;
    }

    if (this.data.isFavorited) {
      // 取消收藏
      api.findFavorite('article', article._id).then(function (record) {
        if (!record) {
          that.setData({ isFavorited: false });
          that._favLock = false;
          return;
        }
        return api.removeFavorite(record._id);
      }).then(function () {
        that.setData({ isFavorited: false });
        wx.showToast({ icon: 'none', title: '已取消收藏' });
        that._favLock = false;
      }).catch(function (err) {
        console.error('[文章详情] 取消收藏失败', err);
        wx.showToast({ icon: 'none', title: '操作失败' });
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
        that.setData({ isFavorited: true });
        wx.showToast({ icon: 'none', title: '已收藏' });
        that._favLock = false;
      }).catch(function (err) {
        console.error('[文章详情] 收藏失败', err);
        wx.showToast({ icon: 'none', title: '收藏失败' });
        that._favLock = false;
      });
    }
  },

  previewImage: function (e) {
    var current = e.currentTarget.dataset.src;
    wx.previewImage({
      current: current,
      urls: this.data.images
    });
  }
});
