// utils/api.js —— 微信云开发兼容层（对接 Django 后端）
//
// 本文件把原项目中的 wx.cloud.database() / wx.cloud.callFunction() 语义
// 映射为本机 Django 后端的 HTTP 接口，页面代码只需把
//   wx.cloud.database()   ->  api.database()
//   wx.cloud.callFunction ->  api.callFunction
// 后续正式后端开发时，可在本文件内逐步替换为具体的业务接口。

const API_BASE = 'http://127.0.0.1:8000/api';

// 集合别名：原仓库新旧版本页面使用了不同集合名，统一映射到 Django 端集合
const COLLECTION_ALIAS = {
  question: 'questions'
};

/**
 * 基础请求（不带鉴权预处理），返回 Promise
 * @param {Object} extraOpts - { timeout?: number, signal?: AbortSignal-like }
 *   timeout: 请求超时毫秒数（透传 wx.request timeout）
 *   signal:  { aborted: boolean, onAbort: Function } 可选，外部可置 aborted=true 中止
 * @returns {Promise} resolve(data) / reject({statusCode, data, errMsg})
 */
function rawRequest(method, path, data, extraOpts) {
  extraOpts = extraOpts || {};
  return new Promise(function (resolve, reject) {
    var task = wx.request({
      url: API_BASE + path,
      method: method,
      data: data,
      timeout: extraOpts.timeout || undefined,
      header: {
        'Content-Type': 'application/json',
        'X-Openid': wx.getStorageSync('openid') || ''
      },
      success: function (res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(res);
        }
      },
      fail: function (err) {
        reject(err);
      }
    });
    // 支持外部中止：signal.aborted=true 时调 task.abort()
    if (extraOpts.signal && task && typeof task.abort === 'function') {
      extraOpts.signal._task = task;
      if (extraOpts.signal.aborted) {
        task.abort();
      } else if (typeof extraOpts.signal.onAbort === 'function') {
        extraOpts.signal.onAbort(function () { task.abort(); });
      }
    }
  });
}

/**
 * 写操作前确保已登录：后端对答题记录/错题等私有集合开启写权限校验，
 * 若本地缓存尚无 openid（例如后端刚启动、onLaunch 登录未完成），
 * 这里先补一次 login 再发起写请求，避免交卷/收藏错题被 403 拦截。
 */
function ensureOpenid() {
  if (wx.getStorageSync('openid')) {
    return Promise.resolve();
  }
  return callFunction({ name: 'login' }).then(function () { }, function () { });
}

/**
 * 带鉴权预处理的请求入口
 * opts.skipAuth 用于 login 自身，避免递归
 */
function request(method, path, data, opts) {
  opts = opts || {};
  var pre = (method === 'GET' || opts.skipAuth) ? Promise.resolve() : ensureOpenid();
  return pre.then(function () {
    return rawRequest(method, path, data, opts);
  });
}

/**
 * 兼容云开发回调风格：
 * 传了 opts.success / opts.fail 则回调，同时返回 Promise
 * transformer 用于把 Django 响应转换成云开发响应结构
 */
function withCallbacks(promiseFactory, opts, transformer) {
  var p = promiseFactory().then(function (res) {
    var result = transformer ? transformer(res) : res;
    if (opts && typeof opts.success === 'function') {
      opts.success(result);
    }
    return result;
  }, function (err) {
    if (opts && typeof opts.fail === 'function') {
      opts.fail(err);
    }
    throw err;
  });
  // 回调模式下吞掉未处理的 Promise 异常，避免控制台噪音
  if (opts && typeof opts.success === 'function') {
    p.catch(function () { });
  }
  return p;
}

/**
 * 兼容 wx.cloud.callFunction —— 目前仅支持 name: 'login'
 * Django 端 /api/login/ 返回演示 openid 并存入本地缓存
 */
function callFunction(options) {
  options = options || {};
  return withCallbacks(
    function () { return request('POST', '/login/', options.data || {}, { skipAuth: true }); },
    options,
    function (res) {
      var openid = res.openid;
      if (openid) {
        wx.setStorageSync('openid', openid);
        var app = getApp();
        if (app && app.globalData) {
          app.globalData.openid = openid;
        }
      }
      return { result: { openid: openid } };
    }
  );
}

/**
 * 账号注册：POST /api/register/
 * @param {Object} data - { username, password, nickname? }
 * @returns {Promise} { openid, nickname }
 */
function register(data) {
  return request('POST', '/register/', data || {}, { skipAuth: true }).then(function (res) {
    if (res && typeof res === 'object' && 'code' in res) {
      if (res.code === 0) {
        return res.data || {};
      }
      throw { message: res.message || '注册失败', code: res.code };
    }
    return res;
  });
}

/**
 * 账号登录：POST /api/account-login/
 * 登录成功后将 openid 写入本地缓存并同步到 app.globalData
 * @param {Object} data - { username, password }
 * @returns {Promise} { openid, nickname, avatarUrl }
 */
function accountLogin(data) {
  return request('POST', '/account-login/', data || {}, { skipAuth: true }).then(function (res) {
    if (res && typeof res === 'object' && 'code' in res) {
      if (res.code === 0) {
        var info = res.data || {};
        if (info.openid) {
          wx.setStorageSync('openid', info.openid);
          var app = getApp();
          if (app && app.globalData) {
            app.globalData.openid = info.openid;
          }
        }
        return info;
      }
      throw { message: res.message || '登录失败', code: res.code };
    }
    return res;
  });
}

// ============ 用户资料 & 密码管理 ============

/**
 * 获取个人资料
 * GET /api/profile/
 * @returns {Promise} { account, nickname, avatarUrl, email, phone, address, createdAt }
 */
function getProfile() {
  return ensureOpenid().then(function () {
    return request('GET', '/profile/');
  }).then(function (res) {
    if (res && typeof res === 'object' && 'code' in res) {
      return res.data || {};
    }
    return res;
  });
}

/**
 * 更新个人资料
 * POST /api/profile/update/
 * @param {Object} data - { nickname?, avatarUrl?, email?, phone?, address? }
 * @returns {Promise} 更新后的资料
 */
function updateProfile(data) {
  return ensureOpenid().then(function () {
    return request('POST', '/profile/update/', data || {});
  }).then(function (res) {
    if (res && typeof res === 'object' && 'code' in res) {
      if (res.code === 0) return res.data || {};
      throw { message: res.message || '保存失败', code: res.code };
    }
    return res;
  });
}

/**
 * 修改密码（需登录，验证原密码）
 * POST /api/change-password/
 * @param {Object} data - { oldPassword, newPassword }
 * @returns {Promise}
 */
function changePassword(data) {
  return ensureOpenid().then(function () {
    return request('POST', '/change-password/', data || {});
  }).then(function (res) {
    if (res && typeof res === 'object' && 'code' in res) {
      if (res.code === 0) return res;
      throw { message: res.message || '密码修改失败', code: res.code };
    }
    return res;
  });
}

/**
 * 忘记密码 - 发送验证码
 * POST /api/forgot-password/
 * @param {Object} data - { account, channel: 'email'|'phone' }
 * @returns {Promise} { devCode?, target? }
 */
function forgotPassword(data) {
  return request('POST', '/forgot-password/', data || {}, { skipAuth: true }).then(function (res) {
    if (res && typeof res === 'object' && 'code' in res) {
      if (res.code === 0) return res.data || {};
      throw { message: res.message || '发送失败', code: res.code };
    }
    return res;
  });
}

/**
 * 重置密码（验证码 + 新密码）
 * POST /api/reset-password/
 * @param {Object} data - { account, code, newPassword }
 * @returns {Promise}
 */
function resetPassword(data) {
  return request('POST', '/reset-password/', data || {}, { skipAuth: true }).then(function (res) {
    if (res && typeof res === 'object' && 'code' in res) {
      if (res.code === 0) return res;
      throw { message: res.message || '重置失败', code: res.code };
    }
    return res;
  });
}

/**
 * 兼容 wx.cloud.database().collection(name) 链式调用
 * 支持：
 *   .get({success, fail}) / .get().then()
 *   .where(cond).get(...)
 *   .doc(id).get(...)
 *   .add({data, success, fail})
 *   .where(cond).count().then(res => res.total)
 */
function collection(rawName) {
  var name = COLLECTION_ALIAS[rawName] || rawName;
  var state = { where: null, docId: null };

  // where 条件转 query string（_openid 也走查询参数，由服务端过滤）
  function buildQueryString(extra) {
    var parts = [];
    if (state.where) {
      Object.keys(state.where).forEach(function (k) {
        parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(state.where[k]));
      });
    }
    if (extra) {
      parts.push('count=1');
    }
    return parts.length ? '?' + parts.join('&') : '';
  }

  var coll = {
    where: function (cond) {
      state.where = cond || {};
      return coll;
    },
    doc: function (id) {
      state.docId = String(id);
      return coll;
    },
    get: function (opts) {
      if (state.docId) {
        return withCallbacks(
          function () { return request('GET', '/collections/' + name + '/' + state.docId + '/'); },
          opts,
          function (res) { return { data: res.data }; }
        );
      }
      return withCallbacks(
        function () { return request('GET', '/collections/' + name + '/' + buildQueryString(false)); },
        opts,
        function (res) { return { data: res.data }; }
      );
    },
    add: function (opts) {
      opts = opts || {};
      return withCallbacks(
        function () { return request('POST', '/collections/' + name + '/', opts.data); },
        opts,
        function (res) { return { _id: res._id }; }
      );
    },
    count: function () {
      return request('GET', '/collections/' + name + '/' + buildQueryString(true)).then(function (res) {
        return { total: res.total };
      });
    },
    update: function (opts) {
      opts = opts || {};
      return withCallbacks(
        function () { return request('PUT', '/collections/' + name + '/' + state.docId + '/', opts.data); },
        opts,
        function (res) { return { stats: { updated: 1 } }; }
      );
    }
  };
  return coll;
}

/** 对外暴露：api.database() 与 wx.cloud.database() 等价 */
function database() {
  return { collection: collection };
}

/**
 * AI 辅助写作：POST /api/ai/assist/（服务端配置）
 * @param {Object} data - {prompt: string, context?: string, action?: string}
 * @returns {Promise} 解析后的响应数据
 */
function aiAssist(data) {
  return request('POST', '/ai/assist/', data || {});
}

/**
 * AI 辅助写作（带超时 + 重试 + 可取消）
 * 后端 complex 分级 timeout=120s，微信默认 wx.request 超时 60s 会提前断开，
 * 此处显式设置 130s 超时（留 10s 余量），超时后重试 1 次。
 *
 * @param {Object} data       - {prompt, context?, model_id?}
 * @param {Object} opts       - { signal?: Object, onRetry?: Function, timeout?: number }
 * @returns {Promise}
 */
var AI_ASSIST_TIMEOUT = 130000;  // 130s（后端 120s + 10s 余量）
var AI_ASSIST_RETRY_DELAY = 2000; // 首次超时后 2s 再重试

function aiAssistWithRetry(data, opts) {
  opts = opts || {};
  var signal = opts.signal;
  var onRetry = opts.onRetry;
  var timeout = opts.timeout || AI_ASSIST_TIMEOUT;
  var attempt = 0;

  function tryOnce() {
    attempt++;
    return request('POST', '/ai/assist/', data || {}, { timeout: timeout, signal: signal })
      .catch(function (err) {
        // 4xx 业务错误（如 400/401/403/503）不重试——非瞬时故障
        var status = (err && err.statusCode) || 0;
        if (status >= 400 && status < 500) {
          throw err;
        }
        // 超时/网络错误且首次尝试 → 等待后重试一次
        if (attempt < 2) {
          return new Promise(function (resolve) {
            setTimeout(resolve, AI_ASSIST_RETRY_DELAY);
          }).then(function () {
            if (onRetry) { try { onRetry(attempt); } catch (e) {} }
            return tryOnce();
          });
        }
        throw err;
      });
  }
  return tryOnce();
}

/**
 * P1: 获取今日复习推荐
 * GET /api/ai/review-plan/
 * @returns {Promise} 复习推荐数据
 */
function aiReviewPlan() {
  return request('GET', '/ai/review-plan/');
}

/**
 * P1: 生成今日复习推荐（异步任务）
 * POST /api/ai/review-plan/
 * @returns {Promise} 包含 job_id 的响应
 */
function aiGenerateReviewPlan() {
  return request('POST', '/ai/review-plan/', {});
}

/**
 * P1: 获取学习画像（答题分析）
 * GET /api/ai/learning-profile/
 * @returns {Promise} 学习画像数据
 */
function aiLearningProfile() {
  return request('GET', '/ai/learning-profile/');
}

/**
 * P1: 生成学习画像（异步任务）
 * POST /api/ai/learning-profile/
 * @returns {Promise} 包含 job_id 的响应
 */
function aiGenerateLearningProfile() {
  return request('POST', '/ai/learning-profile/', {});
}

/**
 * P1: 查询异步任务状态
 * GET /api/ai/jobs/<job_id>/status/
 * @param {string} jobId - 任务 ID
 * @returns {Promise} 任务状态数据
 */
function aiJobStatus(jobId) {
  return request('GET', '/ai/jobs/' + jobId + '/status/').then(function (res) {
    // 解包信封 {code, message, data} → data
    if (res && typeof res === 'object' && 'code' in res) {
      return res.data || {};
    }
    return res;
  });
}

/**
 * P2: 知识库 RAG 问答
 * POST /api/ai/kb-ask/
 * @param {string} question - 用户问题
 * @returns {Promise} {answer, sources, cached}
 */
function aiKbAsk(question, modelId) {
  var payload = { question: question };
  if (modelId) payload.model_id = modelId;
  return request('POST', '/ai/kb-ask/', payload);
}

/**
 * P2: 获取最新学习报告
 * GET /api/ai/report/?type=weekly
 * @param {string} type - weekly | monthly | pre_exam
 * @returns {Promise} 报告数据或 null
 */
function aiLearningReport(type) {
  // GET 请求不经过 request() 的 ensureOpenid 预处理，首次进入时 openid 可能未就绪，
  // 这里先确保登录再发请求，避免 X-Openid 为空导致后端 401。
  return ensureOpenid().then(function () {
    return request('GET', '/ai/report/?type=' + (type || 'weekly'));
  }).then(function (res) {
    // 后端返回信封 {code, message, data}；解包 data 给前端使用
    if (res && typeof res === 'object' && 'code' in res) {
      return res.data || null;
    }
    return res;
  });
}

/**
 * P2: 生成学习报告（异步任务）
 * POST /api/ai/report/
 * @param {string} type - weekly | monthly | pre_exam
 * @returns {Promise} 包含 job_id 的响应
 */
function aiGenerateLearningReport(type) {
  return request('POST', '/ai/report/', { type: type || 'weekly' }).then(function (res) {
    // 解包信封 {code, message, data} → data
    if (res && typeof res === 'object' && 'code' in res) {
      return res.data || {};
    }
    return res;
  });
}

/**
 * P2: 智能客服对话
 * POST /api/ai/cs-chat/
 * @param {string} message - 用户消息
 * @param {Array} history - [{'role':'user'|'assistant','content':str}]
 * @returns {Promise} {reply, suggestions}
 */
function aiCsChat(message, history, modelId) {
  var payload = { message: message, history: history || [] };
  if (modelId) payload.model_id = modelId;
  return request('POST', '/ai/cs-chat/', payload);
}

/**
 * 使用用户自定义 AI 配置直接调用 LLM 接口
 * @param {Object} config - {apiUrl, apiKey, model, systemPrompt}
 * @param {Object} data - {prompt: string, context?: string}
 * @returns {Promise} 解析后的响应数据 {content: string}
 */
function callCustomAI(config, data) {
  return new Promise(function (resolve, reject) {
    var userContent = data.prompt || '';
    if (data.context) {
      userContent = '主题：' + data.prompt + '\n补充说明：' + data.context + '\n\n请根据以上信息撰写一篇结构清晰、内容充实的 Markdown 格式备考文章。';
    } else {
      userContent = '请根据以下主题撰写一篇结构清晰、内容充实的 Markdown 格式备考文章：\n\n' + data.prompt;
    }

    var messages = [
      { role: 'system', content: config.systemPrompt || '你是一个专业的备考文章写作助手。' },
      { role: 'user', content: userContent }
    ];

    wx.request({
      url: config.apiUrl,
      method: 'POST',
      data: {
        model: config.model,
        messages: messages,
        temperature: 0.7,
        max_tokens: 2000
      },
      header: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + config.apiKey
      },
      success: function (res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          var content = '';
          try {
            var choices = res.data.choices || [];
            if (choices.length > 0) {
              content = choices[0].message.content || '';
            }
          } catch (e) {
            reject({ message: '解析 AI 响应失败' });
            return;
          }
          if (content) {
            resolve({ content: content });
          } else {
            reject({ message: 'AI 未返回内容' });
          }
        } else {
          var errMsg = 'AI 接口返回 ' + res.statusCode;
          try {
            if (res.data && res.data.error && res.data.error.message) {
              errMsg = res.data.error.message;
            }
          } catch (e) { }
          reject({ message: errMsg });
        }
      },
      fail: function (err) {
        reject({ message: '连接 AI 接口失败，请检查网络或接口地址' });
      }
    });
  });
}

/**
 * 排行榜：GET /api/ranking/
 * 返回全用户聚合的排行榜（前 100 名）+ 当前用户详细统计。
 * @returns {Promise} {board, myStats, myRank, totalQuestions}
 */
function getRanking() {
  return ensureOpenid().then(function () {
    return request('GET', '/ranking/');
  });
}

/**
 * 单题全站作答统计：GET /api/question-stats/?id=<题目id>
 *
 * 为什么必须走后端专用接口：
 *   historys 属于服务端 PRIVATE_COLLECTIONS，GET 时会按 X-Openid 过滤，
 *   前端直接 db.collection('historys') 只能拿到「本人」的记录，
 *   永远算不出「全站」作答次数与正确率（新用户恒为 0 次 / 0%）。
 * @param {string} questionId 题目 _id
 * @returns {Promise} {data: {totalAttempts, correctCount, correctRate, correctCodes}}
 */
function getQuestionStats(questionId) {
  if (!questionId) {
    return Promise.resolve({ data: { totalAttempts: 0, correctCount: 0, correctRate: 0, correctCodes: [] } });
  }
  return request('GET', '/question-stats/?id=' + encodeURIComponent(questionId));
}

/**
 * 图片上传：POST /api/upload/
 * @param {string} filePath - 本地临时文件路径
 * @returns {Promise} 解析后的响应数据 {url, name, size}
 */
function uploadImage(filePath) {
  return new Promise(function (resolve, reject) {
    wx.uploadFile({
      url: API_BASE + '/upload/',
      filePath: filePath,
      name: 'file',
      header: {
        'X-Openid': wx.getStorageSync('openid') || ''
      },
      success: function (res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          var data;
          try {
            data = JSON.parse(res.data);
          } catch (e) {
            reject(e);
            return;
          }
          resolve(data);
        } else {
          reject(res);
        }
      },
      fail: function (err) {
        reject(err);
      }
    });
  });
}

/**
 * ============ AI 模型管理（多模型自定义接入）============
 * 数据来源为服务端 ai_models 集合，管理员配置的「全局模型」对所有用户可用，
 * 用户可再添加「自有模型」（携带自己的 Key），并从中选择默认 / 本次调用模型。
 * 接口：
 *   GET    /api/ai/models/           列表（含 meta：数量上限 / 预设 / 默认模型 / 生效说明）
 *   POST   /api/ai/models/           新增自有模型
 *   PUT    /api/ai/models/<id>/      更新
 *   DELETE /api/ai/models/<id>/      删除
 *   POST   /api/ai/models/<id>/default/  设为默认（用户模型或全局模型）
 *   POST   /api/ai/models/<id>/test/     测试连通性
 */
function aiModelList() {
  return request('GET', '/ai/models/');
}

function aiModelMeta() {
  return request('GET', '/ai/models/meta/');
}

function aiModelCreate(data) {
  return request('POST', '/ai/models/', data || {});
}

function aiModelUpdate(id, data) {
  return request('PUT', '/ai/models/' + id + '/', data || {});
}

function aiModelDelete(id) {
  return request('DELETE', '/ai/models/' + id + '/');
}

function aiModelSetDefault(id) {
  return request('POST', '/ai/models/' + id + '/default/', {});
}

function aiModelTest(id) {
  return request('POST', '/ai/models/' + id + '/test/', {});
}

// ============ AI 题目解析 & 答题分析总结（VIP 专用）============
// 后端按题目维度处理：已有 AI 解析记录则直接返回（缓存优先），未解析则触发 AI 生成并入库复用。
// 接口：
//   GET  /api/ai/vip-status/                      查询当前用户 VIP 状态
//   GET  /api/ai/question-analysis/<qid>/          查询单题已有 AI 解析（不触发 LLM）
//   POST /api/ai/question-analysis/<qid>/          触发单题 AI 解析（缓存优先）
//   POST /api/ai/exam-summary/                     整份作答的 AI 分析总结

/**
 * 查询当前用户 VIP 状态（前端据此控制 AI 入口显隐）
 * GET /api/ai/vip-status/
 * @returns {Promise} {isVip: bool, features: [...]}
 */
function getVipStatus() {
  return ensureOpenid().then(function () {
    return request('GET', '/ai/vip-status/');
  }).then(function (res) {
    if (res && typeof res === 'object' && 'code' in res) {
      return res.data || { isVip: false, features: [] };
    }
    return res || { isVip: false, features: [] };
  });
}

/**
 * 激活码自助激活
 * POST /api/activation/redeem/
 * @param {string} code 6 位数字激活码
 * @returns {Promise} { vip: true, vipDuration: 30 }
 */
function redeemActivationCode(code) {
  return ensureOpenid().then(function () {
    return request('POST', '/activation/redeem/', { code: code });
  }).then(function (res) {
    if (res && typeof res === 'object' && 'code' in res) {
      if (res.code === 0) {
        return res.data || { vip: true, vipDuration: 30 };
      }
      throw { message: res.message || '激活失败', code: res.code };
    }
    return res;
  });
}

/**
 * 查询单题已有 AI 解析（不触发 LLM，纯缓存读取）
 * GET /api/ai/question-analysis/<question_id>/
 * @param {string} questionId 题目 _id
 * @returns {Promise} {analysis: {...}|null, cached: bool, hasAnalysis: bool}
 */
function aiQuestionAnalysis(questionId) {
  if (!questionId) {
    return Promise.resolve({ analysis: null, cached: false, hasAnalysis: false });
  }
  return ensureOpenid().then(function () {
    return request('GET', '/ai/question-analysis/' + encodeURIComponent(questionId) + '/');
  }).then(function (res) {
    if (res && typeof res === 'object' && 'code' in res) {
      return res.data || { analysis: null, cached: false, hasAnalysis: false };
    }
    return res;
  });
}

/**
 * 触发单题 AI 解析（缓存优先：后端按 content_hash 判断，已解析直接返回，未解析才调 LLM）
 * POST /api/ai/question-analysis/<question_id>/
 * @param {string} questionId 题目 _id
 * @returns {Promise} {analysis: {...}, cached: bool, hasAnalysis: bool}
 */
function aiQuestionAnalysisTrigger(questionId) {
  if (!questionId) {
    return Promise.reject({ message: '题目 ID 不能为空' });
  }
  return ensureOpenid().then(function () {
    return request('POST', '/ai/question-analysis/' + encodeURIComponent(questionId) + '/', {});
  }).then(function (res) {
    if (res && typeof res === 'object' && 'code' in res) {
      return res.data || { analysis: {}, cached: false, hasAnalysis: true };
    }
    return res;
  });
}

/**
 * 整份作答的 AI 分析总结
 * POST /api/ai/exam-summary/
 * @param {Array} questions 题目数组 [{_id, title, qtype, options, difficulty, ...}, ...]
 * @param {Array} answers   作答数组 [["A"], ["B","C"], [], ...]（与 questions 下标对齐）
 * @returns {Promise} {summary: {content, overall, ...}, cached: bool, stats: {...}}
 */
function aiExamSummaryAnalysis(questions, answers) {
  return ensureOpenid().then(function () {
    return request('POST', '/ai/exam-summary/', {
      questions: questions || [],
      answers: answers || []
    });
  }).then(function (res) {
    if (res && typeof res === 'object' && 'code' in res) {
      return res.data || { summary: {}, cached: false, stats: {} };
    }
    return res;
  });
}

// ============ 收藏功能统一封装 ============
// 统一类型标识 favType: 'question' | 'article' | 'knowledge'
// 兼容历史数据：无 favType 时按 docType/questionId/articleId 推断

/**
 * 推断收藏记录的类型（兼容历史数据）
 * 优先级：favType 字段 > docType==='knowledge' > 有 articleId > 有 questionId > 默认 question
 * @param {Object} item 收藏记录
 * @returns {'question'|'article'|'knowledge'}
 */
function inferFavType(item) {
  if (!item) return 'question';
  if (item.favType) return item.favType;
  if (item.docType === 'knowledge') return 'knowledge';
  if (item.articleId) return 'article';
  if (item.questionId) return 'question';
  return 'question';
}

/**
 * 获取收藏列表（可选按类型过滤，客户端过滤兼容历史数据）
 * @param {string} [type] - 'question' | 'article' | 'knowledge'，不传则返回全部
 * @returns {Promise<Array>} 收藏列表，每条记录带 _favType 字段
 */
function getFavorites(type) {
  return ensureOpenid().then(function () {
    return request('GET', '/collections/favorites/');
  }).then(function (res) {
    var list = (res && res.data) || [];
    list.forEach(function (item) {
      item._favType = inferFavType(item);
    });
    if (type) {
      list = list.filter(function (item) { return item._favType === type; });
    }
    return list;
  });
}

/**
 * 查找指定类型的收藏记录（用于获取 _id 后删除）
 * @param {string} type - 'question' | 'article' | 'knowledge'
 * @param {string} targetId - 目标 ID（questionId / articleId / docId）
 * @returns {Promise<Object|null>} 收藏记录或 null
 */
function findFavorite(type, targetId) {
  if (!type || !targetId) return Promise.resolve(null);
  return ensureOpenid().then(function () {
    var idField, extraWhere = '';
    if (type === 'question') {
      idField = 'questionId';
    } else if (type === 'article') {
      idField = 'articleId';
      extraWhere = '&favType=article';
    } else {
      idField = 'docId';
      extraWhere = '&docType=knowledge';
    }
    var qs = idField + '=' + encodeURIComponent(targetId) + extraWhere;
    return request('GET', '/collections/favorites/?' + qs);
  }).then(function (res) {
    var list = (res && res.data) || [];
    return list.length > 0 ? list[0] : null;
  });
}

/**
 * 检查是否已收藏
 * @param {string} type - 'question' | 'article' | 'knowledge'
 * @param {string} targetId - 目标 ID
 * @returns {Promise<boolean>}
 */
function isFavorited(type, targetId) {
  return findFavorite(type, targetId).then(function (record) {
    return !!record;
  });
}

/**
 * 添加收藏（自动写入 favType 和唯一 _id）
 * @param {string} type - 'question' | 'article' | 'knowledge'
 * @param {Object} data - 收藏数据（不含 favType，由本函数注入）
 * @returns {Promise<{_id: string}>}
 */
function addFavorite(type, data) {
  if (!type || !data) return Promise.reject({ message: '参数缺失' });
  var ts = Date.now();
  var rand = Math.floor(Math.random() * 10000);
  var payload = Object.assign({}, data, {
    favType: type,
    _id: 'FAV_' + type + '_' + ts + '_' + rand
  });
  return ensureOpenid().then(function () {
    return request('POST', '/collections/favorites/', payload);
  });
}

/**
 * 删除收藏（通过 _id）
 * @param {string} favId - 收藏记录的 _id
 * @returns {Promise}
 */
function removeFavorite(favId) {
  if (!favId) return Promise.reject({ message: '收藏ID不能为空' });
  return ensureOpenid().then(function () {
    return request('DELETE', '/collections/favorites/' + favId + '/');
  });
}

/**
 * 切换收藏状态（高层封装：自动判断当前状态并切换）
 * @param {string} type - 'question' | 'article' | 'knowledge'
 * @param {string} targetId - 目标 ID
 * @param {Object} data - 收藏数据（添加时使用）
 * @returns {Promise<{favorited: boolean, action: 'added'|'removed'}>}
 */
function toggleFavorite(type, targetId, data) {
  if (!type || !targetId) return Promise.reject({ message: '参数缺失' });
  return findFavorite(type, targetId).then(function (record) {
    if (record) {
      return removeFavorite(record._id).then(function () {
        return { favorited: false, action: 'removed' };
      });
    }
    return addFavorite(type, data).then(function () {
      return { favorited: true, action: 'added' };
    });
  });
}

module.exports = {
  API_BASE: API_BASE,
  request: request,
  database: database,
  callFunction: callFunction,
  register: register,
  accountLogin: accountLogin,
  // 用户资料 & 密码管理
  getProfile: getProfile,
  updateProfile: updateProfile,
  changePassword: changePassword,
  forgotPassword: forgotPassword,
  resetPassword: resetPassword,
  aiAssist: aiAssist,
  aiAssistWithRetry: aiAssistWithRetry,
  callCustomAI: callCustomAI,
  uploadImage: uploadImage,
  getRanking: getRanking,
  getQuestionStats: getQuestionStats,
  aiReviewPlan: aiReviewPlan,
  aiGenerateReviewPlan: aiGenerateReviewPlan,
  aiLearningProfile: aiLearningProfile,
  aiGenerateLearningProfile: aiGenerateLearningProfile,
  aiJobStatus: aiJobStatus,
  aiKbAsk: aiKbAsk,
  aiLearningReport: aiLearningReport,
  aiGenerateLearningReport: aiGenerateLearningReport,
  aiCsChat: aiCsChat,
  aiModelList: aiModelList,
  aiModelMeta: aiModelMeta,
  aiModelCreate: aiModelCreate,
  aiModelUpdate: aiModelUpdate,
  aiModelDelete: aiModelDelete,
  aiModelSetDefault: aiModelSetDefault,
  aiModelTest: aiModelTest,
  // AI 题目解析 & 答题分析总结（VIP）
  getVipStatus: getVipStatus,
  redeemActivationCode: redeemActivationCode,
  aiQuestionAnalysis: aiQuestionAnalysis,
  aiQuestionAnalysisTrigger: aiQuestionAnalysisTrigger,
  aiExamSummaryAnalysis: aiExamSummaryAnalysis,
  // 收藏功能统一封装
  inferFavType: inferFavType,
  getFavorites: getFavorites,
  findFavorite: findFavorite,
  isFavorited: isFavorited,
  addFavorite: addFavorite,
  removeFavorite: removeFavorite,
  toggleFavorite: toggleFavorite
};
