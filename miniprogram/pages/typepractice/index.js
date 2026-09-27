var api = require('../../utils/api.js');
var judge = require('../../utils/judge.js');

Page({
  data: {
    subjectId: '',
    subjectName: '',
    typeGroups: [],      // [{ qtype, label, icon, color, total, answered, correct, correctRate, progress }]
    activeType: '',      // 当前选中题型 tab
    loading: true,
    error: ''
  },

  // 非 setData 存储：完整题目对象按题型分组，供"开始练习"使用
  _typeQuestions: {},

  onLoad: function (options) {
    var id = options.id || '';
    var name = options.name || '';
    // 解码 URL 参数（subject 页面传参时用了 encodeURIComponent）
    if (name) {
      try { name = decodeURIComponent(name); } catch (e) {}
    }
    if (!id) {
      this.setData({ loading: false, error: '缺少科目参数' });
      return;
    }
    this.setData({ subjectId: id, subjectName: name || '题型练习' });
    this.loadSubjectInfo(id);
    this.loadQuestions(id);
  },

  // 加载科目（章节）名称（始终从 DB 获取权威名称，修正 URL 乱码）
  loadSubjectInfo: function (id) {
    var that = this;
    var db = api.database();
    db.collection('subjects').doc(id).get({
      success: function (res) {
        var subject = res.data || {};
        that.setData({ subjectName: subject.name || '题型练习' });
      },
      fail: function () {}
    });
  },

  // 按 chapter 字段加载该章节所有题目（非 examid）
  loadQuestions: function (chapterId) {
    var that = this;
    var db = api.database();
    db.collection('questions').where({ chapter: chapterId }).get({
      success: function (res) {
        var questions = (res.data || []).map(function (q) {
          if (typeof q.options === 'string') {
            try { q.options = JSON.parse(q.options); } catch (e) { q.options = []; }
          }
          q.options = q.options || [];
          q.qtype = q.qtype || q.type || 'single';
          return q;
        });
        if (questions.length === 0) {
          that.setData({ loading: false, error: '该科目暂无题目' });
          return;
        }
        that.loadHistorys(questions);
      },
      fail: function (err) {
        console.error('[typepractice] loadQuestions fail', err);
        that.setData({ loading: false, error: '题目加载失败' });
      }
    });
  },

  // 加载用户答题历史，统计每题的作答状态
  loadHistorys: function (questions) {
    var that = this;
    var openid = wx.getStorageSync('openid');
    if (!openid) {
      that.buildTypeGroups(questions, {});
      return;
    }
    var db = api.database();
    db.collection('historys').where({ _openid: openid }).get({
      success: function (res) {
        var histories = res.data || [];
        // 构建 questionId -> { answered: true, correct: bool } 映射
        var qStats = {};
        histories.forEach(function (h) {
          var items = h.items || [];
          var scoreArr = h.score_arr || [];
          items.forEach(function (qid, idx) {
            if (idx >= scoreArr.length) return;
            var userAns = scoreArr[idx] || [];
            if (!userAns || !Array.isArray(userAns) || userAns.length === 0) return;
            // 在当前章节题目中查找
            for (var i = 0; i < questions.length; i++) {
              if (questions[i]._id === qid) {
                var isCorrect = judge.judgeAnswer(questions[i], userAns);
                qStats[qid] = { answered: true, correct: isCorrect };
                break;
              }
            }
          });
        });
        that.buildTypeGroups(questions, qStats);
      },
      fail: function () {
        that.buildTypeGroups(questions, {});
      }
    });
  },

  // 按题型分组并计算统计
  buildTypeGroups: function (questions, qStats) {
    var that = this;

    var typeMeta = {
      single:     { label: '单选题',   icon: 'S', color: '#4A90F3', bg: '#E8F0FE' },
      multiple:   { label: '多选题',   icon: 'M', color: '#9B59B6', bg: '#F3E8F7' },
      judge:      { label: '判断题',   icon: 'J', color: '#E67E22', bg: '#FDF0E0' },
      fill:       { label: '填空题',   icon: 'F', color: '#1ABC9C', bg: '#E0F8F4' },
      qa:         { label: '问答题',   icon: 'Q', color: '#E74C3C', bg: '#FDE8E7' },
      multi_part: { label: '一题多问', icon: 'P', color: '#34495E', bg: '#EBEEF1' }
    };

    // 按题型分组
    var groups = {};
    questions.forEach(function (q) {
      var qt = q.qtype || q.type || 'single';
      if (!groups[qt]) groups[qt] = [];
      groups[qt].push(q);
    });

    // 按固定顺序排列题型
    var typeOrder = ['single', 'multiple', 'judge', 'fill', 'qa', 'multi_part'];
    var typeGroups = [];
    that._typeQuestions = {};

    typeOrder.forEach(function (qt) {
      if (!groups[qt] || groups[qt].length === 0) return;
      var meta = typeMeta[qt] || { label: qt, icon: '?', color: '#999', bg: '#F5F5F5' };
      var qs = groups[qt];

      // 存储完整题目供练习使用
      that._typeQuestions[qt] = qs;

      // 统计
      var answered = 0;
      var correct = 0;
      qs.forEach(function (q) {
        var s = qStats[q._id];
        if (s && s.answered) {
          answered++;
          if (s.correct) {
            correct++;
          }
        }
      });

      var correctRate = answered > 0 ? Math.round(correct / answered * 100) : 0;
      var progress = qs.length > 0 ? Math.round(answered / qs.length * 100) : 0;

      typeGroups.push({
        qtype: qt,
        label: meta.label,
        icon: meta.icon,
        color: meta.color,
        bg: meta.bg,
        total: qs.length,
        answered: answered,
        correct: correct,
        wrong: answered - correct,
        correctRate: correctRate,
        progress: progress
      });
    });

    var activeType = typeGroups.length > 0 ? typeGroups[0].qtype : '';
    that.setData({
      typeGroups: typeGroups,
      activeType: activeType,
      loading: false
    });
  },

  // 切换题型 tab
  onTypeTap: function (e) {
    var qtype = e.currentTarget.dataset.qtype;
    if (qtype && qtype !== this.data.activeType) {
      this.setData({ activeType: qtype });
    }
  },

  // 开始某题型练习
  startPractice: function (e) {
    var qtype = e.currentTarget.dataset.qtype;
    var questions = this._typeQuestions[qtype];
    if (!questions || questions.length === 0) {
      wx.showToast({ icon: 'none', title: '该题型暂无题目' });
      return;
    }

    // 归一化题目
    var normalized = questions.map(function (q) {
      return judge.normalizeQuestion(q);
    });

    wx.setStorageSync('quiz_questions', normalized);
    wx.setStorageSync('quiz_mode', 'answer');
    wx.setStorageSync('quiz_display', 'single');

    // 科目信息
    var examInfo = { _id: this.data.subjectId, name: this.data.subjectName };
    wx.setStorageSync('subject', examInfo);

    wx.navigateTo({
      url: '/pages/exam/exam?id=' + this.data.subjectId + '&mode=answer'
    });
  },

  // 背题模式
  startMemorize: function (e) {
    var qtype = e.currentTarget.dataset.qtype;
    var questions = this._typeQuestions[qtype];
    if (!questions || questions.length === 0) {
      wx.showToast({ icon: 'none', title: '该题型暂无题目' });
      return;
    }

    var normalized = questions.map(function (q) {
      return judge.normalizeQuestion(q);
    });

    wx.setStorageSync('quiz_questions', normalized);
    wx.setStorageSync('quiz_mode', 'memorize');
    wx.setStorageSync('quiz_display', 'single');

    wx.navigateTo({
      url: '/pages/exam/exam?id=' + this.data.subjectId + '&mode=memorize'
    });
  },

  goBack: function () {
    wx.navigateBack();
  },

  onShareAppMessage: function () {
    return { title: '考试助手 - 题型专项练习', path: '/pages/home/index' };
  }
});
