const api = require('../../utils/api.js');

Page({
  data: {
    questions: [],
    rightNum: 0,
    errNum: 0,
    unAnswered: 0,
    total: 0,
    loading: true
  },

  onLoad: function () {
    var questions = wx.getStorageSync('quiz_questions') || [];
    var userAnswers = wx.getStorageSync('quiz_user_answers') || [];

    if (questions.length === 0) {
      questions = wx.getStorageSync('questions') || [];
      userAnswers = wx.getStorageSync('score_arr') || [];
    }

    if (questions.length === 0) {
      this.setData({ loading: false });
      return;
    }

    var rightNum = 0;
    var errNum = 0;
    var unAnswered = 0;

    var list = questions.map(function (question, idx) {
      var options = question.options || [];
      var rightCode = '';
      options.forEach(function (opt) {
        if (opt.value == 1) rightCode = opt.code;
      });

      var userAnswer = userAnswers[idx] || [];
      var myCode = Array.isArray(userAnswer) ? userAnswer.join(',') : (userAnswer || '未作答');
      var isRight = false;
      var answered = userAnswer && userAnswer.length > 0;

      if (answered) {
        var correctCodes = options.filter(function (opt) { return opt.value == 1; }).map(function (opt) { return opt.code; });
        if (userAnswer.length === correctCodes.length) {
          isRight = true;
          userAnswer.forEach(function (code) {
            if (correctCodes.indexOf(code) === -1) isRight = false;
          });
        }
        isRight ? rightNum++ : errNum++;
      } else {
        unAnswered++;
      }

      return {
        idx: idx,
        title: question.title,
        typename: question.typename || (question.qtype === 'multiple' ? '多选题' : '单选题'),
        myCode: myCode,
        rightCode: rightCode,
        isRight: isRight,
        answered: answered
      };
    });

    this.setData({
      questions: list,
      rightNum: rightNum,
      errNum: errNum,
      unAnswered: unAnswered,
      total: questions.length,
      loading: false
    });
  },

  goHistory: function () {
    wx.redirectTo({ url: '/pages/history/index' });
  },

  goHome: function () {
    wx.switchTab({ url: '/pages/home/index' });
  },

  onShareAppMessage: function () {
    return { title: '考试助手', path: '/pages/home/index' };
  }
});
