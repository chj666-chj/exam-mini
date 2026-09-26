/**
 * AI 复习推荐页
 * 基于艾宾浩斯遗忘曲线和 AI 分析，生成今日复习推荐
 */
var api = require('../../utils/api.js');

Page({
  data: {
    // 复习计划数据
    plan: null,
    items: [],
    total: 0,
    reviewed: 0,
    progressPercent: 0,
    // 生成状态
    generating: false,
    genPercent: 0,
    genStatusText: '',
    // 加载状态
    loading: true,
    // 日期
    todayDate: ''
  },

  onLoad: function () {
    this.setData({
      todayDate: this._formatDate(new Date())
    });
    this.loadReviewPlan();
  },

  onShow: function () {
    // 每次显示时刷新已复习状态
    if (this.data.plan) {
      this.loadReviewPlan();
    }
  },

  onPullDownRefresh: function () {
    var that = this;
    this.loadReviewPlan(function () {
      wx.stopPullDownRefresh();
    });
  },

  /**
   * 加载今日复习推荐
   */
  loadReviewPlan: function (done) {
    var that = this;
    this.setData({ loading: true });
    api.aiReviewPlan().then(function (res) {
      that._processPlanData(res);
      if (done) done();
    }, function (err) {
      that.setData({ loading: false });
      if (err && err.statusCode !== 404) {
        wx.showToast({ icon: 'none', title: '加载失败，请稍后重试' });
      }
      if (done) done();
    });
  },

  /**
   * 处理复习计划数据
   */
  _processPlanData: function (res) {
    if (!res || (!res.items && !res.plan)) {
      this.setData({
        plan: null,
        items: [],
        total: 0,
        reviewed: 0,
        progressPercent: 0,
        loading: false
      });
      return;
    }

    var data = res.items ? res : (res.plan || res);
    var items = data.items || [];
    var total = data.total || items.length;
    var reviewed = data.reviewed || 0;

    // 按 priority 排序（数字越小优先级越高）
    items.sort(function (a, b) {
      var pa = a.priority != null ? a.priority : 99;
      var pb = b.priority != null ? b.priority : 99;
      return pa - pb;
    });

    // 格式化每道题的显示信息
    items.forEach(function (item) {
      // 推荐理由
      if (!item.reason) {
        if (item.reason_type === 'ebbinghaus') {
          item.reason = '艾宾浩斯遗忘曲线';
        } else if (item.reason_type === 'weakness') {
          item.reason = '薄弱知识点';
        } else {
          item.reason = 'AI 智能推荐';
        }
      }
      // 推荐理由标签类型
      if (item.reason_type === 'ebbinghaus') {
        item.reasonTagType = 'primary';
      } else if (item.reason_type === 'weakness') {
        item.reasonTagType = 'danger';
      } else {
        item.reasonTagType = 'success';
      }
      // 复习次数文本
      item.reviewCountText = '第 ' + (item.review_count + 1) + ' 次复习';
      // 题目摘要截断
      if (item.summary && item.summary.length > 60) {
        item.summaryDisplay = item.summary.substring(0, 60) + '...';
      } else {
        item.summaryDisplay = item.summary || item.title || '点击查看详情';
      }
    });

    var percent = total > 0 ? Math.round((reviewed / total) * 100) : 0;

    this.setData({
      plan: data,
      items: items,
      total: total,
      reviewed: reviewed,
      progressPercent: percent,
      loading: false
    });
  },

  /**
   * 生成今日复习推荐
   */
  generatePlan: function () {
    if (this.data.generating) return;
    var that = this;
    this.setData({
      generating: true,
      genPercent: 0,
      genStatusText: '正在生成今日推荐...'
    });

    api.aiGenerateReviewPlan().then(function (res) {
      var jobId = res && (res.job_id || res.jobId);
      if (!jobId) {
        // 如果直接返回了结果
        if (res && res.items) {
          that._processPlanData(res);
          that.setData({ generating: false, genPercent: 100 });
          wx.showToast({ icon: 'success', title: '推荐已生成' });
          return;
        }
        that.setData({
          generating: false,
          genStatusText: '生成失败：未返回任务ID'
        });
        wx.showToast({ icon: 'none', title: '生成失败' });
        return;
      }
      that._pollJobStatus(jobId);
    }, function (err) {
      var msg = '生成失败';
      if (err && err.data && err.data.message) {
        msg = err.data.message;
      }
      that.setData({
        generating: false,
        genStatusText: msg
      });
      wx.showToast({ icon: 'none', title: msg });
    });
  },

  /**
   * 轮询任务状态
   */
  _pollJobStatus: function (jobId) {
    var that = this;
    var count = 0;
    var maxCount = 100; // 3秒 * 100 = 5分钟超时

    this._jobTimer = setInterval(function () {
      count++;
      if (count > maxCount) {
        clearInterval(that._jobTimer);
        that._jobTimer = null;
        that.setData({
          generating: false,
          genStatusText: '生成超时，请稍后重试'
        });
        wx.showToast({ icon: 'none', title: '生成超时' });
        return;
      }

      api.aiJobStatus(jobId).then(function (res) {
        var status = res.status || res.state || '';
        var progress = res.progress || 0;
        that.setData({
          genPercent: Math.min(progress, 99),
          genStatusText: res.message || that._statusText(status)
        });

        if (status === 'completed' || status === 'success' || status === 'done') {
          clearInterval(that._jobTimer);
          that._jobTimer = null;
          that.setData({
            generating: false,
            genPercent: 100,
            genStatusText: '生成完成'
          });
          wx.showToast({ icon: 'success', title: '推荐已生成' });
          that.loadReviewPlan();
        } else if (status === 'failed' || status === 'cancelled' || status === 'canceled') {
          clearInterval(that._jobTimer);
          that._jobTimer = null;
          that.setData({
            generating: false,
            genStatusText: '生成' + (status === 'failed' ? '失败' : '已取消')
          });
          wx.showToast({ icon: 'none', title: '生成失败' });
        }
      }, function (err) {
        // 单次查询失败不中断
      });
    }, 3000);
  },

  _statusText: function (status) {
    var map = {
      pending: '排队中...',
      running: '正在生成推荐...',
      processing: '正在生成推荐...'
    };
    return map[status] || '处理中...';
  },

  /**
   * 点击题目跳转到错题详情
   */
  onTapItem: function (e) {
    var item = e.currentTarget.dataset.item;
    if (!item) return;

    // 标记已复习
    this._markReviewed(item);

    // 跳转到错题详情页
    var questionId = item.question_id || item._id || item.id;
    if (!questionId) {
      wx.showToast({ icon: 'none', title: '无法获取题目ID' });
      return;
    }
    wx.navigateTo({
      url: '/pages/detail/index?id=' + questionId
    });
  },

  /**
   * 标记已复习（本地更新进度）
   */
  _markReviewed: function (item) {
    if (item.reviewed) return;
    item.reviewed = true;
    var reviewed = this.data.reviewed + 1;
    var percent = this.data.total > 0 ? Math.round((reviewed / this.data.total) * 100) : 0;
    this.setData({
      reviewed: reviewed,
      progressPercent: percent
    });
  },

  /**
   * 格式化日期
   */
  _formatDate: function (d) {
    var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  },

  onUnload: function () {
    if (this._jobTimer) {
      clearInterval(this._jobTimer);
      this._jobTimer = null;
    }
  }
});
