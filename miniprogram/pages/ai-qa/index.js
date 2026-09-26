/**
 * 知识库智能问答页
 * 用户提问 → 后端 RAG 检索知识库 → LLM 生成回答（Markdown 渲染）
 * 气泡对话式 UI：用户气泡右对齐、AI 气泡左对齐，AI 气泡下方展示来源标签
 */
var api = require('../../utils/api.js');
var md = require('../../utils/markdown.js');

// 首次进入展示的推荐问题
var RECOMMEND_QUESTIONS = [
  '如何制定高效的备考计划？',
  '常考的重点知识点有哪些？',
  '做题总是粗心怎么办？'
];

Page({
  data: {
    messages: [],
    recommendQuestions: RECOMMEND_QUESTIONS,
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
    // 初始化时预留 AI 消息索引
    this._aiIndex = null;
    this.loadModels();
  },

  onShow: function () {
    // 从模型配置页返回后刷新列表
    if (this._needRefreshModels) {
      this._needRefreshModels = false;
      this.loadModels();
    }
  },

  /**
   * 加载可用模型并恢复本地选择（默认优先使用用户默认模型）
   */
  loadModels: function () {
    var self = this;
    api.aiModelList().then(function (res) {
      var data = res && res.data ? res.data : (res || {});
      var models = data.list || [];
      var meta = data.meta || {};
      var names = models.map(function (m) {
        return m.name + '（' + m.model + '）';
      });
      // 选择优先级：本地已选（仍存在）→ 用户默认 → 全局默认 → 第一个
      var savedId = wx.getStorageSync('ai_selected_model_id') || '';
      var targetId = '';
      var index = 0;
      var order = [savedId, meta.userDefaultModelId, meta.defaultModelId];
      for (var k = 0; k < order.length; k++) {
        if (!order[k]) continue;
        for (var i = 0; i < models.length; i++) {
          if (models[i]._id === order[k]) { index = i; targetId = models[i]._id; break; }
        }
        if (targetId) break;
      }
      if (!targetId && models.length) {
        targetId = models[0]._id;
        index = 0;
      }
      self.setData({
        models: models,
        modelNames: names,
        modelIndex: index,
        selectedModelId: targetId
      });
    }).catch(function (err) {
      console.error('[AI问答] 模型列表加载失败', err);
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
    this._needRefreshModels = true;
    wx.navigateTo({ url: '/pages/ai-config/index' });
  },

  onInput: function (e) {
    this.setData({ inputValue: e.detail.value });
  },

  onSendInput: function () {
    this.doAsk(this.data.inputValue);
  },

  onTapRecommend: function (e) {
    var q = e.currentTarget.dataset.q;
    this.doAsk(q);
  },

  /**
   * 点击来源标签查看出处
   * - 来源为文章（source=article）：跳转文章详情，可核对原始文章编码
   * - 来源为知识库条目：跳转知识库文档详情
   */
  onTapSource: function (e) {
    var source = e.currentTarget.dataset.source;
    if (!source) return;

    if (source.source === 'article' && source.article_id) {
      wx.navigateTo({
        url: '/pages/article/detail?id=' + source.article_id,
        fail: function () {
          wx.showToast({ icon: 'none', title: '文章暂不可访问' });
        }
      });
      return;
    }

    var id = source.doc_id || source.id;
    if (!id) {
      wx.showToast({ icon: 'none', title: '暂不支持跳转' });
      return;
    }
    wx.navigateTo({
      url: '/pages/knowledge/detail?id=' + id,
      fail: function () {
        wx.showToast({ icon: 'none', title: '暂不支持跳转' });
      }
    });
  },

  /**
   * 提问主流程
   */
  doAsk: function (question) {
    question = (question || '').trim();
    if (!question) {
      wx.showToast({ icon: 'none', title: '请输入问题' });
      return;
    }
    if (this.data.sending) return;

    var that = this;
    var messages = this.data.messages.slice();
    messages.push({ role: 'user', text: question, nodes: [], sources: [] });
    messages.push({ role: 'ai', text: '', nodes: [], sources: [], loading: true });
    this._aiIndex = messages.length - 1;
    this.setData({ messages: messages, inputValue: '', sending: true });
    this._scrollToBottom();

    api.aiKbAsk(question, this.data.selectedModelId).then(function (res) {
      // 后端统一返回 {code, message, data} 信封，这里兼容两种形态
      var payload = (res && res.data) ? res.data : (res || {});
      var answer = payload.answer || '抱歉，暂时没有找到相关内容，请换个问法试试。';
      var sources = payload.sources || [];
      that._updateAiMessage(answer, sources);
    }, function (err) {
      var msg = '回答失败，请稍后重试';
      if (err && err.data && err.data.message) {
        msg = err.data.message;
      }
      that._updateAiMessage(msg, []);
      wx.showToast({ icon: 'none', title: msg });
    });
  },

  /**
   * 更新 AI 消息（把 Markdown 解析成 rich-text nodes）
   */
  _updateAiMessage: function (text, sources) {
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
      sources: sources || [],
      loading: false
    };
    this.setData({ messages: messages, sending: false });
    this._scrollToBottom();
  },

  /**
   * 滚动到底部最新消息
   */
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
