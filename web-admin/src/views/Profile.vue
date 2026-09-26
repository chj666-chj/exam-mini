<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">账号设置</div>
    </div>
    <el-row :gutter="14">
      <el-col :xs="24" :md="12">
        <div class="card-block">
          <el-descriptions title="当前账号" :column="1" border>
            <el-descriptions-item label="登录账号">{{ user.profile?.username }}</el-descriptions-item>
            <el-descriptions-item label="姓名">{{ user.profile?.nickname }}</el-descriptions-item>
            <el-descriptions-item label="角色">{{ user.profile?.role_name }}</el-descriptions-item>
            <el-descriptions-item label="最后登录">{{ user.profile?.last_login_at || '-' }}</el-descriptions-item>
            <el-descriptions-item label="登录IP">{{ user.profile?.last_login_ip || '-' }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </el-col>
      <el-col :xs="24" :md="12">
        <div class="card-block">
          <div class="block-title">我的权限（{{ user.permissions.length }} 项）</div>
          <el-tag v-for="p in user.permissions" :key="p" size="small" effect="light" style="margin: 0 6px 6px 0">
            {{ p }}
          </el-tag>
          <div style="margin-top: 16px">
            <el-button type="primary" @click="pwdVisible = true">修改密码</el-button>
          </div>
        </div>
      </el-col>
    </el-row>
    <PasswordDialog v-model="pwdVisible" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import PasswordDialog from '../components/PasswordDialog.vue'
import { useUserStore } from '../stores/user'

const user = useUserStore()
const pwdVisible = ref(false)
</script>

<style scoped>
.block-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
}
</style>
