const api = require('../../utils/api.js');

Page({
  data: {
    length: 0,
    rightNum: 0,
    errNum: 0,
    unAnswerNum: 0,
    ordernum: '',
    score: 0,
    examMode: false,
    assessmentMode: false,
    duration: 0,
    durationDisplay: '',
    avgTimePerQuestion: '',
    passed: false,
    passLine: 60,
    assessmentResults: null,
    weakPoints: [],
    suggestion: '',
    prevScore: null,
    scoreTrend: ''
  },

  onLoad: function (e) {
    var length = parseInt(e.length, 10) || 0;
    var rightNum = parseInt(e.rightNum, 10) || 0;
    var errNum = parseInt(e.errNum, 10) || 0;
    var unAnswerNum = Math.max(0, length - rightNum - errNum);
    var score = parseInt(e.score, 10);
    if (isNaN(score)) {
      score = length ? Math.round(rightNum / length * 100) : 0;
    }
    var examMode = e.examMode === 'true';
    var assessmentMode = e.assessmentMode === 'true';
    var duration = parseInt(e.duration, 10) || 0;
    var passed = score >= 60;

    var durationDisplay = '';
    var avgTimePerQuestion = '';
    if (duration > 0) {
      var h = Math.floor(duration / 3600);
      var m = Math.floor((duration % 3600) / 60);
      var s = duration % 60;
      if (h > 0) {
        durationDisplay = h + '小时' + m + '分' + s + '秒';
      } else if (m > 0) {
        durationDisplay = m + '分' + s + '秒';
      } else {
        durationDisplay = s + '秒';
      }
      if (length > 0) {
        var avg = Math.round(duration / length);
        avgTimePerQuestion = avg + '秒/题';
      }
    }

    this.setData({
      ordernum: e.ordernum || '',
      rightNum: rightNum,
      errNum: errNum,
      length: length,
      unAnswerNum: unAnswerNum,
      score: score,
      examMode: examMode,
      assessmentMode: assessmentMode,
      duration: duration,
      durationDisplay: durationDisplay,
      avgTimePerQuestion: avgTimePerQuestion,
      passed: passed
    });

    if (assessmentMode) {
      this.loadAssessmentReport(e.ordernum);
    }
  },

  loadAssessmentReport: function (assessmentId) {
    var that = this;
    if (!assessmentId) return;
    var db = api.database();
    db.collection('assessments').doc(assessmentId).get({
      success: function (res) {
        var assessment = res.data || {};
        var results = assessment.results || {};
        var weakPoints = results.weakPoints || [];
        var suggestion = results.suggestion || '';
        var byKp = results.byKnowledgePoint || [];

        var weakKpList = byKp.filter(function (kp) {
          return kp.rate < 60;
        });

        that.setData({
          assessmentResults: results,
          weakPoints: weakKpList,
          suggestion: suggestion
        });

        that.loadPrevAssessment(assessment.examId, assessmentId);
      },
      fail: function (err) {
        console.error('[examresult] loadAssessmentReport fail', err);
      }
    });
  },

  loadPrevAssessment: function (examId, currentId) {
    var that = this;
    if (!examId) return;
    var db = api.database();
    var openid = wx.getStorageSync('openid');
    if (!openid) return;

    db.collection('assessments').where({ _openid: openid, examId: examId }).get({
      success: function (res) {
        var all = (res.data || []).filter(function (a) {
          return a._id !== currentId;
        });
        if (all.length === 0) return;
        all.sort(function (a, b) {
          return (a.createTime || '').localeCompare(b.createTime || '');
        });
        var prev = all[all.length - 1];
        var prevScore = prev.results ? prev.results.score : 0;
        var trend = '';
        if (prevScore !== undefined) {
          if (that.data.score > prevScore) trend = 'up';
          else if (that.data.score < prevScore) trend = 'down';
          else trend = 'same';
        }
        that.setData({ prevScore: prevScore, scoreTrend: trend });
      }
    });
  },

  goPracticeWeakKp: function () {
    if (this.data.weakPoints.length === 0) {
      wx.showToast({ icon: 'none', title: '暂无薄弱知识点' });
      return;
    }
    var weakKpIds = this.data.weakPoints.map(function (kp) { return kp.kpId; });
    var weakKpNames = this.data.weakPoints.map(function (kp) { return kp.kpName; });
    wx.setStorageSync('weak_kp_ids', weakKpIds);
    wx.setStorageSync('weak_kp_names', weakKpNames);
    var examId = '';
    if (this.data.assessmentResults) {
      examId = this.data.assessmentResults.examId || '';
    }
    wx.navigateTo({
      url: '/pages/knowledgepoint/index?examId=' + examId + '&weakKpMode=true'
    });
  },

  examBack: function () {
    if (this.data.ordernum) {
      wx.navigateTo({
        url: '/pages/note/note?ordernum=' + this.data.ordernum
      });
    } else {
      wx.showToast({ icon: 'none', title: '无本次作答记录' });
    }
  },

  goScore: function () {
    var length = this.data.length;
    var score = this.data.score;
    wx.redirectTo({
      url: '/pages/score/index?score=' + score +
        '&rightNum=' + this.data.rightNum +
        '&length=' + length +
        '&ordernum=' + this.data.ordernum
    });
  },

  exam_repeat: function () {
    wx.switchTab({ url: '/pages/home/index' });
  }
});
