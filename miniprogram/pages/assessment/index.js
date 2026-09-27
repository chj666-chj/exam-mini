const api = require('../../utils/api.js');

Page({
  data: {
    examList: [],
    selectedExamId: '',
    selectedExamName: '',
    examPickerIndex: 0,
    chapterList: [],
    kpList: [],
    scope: 'all',
    selectedChapterIds: [],
    selectedKpIds: [],
    questionCount: 20,
    countOptions: [10, 20, 30, 50, 100],
    countIndex: 1,
    difficulty: [1, 2, 3],
    difficultyOptions: [
      { value: 1, label: '简单', selected: true },
      { value: 2, label: '中等', selected: true },
      { value: 3, label: '困难', selected: true }
    ],
    qtypes: [
      { value: 'single', label: '单选题', selected: true },
      { value: 'multiple', label: '多选题', selected: true },
      { value: 'judge', label: '判断题', selected: true }
    ],
    timeLimit: 30,
    timeOptions: [0, 10, 20, 30, 60],
    timeLabels: ['不限时', '10分钟', '20分钟', '30分钟', '60分钟'],
    timeIndex: 3,
    feedbackMode: 'unified',
    randomOrder: true,
    estimatedCount: 0,
    loading: false,
    starting: false
  },

  onLoad: function (options) {
    var examId = options.examId || '';
    this.setData({ selectedExamId: examId });
    this.loadExamList(examId);
  },

  loadExamList: function (presetExamId) {
    var that = this;
    var db = api.database();
    db.collection('exam').get({
      success: function (res) {
        var exams = res.data || [];
        if (exams.length === 0) return;
        var selectedIdx = 0;
        if (presetExamId) {
          for (var i = 0; i < exams.length; i++) {
            if (exams[i]._id === presetExamId) { selectedIdx = i; break; }
          }
        }
        var selectedExam = exams[selectedIdx];
        that.setData({
          examList: exams,
          selectedExamId: selectedExam._id,
          selectedExamName: selectedExam.name,
          examPickerIndex: selectedIdx
        });
        that.loadChapters(selectedExam._id);
      }
    });
  },

  loadChapters: function (examId) {
    var that = this;
    var db = api.database();
    db.collection('subjects').where({ pid: examId }).get({
      success: function (res) {
        var subjects = (res.data || []).sort(function (a, b) {
          return (a.sortWeight || 0) - (b.sortWeight || 0);
        });
        that.setData({ chapterList: subjects, selectedChapterIds: subjects.map(function (s) { return s._id; }) });
        that.loadKps(examId);
      }
    });
  },

  loadKps: function (examId) {
    var that = this;
    var db = api.database();
    db.collection('knowledgepoints').where({ examId: examId }).get({
      success: function (res) {
        var kps = (res.data || []).filter(function (kp) { return kp.level === 2; });
        that.setData({ kpList: kps, selectedKpIds: kps.map(function (kp) { return kp._id; }) });
        that.estimateCount();
      },
      fail: function () {
        that.estimateCount();
      }
    });
  },

  onExamChange: function (e) {
    var idx = parseInt(e.detail.value);
    var exams = this.data.examList;
    if (idx < 0 || idx >= exams.length) return;
    var selectedExam = exams[idx];
    this.setData({
      selectedExamId: selectedExam._id,
      selectedExamName: selectedExam.name,
      examPickerIndex: idx,
      scope: 'all'
    });
    this.loadChapters(selectedExam._id);
  },

  selectScope: function (e) {
    var scope = e.currentTarget.dataset.scope;
    this.setData({ scope: scope });
    this.estimateCount();
  },

  toggleChapter: function (e) {
    var chId = e.currentTarget.dataset.chid;
    var selected = this.data.selectedChapterIds.slice();
    var idx = selected.indexOf(chId);
    if (idx > -1) {
      selected.splice(idx, 1);
    } else {
      selected.push(chId);
    }
    this.setData({ selectedChapterIds: selected });
    this.estimateCount();
  },

  toggleKp: function (e) {
    var kpId = e.currentTarget.dataset.kpid;
    var selected = this.data.selectedKpIds.slice();
    var idx = selected.indexOf(kpId);
    if (idx > -1) {
      selected.splice(idx, 1);
    } else {
      selected.push(kpId);
    }
    this.setData({ selectedKpIds: selected });
    this.estimateCount();
  },

  onCountChange: function (e) {
    var idx = parseInt(e.detail.value);
    this.setData({ countIndex: idx, questionCount: this.data.countOptions[idx] });
  },

  toggleDifficulty: function (e) {
    var val = parseInt(e.currentTarget.dataset.val);
    var opts = this.data.difficultyOptions.slice();
    opts.forEach(function (d) {
      if (d.value === val) d.selected = !d.selected;
    });
    var diff = opts.filter(function (d) { return d.selected; }).map(function (d) { return d.value; });
    this.setData({ difficultyOptions: opts, difficulty: diff });
  },

  toggleQtype: function (e) {
    var val = e.currentTarget.dataset.val;
    var opts = this.data.qtypes.slice();
    opts.forEach(function (q) {
      if (q.value === val) q.selected = !q.selected;
    });
    this.setData({ qtypes: opts });
  },

  onTimeChange: function (e) {
    var idx = parseInt(e.detail.value);
    this.setData({ timeIndex: idx, timeLimit: this.data.timeOptions[idx] });
  },

  selectFeedback: function (e) {
    this.setData({ feedbackMode: e.currentTarget.dataset.mode });
  },

  toggleRandom: function () {
    this.setData({ randomOrder: !this.data.randomOrder });
  },

  estimateCount: function () {
    var that = this;
    var db = api.database();
    var examId = this.data.selectedExamId;
    if (!examId) { this.setData({ estimatedCount: 0 }); return; }

    var chapterIds = this.data.scope === 'chapters' ? this.data.selectedChapterIds : [];
    var kpIds = this.data.scope === 'knowledgepoints' ? this.data.selectedKpIds : [];

    if (this.data.scope === 'all') {
      db.collection('subjects').where({ pid: examId }).get({
        success: function (res) {
          var subjects = res.data || [];
          var total = 0;
          var loaded = 0;
          if (subjects.length === 0) { that.setData({ estimatedCount: 0 }); return; }
          subjects.forEach(function (subj) {
            // subj._id 是章节 _id，题目中对应字段为 chapter（非 examid）
            db.collection('questions').where({ chapter: subj._id }).get({
              success: function (r) {
                total += (r.data || []).length;
                loaded++;
                if (loaded === subjects.length) {
                  that.setData({ estimatedCount: total });
                }
              },
              fail: function () {
                loaded++;
                if (loaded === subjects.length) that.setData({ estimatedCount: total });
              }
            });
          });
        }
      });
    } else if (this.data.scope === 'chapters') {
      var total = 0;
      var loaded = 0;
      if (chapterIds.length === 0) { this.setData({ estimatedCount: 0 }); return; }
      chapterIds.forEach(function (chId) {
        // chId 是章节 _id，题目中对应字段为 chapter（非 examid）
        db.collection('questions').where({ chapter: chId }).get({
          success: function (r) {
            total += (r.data || []).length;
            loaded++;
            if (loaded === chapterIds.length) that.setData({ estimatedCount: total });
          },
          fail: function () {
            loaded++;
            if (loaded === chapterIds.length) that.setData({ estimatedCount: total });
          }
        });
      });
    } else if (this.data.scope === 'knowledgepoints') {
      if (kpIds.length === 0) { this.setData({ estimatedCount: 0 }); return; }
      var total = 0;
      var loaded = 0;
      kpIds.forEach(function (kpId) {
        db.collection('questions').where({ knowledgePointIds__contains: kpId }).get({
          success: function (r) {
            total += (r.data || []).length;
            loaded++;
            if (loaded === kpIds.length) that.setData({ estimatedCount: total });
          },
          fail: function () {
            loaded++;
            if (loaded === kpIds.length) that.setData({ estimatedCount: total });
          }
        });
      });
    }
  },

  startAssessment: function () {
    var that = this;
    if (this.data.starting) return;

    var selectedQtypes = this.data.qtypes.filter(function (q) { return q.selected; }).map(function (q) { return q.value; });
    if (selectedQtypes.length === 0) {
      wx.showToast({ icon: 'none', title: '请至少选择一种题型' });
      return;
    }
    if (this.data.difficulty.length === 0) {
      wx.showToast({ icon: 'none', title: '请至少选择一种难度' });
      return;
    }

    this.setData({ starting: true });
    wx.showLoading({ title: '抽题中...' });

    this.fetchQuestions(function (questions) {
      questions = questions.filter(function (q) {
        var qt = q.qtype || q.type || 'single';
        if (selectedQtypes.indexOf(qt) === -1) return false;
        var diff = q.difficulty || 2;
        if (that.data.difficulty.indexOf(diff) === -1) return false;
        return true;
      });

      if (that.data.randomOrder) {
        questions = questions.sort(function () { return Math.random() - 0.5; });
      }

      var targetCount = that.data.questionCount;
      if (targetCount > 0 && targetCount < questions.length) {
        questions = questions.slice(0, targetCount);
      }

      if (questions.length === 0) {
        wx.hideLoading();
        that.setData({ starting: false });
        wx.showToast({ icon: 'none', title: '没有符合条件的题目' });
        return;
      }

      var config = {
        scope: that.data.scope,
        chapterIds: that.data.scope === 'chapters' ? that.data.selectedChapterIds : [],
        knowledgePointIds: that.data.scope === 'knowledgepoints' ? that.data.selectedKpIds : [],
        questionCount: that.data.questionCount,
        difficultyRange: that.data.difficulty,
        qtypeFilter: selectedQtypes,
        timeLimit: that.data.timeLimit,
        feedbackMode: that.data.feedbackMode,
        randomOrder: that.data.randomOrder
      };

      wx.setStorageSync('quiz_questions', questions);
      wx.setStorageSync('quiz_mode', 'answer');
      wx.setStorageSync('quiz_display', 'single');
      wx.setStorageSync('quiz_assessment_config', config);

      var url = '/pages/exam/exam?id=' + that.data.selectedExamId +
        '&mode=answer&assessmentMode=true' +
        '&timeLimit=' + that.data.timeLimit +
        '&feedbackMode=' + that.data.feedbackMode;

      wx.hideLoading();
      that.setData({ starting: false });
      wx.navigateTo({ url: url });
    });
  },

  fetchQuestions: function (callback) {
    var that = this;
    var db = api.database();
    var examId = this.data.selectedExamId;
    var allQuestions = [];
    var sources = [];

    if (this.data.scope === 'all') {
      this.data.chapterList.forEach(function (ch) {
        sources.push({ type: 'chapter', id: ch._id });
      });
    } else if (this.data.scope === 'chapters') {
      this.data.selectedChapterIds.forEach(function (chId) {
        sources.push({ type: 'chapter', id: chId });
      });
    } else if (this.data.scope === 'knowledgepoints') {
      this.data.selectedKpIds.forEach(function (kpId) {
        sources.push({ type: 'kp', id: kpId });
      });
    }

    if (sources.length === 0) { callback([]); return; }

    var loaded = 0;
    var seenIds = {};
    sources.forEach(function (src) {
      var query = src.type === 'chapter'
        ? { chapter: src.id }
        : { knowledgePointIds__contains: src.id };

      db.collection('questions').where(query).get({
        success: function (res) {
          (res.data || []).forEach(function (q) {
            if (!seenIds[q._id]) {
              seenIds[q._id] = true;
              if (typeof q.options === 'string') {
                try { q.options = JSON.parse(q.options); } catch (e) { q.options = []; }
              }
              q.options = q.options || [];
              q.qtype = q.qtype || q.type || 'single';
              allQuestions.push(q);
            }
          });
          loaded++;
          if (loaded === sources.length) callback(allQuestions);
        },
        fail: function () {
          loaded++;
          if (loaded === sources.length) callback(allQuestions);
        }
      });
    });
  }
});
