var api = require('../../utils/api.js');
var util = require('../../utils/util.js');
var app = getApp();

Page({
  data: {
    keyword: '',
    activeCategory: 'all',
    categories: [
      { key: 'all', label: '全部', icon: '📚' },
      { key: 'textbook', label: '教材', icon: '📖' },
      { key: 'summary', label: '总结', icon: '📝' },
      { key: 'notes', label: '笔记', icon: '🖍' },
      { key: 'quickref', label: '速记', icon: '⚡' }
    ],
    docList: [],
    filteredList: [],
    favCount: 0,
    loading: true,
    favIds: {}
  },

  onShow: function () {
    this.loadDocuments();
    this.loadFavorites();
  },

  onPullDownRefresh: function () {
    var that = this;
    this.loadDocuments(function () {
      that.loadFavorites(function () {
        wx.stopPullDownRefresh();
      });
    });
  },

  loadDocuments: function (done) {
    var that = this;
    var database = api.database();

    database.collection('knowledgebase').get({
      success: function (res) {
        var list = (res.data || []).map(function (doc) {
          var tocCount = 0;
          if (doc.toc && doc.toc.length > 0) {
            doc.toc.forEach(function (sec) {
              tocCount++;
              if (sec.children) tocCount += sec.children.length;
            });
          }

          return {
            _id: doc._id,
            title: doc.title || '未命名文档',
            type: doc.type || 'textbook',
            typeLabel: that.getTypeLabel(doc.type),
            typeIcon: that.getTypeIcon(doc.type),
            typeColor: that.getTypeColor(doc.type),
            category: doc.category || '',
            summary: doc.summary || '',
            pages: doc.pages || 0,
            views: doc.views || 0,
            cover: doc.cover || '',
            createTime: doc.createTime || '',
            sortWeight: doc.sortWeight || 0,
            tocCount: tocCount
          };
        });

        list.sort(function (a, b) {
          return (b.sortWeight || 0) - (a.sortWeight || 0);
        });

        that.setData({ docList: list, loading: false });
        that.applyFilter();
        if (done) done();
      },
      fail: function (err) {
        console.error('[知识库] 加载失败', err);
        that.setData({ loading: false });
        if (done) done();
      }
    });
  },

  loadFavorites: function (done) {
    var that = this;
    var openid = wx.getStorageSync('openid');
    if (!openid) {
      if (done) done();
      return;
    }

    var database = api.database();
    database.collection('favorites').where({ _openid: openid, docType: 'knowledge' }).get({
      success: function (res) {
        var favs = res.data || [];
        var favIds = {};
        favs.forEach(function (f) {
          if (f.docId) favIds[f.docId] = true;
        });
        that.setData({ favCount: favs.length, favIds: favIds });
        if (done) done();
      },
      fail: function () {
        if (done) done();
      }
    });
  },

  getTypeLabel: function (type) {
    var map = { textbook: '教材', summary: '总结', notes: '笔记', quickref: '速记' };
    return map[type] || '文档';
  },

  getTypeIcon: function (type) {
    var map = { textbook: '📖', summary: '📝', notes: '🖍', quickref: '⚡' };
    return map[type] || '📄';
  },

  getTypeColor: function (type) {
    var map = {
      textbook: 'type-amber',
      summary: 'type-purple',
      notes: 'type-coral',
      quickref: 'type-teal'
    };
    return map[type] || 'type-blue';
  },

  onSearchInput: function (e) {
    this.setData({ keyword: e.detail.value });
    this.applyFilter();
  },

  onClearSearch: function () {
    this.setData({ keyword: '' });
    this.applyFilter();
  },

  onCategoryTap: function (e) {
    var key = e.currentTarget.dataset.key;
    this.setData({ activeCategory: key });
    this.applyFilter();
  },

  applyFilter: function () {
    var list = this.data.docList.slice();
    var cat = this.data.activeCategory;
    var kw = this.data.keyword.trim().toLowerCase();

    if (cat !== 'all') {
      list = list.filter(function (doc) {
        return doc.type === cat;
      });
    }

    if (kw) {
      list = list.filter(function (doc) {
        return (doc.title || '').toLowerCase().indexOf(kw) > -1 ||
               (doc.summary || '').toLowerCase().indexOf(kw) > -1 ||
               (doc.category || '').toLowerCase().indexOf(kw) > -1;
      });
    }

    this.setData({ filteredList: list });
  },

  openToc: function (e) {
    var id = e.currentTarget.dataset.id;
    if (!id) return;
    wx.navigateTo({ url: '/pages/knowledge/toc?id=' + id });
  },

  goFavorites: function () {
    wx.navigateTo({ url: '/pages/favorites/index?from=knowledge' });
  },

  toggleFav: function (e) {
    var that = this;
    var id = e.currentTarget.dataset.id;
    if (!id) return;

    var openid = wx.getStorageSync('openid');
    if (!openid) {
      wx.showToast({ icon: 'none', title: '请先登录' });
      return;
    }

    var isFav = this.data.favIds[id];
    var database = api.database();

    if (isFav) {
      database.collection('favorites').where({ _openid: openid, docId: id, docType: 'knowledge' }).get({
        success: function (res) {
          var docs = res.data || [];
          if (docs.length > 0) {
            wx.request({
              url: api.API_BASE + '/collections/favorites/' + docs[0]._id + '/',
              method: 'DELETE',
              header: { 'Content-Type': 'application/json', 'X-Openid': openid },
              success: function () {
                var favIds = that.data.favIds;
                delete favIds[id];
                that.setData({ favIds: favIds, favCount: that.data.favCount - 1 });
                wx.showToast({ icon: 'none', title: '已取消收藏' });
              }
            });
          }
        }
      });
    } else {
      var doc = this.data.docList.find(function (d) { return d._id === id; });
      database.collection('favorites').add({
        data: {
          favType: 'knowledge',
          docId: id,
          docType: 'knowledge',
          docTitle: doc ? doc.title : '',
          docTypeLabel: doc ? doc.typeLabel : '',
          createTime: util.getTime(new Date())
        },
        success: function () {
          var favIds = that.data.favIds;
          favIds[id] = true;
          that.setData({ favIds: favIds, favCount: that.data.favCount + 1 });
          wx.showToast({ icon: 'none', title: '已收藏' });
        },
        fail: function () {
          wx.showToast({ icon: 'none', title: '收藏失败' });
        }
      });
    }
  },

  onShareAppMessage: function () {
    return {
      title: '考试助手 - 知识库',
      path: '/pages/knowledge/index'
    };
  }
});
