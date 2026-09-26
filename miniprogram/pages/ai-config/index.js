/**
 * AI 模型配置管理页（服务端多模型）
 *
 * 数据来源：GET /api/ai/models/ —— 返回「全局模型 + 本人模型」及元信息。
 * 能力：
 *   - 查看全部可用模型（全局 / 我的），标注默认模型
 *   - 新增 / 编辑 / 删除本人模型（携带自己的 API Key）
 *   - 把任意可用模型设为「我的默认」（含全局模型）
 *   - 测试单个模型连通性
 *   - 展示数量上限、默认模型、调用解析顺序与配置生效时机
 */
var api = require('../../utils/api.js');

var DEFAULT_FORM = {
  name: '',
  provider: 'openai',
  apiUrl: 'https://api.openai.com/v1/chat/completions',
  apiKey: '',
  model: 'gpt-4o-mini',
  temperature: 0.7,
  maxTokens: 2000,
  enabled: true,
  remark: ''
};

Page({
  data: {
    models: [],
    meta: {
      limits: { global: 10, user: 5 },
      usage: { global: 0, user: 0, global_max: 10, user_max: 5 },
      presets: [],
      defaultModelId: '',
      userDefaultModelId: '',
      effectTiming: '',
      resolutionOrder: []
    },
    loading: false,
    showForm: false,
    editingId: '',
    presetNames: [],
    presetIndex: 0,
    formData: DEFAULT_FORM,
    testingId: ''
  },

  onShow: function () {
    this.loadModels();
  },

  onPullDownRefresh: function () {
    var self = this;
    this.loadModels(function () {
      wx.stopPullDownRefresh();
    });
  },

  loadModels: function (done) {
    var self = this;
    self.setData({ loading: true });
    api.aiModelList().then(function (res) {
      var data = res && res.data ? res.data : (res || {});
      var models = data.list || [];
      var meta = data.meta || self.data.meta;
      var presetNames = (meta.presets || []).map(function (p) { return p.name; });
      self.setData({
        models: models,
        meta: meta,
        presetNames: presetNames,
        loading: false
      });
      if (typeof done === 'function') done();
    }).catch(function (err) {
      console.error('[AI模型] 加载失败', err);
      self.setData({ loading: false });
      wx.showToast({ icon: 'none', title: '加载失败，请重试' });
      if (typeof done === 'function') done();
    });
  },

  // ---------- 表单 ----------
  showAddForm: function () {
    var presets = this.data.meta.presets || [];
    var first = presets[0] || { key: 'custom', apiUrl: '', models: [] };
    var form = Object.assign({}, DEFAULT_FORM, {
      provider: first.key,
      apiUrl: first.apiUrl || '',
      model: (first.models && first.models[0]) || ''
    });
    this.setData({ showForm: true, editingId: '', formData: form, presetIndex: 0 });
  },

  editConfig: function (e) {
    var id = e.currentTarget.dataset.id;
    var model = null;
    for (var i = 0; i < this.data.models.length; i++) {
      if (this.data.models[i]._id === id) { model = this.data.models[i]; break; }
    }
    if (!model) return;
    var form = {
      name: model.name || '',
      provider: model.provider || 'custom',
      apiUrl: model.apiUrl || '',
      apiKey: model.apiKey || '',   // 服务端返回脱敏值，原样保存表示不修改
      model: model.model || '',
      temperature: model.temperature === undefined ? 0.7 : model.temperature,
      maxTokens: model.maxTokens || 2000,
      enabled: model.enabled !== false,
      remark: model.remark || ''
    };
    var presetIndex = 0;
    var presets = this.data.meta.presets || [];
    for (var j = 0; j < presets.length; j++) {
      if (presets[j].key === form.provider) { presetIndex = j; break; }
    }
    this.setData({ showForm: true, editingId: id, formData: form, presetIndex: presetIndex });
  },

  hideForm: function (e) {
    // 防御：仅当点击目标就是遮罩本身时才关闭（非子元素冒泡）
    if (e && e.target && e.currentTarget && e.target !== e.currentTarget) {
      return;
    }
    this.setData({ showForm: false });
  },

  // 空操作：用于 catchtap 阻止事件冒泡（catchtap="" 空 handler 不可靠，
  // 部分微信版本/基础库下无法阻止冒泡，导致点击输入框时 tap 冒泡到遮罩触发 hideForm）
  noop: function () {},

  onFormInput: function (e) {
    var field = e.currentTarget.dataset.field;
    var update = {};
    update['formData.' + field] = e.detail.value;
    this.setData(update);
  },

  onEnabledChange: function (e) {
    this.setData({ 'formData.enabled': e.detail.value });
  },

  onProviderChange: function (e) {
    var index = parseInt(e.detail.value) || 0;
    var presets = this.data.meta.presets || [];
    var preset = presets[index];
    if (!preset) return;
    this.setData({
      presetIndex: index,
      'formData.provider': preset.key,
      'formData.apiUrl': preset.apiUrl || this.data.formData.apiUrl,
      'formData.model': (preset.models && preset.models[0]) || this.data.formData.model
    });
  },

  onModelChange: function (e) {
    this.setData({ 'formData.model': e.detail.value });
  },

  saveConfig: function () {
    var f = this.data.formData;
    if (!String(f.name || '').trim()) { wx.showToast({ icon: 'none', title: '请输入模型名称' }); return; }
    if (!String(f.apiUrl || '').trim()) { wx.showToast({ icon: 'none', title: '请输入接口地址' }); return; }
    if (!String(f.apiKey || '').trim()) { wx.showToast({ icon: 'none', title: '请输入 API Key' }); return; }
    if (!String(f.model || '').trim()) { wx.showToast({ icon: 'none', title: '请输入模型标识' }); return; }

    var self = this;
    var payload = {
      name: String(f.name).trim(),
      provider: f.provider,
      apiUrl: String(f.apiUrl).trim(),
      apiKey: String(f.apiKey).trim(),
      model: String(f.model).trim(),
      temperature: Number(f.temperature) || 0.7,
      maxTokens: Number(f.maxTokens) || 2000,
      enabled: f.enabled !== false,
      remark: String(f.remark || '').trim()
    };

    wx.showLoading({ title: '保存中...' });
    var task = this.data.editingId
      ? api.aiModelUpdate(this.data.editingId, payload)
      : api.aiModelCreate(payload);

    task.then(function () {
      wx.hideLoading();
      self.setData({ showForm: false });
      wx.showToast({ icon: 'success', title: '保存成功' });
      self.loadModels();
    }).catch(function (err) {
      wx.hideLoading();
      var msg = (err && (err.message || (err.data && err.data.message))) || '保存失败';
      wx.showToast({ icon: 'none', title: msg });
    });
  },

  // ---------- 列表操作 ----------
  selectConfig: function (e) {
    var id = e.currentTarget.dataset.id;
    var self = this;
    wx.showLoading({ title: '设置中...' });
    api.aiModelSetDefault(id).then(function () {
      wx.hideLoading();
      wx.showToast({ icon: 'success', title: '已设为默认' });
      self.loadModels();
    }).catch(function (err) {
      wx.hideLoading();
      var msg = (err && (err.message || (err.data && err.data.message))) || '设置失败';
      wx.showToast({ icon: 'none', title: msg });
    });
  },

  testConfig: function (e) {
    var id = e.currentTarget.dataset.id;
    var self = this;
    self.setData({ testingId: id });
    wx.showLoading({ title: '测试中...' });
    api.aiModelTest(id).then(function (res) {
      wx.hideLoading();
      self.setData({ testingId: '' });
      var data = res && res.data ? res.data : {};
      wx.showModal({
        title: '连接成功',
        content: (data.response || 'ok').slice(0, 120),
        showCancel: false
      });
    }).catch(function (err) {
      wx.hideLoading();
      self.setData({ testingId: '' });
      var status = (err && err.statusCode) || 0;
      var msg = '测试失败';
      if (err && err.data && typeof err.data === 'object' && err.data.message) {
        msg = err.data.message;
      } else if (err && err.data && typeof err.data === 'string') {
        msg = 'AI 服务异常（HTTP ' + (status || 500) + '），请稍后重试';
      } else if (err && err.errMsg) {
        msg = err.errMsg;
      }
      // 503 = 模型配置不完整（缺 Key 等），引导用户填写
      if (status === 503) {
        msg = msg + '\n\n请检查该模型的 API Key 是否已填写';
      }
      wx.showModal({ title: '连接失败', content: msg, showCancel: false });
    });
  },

  deleteConfig: function (e) {
    var id = e.currentTarget.dataset.id;
    var self = this;
    wx.showModal({
      title: '确认删除',
      content: '确定删除这个自定义模型吗？',
      confirmColor: '#f56c6c',
      success: function (res) {
        if (!res.confirm) return;
        api.aiModelDelete(id).then(function () {
          wx.showToast({ icon: 'success', title: '已删除' });
          self.loadModels();
        }).catch(function (err) {
          var msg = (err && (err.message || (err.data && err.data.message))) || '删除失败';
          wx.showToast({ icon: 'none', title: msg });
        });
      }
    });
  }
});
