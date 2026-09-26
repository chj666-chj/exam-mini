const api = require('../../utils/api.js');

Page({
  data: {
    examList: [],
    selectedExamId: '',
    selectedExamName: '',
    examPickerIndex: 0,
    subjects: [],
    // 配置参数
    questionCount: 50,
    countOptions: [10, 20, 30, 50, 100],
    countIndex: 3,
    timeLimit: 60,
    timeOptions: [30, 60, 90, 120, 0],
    timeLabels: ['30 分钟', '60 分钟', '90 分钟', '120 分钟', '不限时'],
    timeIndex: 1,
    mixChapters: true,
    // 状态
    loading: true,
    error: '',
    totalAvailable: 0
  },

  onLoad: function () {
    this.loadExamList();
  },

  loadExamList: function () {
    var that = this;
    var db = api.database();
    db.collection('exam').get({
      success: function (res) {
        var exams = res.data || [];
        if (exams.length === 0) {
          that.setData({ loading: false, error: '暂无考试数据' });
          return;
        }
        var cachedId = wx.getStorageSync('home_selected_exam_id') || '';
        var idx = 0;
        if (cachedId) {
          for (var i = 0; i < exams.length; i++) {
            if (exams[i]._id === cachedId) { idx = i; break; }
          }
        }
        that.setData({
          examList: exams,
          selectedExamId: exams[idx]._id,
          selectedExamName: exams[idx].name,
          examPickerIndex: idx,
          loading: false
        });
        that.loadSubjects(exams[idx]._id);
      },
      fail: function (err) {
        console.error('[examsetup] loadExamList fail', err);
        that.setData({ loading: false, error: '考试数据加载失败' });
      }
    });
  },

  loadSubjects: function (examId) {
    var that = this;
    var db = api.database();
    db.collection('subjects').where({ pid: examId }).get({
      success: function (res) {
        var subjects = res.data || [];
        subjects.sort(function (a, b) {
          return (a.sortWeight || 0) - (b.sortWeight || 0);
        });
        that.setData({ subjects: subjects });
        that.countTotalQuestions(subjects);
      },
      fail: function () {
        that.setData({ subjects: [], totalAvailable: 0 });
      }
    });
  },

  countTotalQuestions: function (subjects) {
    var that = this;
    var db = api.database();
    var total = 0;
    var loaded = 0;
    if (subjects.length === 0) {
      that.setData({ totalAvailable: 0 });
      return;
    }
    subjects.forEach(function (subj) {
      db.collection('questions').where({ examid: subj._id }).get({
        success: function (res) {
          total += (res.data || []).length;
          loaded++;
          if (loaded === subjects.length) {
            that.setData({ totalAvailable: total });
          }
        },
        fail: function () {
          loaded++;
          if (loaded === subjects.length) {
            that.setData({ totalAvailable: total });
          }
        }
      });
    });
  },

  // ===== 选择器回调 =====
  onExamChange: function (e) {
    var idx = parseInt(e.detail.value);
    var exam = this.data.examList[idx];
    this.setData({
      selectedExamId: exam._id,
      selectedExamName: exam.name,
      examPickerIndex: idx
    });
    this.loadSubjects(exam._id);
  },

  onCountChange: function (e) {
    var idx = parseInt(e.detail.value);
    this.setData({
      countIndex: idx,
      questionCount: this.data.countOptions[idx]
    });
  },

  onTimeChange: function (e) {
    var idx = parseInt(e.detail.value);
    this.setData({
      timeIndex: idx,
      timeLimit: this.data.timeOptions[idx]
    });
  },

  toggleMixChapters: function () {
    this.setData({ mixChapters: !this.data.mixChapters });
  },

  // ===== 开始考试 =====
  startExam: function () {
    var that = this;
    var examId = this.data.selectedExamId;
    if (!examId) {
      wx.showToast({ icon: 'none', title: '请选择考试科目' });
      return;
    }

    var subjects = this.data.subjects;
    if (subjects.length === 0) {
      wx.showToast({ icon: 'none', title: '该考试暂无科目' });
      return;
    }

    wx.showLoading({ title: '生成试卷中...' });

    // 加载题目
    if (this.data.mixChapters) {
      this.loadAllQuestions(examId, subjects);
    } else {
      // 仅加载第一个科目的题目
      this.loadSingleSubjectQuestions(subjects[0]);
    }
  },

  loadAllQuestions: function (examId, subjects) {
    var that = this;
    var db = api.database();
    var allQuestions = [];
    var loaded = 0;

    subjects.forEach(function (subj) {
      db.collection('questions').where({ examid: subj._id }).get({
        success: function (res) {
          (res.data || []).forEach(function (q) {
            if (typeof q.options === 'string') {
              try { q.options = JSON.parse(q.options); } catch (e) { q.options = []; }
            }
            q.options = q.options || [];
            q.qtype = q.qtype || q.type || 'single';
            allQuestions.push(q);
          });
          loaded++;
          if (loaded === subjects.length) {
            that.assembleExam(allQuestions);
          }
        },
        fail: function () {
          loaded++;
          if (loaded === subjects.length) {
            that.assembleExam(allQuestions);
          }
        }
      });
    });
  },

  loadSingleSubjectQuestions: function (subject) {
    var that = this;
    var db = api.database();
    db.collection('questions').where({ examid: subject._id }).get({
      success: function (res) {
        var questions = (res.data || []).map(function (q) {
          if (typeof q.options === 'string') {
            try { q.options = JSON.parse(q.options); } catch (e) { q.options = []; }
          }
          q.options = q.options || [];
          q.qtype = q.qtype || q.type || 'single';
          return q;
        });
        that.assembleExam(questions);
      },
      fail: function () {
        wx.hideLoading();
        wx.showToast({ icon: 'none', title: '题目加载失败' });
      }
    });
  },

  assembleExam: function (questions) {
    wx.hideLoading();
    if (questions.length === 0) {
      wx.showToast({ icon: 'none', title: '暂无可用题目' });
      return;
    }

    // 随机打乱
    questions.sort(function () { return Math.random() - 0.5; });

    // 按配置截取题量
    var count = this.data.questionCount;
    if (count > 0 && count < questions.length) {
      questions = questions.slice(0, count);
    }

    // 存入 storage
    wx.setStorageSync('quiz_questions', questions);
    wx.setStorageSync('quiz_mode', 'answer');
    wx.setStorageSync('quiz_display', 'single');
    wx.setStorageSync('quiz_exam_mode', 'true');
    wx.setStorageSync('quiz_time_limit', this.data.timeLimit);

    // 缓存科目信息
    var examInfo = {
      _id: this.data.selectedExamId,
      name: this.data.selectedExamName
    };
    wx.setStorageSync('subject', examInfo);

    // 跳转考试页
    wx.navigateTo({
      url: '/pages/exam/exam?id=' + this.data.selectedExamId +
        '&mode=answer&examMode=true&timeLimit=' + this.data.timeLimit +
        '&questionCount=' + questions.length
    });
  },

  goBack: function () {
    wx.navigateBack();
  },

  onShareAppMessage: function () {
    return { title: '考试助手 - 模拟考试', path: '/pages/home/index' };
  }
});
