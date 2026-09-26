import axios from 'axios'
import { ElMessage } from 'element-plus'

export const TOKEN_KEY = 'exam_admin_token'

const http = axios.create({
  baseURL: '/api/admin',
  timeout: 30000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 统一响应处理：后端返回 { code, message, data }
http.interceptors.response.use(
  (response) => {
    const body = response.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) {
        return body.data
      }
      ElMessage.error(body.message || '请求失败')
      const error = new Error(body.message || '请求失败')
      error.code = body.code
      error.status = response.status
      return Promise.reject(error)
    }
    return body
  },
  (error) => {
    const status = error.response?.status
    const body = error.response?.data
    const message = body?.message || error.message || '网络异常'
    if (status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      ElMessage.error(message)
      // 避免登录页自身重复跳转
      if (!location.hash.startsWith('#/login')) {
        location.hash = '#/login'
        setTimeout(() => location.reload(), 100)
      }
      return Promise.reject(error)
    }
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

export default http
