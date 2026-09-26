import { defineStore } from 'pinia'
import { authApi } from '../api'
import { TOKEN_KEY } from '../api/http'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    profile: null,
    loaded: false,
  }),
  getters: {
    loggedIn: (state) => !!state.token,
    permissions: (state) => state.profile?.permissions || [],
    isSuper: (state) => !!state.profile?.is_superuser,
    nickname: (state) => state.profile?.nickname || state.profile?.username || '',
  },
  actions: {
    async login(payload) {
      const data = await authApi.login(payload)
      this.token = data.token
      this.profile = data.user
      localStorage.setItem(TOKEN_KEY, data.token)
      return data
    },
    async fetchProfile() {
      if (!this.token) return null
      this.profile = await authApi.profile()
      this.loaded = true
      return this.profile
    },
    async logout() {
      try {
        await authApi.logout()
      } catch (e) {
        // 令牌失效时也要清理本地状态
      }
      this.token = ''
      this.profile = null
      this.loaded = false
      localStorage.removeItem(TOKEN_KEY)
    },
    hasPerm(code) {
      if (!code) return true
      if (this.isSuper) return true
      return this.permissions.includes(code)
    },
  },
})
