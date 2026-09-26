<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <span class="brand-mark">考</span>
        <div>
          <h2>考试宝管理后台</h2>
          <p class="text-muted">小程序业务数据与用户运营平台</p>
        </div>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" size="large" @keyup.enter="submit">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="登录账号" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="登录密码"
            :prefix-icon="Lock"
          />
        </el-form-item>
        <el-button type="primary" class="login-btn" :loading="loading" @click="submit">登 录</el-button>
      </el-form>

      <div class="login-tip">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>本地演示账号：admin / admin123（角色：超级管理员）</template>
        </el-alert>
        <div class="demo-accounts">
          <el-link type="primary" @click="fill('admin', 'admin123')">填入超管账号</el-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useUserStore } from '../stores/user'

const route = useRoute()
const router = useRouter()
const user = useUserStore()

const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

function fill(username, password) {
  form.username = username
  form.password = password
}

async function submit() {
  await formRef.value.validate()
  loading.value = true
  try {
    await user.login({ username: form.username, password: form.password })
    ElMessage.success(`欢迎回来，${user.nickname}`)
    const redirect = route.query.redirect
    router.replace(redirect && redirect !== '/login' ? redirect : '/dashboard')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #eef2ff 0%, #f7f9fc 55%, #eaf6f4 100%);
  padding: 16px;
}

.login-card {
  width: 100%;
  max-width: 400px;
  background: #fff;
  border-radius: 16px;
  padding: 32px 28px 24px;
  box-shadow: 0 12px 32px rgba(31, 41, 55, 0.08);
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 26px;
}

.login-brand h2 {
  margin: 0;
  font-size: 20px;
}

.login-brand p {
  margin: 4px 0 0;
  font-size: 13px;
}

.brand-mark {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, #4f7cff, #7b5bff);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.login-btn {
  width: 100%;
}

.login-tip {
  margin-top: 18px;
}

.demo-accounts {
  margin-top: 10px;
  text-align: center;
}
</style>
