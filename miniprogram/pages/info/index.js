const api = require('../../utils/api.js');

Page({
  data: {
    // 模式：'login' 登录 / 'register' 注册
    mode: 'login',

    // 登录表单
    loginForm: {
      username: '',
      password: ''
    },

    // 注册表单
    registerForm: {
      username: '',
      nickname: '',
      password: '',
      confirmPassword: ''
    },

    // 错误提示（按字段名 key 存放，空串表示无错误）
    loginErrors: { username: '', password: '' },
    registerErrors: { username: '', nickname: '', password: '', confirmPassword: '' },

    // 全局错误/提示
    globalError: '',

    // 提交状态
    submitting: false,

    // 密码可见性
    showLoginPwd: false,
    showRegPwd: false,
    showRegConfirmPwd: false
  },

  onLoad: function (options) {
    // 不在 onLoad 中自动 navigateBack——这会导致：
    // 1. 游客模式：app.js onLaunch 已自动 login 写入 openid，onLoad 检测到后立即弹回，
    //    用户根本看不到登录页，无法操作游客登录按钮
    // 2. 页面一闪而过，用户体验差
    // 登录页应始终展示，已登录状态的提示在 onShow 中处理
  },

  onShow: function () {
    // 已登录时温和提示，不强制弹回（用户可能想切换账号）
    var openid = wx.getStorageSync('openid') || '';
    if (openid) {
      this.setData({
        'loginForm.username': '',
        'loginForm.password': '',
        globalError: '当前已登录，如需切换账号请先退出登录'
      });
    }
  },

  // ===== 模式切换 =====
  switchToLogin: function () {
    this.setData({
      mode: 'login',
      globalError: '',
      registerErrors: { username: '', nickname: '', password: '', confirmPassword: '' }
    });
  },

  switchToRegister: function () {
    this.setData({
      mode: 'register',
      globalError: '',
      loginErrors: { username: '', password: '' }
    });
  },

  // ===== 登录表单输入 =====
  onLoginUsernameInput: function (e) {
    var val = (e.detail.value || '').trim();
    this.setData({
      'loginForm.username': val,
      'loginErrors.username': '',
      globalError: ''
    });
  },

  onLoginPasswordInput: function (e) {
    this.setData({
      'loginForm.password': e.detail.value || '',
      'loginErrors.password': '',
      globalError: ''
    });
  },

  toggleLoginPwd: function () {
    this.setData({ showLoginPwd: !this.data.showLoginPwd });
  },

  // ===== 注册表单输入 =====
  onRegUsernameInput: function (e) {
    var val = (e.detail.value || '').trim();
    this.setData({
      'registerForm.username': val,
      'registerErrors.username': '',
      globalError: ''
    });
  },

  onRegNicknameInput: function (e) {
    var val = (e.detail.value || '').trim();
    this.setData({
      'registerForm.nickname': val,
      'registerErrors.nickname': '',
      globalError: ''
    });
  },

  onRegPasswordInput: function (e) {
    this.setData({
      'registerForm.password': e.detail.value || '',
      'registerErrors.password': '',
      globalError: ''
    });
  },

  onRegConfirmPasswordInput: function (e) {
    this.setData({
      'registerForm.confirmPassword': e.detail.value || '',
      'registerErrors.confirmPassword': '',
      globalError: ''
    });
  },

  toggleRegPwd: function () {
    this.setData({ showRegPwd: !this.data.showRegPwd });
  },

  toggleRegConfirmPwd: function () {
    this.setData({ showRegConfirmPwd: !this.data.showRegConfirmPwd });
  },

  // ===== 表单校验 =====
  validateLogin: function () {
    var form = this.data.loginForm;
    var errors = { username: '', password: '' };
    var valid = true;

    if (!form.username) {
      errors.username = '请输入用户名';
      valid = false;
    }
    if (!form.password) {
      errors.password = '请输入密码';
      valid = false;
    }

    this.setData({ loginErrors: errors });
    return valid;
  },

  validateRegister: function () {
    var form = this.data.registerForm;
    var errors = { username: '', nickname: '', password: '', confirmPassword: '' };
    var valid = true;

    // 用户名：3-20 位字母/数字/下划线
    var u = form.username;
    if (!u) {
      errors.username = '请输入用户名';
      valid = false;
    } else if (u.length < 3 || u.length > 20) {
      errors.username = '用户名长度需 3-20 位';
      valid = false;
    } else if (!/^[a-zA-Z0-9_]+$/.test(u)) {
      errors.username = '用户名仅支持字母、数字和下划线';
      valid = false;
    }

    // 昵称：选填，最长 20 位
    if (form.nickname && form.nickname.length > 20) {
      errors.nickname = '昵称长度不能超过 20 位';
      valid = false;
    }

    // 密码：6-32 位
    var p = form.password;
    if (!p) {
      errors.password = '请输入密码';
      valid = false;
    } else if (p.length < 6 || p.length > 32) {
      errors.password = '密码长度需 6-32 位';
      valid = false;
    }

    // 确认密码
    var cp = form.confirmPassword;
    if (!cp) {
      errors.confirmPassword = '请再次输入密码';
      valid = false;
    } else if (cp !== p) {
      errors.confirmPassword = '两次输入的密码不一致';
      valid = false;
    }

    this.setData({ registerErrors: errors });
    return valid;
  },

  // ===== 提交：登录 =====
  handleLogin: function () {
    if (this.data.submitting) return;
    if (!this.validateLogin()) return;

    var that = this;
    var form = this.data.loginForm;

    this.setData({ submitting: true, globalError: '' });

    api.accountLogin({
      username: form.username,
      password: form.password
    }).then(function (info) {
      // 登录成功：openid 已写入 storage
      that.setData({ submitting: false });

      // 检查是否需要强制改密码（管理员重置后标记）
      if (info && info.forceResetPassword) {
        wx.showModal({
          title: '需要修改密码',
          content: '您的密码已被管理员重置，为保障账号安全，请立即修改密码。',
          confirmText: '去修改',
          cancelText: '稍后',
          confirmColor: '#e6a23c',
          success: function (res) {
            if (res.confirm) {
              wx.redirectTo({ url: '/pages/change-password/index?force=1' });
            } else {
              // 用户选择稍后，仍返回上一页，但下次登录还会提示
              wx.navigateBack({ delta: 1 });
            }
          }
        });
        return;
      }

      wx.showToast({
        title: '登录成功',
        icon: 'success',
        duration: 1500
      });
      // 延迟返回，让 Toast 显示完整
      setTimeout(function () {
        wx.navigateBack({ delta: 1 });
      }, 1200);
    }).catch(function (err) {
      that.setData({
        submitting: false,
        globalError: (err && err.message) || '登录失败，请检查网络后重试'
      });
    });
  },

  // ===== 提交：注册 =====
  handleRegister: function () {
    if (this.data.submitting) return;
    if (!this.validateRegister()) return;

    var that = this;
    var form = this.data.registerForm;

    this.setData({ submitting: true, globalError: '' });

    api.register({
      username: form.username,
      password: form.password,
      nickname: form.nickname || form.username
    }).then(function (info) {
      // 注册成功：后端已创建 profile 文档
      // 自动用刚注册的账号登录，免去用户手动再输一次
      that.setData({ submitting: false });
      wx.showToast({
        title: '注册成功，正在登录...',
        icon: 'success',
        duration: 1500
      });

      // 延迟后自动发起登录
      setTimeout(function () {
        that.setData({ submitting: true });
        api.accountLogin({
          username: form.username,
          password: form.password
        }).then(function (loginInfo) {
          that.setData({ submitting: false });
          wx.showToast({
            title: '登录成功',
            icon: 'success',
            duration: 1200
          });
          setTimeout(function () {
            wx.navigateBack({ delta: 1 });
          }, 1000);
        }).catch(function (err) {
          // 自动登录失败（极端情况），回退到手动登录
          that.setData({
            submitting: false,
            mode: 'login',
            'loginForm.username': form.username,
            'loginForm.password': '',
            registerForm: { username: '', nickname: '', password: '', confirmPassword: '' },
            globalError: '注册成功但自动登录失败，请手动登录'
          });
        });
      }, 1200);
    }).catch(function (err) {
      that.setData({
        submitting: false,
        globalError: (err && err.message) || '注册失败，请检查网络后重试'
      });
    });
  },

  // ===== 游客登录（沿用原 /api/login/ 演示账号）=====
  handleGuestLogin: function () {
    if (this.data.submitting) return;
    var that = this;
    this.setData({ submitting: true, globalError: '' });

    api.callFunction({
      name: 'login',
      data: {},
      success: function () {
        that.setData({ submitting: false });
        wx.showToast({
          title: '已进入体验模式',
          icon: 'success',
          duration: 1500
        });
        setTimeout(function () {
          wx.navigateBack({ delta: 1 });
        }, 1200);
      },
      fail: function () {
        that.setData({
          submitting: false,
          globalError: '体验模式登录失败，请确认后端服务已启动'
        });
      }
    });
  },

  // ===== 忘记密码 =====
  goForgotPassword: function () {
    wx.navigateTo({ url: '/pages/forgot-password/index' });
  },

  noop: function () {}
});
