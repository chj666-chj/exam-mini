var api = require('../../utils/api.js');

Page({
  data: {
    items: [],
    title: '考试规则',
    loading: true
  },

  onLoad: function () {
    this.loadContent();
  },

  loadContent: function () {
    var that = this;
    var db = api.database();
    var defaultItems = [
      '【考试流程】进入考试前，请确保网络连接稳定，建议在WiFi环境下进行，以获得流畅的答题体验。',
      '【考试流程】系统提供"单题模式"与"列表模式"两种答题方式，考生可根据个人习惯自行选择。',
      '【考试流程】每场考试共10道题目，每题1分，满分10分，请在规定时间内完成全部作答。',
      '【考试流程】答题过程中可随时切换题目，系统自动保存已作答内容，支持中途退出后断点续答。',
      '【考试流程】提交试卷后，系统将自动生成成绩报告，并支持查看每道题的详细解析与知识点关联。',
      '【评分标准】客观题（单选题、多选题、判断题）由系统自动评阅，答案完全匹配方可得分。',
      '【评分标准】主观题（填空题、简答题）采用AI智能评分与人工复核相结合的方式，确保评分结果公正客观。',
      '【评分标准】每场考试成绩即时生成并记录，历史成绩可在"答题记录"模块中随时查阅。',
      '【评分标准】系统将根据答题正确率、答题用时等维度综合评估学习水平，自动生成个性化学习画像。',
      '【违规处理】考试过程中如检测到异常行为（如频繁切屏、使用外部辅助工具等），系统将自动记录并发出警告。',
      '【违规处理】多次违规者，管理员有权暂停其考试权限；情节严重者，账号将被永久封禁。',
      '【违规处理】对考试成绩或评分结果有异议者，可在考试结束后通过"错题笔记"功能提交复核申请。',
      '【注意事项】请勿在考试期间强制退出小程序或关闭页面，以免造成答题数据丢失或考试异常。',
      '【注意事项】考试成绩和错题记录将自动同步至个人账户，可在"错题本"中复习巩固薄弱知识点。',
      '【注意事项】建议定期进行模拟考试，结合系统提供的AI分析与复习推荐，持续提升备考效果。',
      '【注意事项】如遇系统异常或技术问题，请及时通过"意见反馈"功能联系我们，我们将尽快处理。'
    ];
    db.collection('app_config').where({ doc_id: 'rules' }).get({
      success: function (res) {
        var data = res.data || [];
        if (data.length > 0 && data[0].items) {
          that.setData({ items: data[0].items, title: data[0].title || '考试规则', loading: false });
        } else {
          that.setData({ items: defaultItems, loading: false });
        }
      },
      fail: function () {
        that.setData({ items: defaultItems, loading: false });
      }
    });
  },

  onShareAppMessage: function () {
    return { title: '考试助手 - 考试规则', path: '/pages/home/index' };
  }
});