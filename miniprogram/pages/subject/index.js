const api = require('../../utils/api.js');

Page({
  data: {
    pid: '',
    subjects: [],
    loading: true,
    error: '',
    mode: '',  // 从首页传入的模式：order/type/shuffle/undone
    modeTitle: '请选择考试科目'
  },

  onLoad: function (options) {
    var pid = options.id || '';
    var mode = options.mode || '';
    if (!pid) {
      this.setData({ loading: false, error: '缺少考试参数' });
      return;
    }
    var titleMap = {
      '': '请选择考试科目',
      'order': '顺序刷题 - 选择科目',
      'type': '题型刷题 - 选择科目',
      'shuffle': '乱序刷题 - 选择科目',
      'undone': '未作习题 - 选择科目'
    };
    this.setData({ pid: pid, mode: mode, modeTitle: titleMap[mode] || '请选择考试科目' });
    this.loadSubjects(pid);
  },

  loadSubjects: function (pid) {
    var that = this;
    var db = api.database();
    db.collection('subjects').where({ pid: pid }).get({
      success: function (res) {
        var subjects = res.data || [];
        if (subjects.length === 0) {
          that.setData({ loading: false, error: '该考试暂无科目' });
          return;
        }
        // 按sortWeight排序
        subjects.sort(function (a, b) {
          return (a.sortWeight || 0) - (b.sortWeight || 0);
        });
        wx.setStorageSync('subjects', subjects);
        if (subjects.length === 1) {
          wx.setStorageSync('subject', subjects[0]);
        }
        that.setData({ subjects: subjects, loading: false });
      },
      fail: function (err) {
        console.error('[subject] loadSubjects fail', err);
        that.setData({ loading: false, error: '科目加载失败，请检查网络' });
      }
    });
  },

  toEntryPage: function (e) {
    var id = e.currentTarget.dataset.id;
    if (!id) {
      wx.showToast({ icon: 'none', title: '科目ID异常' });
      return;
    }
    var mode = this.data.mode;
    // 根据首页传入的mode决定跳转目标
    if (mode === 'undone') {
      wx.navigateTo({ url: '/pages/question/index?id=' + id + '&undone=true' });
    } else if (mode === 'shuffle') {
      wx.navigateTo({ url: '/pages/entry/index?id=' + id + '&order=random' });
    } else if (mode === 'type') {
      wx.navigateTo({ url: '/pages/entry/index?id=' + id });
    } else if (mode === 'order') {
      wx.navigateTo({ url: '/pages/entry/index?id=' + id });
    } else {
      // 默认模式（专项刷题）：进入entry页
      wx.navigateTo({ url: '/pages/entry/index?id=' + id });
    }
  },

  onShareAppMessage: function () {
    return { title: '考试助手', path: '/pages/home/index' };
  }
});
