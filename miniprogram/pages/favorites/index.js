var api = require('../../utils/api.js');
var util = require('../../utils/util.js');

// 类型标签映射
var FAV_TYPE_LABELS = {
  question: '题目',
  article: '文章',
  knowledge: '知识库'
};

Page({
  data: {
    favorites: [],
    filteredList: [],
    loading: true,
    error: '',
    isEmpty: false,
    // 类型 Tab
    activeTab: 'all',
    tabs: [
      { key: 'all', label: '全部' },
      { key: 'question', label: '题目' },
      { key: 'article', label: '文章' },
      { key: 'knowledge', label: '知识库' }
    ],
    // 各类型计数
    typeCounts: { all: 0, question: 0, article: 0, knowledge: 0 },
    // 题目筛选用
    examFilter: '',
    examOptions: [],
    examPickerIndex: 0,
    qtypeFilter: '',
    qtypeOptions: [
      { value: '', label: '全部题型' },
      { value: 'single', label: '单选题' },
      { value: 'multiple', label: '多选题' },
      { value: 'judge', label: '判断题' }
    ],
    qtypePickerIndex: 0
  },

  onLoad: function (options) {
    // 支持 from 参数（知识库页跳转来自动切到 knowledge tab）
    if (options && options.from === 'knowledge') {
      this.setData({ activeTab: 'knowledge' });
    }
    this.loadFavorites();
  },

  onShow: function () {
    if (!this.data.loading) {
      this.loadFavorites();
    }
  },

  onPullDownRefresh: function () {
    var that = this;
    this.loadFavorites(function () {
      wx.stopPullDownRefresh();
    });
  },

  // ===== 加载收藏 =====
  loadFavorites: function (done) {
    var that = this;
    var openid = wx.getStorageSync('openid');
    if (!openid) {
      that.setData({ loading: false, error: '请先登录后查看收藏' });
      if (done) done();
      return;
    }

    // 使用统一封装获取全部收藏（自动推断 _favType）
    api.getFavorites().then(function (list) {
      // 按时间倒序
      list.sort(function (a, b) {
        return (b.createTime || '') > (a.createTime || '') ? 1 : -1;
      });

      // 统计各类型数量
      var typeCounts = { all: list.length, question: 0, article: 0, knowledge: 0 };
      list.forEach(function (item) {
        typeCounts[item._favType] = (typeCounts[item._favType] || 0) + 1;
      });

      // 为题目类型补充考试名称映射
      var questionFavs = list.filter(function (f) { return f._favType === 'question'; });
      that._enrichQuestionFavorites(questionFavs, function () {
        // 补充展示字段
        var qtypeMap = { single: '单选', multiple: '多选', judge: '判断' };
        list.forEach(function (item) {
          if (item._favType === 'question') {
            item.qtypeLabel = qtypeMap[item.qtype] || '未知';
            item.diffLabel = item.difficulty === 1 ? '简单' : item.difficulty === 2 ? '中等' : item.difficulty === 3 ? '困难' : '普通';
          }
          item.typeLabel = FAV_TYPE_LABELS[item._favType] || '其他';
        });

        // 构建考试筛选选项（仅题目类型）
        var examMap = {};
        questionFavs.forEach(function (item) {
          var eid = item._examId || '';
          if (eid && !examMap[eid]) {
            examMap[eid] = { value: eid, label: that._examNameMap[eid] || item.subjectName || eid };
          }
        });
        var examOptions = [{ value: '', label: '全部科目' }];
        Object.keys(examMap).forEach(function (key) {
          examOptions.push(examMap[key]);
        });

        var selectedExamId = wx.getStorageSync('home_selected_exam_id') || '';
        var defaultExamIdx = 0;
        if (selectedExamId) {
          for (var i = 0; i < examOptions.length; i++) {
            if (examOptions[i].value === selectedExamId) {
              defaultExamIdx = i;
              break;
            }
          }
        }

        that.setData({
          favorites: list,
          typeCounts: typeCounts,
          examOptions: examOptions,
          examPickerIndex: defaultExamIdx,
          examFilter: examOptions[defaultExamIdx].value,
          loading: false,
          isEmpty: list.length === 0,
          error: ''
        });
        that.applyFilter();
        if (done) done();
      });
    }).catch(function (err) {
      console.error('[favorites] load fail', err);
      that.setData({ loading: false, error: '收藏加载失败，请检查网络' });
      if (done) done();
    });
  },

  // 为题目收藏补充考试名称
  _enrichQuestionFavorites: function (questionFavs, done) {
    var that = this;
    if (questionFavs.length === 0) {
      that._subjToExam = {};
      that._examNameMap = {};
      done();
      return;
    }

    var db = api.database();
    db.collection('subjects').get({
      success: function (subjRes) {
        var subjects = subjRes.data || [];
        var subjToExam = {};
        subjects.forEach(function (s) {
          subjToExam[s._id] = s.pid;
        });
        that._subjToExam = subjToExam;

        db.collection('exam').get({
          success: function (examRes) {
            var exams = examRes.data || [];
            var examNameMap = {};
            exams.forEach(function (e) {
              examNameMap[e._id] = e.name;
            });
            that._examNameMap = examNameMap;

            // 为每个题目收藏补充 _examId
            questionFavs.forEach(function (item) {
              item._examId = subjToExam[item.examid] || '';
            });
            done();
          },
          fail: function () {
            that._examNameMap = {};
            questionFavs.forEach(function (item) {
              item._examId = subjToExam[item.examid] || '';
            });
            done();
          }
        });
      },
      fail: function () {
        that._subjToExam = {};
        that._examNameMap = {};
        done();
      }
    });
  },

  // ===== Tab 切换 =====
  onTabChange: function (e) {
    var key = e.currentTarget.dataset.key;
    this.setData({ activeTab: key });
    this.applyFilter();
  },

  // ===== 筛选 =====
  onExamFilterChange: function (e) {
    var idx = parseInt(e.detail.value);
    this.setData({
      examPickerIndex: idx,
      examFilter: this.data.examOptions[idx].value
    });
    this.applyFilter();
  },

  onQtypeFilterChange: function (e) {
    var idx = parseInt(e.detail.value);
    this.setData({
      qtypePickerIndex: idx,
      qtypeFilter: this.data.qtypeOptions[idx].value
    });
    this.applyFilter();
  },

  applyFilter: function () {
    var list = this.data.favorites.slice();
    var tab = this.data.activeTab;
    var examFilter = this.data.examFilter;
    var qtypeFilter = this.data.qtypeFilter;

    // 按 Tab 筛选
    if (tab !== 'all') {
      list = list.filter(function (item) { return item._favType === tab; });
    }

    // 题目专属筛选（仅在显示题目时生效）
    if (tab === 'all' || tab === 'question') {
      if (examFilter) {
        list = list.filter(function (item) {
          return item._favType === 'question' && item._examId === examFilter;
        });
      }
      if (qtypeFilter) {
        list = list.filter(function (item) {
          return item._favType === 'question' && item.qtype === qtypeFilter;
        });
      }
    }

    this.setData({ filteredList: list });
  },

  // ===== 跳转详情（通用） =====
  goDetail: function (e) {
    var id = e.currentTarget.dataset.id;
    var type = e.currentTarget.dataset.type;
    if (!id || !type) return;

    if (type === 'question') {
      // 题目：走练习逻辑
      this.goPractice(e);
    } else if (type === 'article') {
      wx.navigateTo({ url: '/pages/article/detail?id=' + id });
    } else if (type === 'knowledge') {
      wx.navigateTo({ url: '/pages/knowledge/detail?id=' + id });
    }
  },

  // ===== 单题练习 =====
  goPractice: function (e) {
    var questionId = e.currentTarget.dataset.questionid;
    var examid = e.currentTarget.dataset.examid;
    if (!questionId || !examid) {
      wx.showToast({ icon: 'none', title: '题目信息不完整' });
      return;
    }

    var db = api.database();
    db.collection('questions').doc(questionId).get({
      success: function (res) {
        var question = res.data;
        if (!question) {
          wx.showToast({ icon: 'none', title: '题目不存在' });
          return;
        }
        if (typeof question.options === 'string') {
          try { question.options = JSON.parse(question.options); } catch (e) { question.options = []; }
        }
        question.options = question.options || [];
        question.qtype = question.qtype || question.type || 'single';

        var questions = [question];
        wx.setStorageSync('quiz_questions', questions);
        wx.setStorageSync('quiz_mode', 'answer');
        wx.setStorageSync('quiz_display', 'single');

        wx.navigateTo({
          url: '/pages/exam/exam?id=' + examid + '&mode=answer'
        });
      },
      fail: function () {
        wx.showToast({ icon: 'none', title: '题目加载失败' });
      }
    });
  },

  // ===== 批量练习（仅题目类型） =====
  goBatchPractice: function () {
    var that = this;
    var list = this.data.filteredList.filter(function (f) { return f._favType === 'question'; });
    if (list.length === 0) {
      wx.showToast({ icon: 'none', title: '暂无收藏题目' });
      return;
    }

    wx.showLoading({ title: '加载题目中...' });

    var questionIds = list.map(function (f) { return f.questionId; });
    var db = api.database();
    var loaded = 0;
    var questions = [];

    questionIds.forEach(function (qid) {
      db.collection('questions').doc(qid).get({
        success: function (res) {
          if (res.data) {
            var q = res.data;
            if (typeof q.options === 'string') {
              try { q.options = JSON.parse(q.options); } catch (e) { q.options = []; }
            }
            q.options = q.options || [];
            q.qtype = q.qtype || q.type || 'single';
            questions.push(q);
          }
          loaded++;
          if (loaded === questionIds.length) {
            that.startBatchQuiz(questions);
          }
        },
        fail: function () {
          loaded++;
          if (loaded === questionIds.length) {
            that.startBatchQuiz(questions);
          }
        }
      });
    });
  },

  startBatchQuiz: function (questions) {
    wx.hideLoading();
    if (questions.length === 0) {
      wx.showToast({ icon: 'none', title: '题目加载失败' });
      return;
    }

    questions.sort(function () { return Math.random() - 0.5; });

    wx.setStorageSync('quiz_questions', questions);
    wx.setStorageSync('quiz_mode', 'answer');
    wx.setStorageSync('quiz_display', 'single');

    var examid = questions[0].examid || '';
    wx.navigateTo({
      url: '/pages/exam/exam?id=' + examid + '&mode=answer'
    });
  },

  // ===== 取消收藏（通用，按 _id 删除） =====
  removeFavorite: function (e) {
    var that = this;
    var favId = e.currentTarget.dataset.favid;
    var type = e.currentTarget.dataset.type;
    if (!favId) return;

    var typeLabel = FAV_TYPE_LABELS[type] || '收藏';
    wx.showModal({
      title: '取消收藏',
      content: '确定取消收藏这条' + typeLabel + '吗？',
      success: function (res) {
        if (!res.confirm) return;

        api.removeFavorite(favId).then(function () {
          wx.showToast({ icon: 'success', title: '已取消收藏' });
          that.loadFavorites();
        }).catch(function () {
          wx.showToast({ icon: 'none', title: '操作失败' });
        });
      }
    });
  },

  // ===== 清空当前列表收藏 =====
  clearAll: function () {
    var that = this;
    var list = this.data.filteredList;
    if (list.length === 0) return;

    var tab = this.data.activeTab;
    var scopeLabel = tab === 'all' ? '全部' : FAV_TYPE_LABELS[tab] || '';

    wx.showModal({
      title: '清空收藏',
      content: '确定清空当前' + scopeLabel + '的 ' + list.length + ' 条收藏吗？此操作不可恢复。',
      confirmColor: '#e64340',
      success: function (res) {
        if (!res.confirm) return;
        that._batchDelete(list, 0);
      }
    });
  },

  _batchDelete: function (list, index) {
    var that = this;
    if (index >= list.length) {
      wx.showToast({ icon: 'success', title: '已清空收藏' });
      that.loadFavorites();
      return;
    }

    api.removeFavorite(list[index]._id).then(function () {
      that._batchDelete(list, index + 1);
    }).catch(function () {
      that._batchDelete(list, index + 1);
    });
  },

  goHome: function () {
    wx.switchTab({ url: '/pages/home/index' });
  },

  onShareAppMessage: function () {
    return { title: '考试助手 - 我的收藏', path: '/pages/home/index' };
  }
});
