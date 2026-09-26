const api = require('../../utils/api.js');
const app = getApp();

Page({
  data: {
    openid: '',
    queryResult: [],
    firstExamId: '',
    // ===== 科目选择栏目 =====
    examList: [],          // 所有考试(科目)列表
    selectedExamId: '',    // 当前选中的考试ID
    selectedExamName: '',  // 当前选中的考试名称
    subjectPickerIndex: 0  // picker当前索引
  },

  onLoad: function () {
    this.onGetOpenid();
  },

  onShow: function () {
    this.loadExamList();
  },

  onGetOpenid: function () {
    if (app.globalData.openid || wx.getStorageSync('openid')) {
      app.globalData.openid = wx.getStorageSync('openid');
      this.setData({ openid: app.globalData.openid });
      return;
    }
    api.callFunction({
      name: 'login',
      data: {},
      success: res => {
        this.setData({ openid: res.result.openid });
      },
      fail: err => {
        console.error('[login] 失败，请确认 Django 后端已启动', err);
        wx.showToast({ icon: 'none', title: '后端未启动或网络异常' });
      }
    });
  },

  // ===== 科目选择：加载考试列表 =====
  loadExamList: function () {
    var that = this;
    var db = api.database();
    db.collection('exam').get({
      success: function (res) {
        var exams = res.data || [];
        if (exams.length === 0) {
          that.setData({ examList: [], selectedExamId: '', queryResult: [] });
          return;
        }
        // 读取上次缓存的选中考试ID
        var cachedId = wx.getStorageSync('home_selected_exam_id') || '';
        var selectedIdx = 0;
        if (cachedId) {
          for (var i = 0; i < exams.length; i++) {
            if (exams[i]._id === cachedId) { selectedIdx = i; break; }
          }
        }
        var selectedExam = exams[selectedIdx];
        that.setData({
          examList: exams,
          selectedExamId: selectedExam._id,
          selectedExamName: selectedExam.name,
          subjectPickerIndex: selectedIdx,
          firstExamId: exams[0]._id,
          queryResult: exams
        });
        // 缓存选中ID，并同步到全局storage供其他页面使用
        wx.setStorageSync('home_selected_exam_id', selectedExam._id);
        wx.setStorageSync('selected_exam', selectedExam);
      },
      fail: function (err) {
        console.error('[home] loadExamList fail', err);
      }
    });
  },

  // ===== 科目选择：picker切换 =====
  onExamChange: function (e) {
    var idx = parseInt(e.detail.value);
    var exams = this.data.examList;
    if (idx < 0 || idx >= exams.length) return;

    var selectedExam = exams[idx];
    this.setData({
      selectedExamId: selectedExam._id,
      selectedExamName: selectedExam.name,
      subjectPickerIndex: idx
    });

    // 缓存选中ID，并同步到全局storage供其他页面使用
    wx.setStorageSync('home_selected_exam_id', selectedExam._id);
    wx.setStorageSync('selected_exam', selectedExam);

    wx.showToast({
      title: '已切换: ' + selectedExam.name,
      icon: 'none',
      duration: 1200
    });
  },

  // ===== 导航（统一通过科目页选择章节） =====
  goSpecial: function () {
    var id = this.data.selectedExamId || this.data.firstExamId;
    if (id) { wx.navigateTo({ url: '/pages/subject/index?id=' + id }); }
    else { wx.showToast({ icon: 'none', title: '暂无考试数据' }); }
  },
  goType: function () {
    var id = this.data.selectedExamId || this.data.firstExamId;
    if (id) { wx.navigateTo({ url: '/pages/subject/index?id=' + id + '&mode=type' }); }
    else { wx.showToast({ icon: 'none', title: '暂无考试数据' }); }
  },
  goShuffle: function () {
    var id = this.data.selectedExamId || this.data.firstExamId;
    if (id) { wx.navigateTo({ url: '/pages/subject/index?id=' + id + '&mode=shuffle' }); }
    else { wx.showToast({ icon: 'none', title: '暂无考试数据' }); }
  },
  goFav: function () { wx.navigateTo({ url: '/pages/favorites/index' }); },
  goOrder: function () {
    var id = this.data.selectedExamId || this.data.firstExamId;
    if (id) { wx.navigateTo({ url: '/pages/subject/index?id=' + id + '&mode=order' }); }
    else { wx.showToast({ icon: 'none', title: '暂无考试数据' }); }
  },
  goExam: function () {
    var id = this.data.selectedExamId || this.data.firstExamId;
    if (id) { wx.navigateTo({ url: '/pages/examsetup/index' }); }
    else { wx.showToast({ icon: 'none', title: '暂无考试数据' }); }
  },
  goWrong: function () { wx.navigateTo({ url: '/pages/wrong/index' }); },
  goUndone: function () {
    var id = this.data.selectedExamId || this.data.firstExamId;
    if (id) { wx.navigateTo({ url: '/pages/subject/index?id=' + id + '&mode=undone' }); }
    else { wx.showToast({ icon: 'none', title: '暂无考试数据' }); }
  },
  goKnowledge: function () {
    var id = this.data.selectedExamId || this.data.firstExamId;
    if (id) { wx.navigateTo({ url: '/pages/knowledgepoint/index?examId=' + id }); }
    else { wx.navigateTo({ url: '/pages/knowledgepoint/index' }); }
  },
  goSelfTest: function () {
    var id = this.data.selectedExamId || this.data.firstExamId;
    if (id) { wx.navigateTo({ url: '/pages/assessment/index?examId=' + id }); }
    else { wx.navigateTo({ url: '/pages/assessment/index' }); }
  },
  goPay: function () { wx.navigateTo({ url: '/pages/pay/index' }); }
});
