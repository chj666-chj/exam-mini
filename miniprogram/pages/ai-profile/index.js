/**
 * AI 学习画像页
 * 基于答题数据分析用户能力分布、薄弱知识点、错误模式和学习趋势
 * 使用 Canvas 2D 绘制雷达图和趋势折线图
 */
var api = require('../../utils/api.js');

// 能力维度配置
var ABILITY_DIMS = [
  { key: 'basics', label: '基础知识' },
  { key: 'application', label: '应用能力' },
  { key: 'analysis', label: '综合分析' },
  { key: 'calculation', label: '计算能力' },
  { key: 'memory', label: '记忆理解' }
];

Page({
  data: {
    // 画像数据
    profile: null,
    abilities: {},
    weakPoints: [],
    errorPatterns: [],
    trend: { dates: [], accuracies: [] },
    practiceRecs: [],
    avgAccuracy: 0,
    totalQuestions: 0,
    // 生成状态
    generating: false,
    genPercent: 0,
    genStatusText: '',
    // 加载状态
    loading: true,
    // Canvas 尺寸
    canvasWidth: 300,
    canvasHeight: 260
  },

  onLoad: function () {
    // 获取屏幕宽度用于 Canvas 尺寸计算
    try {
      var sysInfo = wx.getSystemInfoSync();
      var canvasWidth = Math.min(sysInfo.windowWidth - 48, 340);
      this.setData({
        canvasWidth: canvasWidth,
        canvasHeight: Math.round(canvasWidth * 0.85)
      });
    } catch (e) {
      // 使用默认尺寸
    }
    this.loadProfile();
  },

  onPullDownRefresh: function () {
    var that = this;
    this.loadProfile(function () {
      wx.stopPullDownRefresh();
    });
  },

  /**
   * 加载学习画像
   */
  loadProfile: function (done) {
    var that = this;
    this.setData({ loading: true });
    api.aiLearningProfile().then(function (res) {
      that._processProfileData(res);
      if (done) done();
    }, function (err) {
      that.setData({ loading: false });
      if (err && err.statusCode !== 404) {
        wx.showToast({ icon: 'none', title: '加载失败' });
      }
      if (done) done();
    });
  },

  /**
   * 处理画像数据
   */
  _processProfileData: function (res) {
    if (!res || (!res.abilities && !res.weak_points && !res.generated_at)) {
      this.setData({
        profile: null,
        loading: false
      });
      return;
    }

    var abilities = res.abilities || {};
    var weakPoints = res.weak_points || res.weak_knowledge || [];
    var errorPatterns = res.error_patterns || res.common_errors || [];
    var trend = res.trend || { dates: [], accuracies: [] };
    var practiceRecs = res.practice_recommendations || res.recommendations || [];

    // 格式化能力维度数据（确保值为 0-1 范围）
    ABILITY_DIMS.forEach(function (dim) {
      var v = abilities[dim.key];
      if (v == null) {
        v = 0;
      } else if (v > 1) {
        v = v / 100;
      }
      abilities[dim.key] = v;
    });

    // 格式化薄弱知识点
    weakPoints.forEach(function (wp) {
      var acc = wp.accuracy;
      if (acc == null) acc = 0;
      else if (acc > 1) acc = acc / 100;
      wp.accuracyPercent = Math.round(acc * 100);
      wp.accuracyLevel = acc >= 0.6 ? 'medium' : 'low';
      wp.totalCount = wp.total || wp.count || 0;
      wp.recommendation = wp.recommendation || wp.suggestion || '建议针对性练习';
    });

    // 格式化错误模式
    errorPatterns.forEach(function (ep) {
      ep.frequencyText = (ep.frequency || 0) + ' 次';
      ep.typeName = ep.type || ep.pattern || '未知错误';
      ep.descText = ep.description || '';
    });

    // 格式化趋势数据
    var trendDates = trend.dates || [];
    var trendAccuracies = (trend.accuracies || []).map(function (a) {
      if (a > 1) return a / 100;
      return a;
    });
    // 最多取最近5次
    if (trendDates.length > 5) {
      trendDates = trendDates.slice(-5);
      trendAccuracies = trendAccuracies.slice(-5);
    }

    // 格式化练习推荐
    practiceRecs.forEach(function (rec) {
      rec.typeName = rec.type || rec.question_type || '练习题';
      rec.kpName = rec.knowledge_point || rec.knowledge || '综合练习';
      rec.countText = (rec.count || 10) + ' 题';
    });

    var avgAccuracy = res.avg_accuracy || 0;
    if (avgAccuracy > 1) avgAccuracy = avgAccuracy / 100;

    this.setData({
      profile: res,
      abilities: abilities,
      weakPoints: weakPoints,
      errorPatterns: errorPatterns,
      trend: { dates: trendDates, accuracies: trendAccuracies },
      practiceRecs: practiceRecs,
      avgAccuracy: Math.round(avgAccuracy * 100),
      totalQuestions: res.total_questions || 0,
      loading: false
    });

    // 延迟绘制 Canvas（等待 DOM 更新）
    var that = this;
    setTimeout(function () {
      that._drawRadarChart();
      that._drawTrendChart();
    }, 200);
  },

  /**
   * 生成分析报告
   */
  generateProfile: function () {
    if (this.data.generating) return;
    var that = this;
    this.setData({
      generating: true,
      genPercent: 0,
      genStatusText: '正在生成分析报告...'
    });

    api.aiGenerateLearningProfile().then(function (res) {
      var jobId = res && (res.job_id || res.jobId);
      if (!jobId) {
        if (res && res.abilities) {
          that._processProfileData(res);
          that.setData({ generating: false, genPercent: 100 });
          wx.showToast({ icon: 'success', title: '报告已生成' });
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
            genStatusText: '报告生成完成'
          });
          wx.showToast({ icon: 'success', title: '报告已生成' });
          that.loadProfile();
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
      running: '正在分析答题数据...',
      processing: '正在分析答题数据...'
    };
    return map[status] || '处理中...';
  },

  /**
   * 绘制能力雷达图
   */
  _drawRadarChart: function () {
    var that = this;
    var query = wx.createSelectorQuery();
    query.select('#radarCanvas').fields({ node: true, size: true }).exec(function (res) {
      if (!res || !res[0] || !res[0].node) return;
      var canvas = res[0].node;
      var ctx = canvas.getContext('2d');
      var dpr = 1;
      try {
        dpr = wx.getSystemInfoSync().pixelRatio;
      } catch (e) {}
      var w = res[0].width;
      var h = res[0].height;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.scale(dpr, dpr);

      var centerX = w / 2;
      var centerY = h / 2 + 5;
      var radius = Math.min(w, h) / 2 - 40;
      var sides = ABILITY_DIMS.length;
      var levels = 4; // 网格层数

      ctx.clearRect(0, 0, w, h);

      // 绘制网格（同心多边形）
      for (var lv = 1; lv <= levels; lv++) {
        var r = (radius / levels) * lv;
        ctx.beginPath();
        for (var i = 0; i <= sides; i++) {
          var angle = (Math.PI * 2 / sides) * i - Math.PI / 2;
          var x = centerX + r * Math.cos(angle);
          var y = centerY + r * Math.sin(angle);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.strokeStyle = '#e0e6ed';
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // 绘制轴线
      for (var j = 0; j < sides; j++) {
        var axisAngle = (Math.PI * 2 / sides) * j - Math.PI / 2;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(centerX + radius * Math.cos(axisAngle), centerY + radius * Math.sin(axisAngle));
        ctx.strokeStyle = '#e0e6ed';
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // 绘制数据多边形
      ctx.beginPath();
      for (var k = 0; k < sides; k++) {
        var dataAngle = (Math.PI * 2 / sides) * k - Math.PI / 2;
        var dimKey = ABILITY_DIMS[k].key;
        var val = that.data.abilities[dimKey] || 0;
        var dataR = radius * Math.max(0, Math.min(1, val));
        var dx = centerX + dataR * Math.cos(dataAngle);
        var dy = centerY + dataR * Math.sin(dataAngle);
        if (k === 0) ctx.moveTo(dx, dy);
        else ctx.lineTo(dx, dy);
      }
      ctx.closePath();
      ctx.fillStyle = 'rgba(74, 144, 243, 0.2)';
      ctx.fill();
      ctx.strokeStyle = '#4A90F3';
      ctx.lineWidth = 2;
      ctx.stroke();

      // 绘制数据点
      for (var m = 0; m < sides; m++) {
        var ptAngle = (Math.PI * 2 / sides) * m - Math.PI / 2;
        var ptKey = ABILITY_DIMS[m].key;
        var ptVal = that.data.abilities[ptKey] || 0;
        var ptR = radius * Math.max(0, Math.min(1, ptVal));
        var px = centerX + ptR * Math.cos(ptAngle);
        var py = centerY + ptR * Math.sin(ptAngle);
        ctx.beginPath();
        ctx.arc(px, py, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#4A90F3';
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // 绘制标签
      ctx.font = '12px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#606266';
      for (var n = 0; n < sides; n++) {
        var labelAngle = (Math.PI * 2 / sides) * n - Math.PI / 2;
        var labelR = radius + 20;
        var lx = centerX + labelR * Math.cos(labelAngle);
        var ly = centerY + labelR * Math.sin(labelAngle);
        ctx.fillText(ABILITY_DIMS[n].label, lx, ly);
      }
    });
  },

  /**
   * 绘制学习趋势折线图
   */
  _drawTrendChart: function () {
    var that = this;
    var query = wx.createSelectorQuery();
    query.select('#trendCanvas').fields({ node: true, size: true }).exec(function (res) {
      if (!res || !res[0] || !res[0].node) return;
      var canvas = res[0].node;
      var ctx = canvas.getContext('2d');
      var dpr = 1;
      try {
        dpr = wx.getSystemInfoSync().pixelRatio;
      } catch (e) {}
      var w = res[0].width;
      var h = res[0].height;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.scale(dpr, dpr);

      var padding = { top: 20, right: 20, bottom: 30, left: 40 };
      var chartW = w - padding.left - padding.right;
      var chartH = h - padding.top - padding.bottom;

      ctx.clearRect(0, 0, w, h);

      var dates = that.data.trend.dates;
      var accuracies = that.data.trend.accuracies;

      if (!dates.length || !accuracies.length) {
        ctx.font = '13px sans-serif';
        ctx.fillStyle = '#909399';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('暂无趋势数据', w / 2, h / 2);
        return;
      }

      var n = dates.length;
      var stepX = n > 1 ? chartW / (n - 1) : 0;

      // 绘制 Y 轴刻度线 (0%, 50%, 100%)
      ctx.strokeStyle = '#e0e6ed';
      ctx.lineWidth = 1;
      ctx.font = '10px sans-serif';
      ctx.fillStyle = '#909399';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      var yLabels = [0, 0.5, 1];
      for (var yi = 0; yi < yLabels.length; yi++) {
        var yVal = yLabels[yi];
        var yPos = padding.top + chartH - (chartH * yVal);
        ctx.beginPath();
        ctx.moveTo(padding.left, yPos);
        ctx.lineTo(padding.left + chartW, yPos);
        ctx.strokeStyle = '#e0e6ed';
        ctx.stroke();
        ctx.fillText(Math.round(yVal * 100) + '%', padding.left - 6, yPos);
      }

      // 绘制折线
      ctx.beginPath();
      ctx.strokeStyle = '#4A90F3';
      ctx.lineWidth = 2;
      for (var i = 0; i < n; i++) {
        var xPos = padding.left + (n > 1 ? stepX * i : chartW / 2);
        var yPos = padding.top + chartH - (chartH * (accuracies[i] || 0));
        if (i === 0) ctx.moveTo(xPos, yPos);
        else ctx.lineTo(xPos, yPos);
      }
      ctx.stroke();

      // 绘制折线下方填充
      ctx.beginPath();
      for (var fi = 0; fi < n; fi++) {
        var fxPos = padding.left + (n > 1 ? stepX * fi : chartW / 2);
        var fyPos = padding.top + chartH - (chartH * (accuracies[fi] || 0));
        if (fi === 0) ctx.moveTo(fxPos, fyPos);
        else ctx.lineTo(fxPos, fyPos);
      }
      var lastX = padding.left + (n > 1 ? stepX * (n - 1) : chartW / 2);
      ctx.lineTo(lastX, padding.top + chartH);
      ctx.lineTo(padding.left, padding.top + chartH);
      ctx.closePath();
      ctx.fillStyle = 'rgba(74, 144, 243, 0.1)';
      ctx.fill();

      // 绘制数据点
      for (var di = 0; di < n; di++) {
        var dxPos = padding.left + (n > 1 ? stepX * di : chartW / 2);
        var dyPos = padding.top + chartH - (chartH * (accuracies[di] || 0));
        ctx.beginPath();
        ctx.arc(dxPos, dyPos, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#4A90F3';
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();

        // 在点上方标注百分比
        ctx.font = '11px sans-serif';
        ctx.fillStyle = '#4A90F3';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(Math.round((accuracies[di] || 0) * 100) + '%', dxPos, dyPos - 6);
      }

      // 绘制 X 轴日期标签
      ctx.font = '10px sans-serif';
      ctx.fillStyle = '#909399';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      for (var xi = 0; xi < n; xi++) {
        var xxPos = padding.left + (n > 1 ? stepX * xi : chartW / 2);
        var dateLabel = dates[xi] || '';
        // 简化日期显示：只取月-日
        if (dateLabel.length > 5) {
          dateLabel = dateLabel.substring(5);
        }
        ctx.fillText(dateLabel, xxPos, padding.top + chartH + 6);
      }
    });
  },

  /**
   * 跳转到定向练习
   */
  onTapPractice: function (e) {
    var rec = e.currentTarget.dataset.rec;
    if (!rec) return;
    var kpName = rec.kpName || '';
    var typeName = rec.typeName || '';
    // 跳转到练习页面，传知识点参数
    wx.navigateTo({
      url: '/pages/subject/index?kp=' + encodeURIComponent(kpName) + '&type=' + encodeURIComponent(typeName),
      fail: function () {
        // 如果目标页面不存在，跳转到首页
        wx.switchTab({ url: '/pages/home/index' });
      }
    });
  },

  onUnload: function () {
    if (this._jobTimer) {
      clearInterval(this._jobTimer);
      this._jobTimer = null;
    }
  }
});
