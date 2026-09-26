<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">管理员账号</div>
      <el-button v-if="canManage" type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>新建管理员
      </el-button>
    </div>

    <div class="card-block">
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索账号 / 姓名" clearable @keyup.enter="load" @clear="load" />
        <el-select v-model="roleFilter" placeholder="角色" clearable style="width: 160px" @change="load">
          <el-option v-for="r in roles" :key="r.code" :label="r.name" :value="r.code" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="list" border stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="账号" min-width="160">
          <template #default="{ row }">
            <div class="cell-strong">{{ row.username }}</div>
            <div class="text-muted" style="font-size: 12px">{{ row.nickname }}</div>
          </template>
        </el-table-column>
        <el-table-column label="角色" width="140">
          <template #default="{ row }">
            <el-tag :type="row.role === 'superadmin' ? 'danger' : row.role === 'operator' ? 'primary' : 'info'" size="small" effect="plain">
              {{ row.role_name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small" effect="plain">
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最后登录" width="170" />
        <el-table-column prop="last_login_ip" label="登录IP" width="130" />
        <el-table-column prop="created_at" label="创建时间" width="170" />
        <el-table-column v-if="canManage" label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" @click="resetPassword(row)">重置密码</el-button>
            <el-button link type="danger" @click="removeAdmin(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑管理员' : '新建管理员'" width="480px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="登录账号">
          <el-input v-model="form.username" :disabled="isEdit" placeholder="英文/数字" />
        </el-form-item>
        <el-form-item v-if="!isEdit" label="初始密码">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.nickname" placeholder="显示名称" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width: 100%" :disabled="isEdit && form.username === user.profile?.username">
            <el-option v-for="r in roles" :key="r.code" :label="r.name" :value="r.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio value="active">启用</el-radio>
            <el-radio value="disabled">停用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取 消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保 存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { adminApi, roleApi } from '../api'
import { useUserStore } from '../stores/user'

const user = useUserStore()
const canManage = user.hasPerm('admin.manage')

const list = ref([])
const roles = ref([])
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const roleFilter = ref('')
const dialogVisible = ref(false)
const isEdit = ref(false)
const form = reactive({ id: null, username: '', password: '', nickname: '', role: 'operator', status: 'active' })

async function load() {
  loading.value = true
  try {
    const params = {}
    if (keyword.value) params.keyword = keyword.value
    if (roleFilter.value) params.role = roleFilter.value
    const data = await adminApi.list(params)
    list.value = data.list
  } finally {
    loading.value = false
  }
}

function openCreate() {
  isEdit.value = false
  Object.assign(form, { id: null, username: '', password: '', nickname: '', role: 'operator', status: 'active' })
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  Object.assign(form, {
    id: row.id,
    username: row.username,
    password: '',
    nickname: row.nickname,
    role: row.role,
    status: row.status,
  })
  dialogVisible.value = true
}

async function submit() {
  if (!form.username.trim()) return ElMessage.warning('请填写登录账号')
  if (!isEdit.value && form.password.length < 6) return ElMessage.warning('初始密码至少 6 位')
  saving.value = true
  try {
    if (isEdit.value) {
      await adminApi.update(form.id, {
        nickname: form.nickname,
        role: form.role,
        status: form.status,
      })
    } else {
      await adminApi.create({
        username: form.username,
        password: form.password,
        nickname: form.nickname,
        role: form.role,
        status: form.status,
      })
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function resetPassword(row) {
  const { value } = await ElMessageBox.prompt(`为「${row.username}」设置新密码`, '重置密码', {
    inputType: 'password',
    inputPattern: /^.{6,}$/,
    inputErrorMessage: '密码至少 6 位',
  })
  await adminApi.resetPassword(row.id, value)
  ElMessage.success('密码已重置，该账号需要重新登录')
}

async function removeAdmin(row) {
  await ElMessageBox.confirm(`确定删除管理员「${row.username}」吗？`, '删除确认', { type: 'warning' })
  await adminApi.remove(row.id)
  ElMessage.success('已删除')
  await load()
}

onMounted(async () => {
  roles.value = await roleApi.list()
  await load()
})
</script>

<style scoped>
.cell-strong {
  font-weight: 500;
}
</style>
