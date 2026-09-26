var api = require('../../utils/api.js');

Page({
  data: {
    docId: '',
    doc: null,
    tocTree: [],
    loading: true,
    totalSections: 0
  },

  onLoad: function (options) {
    this.setData({ docId: options.id || '' });
    if (options.id) {
      this.loadDocument(options.id);
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
        doc.typeColor = that.getTypeColor(doc.type);

        var tocTree = that.buildToc(doc);
        var totalSections = 0;
        tocTree.forEach(function (node) {
          totalSections++;
          if (node.children) totalSections += node.children.length;
        });

        that.setData({
          doc: doc,
          tocTree: tocTree,
          totalSections: totalSections,
          loading: false
        });

        wx.setNavigationBarTitle({ title: doc.title || '目录' });
      },
      fail: function (err) {
        console.error('[知识库目录] 加载失败', err);
        that.setData({ loading: false });
        wx.showToast({ icon: 'none', title: '加载失败' });
      }
    });
  },

  buildToc: function (doc) {
    if (doc.toc && doc.toc.length > 0) {
      return doc.toc.map(function (entry) {
        return {
          title: entry.title,
          page: entry.page || 0,
          level: 1,
          expanded: false,
          children: (entry.children || []).map(function (child) {
            return {
              title: child.title,
              page: child.page || 0,
              level: 2,
              children: (child.children || []).map(function (grandchild) {
                return {
                  title: grandchild.title,
                  page: grandchild.page || 0,
                  level: 3
                };
              })
            };
          })
        };
      });
    }

    if (doc.content) {
      return this.parseContentToc(doc.content);
    }

    return [];
  },

  parseContentToc: function (content) {
    var lines = content.split('\n');
    var tree = [];
    var l1Node = null;
    var l2Node = null;

    lines.forEach(function (line) {
      var trimmed = line.trim();
      if (!trimmed) return;

      var match = trimmed.match(/^(#{1,3})\s+(.+)/);
      if (!match) return;

      var level = match[1].length;
      var title = match[2];

      if (level === 1) {
        l1Node = { title: title, page: 0, level: 1, expanded: false, children: [] };
        l2Node = null;
        tree.push(l1Node);
      } else if (level === 2 && l1Node) {
        l2Node = { title: title, page: 0, level: 2, children: [] };
        l1Node.children.push(l2Node);
      } else if (level === 3 && l2Node) {
        l2Node.children.push({ title: title, page: 0, level: 3 });
      } else if (level === 3 && l1Node) {
        l1Node.children.push({ title: title, page: 0, level: 3 });
      }
    });

    return tree;
  },

  toggleNode: function (e) {
    var idx = e.currentTarget.dataset.idx;
    if (idx === undefined || idx === null) return;
    var tree = this.data.tocTree.slice();
    tree[idx].expanded = !tree[idx].expanded;
    this.setData({ tocTree: tree });
  },

  openSection: function (e) {
    var docId = this.data.docId;
    var section = e.currentTarget.dataset.section || '';
    var url = '/pages/knowledge/detail?id=' + docId;
    if (section) url += '&section=' + encodeURIComponent(section);
    wx.navigateTo({ url: url });
  },

  readAll: function () {
    wx.navigateTo({ url: '/pages/knowledge/detail?id=' + this.data.docId });
  },

  goBack: function () {
    wx.navigateBack();
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

  onShareAppMessage: function () {
    var doc = this.data.doc || {};
    return {
      title: doc.title || '考试助手 - 知识库',
      path: '/pages/knowledge/toc?id=' + this.data.docId
    };
  }
});
