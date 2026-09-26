const api = require('../../utils/api.js');

Page({
  data: {
    groups: [],
    filteredGroups: [],
    totalWrong: 0,
    unresolvedCount: 0,
    resolvedCount: 0,
    activeTab: 'all',
    // 科目筛选
    examFilter: '',
    examOptions: [],
    examPickerIndex: 0,
    allNotes: [],
    subjToExamMap: {}
  },

  onShow: function () {
    this.load();
  },

  onPullDownRefresh: function () {
    this.load(function () { wx.stopPullDownRefresh(); });
  },

  load: function (done) {
    var that = this;
    var openid = wx.getStorageSync('openid');
    if (!openid) {
      if (done) done();
      return;
    }

    var db = api.database();
    var selectedExamId = wx.getStorageSync('home_selected_exam_id') || '';

    // Step 1: 加载subjects建立 subjectId -> examId 映射
    db.collection('subjects').get({
      success: function (subjRes) {
        var subjects = subjRes.data || [];
        var subjToExam = {};
        var examIds = {};
        subjects.forEach(function (s) {
          subjToExam[s._id] = s.pid;
          if (s.pid) examIds[s.pid] = true;
        });

        // Step 2: 加载exam列表获取考试名称
        db.collection('exam').get({
          success: function (examRes) {
            var exams = examRes.data || [];
            var examNameMap = {};
            exams.forEach(function (e) {
              examNameMap[e._id] = e.name;
            });

            // 构建筛选选项
            var examOptions = [{ value: '', label: '全部科目' }];
            Object.keys(examIds).forEach(function (eid) {
              if (examNameMap[eid]) {
                examOptions.push({ value: eid, label: examNameMap[eid] });
              }
            });

            // 默认选中当前科目
            var defaultIdx = 0;
            if (selectedExamId) {
              for (var i = 0; i < examOptions.length; i++) {
                if (examOptions[i].value === selectedExamId) {
                  defaultIdx = i;
                  break;
                }
              }
            }

            that.setData({
              examOptions: examOptions,
              examPickerIndex: defaultIdx,
              examFilter: examOptions[defaultIdx].value,
              subjToExamMap: subjToExam
            });

            // Step 3: 加载notes
            that.loadNotes(subjToExam, done);
          },
          fail: function () {
            that.loadNotes({}, done);
          }
        });
      },
      fail: function () {
        that.loadNotes({}, done);
      }
    });
  },

  loadNotes: function (subjToExam, done) {
    var that = this;
    var openid = wx.getStorageSync('openid');
    var db = api.database();

    db.collection('notes').where({ _openid: openid }).get({
      success: function (res) {
        var notes = res.data || [];
        // 为每个note添加_examId字段
        notes.forEach(function (n) {
          var subjId = (n.question && n.question.examid) || '';
          n._examId = subjToExam[subjId] || '';
        });
        that.setData({ allNotes: notes });
        that.processNotes();
        if (done) done();
      },
      fail: function (err) {
        console.error('[错题] 查询失败', err);
        wx.showToast({ icon: 'none', title: '错题加载失败' });
        if (done) done();
      }
    });
  },

  processNotes: function () {
    var that = this;
    var notes = this.data.allNotes.slice();
    var examFilter = this.data.examFilter;

    // 按科目筛选
    if (examFilter) {
      notes = notes.filter(function (n) { return n._examId === examFilter; });
    }

    var resolvedCount = notes.filter(function (n) { return n.resolved; }).length;
    var unresolvedCount = notes.length - resolvedCount;

    var map = {};
    notes.forEach(function (n) {
      var key = n.ordernum || 'unknown';
      if (!map[key]) {
        map[key] = { ordernum: key, count: 0, resolvedCount: 0, createTime: '', notes: [] };
      }
      map[key].count += 1;
      if (n.resolved) map[key].resolvedCount += 1;
      map[key].notes.push(n);
      var t = n.createTime || '';
      if (t && (!map[key].createTime || t > map[key].createTime)) {
        map[key].createTime = t;
      }
    });

    var groups = Object.values(map).sort(function (a, b) {
      return b.ordernum > a.ordernum ? 1 : -1;
    });

    that.setData({
      groups: groups,
      totalWrong: notes.length,
      resolvedCount: resolvedCount,
      unresolvedCount: unresolvedCount
    });
    that.applyFilter();
  },

  // ===== 科目筛选切换 =====
  onExamFilterChange: function (e) {
    var idx = parseInt(e.detail.value);
    this.setData({
      examPickerIndex: idx,
      examFilter: this.data.examOptions[idx].value
    });
    this.processNotes();
  },

  switchTab: function (e) {
    var tab = e.currentTarget.dataset.tab;
    this.setData({ activeTab: tab });
    this.applyFilter();
  },

  applyFilter: function () {
    var groups = this.data.groups.slice();
    var tab = this.data.activeTab;

    if (tab === 'unresolved') {
      groups = groups.filter(function (g) {
        return g.count > g.resolvedCount;
      });
      groups.forEach(function (g) {
        g.displayCount = g.count - g.resolvedCount;
      });
    } else if (tab === 'resolved') {
      groups = groups.filter(function (g) {
        return g.resolvedCount > 0;
      });
      groups.forEach(function (g) {
        g.displayCount = g.resolvedCount;
      });
    } else {
      groups.forEach(function (g) {
        g.displayCount = g.count;
      });
    }

    this.setData({ filteredGroups: groups });
  },

  goRedo: function (e) {
    var ordernum = e.currentTarget.dataset.ordernum;
    wx.navigateTo({ url: '/pages/note/note?ordernum=' + ordernum });
  }
});
