import http, { TOKEN_KEY } from './http'

/** 通用集合资源：exams / subjects / questions / records / notes */
export function resource(name) {
  return {
    list: (params) => http.get(`/${name}/`, { params }),
    get: (id) => http.get(`/${name}/${id}/`),
    create: (data) => http.post(`/${name}/`, data),
    update: (id, data) => http.put(`/${name}/${id}/`, data),
    remove: (id) => http.delete(`/${name}/${id}/`),
    bulkDelete: (ids) => http.post(`/${name}/bulk-delete/`, { ids }),
  }
}

export const authApi = {
  login: (data) => http.post('/auth/login/', data),
  logout: () => http.post('/auth/logout/'),
  profile: () => http.get('/auth/profile/'),
  changePassword: (data) => http.post('/auth/password/', data),
  permissions: () => http.get('/auth/permissions/'),
}

export const dashboardApi = {
  overview: () => http.get('/dashboard/overview/'),
  trend: (days) => http.get('/dashboard/trend/', { params: { days } }),
  ranking: () => http.get('/dashboard/ranking/'),
  logs: (params) => http.get('/dashboard/logs/', { params }),
  // ---- AI 使用分析 ----
  aiUsageOverview: (days) => http.get('/dashboard/ai-usage/', { params: { days } }),
  aiUsageTrend: (days) => http.get('/dashboard/ai-usage/trend/', { params: { days } }),
  aiUsageByFunction: (days) => http.get('/dashboard/ai-usage/by-function/', { params: { days } }),
  aiUsageByUser: (days, topN) => http.get('/dashboard/ai-usage/by-user/', { params: { days, top_n: topN } }),
  aiUsageFunctionTrend: (days) => http.get('/dashboard/ai-usage/function-trend/', { params: { days } }),
  aiUsageTokenDist: (days) => http.get('/dashboard/ai-usage/token-distribution/', { params: { days } }),
  aiUsageFeatures: () => http.get('/dashboard/ai-usage/features/'),
}

export const userApi = {
  list: (params) => http.get('/users/', { params }),
  detail: (openid) => http.get(`/users/${openid}/`),
  update: (openid, data) => http.put(`/users/${openid}/`, data),
  remove: (openid) => http.delete(`/users/${openid}/`),
  profile: (openid) => http.get(`/users/${openid}/profile/`),
}

export const adminApi = {
  list: (params) => http.get('/admins/', { params }),
  create: (data) => http.post('/admins/', data),
  update: (id, data) => http.put(`/admins/${id}/`, data),
  remove: (id) => http.delete(`/admins/${id}/`),
  resetPassword: (id, password) => http.post(`/admins/${id}/reset-password/`, { password }),
}

export const roleApi = {
  list: () => http.get('/roles/'),
  detail: (id) => http.get(`/roles/${id}/`),
  update: (id, data) => http.put(`/roles/${id}/`, data),
}

export const collectionApi = {
  index: () => http.get('/collections/'),
  docs: (name, params) => http.get(`/collections/${name}/`, { params }),
}

// ---- 标签管理 ----
export const tagApi = {
  list: (params) => http.get('/tags/', { params }),
  create: (data) => http.post('/tags/', data),
  update: (id, data) => http.put(`/tags/${id}/`, data),
  remove: (id) => http.delete(`/tags/${id}/`),
  batchBind: (data) => http.post('/tags/bind/', data),
  questionTags: (docId) => http.get(`/questions/${docId}/tags/`),
  bindQuestionTags: (docId, tagIds) => http.post(`/questions/${docId}/tags/`, { tag_ids: tagIds }),
  // 标签使用统计（按学科/题型/难度维度）
  stats: (id) => http.get(`/tags/${id}/stats/`),
}

// ---- 批量导入 ----
export const importApi = {
  create: (data) => http.post('/questions/import/', data),
  list: (params) => http.get('/questions/import/', { params }),
  detail: (jobId, withResults = true) => http.get(`/questions/import/${jobId}/`, { params: { with_results: withResults ? 1 : 0 } }),
  // Excel 模板列表
  templates: () => http.get('/questions/import/templates/'),
  // Excel 模板下载（使用 fetch 保留响应头中的文件名）
  downloadTemplate: async (qtype) => {
    const token = localStorage.getItem(TOKEN_KEY)
    const response = await fetch(`/api/admin/questions/import/templates/${qtype}/`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok) {
      const errData = await response.json().catch(() => null)
      throw new Error(errData?.message || '模板下载失败')
    }
    const blob = await response.blob()
    const disposition = response.headers.get('Content-Disposition') || ''
    let filename = `${qtype}_template.xlsx`
    const match = disposition.match(/filename\*=UTF-8''(.+)/)
    if (match) {
      filename = decodeURIComponent(match[1])
    }
    return { blob, filename }
  },
  // Excel 文件上传导入
  importExcel: (file, options = {}) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('qtype', options.qtype || '')
    fd.append('on_duplicate', options.on_duplicate || 'skip')
    if (options.default_examid) fd.append('default_examid', options.default_examid)
    if (options.tags) fd.append('tags', options.tags)
    fd.append('async', options.async ? 'true' : 'false')
    return http.post('/questions/import/excel/', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },
}

// ---- 图片上传 ----
export const uploadApi = {
  image: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/upload/', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
}

// ---- AI 判卷（预留） ----
export const aiGradeApi = {
  grade: (docId, data) => http.post(`/questions/${docId}/ai-grade/`, data),
}

// ---- 文章管理 ----
export const articleApi = {
  ...resource('articles'),
  audit: (id, action, reason) => http.post(`/articles/${id}/audit/`, { action, reason }),
}

// ---- 激活码管理 ----
export const activationCodeApi = {
  ...resource('activation-codes'),
  generate: (data) => http.post('/activation-codes/generate/', data),
}

// ---- AI 配置及 P0 AI 功能 ----
export const aiApi = {
  // 基础配置
  getConfig: () => http.get('/ai/config/'),
  saveConfig: (data) => http.put('/ai/config/', data),
  test: () => http.post('/ai/test/'),
  // ---- AI 多模型管理（全局模型：管理员维护，全部用户可用）----
  modelList: () => http.get('/ai/models/'),
  modelMeta: () => http.get('/ai/models/meta/'),
  modelCreate: (data) => http.post('/ai/models/', data),
  modelUpdate: (id, data) => http.put(`/ai/models/${id}/`, data),
  modelDelete: (id) => http.delete(`/ai/models/${id}/`),
  modelSetDefault: (id) => http.post(`/ai/models/${id}/default/`),
  modelTest: (id) => http.post(`/ai/models/${id}/test/`),
  assist: (data) => http.post('/ai/assist/', data),
  // AI 任务管理
  jobList: (params) => http.get('/ai/jobs/', { params }),
  jobStatus: (jobId) => http.get(`/ai/jobs/${jobId}/`),
  jobCancel: (jobId) => http.post(`/ai/jobs/${jobId}/cancel/`),
  // AI 题目解析
  analyzeQuestion: (docId) => http.post(`/ai/questions/${docId}/analyze/`),
  analyzeBatch: (questionIds) => http.post('/ai/questions/analyze-batch/', { question_ids: questionIds }),
  // AI 智能组卷
  compose: (config) => http.post('/ai/compose/', config),
  composeStatus: (jobId) => http.get(`/ai/compose/${jobId}/`),
  composeConfirm: (jobId, examName) => http.post(`/ai/compose/${jobId}/confirm/`, { exam_name: examName }),
  // AI 智能组卷 V2（三阶段定向组卷）
  smartCompose: (config) => http.post('/ai/smart-compose/', config),
  smartComposeKpStats: (examid) => http.get('/ai/smart-compose/kp-stats/', { params: { examid } }),
  smartComposeRebuildIndex: (examid) => http.post('/ai/smart-compose/rebuild-index/', { examid }),
  // AI 智能判卷
  gradeBatch: (historyId) => http.post('/ai/grade-batch/', { history_id: historyId }),
  gradeReviewList: (params) => http.get('/ai/grade/review-list/', { params }),
  gradeReview: (historyId, data) => http.put(`/ai/grade/${historyId}/review/`, data),
  // P1: 试卷分析
  examAnalyze: (examid) => http.post(`/ai/exams/${examid}/analyze/`),
  examAnalysisResult: (examid) => http.get(`/ai/exams/${examid}/analysis/`),
  // ---- P2: 知识库 RAG 问答（管理端：索引重建 / 统计 / 已索引文章）----
  kbRebuild: () => http.post('/ai/kb/rebuild/'),
  kbStats: () => http.get('/ai/kb/stats/'),
  kbIndexedArticles: () => http.get('/ai/kb/articles/'),
  // 文章 -> 知识库索引（按唯一编码 ART-YYYYMMDD-NNNN 可追溯）
  articleToKnowledge: (docId) => http.post(`/articles/${docId}/to-knowledge/`),
  articleFromKnowledge: (docId) => http.delete(`/articles/${docId}/to-knowledge/`),
  // 批量加入/移出：action = 'add' | 'remove'
  articlesToKnowledgeBatch: (ids, action = 'add') =>
    http.post('/articles/to-knowledge/', { ids, action }),
  // ---- AI 题目标签（已整合到题库管理模块）----
  // 按标签名应用（PUT /ai/questions/<docId>/tags/，body {tag_names}）
  applyQuestionTags: (docId, data) => http.put(`/ai/questions/${docId}/tags/`, data),
  // AI 标签推荐 + 自动同步到标签管理 + 自动绑定（一步完成）
  autoTagSync: (docId, data) => http.post(`/ai/questions/${docId}/auto-tag-sync/`, data),
  // 批量 AI 标签推荐 + 自动同步 + 自动绑定（异步）：返回 { job_id }
  autoTagSyncBatch: (questionIds, autoBind = true) =>
    http.post('/ai/questions/auto-tag-sync-batch/', { question_ids: questionIds, auto_bind: autoBind }),
  // ---- P2: Excel 智能校验（异步）：body { rows:[...], qtype } → { job_id } ----
  excelValidate: (data) => http.post('/ai/excel-validate/', data),
}
