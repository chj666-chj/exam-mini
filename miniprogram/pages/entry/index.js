const api = require('../../utils/api.js');

Page({
  data: {
    subjectId: '',
    subjectName: '',
    questionCount: 0,
    questions: [],
    mode: 'answer',
    display: 'single',
    order: 'seq',
    qtypeFilter: '',
    loading: true,
    error: '',
    qtypes: [],
    kpId: '',
    kpName: ''
  },

  onLoad: function (options) {
    var id = options.id || options.code || '';
    if (!id) {
      this.setData({ loading: false, error: '缺少科目参数' });
      return;
    }
    var order = options.order === 'random' ? 'random' : 'seq';
    var mode = options.mode || 'answer';
    var kpId = options.kpId || '';
    this.setData({ subjectId: id, order: order, mode: mode, kpId: kpId });
    if (kpId) {
      this.loadQuestionsByKp(kpId, id);
    } else {
      this.loadSubject(id);
    }
  },

  loadQuestionsByKp: function (kpId, subjectId) {
    var that = this;
    var db = api.database();
    db.collection('knowledgepoints').doc(kpId).get({
      success: function (res) {
        var kp = res.data || {};
        that.setData({ kpName: kp.name || '' });
        that.setData({ subjectName: kp.name || '知识点练习' });
      },
      fail: function () {
        that.setData({ subjectName: '知识点练习' });
      }
    });
    db.collection('questions').where({ knowledgePointIds__contains: kpId }).get({
      success: function (res) {
        var questions = (res.data || []).map(function (q) {
          if (typeof q.options === 'string') {
            try { q.options = JSON.parse(q.options); } catch (e) { q.options = []; }
          }
          q.options = q.options || [];
          q.qtype = q.qtype || q.type || 'single';
          return q;
        });
        var qtypeMap = {};
        questions.forEach(function (q) {
          if (q.qtype && !qtypeMap[q.qtype]) qtypeMap[q.qtype] = true;
        });
        var qtypes = Object.keys(qtypeMap).map(function (t) {
          return { value: t, label: that.qtypeLabel(t) };
        });
        that.setData({
          questions: questions,
          questionCount: questions.length,
          qtypes: qtypes,
          loading: false
        });
        wx.setStorageSync('quiz_questions', questions);
        wx.setStorageSync('quiz_arr', questions.map(function (q) { return q._id; }));
      },
      fail: function (err) {
        console.error('[entry] loadQuestionsByKp fail', err);
        that.setData({ loading: false, error: '知识点题目加载失败' });
      }
    });
  },

  loadSubject: function (id) {
    var that = this;
    var db = api.database();
    db.collection('subjects').doc(id).get({
      success: function (res) {
        var subject = res.data || {};
        that.setData({ subjectName: subject.name || '未知科目' });
        wx.setStorageSync('subject', subject);
        that.loadQuestions(id);
      },
      fail: function (err) {
        console.error('[entry] loadSubject fail', err);
        that.setData({ loading: false, error: '科目信息加载失败' });
      }
    });
  },

  loadQuestions: function (examid) {
    var that = this;
    var db = api.database();
    db.collection('questions').where({ examid: examid }).get({
      success: function (res) {
        var questions = (res.data || []).map(function (q) {
          if (typeof q.options === 'string') {
            try { q.options = JSON.parse(q.options); } catch (e) { q.options = []; }
          }
          q.options = q.options || [];
          q.qtype = q.qtype || q.type || 'single';
          return q;
        });
        var qtypeMap = {};
        questions.forEach(function (q) {
          if (q.qtype && !qtypeMap[q.qtype]) qtypeMap[q.qtype] = true;
        });
        var qtypes = Object.keys(qtypeMap).map(function (t) {
          return { value: t, label: that.qtypeLabel(t) };
        });
        that.setData({
          questions: questions,
          questionCount: questions.length,
          qtypes: qtypes,
          loading: false
        });
        wx.setStorageSync('quiz_questions', questions);
        wx.setStorageSync('quiz_arr', questions.map(function (q) { return q._id; }));
      },
      fail: function (err) {
        console.error('[entry] loadQuestions fail', err);
        that.setData({ loading: false, error: '题目加载失败，请检查网络连接' });
      }
    });
  },

  qtypeLabel: function (t) {
    var map = { single: '单选题', multiple: '多选题', judge: '判断题', fill: '填空题', qa: '问答题', multi_part: '一题多问' };
    return map[t] || t;
  },

  selectMode: function (e) {
    this.setData({ mode: e.currentTarget.dataset.mode });
  },

  selectDisplay: function (e) {
    this.setData({ display: e.currentTarget.dataset.display });
  },

  selectOrder: function (e) {
    this.setData({ order: e.currentTarget.dataset.order });
  },

  selectQtype: function (e) {
    this.setData({ qtypeFilter: e.currentTarget.dataset.qtype });
  },

  startQuiz: function () {
    var that = this;
    var questions = this.data.questions.slice();

    if (this.data.qtypeFilter) {
      questions = questions.filter(function (q) {
        return (q.qtype || 'single') === that.data.qtypeFilter;
      });
    }

    if (questions.length === 0) {
      wx.showToast({ icon: 'none', title: '没有符合条件的题目' });
      return;
    }

    if (this.data.order === 'random') {
      questions = questions.sort(function () { return Math.random() - 0.5; });
    }

    wx.setStorageSync('quiz_questions', questions);
    wx.setStorageSync('quiz_mode', this.data.mode);
    wx.setStorageSync('quiz_display', this.data.display);

    if (this.data.display === 'list') {
      wx.navigateTo({
        url: '/pages/question/index?id=' + this.data.subjectId + '&mode=' + this.data.mode
      });
    } else {
      wx.navigateTo({
        url: '/pages/exam/exam?id=' + this.data.subjectId + '&mode=' + this.data.mode
      });
    }
  }
});
