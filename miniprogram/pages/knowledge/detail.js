var api = require('../../utils/api.js');
var util = require('../../utils/util.js');

Page({
  data: {
    docId: '',
    doc: null,
    loading: true,
    isFavorited: false,
    fontSizeClass: 'fs-medium',
    fontSize: 'medium',
    contentParagraphs: [],
    pendingSection: ''
  },

  onLoad: function (options) {
    var settings = wx.getStorageSync('quiz_settings') || {};
    var fontSizeMap = { small: 'fs-small', medium: 'fs-medium', large: 'fs-large' };
    var fontSizeClass = fontSizeMap[settings.fontSize] || 'fs-medium';

    this.setData({
      docId: options.id || '',
      fontSizeClass: fontSizeClass,
      fontSize: settings.fontSize || 'medium',
      pendingSection: options.section ? decodeURIComponent(options.section) : ''
    });

    if (options.id) {
      this.loadDocument(options.id);
      this.checkFavorite(options.id);
    }
  },

  loadDocument: function (id) {
    var that = this;
    var database = api.database();

    database.collection('knowledgebase').doc(id).get({
      success: function (res) {
        var doc = res.data || null;
        if (!doc) {
          that.setData({ loading: false });
          wx.showToast({ icon: 'none', title: '文档不存在' });
          return;
        }

        doc.typeLabel = that.getTypeLabel(doc.type);
        doc.typeIcon = that.getTypeIcon(doc.type);

        var paragraphs = [];
        if (doc.content) {
          paragraphs = doc.content.split('\n').filter(function (p) {
            return p.trim().length > 0;
          }).map(function (p) {
            var trimmed = p.trim();
            var isHeading = /^#{1,3}\s/.test(trimmed);
            var isHighlight = /^\*\*.+\*\*$/.test(trimmed);
            var level = 0;
            var text = trimmed;

            if (isHeading) {
              var match = trimmed.match(/^(#{1,3})\s+(.+)/);
              if (match) {
                level = match[1].length;
                text = match[2];
              }
            } else if (isHighlight) {
              text = trimmed.replace(/^\*\*/, '').replace(/\*\*$/, '');
              level = 4;
            }

            return { text: text, level: level };
          });
        }

        that.setData({
          doc: doc,
          contentParagraphs: paragraphs,
          loading: false
        });

        that.incrementViews(id);

        if (that.data.pendingSection) {
          var target = that.data.pendingSection;
          that.setData({ pendingSection: '' });
          setTimeout(function () {
            that.scrollToSection(target, paragraphs);
          }, 500);
        }
      },
      fail: function (err) {
        console.error('[知识库详情] 加载失败', err);
        that.setData({ loading: false });
        wx.showToast({ icon: 'none', title: '加载失败' });
      }
    });
  },

  incrementViews: function (id) {
    var database = api.database();
    database.collection('knowledgebase').where({ _id: id }).get({
      success: function (res) {
        var docs = res.data || [];
        if (docs.length > 0) {
          var doc = docs[0];
          var newViews = (doc.views || 0) + 1;
          var openid = wx.getStorageSync('openid');
          wx.request({
            url: api.API_BASE + '/collections/knowledgebase/' + doc._id + '/',
            method: 'PUT',
            header: { 'Content-Type': 'application/json', 'X-Openid': openid || 'system' },
            data: { views: newViews }
          });
        }
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

  checkFavorite: function (docId) {
    var that = this;
    var openid = wx.getStorageSync('openid');
    if (!openid || !docId) return;

    var database = api.database();
    database.collection('favorites').where({ _openid: openid, docId: docId, docType: 'knowledge' }).get({
      success: function (res) {
        var isFav = (res.data || []).length > 0;
        that.setData({ isFavorited: isFav });
      }
    });
  },

  toggleFavorite: function () {
    var that = this;
    var openid = wx.getStorageSync('openid');
    var doc = this.data.doc;
    if (!openid || !doc) {
      wx.showToast({ icon: 'none', title: '请先登录' });
      return;
    }

    var database = api.database();

    if (this.data.isFavorited) {
      database.collection('favorites').where({ _openid: openid, docId: doc._id, docType: 'knowledge' }).get({
        success: function (res) {
          var docs = res.data || [];
          if (docs.length > 0) {
            wx.request({
              url: api.API_BASE + '/collections/favorites/' + docs[0]._id + '/',
              method: 'DELETE',
              header: { 'Content-Type': 'application/json', 'X-Openid': openid },
              success: function () {
                that.setData({ isFavorited: false });
                wx.showToast({ icon: 'none', title: '已取消收藏' });
              }
            });
          }
        }
      });
    } else {
      database.collection('favorites').add({
        data: {
          favType: 'knowledge',
          docId: doc._id,
          docType: 'knowledge',
          docTitle: doc.title || '',
          docTypeLabel: doc.typeLabel || '',
          createTime: util.getTime(new Date())
        },
        success: function () {
          that.setData({ isFavorited: true });
          wx.showToast({ icon: 'none', title: '已收藏' });
        },
        fail: function () {
          wx.showToast({ icon: 'none', title: '收藏失败' });
        }
      });
    }
  },

  changeFontSize: function (e) {
    var size = e.currentTarget.dataset.size;
    var sizeMap = { small: 'fs-small', medium: 'fs-medium', large: 'fs-large' };
    this.setData({
      fontSize: size,
      fontSizeClass: sizeMap[size] || 'fs-medium'
    });
  },

  scrollToSection: function (title, paragraphs) {
    var ps = paragraphs || this.data.contentParagraphs;
    var matchIdx = -1;
    for (var i = 0; i < ps.length; i++) {
      if (ps[i].level > 0 && ps[i].level <= 3 && ps[i].text === title) {
        matchIdx = i;
        break;
      }
    }
    if (matchIdx >= 0) {
      this.scrollToIndex(matchIdx);
    }
  },

  scrollToIndex: function (index) {
    wx.createSelectorQuery()
      .select('#kb-p-' + index)
      .boundingClientRect()
      .selectViewport()
      .scrollOffset()
      .exec(function (res) {
        if (res[0] && res[1]) {
          var scrollTop = res[1].scrollTop + res[0].top - 80;
          wx.pageScrollTo({ scrollTop: scrollTop, duration: 300 });
        }
      });
  },

  goToc: function () {
    wx.navigateBack();
  },

  onShareAppMessage: function () {
    var doc = this.data.doc || {};
    return {
      title: doc.title || '考试助手 - 知识库',
      path: '/pages/knowledge/detail?id=' + this.data.docId
    };
  }
});
