const api = require('../../utils/api.js');

Page({
  data: {
    examList: [],
    selectedExamId: '',
    selectedExamName: '',
    examPickerIndex: 0,
    treeData: [],
    expandedKeys: {},
    stats: { total: 0, practiced: 0, weak: 0, unpracticed: 0 },
    loading: true,
    detailKp: null,
    detailVisible: false,
    weakKpMode: false,
    weakKpIds: []
  },

  onLoad: function (options) {
    var examId = options.examId || '';
    var weakKpMode = options.weakKpMode === 'true';
    var weakKpIds = wx.getStorageSync('weak_kp_ids') || [];
    this.setData({
      selectedExamId: examId,
      weakKpMode: weakKpMode,
      weakKpIds: weakKpIds
    });
    this.loadExamList(examId);
  },

  loadExamList: function (presetExamId) {
    var that = this;
    var db = api.database();
    db.collection('exam').get({
      success: function (res) {
        var exams = res.data || [];
        if (exams.length === 0) {
          that.setData({ loading: false });
          return;
        }
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
        that.loadKnowledgeTree(selectedExam._id);
      },
      fail: function (err) {
        console.error('[kp] loadExamList fail', err);
        that.setData({ loading: false });
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
      loading: true,
      treeData: [],
      expandedKeys: {}
    });
    this.loadKnowledgeTree(selectedExam._id);
  },

  loadKnowledgeTree: function (examId) {
    var that = this;
    var db = api.database();
    db.collection('knowledgepoints').where({ examId: examId }).get({
      success: function (res) {
        var allKps = res.data || [];
        var level1 = allKps.filter(function (kp) { return kp.level === 1; });
        level1.sort(function (a, b) { return (a.sortWeight || 0) - (b.sortWeight || 0); });

        var weakKpIds = that.data.weakKpIds;
        var autoExpand = {};

        var treeData = level1.map(function (kp1) {
          var children = allKps.filter(function (kp) {
            return kp.level === 2 && kp.pid === kp1._id;
          });
          children.sort(function (a, b) { return (a.sortWeight || 0) - (b.sortWeight || 0); });
          var masteryLevel = that.getMasteryLabel(kp1.masteryCache);
          var hasWeakChild = false;
          var isLeaf = children.length === 0;
          return {
            _id: kp1._id,
            name: kp1.name,
            level: 1,
            isLeaf: isLeaf,
            questionCount: kp1.questionCount || 0,
            children: children.map(function (kp2) {
              var m2 = that.getMasteryLabel(kp2.masteryCache);
              var isWeakFromAssessment = weakKpIds.indexOf(kp2._id) > -1;
              if (isWeakFromAssessment) hasWeakChild = true;
              return {
                _id: kp2._id,
                name: kp2.name,
                level: 2,
                questionCount: kp2.questionCount || 0,
                masteryLevel: m2.level,
                masteryLabel: m2.label,
                masteryColor: m2.color,
                subjectId: kp2.subjectId,
                isWeakFromAssessment: isWeakFromAssessment,
                masteryCache: kp2.masteryCache || null
              };
            }),
            masteryLevel: masteryLevel.level,
            masteryLabel: masteryLevel.label,
            masteryColor: masteryLevel.color,
            subjectId: kp1.subjectId,
            masteryCache: kp1.masteryCache || null,
            hasWeakChild: hasWeakChild
          };
        });

        // 薄弱知识点模式: 自动展开含有薄弱知识点的章节
        if (that.data.weakKpMode) {
          treeData.forEach(function (kp1) {
            if (kp1.hasWeakChild) {
              autoExpand[kp1._id] = true;
            }
          });
        }

        var totalKp = 0;
        var practicedKp = 0;
        var weakKp = 0;
        treeData.forEach(function (kp1) {
          if (kp1.isLeaf) {
            // 叶子级 level-1 知识点直接计入统计
            totalKp++;
            if (kp1.masteryLevel === 'weak') weakKp++;
            if (kp1.masteryLevel !== 'none') practicedKp++;
          } else {
            totalKp += kp1.children.length;
            kp1.children.forEach(function (kp2) {
              if (kp2.masteryLevel === 'weak') weakKp++;
              if (kp2.masteryLevel !== 'none') practicedKp++;
            });
          }
        });

        that.setData({
          treeData: treeData,
          expandedKeys: autoExpand,
          stats: {
            total: totalKp,
            practiced: practicedKp,
            weak: weakKp,
            unpracticed: totalKp - practicedKp
          },
          loading: false
        });
      },
      fail: function (err) {
        console.error('[kp] loadKnowledgeTree fail', err);
        that.setData({ loading: false, treeData: [] });
      }
    });
  },

  getMasteryLabel: function (masteryCache) {
    if (!masteryCache || !masteryCache.masteryRate) {
      return { level: 'none', label: '未练习', color: '#B4B2A9' };
    }
    var rate = masteryCache.masteryRate;
    if (rate >= 85) return { level: 'mastered', label: '精通', color: '#1D9E75' };
    if (rate >= 70) return { level: 'proficient', label: '熟练', color: '#378ADD' };
    if (rate >= 60) return { level: 'fair', label: '一般', color: '#EF9F27' };
    return { level: 'weak', label: '薄弱', color: '#E24B4A' };
  },

  toggleExpand: function (e) {
    var kpId = e.currentTarget.dataset.kpid;
    var expanded = Object.assign({}, this.data.expandedKeys);
    if (expanded[kpId]) {
      delete expanded[kpId];
    } else {
      expanded[kpId] = true;
    }
    this.setData({ expandedKeys: expanded });
  },

  onKpTap: function (e) {
    var kpId = e.currentTarget.dataset.kpid;
    var kpName = e.currentTarget.dataset.kpname;
    var qCount = e.currentTarget.dataset.qcount;
    var subjectId = e.currentTarget.dataset.subjectid;
    var masteryLabel = e.currentTarget.dataset.masterylabel;
    var isWeak = e.currentTarget.dataset.isweak === 'true' || e.currentTarget.dataset.isweak === true;

    // 从 treeData 中找到对应知识点获取 masteryCache（兼容 level 1 叶子节点和 level 2 子节点）
    var masteryCache = null;
    this.data.treeData.forEach(function (kp1) {
      if (kp1._id === kpId) masteryCache = kp1.masteryCache;
      kp1.children.forEach(function (kp2) {
        if (kp2._id === kpId) masteryCache = kp2.masteryCache;
      });
    });

    var masteryDetail = '';
    if (masteryCache) {
      masteryDetail = '已答 ' + (masteryCache.totalAnswered || 0) + ' 题，答对 ' +
        (masteryCache.totalCorrect || 0) + ' 题，正确率 ' +
        (masteryCache.masteryRate || 0) + '%';
    }

    this.setData({
      detailKp: {
        _id: kpId,
        name: kpName,
        questionCount: qCount,
        subjectId: subjectId,
        masteryLabel: masteryLabel,
        isWeakFromAssessment: isWeak,
        masteryDetail: masteryDetail
      },
      detailVisible: true
    });
  },

  closeDetail: function (e) {
    if (e && e.target && e.currentTarget && e.target !== e.currentTarget) return;
    this.setData({ detailVisible: false });
  },

  noop: function () {},

  clearWeakMode: function () {
    wx.removeStorageSync('weak_kp_ids');
    wx.removeStorageSync('weak_kp_names');
    this.setData({ weakKpMode: false, weakKpIds: [] });
    this.loadKnowledgeTree(this.data.selectedExamId);
  },

  practiceKp: function () {
    var kp = this.data.detailKp;
    if (!kp) return;
    this.setData({ detailVisible: false });
    wx.navigateTo({
      url: '/pages/entry/index?id=' + kp.subjectId + '&kpId=' + kp._id + '&mode=answer'
    });
  },

  memorizeKp: function () {
    var kp = this.data.detailKp;
    if (!kp) return;
    this.setData({ detailVisible: false });
    wx.navigateTo({
      url: '/pages/entry/index?id=' + kp.subjectId + '&kpId=' + kp._id + '&mode=memorize'
    });
  },

  wrongKp: function () {
    var kp = this.data.detailKp;
    if (!kp) return;
    this.setData({ detailVisible: false });
    wx.navigateTo({
      url: '/pages/note/note?kpId=' + kp._id
    });
  }
});
