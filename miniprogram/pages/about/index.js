var api = require('../../utils/api.js');

Page({
  data: {
    content: '',
    loading: true
  },

  onLoad: function () {
    this.loadContent();
  },

  loadContent: function () {
    var that = this;
    var db = api.database();
    var defaultContent =
      '考试宝是一款专注于在线模拟考试与学习测评的教育辅助平台，致力于为考生提供高效、便捷的备考体验。\n\n' +
      '【系统简介】\n' +
      '本系统涵盖多学科题库资源，支持单题练习、模拟考试、错题回顾、智能组卷等多种学习模式。通过AI技术赋能，系统可为每位考生生成个性化学习画像、复习计划与能力分析报告，助力精准提分。\n\n' +
      '【服务宗旨】\n' +
      '以考生为中心，以技术为驱动，提供专业、公正、智能的在线考试与学习服务，帮助每一位用户高效备考、稳步提升。\n\n' +
      '【团队介绍】\n' +
      '我们的团队由资深教育专家与技术开发人员组成，拥有丰富的题库建设、考试系统设计与AI应用经验。团队成员持续优化系统功能与内容质量，确保为用户提供可靠、专业的学习平台。\n\n' +
      '【联系方式】\n' +
      '如有任何疑问或建议，欢迎通过小程序内"意见反馈"功能与我们取得联系，我们将及时为您解答。';
    db.collection('app_config').where({ doc_id: 'about' }).get({
      success: function (res) {
        var data = res.data || [];
        if (data.length > 0 && data[0].content) {
          that.setData({ content: data[0].content, loading: false });
        } else {
          that.setData({ content: defaultContent, loading: false });
        }
      },
      fail: function () {
        that.setData({ content: defaultContent, loading: false });
      }
    });
  },

  onShareAppMessage: function () {
    return { title: '考试助手 - 关于我们', path: '/pages/home/index' };
  }
});