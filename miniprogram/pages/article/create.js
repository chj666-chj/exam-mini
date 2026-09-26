var api = require('../../utils/api.js');

// 本地记录「上次选择的模型」，切换后写回（与服务端默认模型配合）
var AI_MODEL_KEY = 'ai_selected_model_id';

Page({
  data: {
    form: {
      title: '',
      summary: '',
      content: '',
      images: [],
      tags: []
    },
    tagInput: '',
    aiLoading: false,
    aiProgressText: '',       // AI 生成中的动态提示文案
    aiCancelable: false,      // 是否可取消（请求发出后可取消）
    submitting: false,
    // 调用模型（来自服务端「AI 模型配置」）
    models: [],
    modelNames: [],
    modelIndex: 0,
    selectedModelId: ''
  },

  onShow: function () {
    this.loadModels();
  },

  onHide: function () {
    // 页面隐藏时清理 AI 进度定时器，防止后台 setInterval 泄漏
    if (this._aiProgressTimer) { clearInterval(this._aiProgressTimer); this._aiProgressTimer = null; }
  },

  onUnload: function () {
    if (this._aiProgressTimer) { clearInterval(this._aiProgressTimer); this._aiProgressTimer = null; }
    // 页面卸载时中止进行中的 AI 请求
    if (this._aiSignal && !this._aiSignal.aborted) {
      this._aiSignal.aborted = true;
      if (this._aiSignal._task && typeof this._aiSignal._task.abort === 'function') {
        this._aiSignal._task.abort();
      }
    }
  },

  /**
   * 加载可用模型（全局 + 本人），默认选中：本地选择 → 我的默认 → 全局默认 → 第一个
   */
  loadModels: function () {
    var self = this;
    api.aiModelList().then(function (res) {
      var data = res && res.data ? res.data : (res || {});
      var models = data.list || [];
      var meta = data.meta || {};
      var names = models.map(function (m) { return m.name + '（' + m.model + '）'; });
      var savedId = wx.getStorageSync(AI_MODEL_KEY) || '';
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
      console.error('[写文章] 模型列表加载失败', err);
    });
  },

  onModelChange: function (e) {
    var index = parseInt(e.detail.value) || 0;
    var model = this.data.models[index];
    if (!model) return;
    this.setData({ modelIndex: index, selectedModelId: model._id });
    wx.setStorageSync(AI_MODEL_KEY, model._id);
  },

  goAIConfig: function () {
    wx.navigateTo({ url: '/pages/ai-config/index' });
  },

  onTitleInput: function (e) {
    this.setData({ 'form.title': e.detail.value });
  },

  onSummaryInput: function (e) {
    this.setData({ 'form.summary': e.detail.value });
  },

  onEditorInput: function (e) {
    this.setData({ 'form.content': e.detail.value });
  },

  onTagInput: function (e) {
    this.setData({ tagInput: e.detail.value });
  },

  addTag: function () {
    var tag = (this.data.tagInput || '').trim();
    if (!tag) return;
    var tags = this.data.form.tags.slice();
    if (tags.length >= 5) {
      wx.showToast({ icon: 'none', title: '最多 5 个标签' });
      return;
    }
    if (tags.indexOf(tag) >= 0) {
      wx.showToast({ icon: 'none', title: '标签已存在' });
      return;
    }
    tags.push(tag);
    this.setData({ 'form.tags': tags, tagInput: '' });
  },

  removeTag: function (e) {
    var index = e.currentTarget.dataset.index;
    var tags = this.data.form.tags.slice();
    tags.splice(index, 1);
    this.setData({ 'form.tags': tags });
  },

  chooseImages: function () {
    var self = this;
    var remaining = 3 - this.data.form.images.length;
    if (remaining <= 0) {
      wx.showToast({ icon: 'none', title: '最多 3 张图片' });
      return;
    }
    wx.chooseMedia({
      count: remaining,
      mediaType: ['image'],
      sizeType: ['compressed'],
      success: function (res) {
        var tempFiles = res.tempFiles || [];
        wx.showLoading({ title: '上传中...' });
        var uploadPromises = tempFiles.map(function (file) {
          return api.uploadImage(file.tempFilePath);
        });
        Promise.all(uploadPromises).then(function (results) {
          wx.hideLoading();
          var images = self.data.form.images.slice();
          results.forEach(function (data) {
            var url = data.url || '';
            if (url && url.indexOf('http') !== 0) {
              url = api.API_BASE.replace('/api', '') + url;
            }
            if (url) images.push(url);
          });
          if (images.length > 3) images = images.slice(0, 3);
          self.setData({ 'form.images': images });
        }).catch(function (err) {
          wx.hideLoading();
          console.error('[写文章] 图片上传失败', err);
          wx.showToast({ icon: 'none', title: '图片上传失败' });
        });
      }
    });
  },

  removeImage: function (e) {
    var index = e.currentTarget.dataset.index;
    var images = this.data.form.images.slice();
    images.splice(index, 1);
    this.setData({ 'form.images': images });
  },

  previewImage: function (e) {
    var current = e.currentTarget.dataset.src;
    wx.previewImage({
      current: current,
      urls: this.data.form.images
    });
  },

  aiAssist: function () {
    var self = this;
    var title = (this.data.form.title || '').trim();
    if (!title) {
      wx.showToast({ icon: 'none', title: '请先输入文章标题' });
      return;
    }

    if (!this.data.models.length) {
      wx.showToast({ icon: 'none', title: '请先添加 AI 模型' });
      return;
    }

    if (this.data.aiLoading) return;  // 防重复点击

    // 可取消信号：cancelAI() 时置 aborted=true
    var signal = { aborted: false, onAbort: null };

    // 进度文案轮换（让用户感知"正在工作"，不焦虑）
    var progressTexts = ['AI 正在构思文章结构...', '正在生成正文内容，请耐心等待...', '大模型思考中，预计还需 30 秒...'];
    var progressIndex = 0;
    function startProgress() {
      self.setData({ aiProgressText: progressTexts[0], aiCancelable: true });
      self._aiProgressTimer = setInterval(function () {
        progressIndex++;
        if (progressIndex >= progressTexts.length) progressIndex = progressTexts.length - 1;
        self.setData({ aiProgressText: progressTexts[progressIndex] });
      }, 15000);  // 每 15s 换一次文案
    }
    function stopProgress() {
      if (self._aiProgressTimer) { clearInterval(self._aiProgressTimer); self._aiProgressTimer = null; }
    }

    this.setData({ aiLoading: true });
    startProgress();

    api.aiAssistWithRetry({
      prompt: title,
      context: this.data.form.summary || '',
      model_id: this.data.selectedModelId || ''
    }, {
      signal: signal,
      onRetry: function (attempt) {
        // 重试时更新提示
        self.setData({ aiProgressText: '网络较慢，正在重试（第 ' + (attempt + 1) + ' 次）...' });
      }
    }).then(function (res) {
      stopProgress();
      self.setData({ aiLoading: false, aiProgressText: '', aiCancelable: false });
      var payload = (res && res.data) ? res.data : (res || {});
      if (payload.content) {
        self.setData({ 'form.content': payload.content });
        wx.showToast({ icon: 'success', title: 'AI 生成成功' });
      } else {
        wx.showToast({ icon: 'none', title: 'AI 未返回内容' });
      }
    }).catch(function (err) {
      stopProgress();
      self.setData({ aiLoading: false, aiProgressText: '', aiCancelable: false });

      // 用户主动取消
      if (signal.aborted || (err && err.errMsg && err.errMsg.indexOf('abort') >= 0)) {
        console.log('[写文章] AI 辅助已取消');
        return;
      }

      console.error('[写文章] AI 辅助失败', err);
      var status = (err && err.statusCode) || 0;
      var errMsg = (err && err.errMsg) || '';
      var msg = 'AI 辅助失败，请稍后重试';

      // 超时：request:fail timeout
      if (errMsg.indexOf('timeout') >= 0) {
        msg = 'AI 响应超时，大模型可能正忙或网络较慢。请检查网络后重试，或换一个模型试试。';
      } else if (err && err.data && typeof err.data === 'object' && err.data.message) {
        msg = err.data.message;
      } else if (err && err.data && typeof err.data === 'string') {
        msg = 'AI 服务异常（HTTP ' + (status || 500) + '），请稍后重试';
      } else if (errMsg) {
        msg = errMsg;
      }
      if (status === 503) {
        msg = 'AI 功能暂未就绪，请联系管理员配置 AI 模型';
      }
      if (status === 502) {
        msg = 'AI 服务暂时不可用，请稍后重试';
      }
      wx.showModal({
        title: 'AI 辅助',
        content: msg,
        showCancel: false,
        confirmText: '知道了'
      });
    });

    // 保存信号，供 cancelAI 使用
    this._aiSignal = signal;
  },

  cancelAI: function () {
    if (this._aiSignal) {
      this._aiSignal.aborted = true;
      if (this._aiSignal._task && typeof this._aiSignal._task.abort === 'function') {
        this._aiSignal._task.abort();
      }
    }
  },

  submit: function () {
    var self = this;
    var form = this.data.form;

    if (!form.title || !form.title.trim()) {
      wx.showToast({ icon: 'none', title: '请输入文章标题' });
      return;
    }
    if (!form.content || !form.content.trim()) {
      wx.showToast({ icon: 'none', title: '请输入文章正文' });
      return;
    }

    this.setData({ submitting: true });

    var db = api.database();
    db.collection('articles').add({
      data: {
        title: form.title.trim(),
        summary: form.summary || '',
        content: form.content,
        images: form.images || [],
        tags: form.tags || [],
        author: '匿名用户'
      },
      success: function () {
        self.setData({ submitting: false });
        wx.showToast({ icon: 'success', title: '已提交，待审核' });
        setTimeout(function () {
          wx.navigateBack();
        }, 1500);
      },
      fail: function (err) {
        self.setData({ submitting: false });
        console.error('[写文章] 提交失败', err);
        wx.showToast({ icon: 'none', title: '提交失败，请重试' });
      }
    });
  }
});
