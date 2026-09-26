/**
 * 智能客服 / 答疑页
 * 气泡对话式 UI（同知识库问答），支持常见问题快捷入口与推荐追问
 * 发送 → api.aiCsChat(message, history)
 */
var api = require('../../utils/api.js');
var md = require('../../utils/markdown.js');

// 顶常见问题快捷入口
var QUICK_QUESTIONS = [
  '如何开始练习？',
  '错题怎么复习？',
  '如何查看学习报告？',
  '账号登录有问题怎么办？'
];

Page({
  data: {
    messages: [],
    quickQuestions: QUICK_QUESTIONS,
    scrollIntoView: '',
    inputValue: '',
    sending: false,
    // 模型选择
    models: [],
    modelNames: [],
    modelIndex: 0,
    selectedModelId: ''
  },

  onLoad: function () {
    this._aiIndex = null;
    this.loadModels();
  },

  /**
   * 加载可用模型，默认选中：本地选择 → 我的默认 → 全局默认 → 第一个
   */
  loadModels: function () {
    var self = this;
    api.aiModelList().then(function (res) {
      var data = res && res.data ? res.data : (res || {});
      var models = data.list || [];
      var meta = data.meta || {};
      var names = models.map(function (m) { return m.name + '（' + m.model + '）'; });
      var savedId = wx.getStorageSync('ai_selected_model_id') || '';
      var index = 0;
      var targetId = '';
      var order = [savedId, meta.userDefaultModelId, meta.defaultModelId];
      for (var k = 0; k < order.length; k++) {
        if (!order[k]) continue;
        for (var i = 0; i < models.length; i++) {
          if (models[i]._id === order[k]) { index = i; targetId = models[i]._id; break; }
        }
        if (targetId) break;
      }
      if (!targetId && models.length) { targetId = models[0]._id; index = 0; }
      self.setData({
        models: models,
        modelNames: names,
        modelIndex: index,
        selectedModelId: targetId
      });
    }).catch(function (err) {
      console.error('[智能客服] 模型列表加载失败', err);
    });
  },

  onModelChange: function (e) {
    var index = parseInt(e.detail.value) || 0;
    var model = this.data.models[index];
    if (!model) return;
    this.setData({ modelIndex: index, selectedModelId: model._id });
    wx.setStorageSync('ai_selected_model_id', model._id);
    wx.showToast({ icon: 'none', title: '已切换为 ' + model.name });
  },

  goModelConfig: function () {
    wx.navigateTo({ url: '/pages/ai-config/index' });
  },

  onInput: function (e) {
    this.setData({ inputValue: e.detail.value });
  },

  onSendInput: function () {
    this.doChat(this.data.inputValue);
  },

  onTapQuick: function (e) {
    this.doChat(e.currentTarget.dataset.q);
  },

  onTapSuggestion: function (e) {
    this.doChat(e.currentTarget.dataset.q);
  },

  /**
   * 发送对话
   */
  doChat: function (message) {
    message = (message || '').trim();
    if (!message) {
      wx.showToast({ icon: 'none', title: '请输入内容' });
      return;
    }
    if (this.data.sending) return;

    var that = this;
    // 取发送前的历史（不含本次新消息）
    var history = this._buildHistory();
    var messages = this.data.messages.slice();
    messages.push({ role: 'user', text: message, nodes: [], suggestions: [] });
    messages.push({ role: 'ai', text: '', nodes: [], suggestions: [], loading: true });
    this._aiIndex = messages.length - 1;
    this.setData({ messages: messages, inputValue: '', sending: true });
    this._scrollToBottom();

    api.aiCsChat(message, history, this.data.selectedModelId).then(function (res) {
      // 后端统一返回 {code, message, data} 信封，这里兼容两种形态
      var payload = (res && res.data) ? res.data : (res || {});
      var reply = payload.reply || '抱歉，我暂时没办法回答这个问题，请换个问法或联系人工客服。';
      var suggestions = payload.suggestions || [];
      that._updateAiMessage(reply, suggestions);
    }, function (err) {
      var msg = '回复失败，请稍后重试';
      if (err && err.data && err.data.message) {
        msg = err.data.message;
      }
      that._updateAiMessage(msg, []);
      wx.showToast({ icon: 'none', title: msg });
    });
  },

  /**
   * 构造对话历史（最多最近 6 条）
   */
  _buildHistory: function () {
    var history = [];
    this.data.messages.forEach(function (m) {
      history.push({
        role: m.role === 'user' ? 'user' : 'assistant',
        content: m.text || ''
      });
    });
    if (history.length > 6) {
      history = history.slice(-6);
    }
    return history;
  },

  _updateAiMessage: function (text, suggestions) {
    var messages = this.data.messages.slice();
    var idx = this._aiIndex;
    if (idx == null || !messages[idx]) {
      this.setData({ sending: false });
      return;
    }
    messages[idx] = {
      role: 'ai',
      text: text,
      nodes: md.parse(text),
      suggestions: suggestions || [],
      loading: false
    };
    this.setData({ messages: messages, sending: false });
    this._scrollToBottom();
  },

  /**
   * 提交反馈（跳转 feedback 页，无页面时 toast 兜底）
   */
  onSubmitFeedback: function () {
    wx.navigateTo({
      url: '/pages/feedback/index',
      fail: function () {
        wx.showToast({ icon: 'none', title: '反馈已记录，感谢你的建议' });
      }
    });
  },

  _scrollToBottom: function () {
    var len = this.data.messages.length;
    if (!len) return;
    this.setData({ scrollIntoView: 'msg-' + (len - 1) });
  },

  onUnload: function () {
    if (this._jobTimer) {
      clearInterval(this._jobTimer);
      this._jobTimer = null;
    }
  }
});
