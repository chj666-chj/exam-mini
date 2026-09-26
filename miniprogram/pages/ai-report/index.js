/**
 * 学习报告页
 * 周报 / 月报 / 考前报告：调用后端聚合学习记录 + LLM 生成报告（Markdown 渲染）
 *
 * 后端 LLM 调用为同步阻塞模式（无 SSE/stream），通过 AIJobManager 异步线程执行。
 * 前端通过轮询 job status 获取 progress_text 中间文案作为"思考过程"反馈，
 * 任务完成后拉取最终报告渲染。
 */
var api = require('../../utils/api.js');
var md = require('../../utils/markdown.js');

var TABS = [
  { key: 'weekly', label: '周报' },
  { key: 'monthly', label: '月报' },
  { key: 'pre_exam', label: '考前报告' }
];

// 后端 AIJobManager 状态值（ai_jobs.py）
var JOB_SUCCESS = 'success';
var JOB_FAILED = 'failed';
var JOB_CANCELLED = 'cancelled';
var JOB_PENDING = 'pending';
var JOB_RUNNING = 'running';

// 后端 generate() 中通过 AIJobManager.update(progress_text=...) 设置的阶段性文案
// 按出现顺序匹配，用于展示"思考过程"
var DEFAULT_STEPS = [
  '正在聚合学习数据',
  '正在生成学习报告',
  '学习报告生成完成'
];

Page({
  data: {
    tabs: TABS,
    activeTab: 'weekly',
    activeTabText: '周报',
    report: null,
    reportNodes: [],
    highlights: [],
    suggestions: [],
    generatedAt: '',
    periodText: '',
    generating: false,
    genStatusText: '',
    thinkingSteps: [],
    loading: false
  },

  onLoad: function () {
    this._jobTimer = null;
    this._polledJobId = null;
    this._seenProgressTexts = {};
    this.loadReport();
  },

  onPullDownRefresh: function () {
    var that = this;
    this.loadReport(function () {
      wx.stopPullDownRefresh();
    });
  },

  /**
   * 切换报告类型 Tab
   */
  switchTab: function (e) {
    var key = e.currentTarget.dataset.key;
    if (!key || key === this.data.activeTab) return;
    this._stopPolling();
    this.setData({
      activeTab: key,
      activeTabText: this._tabLabel(key),
      report: null,
      reportNodes: [],
      highlights: [],
      suggestions: [],
      generatedAt: '',
      periodText: '',
      generating: false,
      thinkingSteps: [],
      genStatusText: ''
    });
    this.loadReport();
  },

  /**
   * 加载当前类型最新报告
   */
  loadReport: function (done) {
    var that = this;
    this.setData({ loading: true });
    api.aiLearningReport(this.data.activeTab).then(function (res) {
      that._processReport(res);
      if (done) done();
    }, function (err) {
      that.setData({ loading: false });
      if (err && err.statusCode >= 500) {
        wx.showToast({ icon: 'none', title: '加载失败，请稍后重试' });
      }
      if (done) done();
    });
  },

  /**
   * 处理报告数据
   * 后端可能存储两种 content_md：
   *   1. 正确的 Markdown 文本（理想情况）
   *   2. 原始 JSON 字符串（LLM 返回的 JSON 未被后端正确解包时）
   * 此函数统一解包为结构化数据后渲染。
   */
  _processReport: function (res) {
    var report = res;
    if (!report || (!report.content_md && !report.summary && !report.content)) {
      this.setData({
        report: null,
        reportNodes: [],
        highlights: [],
        suggestions: [],
        generatedAt: '',
        periodText: '',
        loading: false
      });
      return;
    }

    // 尝试从 content_md 中解析嵌套的 JSON 结构
    var parsed = this._parseReportContent(report);

    this.setData({
      report: parsed,
      reportNodes: md.parse(parsed.content_md),
      highlights: parsed.highlights || [],
      suggestions: parsed.suggestions || [],
      generatedAt: this._formatTime(report.generated_at),
      periodText: typeof report.period === 'string' ? report.period : '',
      loading: false
    });
  },

  /**
   * 解析报告内容，处理后端可能存储的多种格式
   *
   * 情况1：content_md 是纯 Markdown（正常路径）→ 直接使用
   * 情况2：content_md 是 JSON 字符串（后端未正确解包 LLM 响应）→ 提取内部字段
   * 情况3：content_md 含有转义的 \\n（JSON 内部字符串）→ 反转义为真实换行
   * 情况4：highlights/suggestions 为空但 JSON 内部有值 → 补充提取
   */
  _parseReportContent: function (report) {
    var contentMd = report.content_md || report.content || report.summary || '';
    var highlights = (report.highlights || []).slice();
    var suggestions = (report.suggestions || []).slice();
    var summary = report.summary || '';

    // 检测 content_md 是否为 JSON 字符串
    if (contentMd && contentMd.trim().charAt(0) === '{') {
      try {
        var inner = JSON.parse(contentMd);
        if (inner && typeof inner === 'object') {
          // 提取内层 content_md
          if (inner.content_md && typeof inner.content_md === 'string') {
            contentMd = inner.content_md;
          }
          // 提取 summary
          if (inner.summary && !summary) {
            summary = inner.summary;
          }
          // 提取 highlights（仅当外层为空时补充）
          if (highlights.length === 0 && Array.isArray(inner.highlights)) {
            highlights = inner.highlights.filter(function (h) {
              return h && typeof h === 'string' && h.trim();
            });
          }
          // 提取 suggestions（仅当外层为空时补充）
          if (suggestions.length === 0 && Array.isArray(inner.suggestions)) {
            suggestions = inner.suggestions.filter(function (s) {
              return s && typeof s === 'string' && s.trim();
            });
          }
        }
      } catch (e) {
        // JSON 解析失败，保持原始 content_md 不变
      }
    }

    // 处理转义换行符：某些情况下 \n 被存储为字面量 \\n
    if (contentMd && contentMd.indexOf('\\n') >= 0 && contentMd.indexOf('\n') < 0) {
      contentMd = contentMd.replace(/\\n/g, '\n');
    }

    return {
      content_md: contentMd,
      summary: summary,
      highlights: highlights,
      suggestions: suggestions,
      report_type: report.report_type || '',
      period: report.period || '',
      generated_at: report.generated_at || ''
    };
  },

  /**
   * 生成报告（异步任务）
   */
  generateReport: function () {
    if (this.data.generating) return;
    var that = this;
    var type = this.data.activeTab;

    // 初始化生成状态
    this._seenProgressTexts = {};
    this.setData({
      generating: true,
      genStatusText: '正在提交生成请求...',
      thinkingSteps: [],
      report: null,
      reportNodes: [],
      highlights: [],
      suggestions: []
    });

    api.aiGenerateLearningReport(type).then(function (res) {
      var jobId = res && (res.job_id || res.jobId);
      if (!jobId) {
        // 同步返回结果（记录不足等场景）
        if (res && (res.content_md || res.report)) {
          that._processReport(res);
          that.setData({ generating: false });
          wx.showToast({ icon: 'success', title: '报告已生成' });
          return;
        }
        var tip = (res && res.message) || '生成失败：未返回任务ID';
        that.setData({ generating: false, genStatusText: tip });
        wx.showToast({ icon: 'none', title: tip });
        return;
      }
      that._startPolling(jobId);
    }, function (err) {
      that.setData({ generating: false });
      var msg = '生成失败，请稍后重试';
      var status = (err && err.statusCode) || 0;
      if (err && err.data) {
        if (typeof err.data === 'string') {
          msg = 'AI 服务异常（HTTP ' + (status || 500) + '），请稍后重试';
        } else if (err.data.message) {
          msg = err.data.message;
        }
      } else if (err && err.errMsg) {
        msg = err.errMsg;
      }
      that.setData({ genStatusText: msg });
      // 用 showModal 替代 showToast，避免长消息被截断
      wx.showModal({
        title: '生成失败',
        content: msg,
        showCancel: false,
        confirmText: '知道了'
      });
    });
  },

  /**
   * 开始轮询任务状态
   * 策略：首次立即查询，之后每 3 秒轮询一次，最长 5 分钟
   * 收到 success/failed/cancelled 后立即终止
   */
  _startPolling: function (jobId) {
    var that = this;
    this._polledJobId = jobId;
    this._pollCount = 0;
    this._maxPollCount = 100; // 3s * 100 = 5min

    // 立即查一次（不等 3 秒）
    this._doPoll();

    this._jobTimer = setInterval(function () {
      that._doPoll();
    }, 3000);
  },

  /**
   * 执行单次轮询
   */
  _doPoll: function () {
    var that = this;
    this._pollCount++;

    if (this._pollCount > this._maxPollCount) {
      this._stopPolling();
      this.setData({
        generating: false,
        genStatusText: '生成超时，请稍后重试'
      });
      wx.showToast({ icon: 'none', title: '生成超时' });
      return;
    }

    api.aiJobStatus(this._polledJobId).then(function (res) {
      if (!res || !that.data.generating) return;

      var status = res.status || res.state || '';
      var progressText = res.progress_text || res.progressText || '';
      var errorMsg = res.error || '';

      // 更新思考步骤（progress_text 去重追加）
      that._addThinkingStep(progressText, status);

      // 更新状态文案
      var statusText = that._buildStatusText(status, progressText, errorMsg);
      that.setData({ genStatusText: statusText });

      // 任务成功 → 终止轮询，拉取报告
      if (status === JOB_SUCCESS) {
        that._stopPolling();
        that.setData({ genStatusText: '报告生成完成，正在加载...' });
        that.loadReport(function () {
          that.setData({ generating: false });
          wx.showToast({ icon: 'success', title: '报告已生成' });
        });
        return;
      }

      // 任务失败/取消 → 终止轮询
      if (status === JOB_FAILED || status === JOB_CANCELLED) {
        that._stopPolling();
        var failMsg = errorMsg || (status === JOB_FAILED ? '生成失败' : '已取消');
        that.setData({ generating: false, genStatusText: failMsg });
        wx.showToast({ icon: 'none', title: failMsg });
        return;
      }
    }, function () {
      // 单次查询失败不中断轮询
    });
  },

  /**
   * 添加思考步骤（去重）
   * 后端在 generate() 中通过 AIJobManager.update(progress_text=...) 设置阶段文案，
   * 每次轮询拿到的 progress_text 是当前阶段的描述，按首次出现顺序追加展示。
   */
  _addThinkingStep: function (progressText, status) {
    if (!progressText) return;

    // 去重：同一文案只追加一次
    if (this._seenProgressTexts[progressText]) return;
    this._seenProgressTexts[progressText] = true;

    var steps = this.data.thinkingSteps.slice();
    steps.push(progressText);
    this.setData({ thinkingSteps: steps });
  },

  /**
   * 构建状态文案
   */
  _buildStatusText: function (status, progressText, errorMsg) {
    if (errorMsg) return errorMsg;
    if (progressText) return progressText;
    var map = {
      pending: '排队中...',
      running: '正在分析学习数据...'
    };
    return map[status] || '处理中...';
  },

  /**
   * 停止轮询
   */
  _stopPolling: function () {
    if (this._jobTimer) {
      clearInterval(this._jobTimer);
      this._jobTimer = null;
    }
    this._polledJobId = null;
  },

  _tabLabel: function (key) {
    for (var i = 0; i < TABS.length; i++) {
      if (TABS[i].key === key) return TABS[i].label;
    }
    return '周报';
  },

  _formatTime: function (v) {
    if (!v) return '';
    var s = String(v);
    if (s.indexOf('T') > 0) {
      return s.replace('T', ' ').substring(0, 16);
    }
    return s.length > 16 ? s.substring(0, 16) : s;
  },

  onUnload: function () {
    this._stopPolling();
  },

  onHide: function () {
    // 页面隐藏时停止轮询，避免后台无用请求
    this._stopPolling();
    if (this.data.generating) {
      this.setData({ generating: false, genStatusText: '已暂停' });
    }
  }
});
