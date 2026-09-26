/**
 * md-editor 组件 —— 轻量级 Markdown 编辑器（支持编辑/预览切换）
 *
 * Properties:
 *   value      - 编辑器内容（双向绑定）
 *   placeholder - 占位提示文本
 *
 * Events:
 *   input - 内容变化时触发，e.detail.value 为最新内容
 */
var api = require('../../utils/api.js');
var md = require('../../utils/markdown.js');

Component({
  properties: {
    value: { type: String, value: '' },
    placeholder: { type: String, value: '请输入正文...' }
  },

  data: {
    mode: 'edit',
    cursor: 0,
    previewNodes: [],
    toolbar: [
      { type: 'h1', label: 'H1' },
      { type: 'h2', label: 'H2' },
      { type: 'h3', label: 'H3' },
      { type: 'bold', label: '加粗' },
      { type: 'italic', label: '斜体' },
      { type: 'image', label: '图片' },
      { type: 'list', label: '列表' },
      { type: 'table', label: '表格' },
      { type: 'quote', label: '引用' },
      { type: 'code', label: '代码' }
    ]
  },

  observers: {
    'value': function (val) {
      if (this.data.mode === 'preview') {
        this.setData({ previewNodes: md.parse(val || '') });
      }
    }
  },

  methods: {
    switchMode: function (e) {
      var mode = e.currentTarget.dataset.mode;
      if (mode === this.data.mode) return;
      if (mode === 'preview') {
        this.setData({ mode: 'preview', previewNodes: md.parse(this.data.value || '') });
      } else {
        this.setData({ mode: 'edit' });
      }
    },

    onInput: function (e) {
      this.setData({ value: e.detail.value, cursor: e.detail.cursor || 0 });
      this.triggerEvent('input', { value: e.detail.value });
    },

    onBlur: function (e) {
      this.setData({ cursor: e.detail.cursor || (e.detail.value ? e.detail.value.length : 0) });
    },

    insertSyntax: function (e) {
      var type = e.currentTarget.dataset.type;
      var syntax = '';
      switch (type) {
        case 'h1': syntax = '# '; break;
        case 'h2': syntax = '## '; break;
        case 'h3': syntax = '### '; break;
        case 'bold': syntax = '****'; break;
        case 'italic': syntax = '**'; break;
        case 'list': syntax = '- '; break;
        case 'quote': syntax = '> '; break;
        case 'code': syntax = '``'; break;
        case 'image': this.chooseImage(); return;
        case 'table': this.insertTable(); return;
        default: return;
      }
      this._insertAtCursor(syntax);
    },

    chooseImage: function () {
      var self = this;
      wx.chooseMedia({
        count: 1,
        mediaType: ['image'],
        sizeType: ['compressed'],
        success: function (res) {
          var tempFilePath = res.tempFiles[0].tempFilePath;
          wx.showLoading({ title: '上传中...' });
          api.uploadImage(tempFilePath).then(function (data) {
            wx.hideLoading();
            var url = data.url || '';
            if (url && url.indexOf('http') !== 0) {
              url = api.API_BASE.replace('/api', '') + url;
            }
            self._insertAtCursor('\n![](' + url + ')\n');
          }).catch(function (err) {
            wx.hideLoading();
            console.error('[md-editor] 图片上传失败', err);
            wx.showToast({ icon: 'none', title: '图片上传失败' });
          });
        }
      });
    },

    insertTable: function () {
      var template = '\n| 列1 | 列2 | 列3 |\n|---|---|---|\n| 内容 | 内容 | 内容 |\n';
      this._insertAtCursor(template);
    },

    _insertAtCursor: function (text) {
      var value = this.data.value || '';
      var cursor = this.data.cursor || value.length;
      var newValue = value.slice(0, cursor) + text + value.slice(cursor);
      this.setData({ value: newValue, cursor: cursor + text.length });
      this.triggerEvent('input', { value: newValue });
    }
  }
});
