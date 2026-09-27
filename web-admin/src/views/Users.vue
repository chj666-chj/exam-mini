<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">用户管理</div>
      <el-button :loading="loading" @click="load">
        <el-icon><Refresh /></el-icon>
      </el-button>
    </div>

    <div class="card-block">
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索昵称 / 用户名 / OpenID" clearable @keyup.enter="search" @clear="search">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="status" placeholder="账号状态" clearable @change="search">
          <el-option label="启用" value="active" />
          <el-option label="停用" value="disabled" />
        </el-select>
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="list" size="default" border stripe @sort-change="onSort">
        <el-table-column label="用户" min-width="200">
          <template #default="{ row }">
            <div class="user-cell">
              <el-avatar :size="34" :src="row.avatar">{{ (row.nickname || 'U').slice(0, 1) }}</el-avatar>
              <div>
                <div class="cell-strong">{{ row.nickname }}</div>
                <div class="text-muted cell-sub">{{ row.openid }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="account" label="用户名" width="120" show-overflow-tooltip />
        <el-table-column prop="city" label="城市" width="100" />
        <el-table-column label="联系方式" width="180">
          <template #default="{ row }">
            <div v-if="row.email || row.phone" class="contact-cell">
              <div v-if="row.email" class="contact-line">邮箱: {{ row.email }}</div>
              <div v-if="row.phone" class="contact-line">手机: {{ row.phone }}</div>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="records" label="答题次数" width="100" align="right" sortable="custom" />
        <el-table-column prop="notes" label="错题数" width="90" align="right" sortable="custom" />
        <el-table-column label="正确率" width="100" align="right">
          <template #default="{ row }">{{ percent(row.accuracy) }}</template>
        </el-table-column>
        <el-table-column prop="last_active" label="最近活跃" width="120" />
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'disabled' ? 'danger' : 'success'" size="small" effect="plain">
              {{ row.status === 'disabled' ? '已停用' : '正常' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewProfile(row)">画像</el-button>
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button v-if="canManage" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canManage" link type="warning" @click="handleResetPassword(row)">重置密码</el-button>
            <el-button v-if="user.isSuper" link type="danger" @click="removeUser(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @current-change="load"
          @size-change="load"
        />
      </div>
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="`用户详情 · ${current.nickname || ''}`" size="46%">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="OpenID">{{ current.openid }}</el-descriptions-item>
        <el-descriptions-item label="用户名">{{ current.account || '-' }}</el-descriptions-item>
        <el-descriptions-item label="昵称">{{ current.nickname }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ current.email || '-' }}</el-descriptions-item>
        <el-descriptions-item label="手机号">{{ current.phone || '-' }}</el-descriptions-item>
        <el-descriptions-item label="地址">{{ current.address || '-' }}</el-descriptions-item>
        <el-descriptions-item label="城市">{{ current.city || '-' }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="current.status === 'disabled' ? 'danger' : 'success'" size="small" effect="plain">
            {{ current.status === 'disabled' ? '已停用' : '正常' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="备注">{{ current.remark || '-' }}</el-descriptions-item>
        <el-descriptions-item label="答题次数">{{ current.records }}</el-descriptions-item>
        <el-descriptions-item label="错题数">{{ current.notes }}</el-descriptions-item>
        <el-descriptions-item label="平均正确率">{{ percent(current.accuracy) }}</el-descriptions-item>
        <el-descriptions-item label="最近活跃">{{ current.last_active || '-' }}</el-descriptions-item>
      </el-descriptions>

      <div class="block-title" style="margin: 18px 0 8px">最近答题记录</div>
      <el-table :data="detail.recent_records" size="small" border max-height="220">
        <el-table-column prop="createTime" label="时间" width="140" />
        <el-table-column prop="subject" label="科目" min-width="120" />
        <el-table-column label="成绩" width="110">
          <template #default="{ row }">{{ row.rightNum }} / {{ row.total }}</template>
        </el-table-column>
        <el-table-column prop="time" label="用时" width="90" />
      </el-table>

      <div class="block-title" style="margin: 18px 0 8px">最近错题</div>
      <el-table :data="detail.recent_notes" size="small" border max-height="200">
        <el-table-column prop="ordernum" label="批次号" width="150" />
        <el-table-column prop="title" label="题目" min-width="200" show-overflow-tooltip />
      </el-table>
    </el-drawer>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editVisible" title="编辑用户" width="480px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="OpenID">
          <el-input :model-value="form.openid" disabled />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input :model-value="form.account" disabled />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model="form.nickname" placeholder="未授权资料的用户可在此补充" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="用户邮箱地址" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" placeholder="用户手机号码" />
        </el-form-item>
        <el-form-item label="地址">
          <el-input v-model="form.address" placeholder="用户联系地址" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio value="active">正常</el-radio>
            <el-radio value="disabled">停用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="运营备注，仅后台可见" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取 消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">保 存</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码结果弹窗 -->
    <el-dialog v-model="resetResultVisible" title="密码已重置" width="440px" :close-on-click-modal="false">
      <el-alert type="warning" :closable="false" style="margin-bottom: 16px">
        已为用户 <strong>{{ resetResult.nickname }}</strong> 生成临时密码，用户首次登录时需强制修改密码。
      </el-alert>
      <el-form label-width="90px">
        <el-form-item label="临时密码">
          <el-input :model-value="resetResult.tempPassword" readonly>
            <template #append>
              <el-button @click="copyTempPassword">复制</el-button>
            </template>
          </el-input>
        </el-form-item>
      </el-form>
      <div class="reset-tip">请将临时密码安全地告知用户（建议通过邮箱/短信等渠道通知），用户登录后系统将要求其立即修改密码。</div>
      <template #footer>
        <el-button type="primary" @click="resetResultVisible = false">我已知晓</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { Refresh, Search } from '@element-plus/icons-vue'
import { userApi } from '../api'
import { useUserStore } from '../stores/user'

const router = useRouter()
const user = useUserStore()
const canManage = user.hasPerm('user.manage')

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const status = ref('')
const sortKey = ref('')

const detailVisible = ref(false)
const editVisible = ref(false)
const saving = ref(false)
const current = reactive({ openid: '', nickname: '', account: '', email: '', phone: '', address: '', status: 'active', remark: '' })
const detail = ref({ recent_records: [], recent_notes: [] })
const form = reactive({ openid: '', nickname: '', account: '', email: '', phone: '', address: '', status: 'active', remark: '' })
const resetResultVisible = ref(false)
const resetResult = reactive({ nickname: '', tempPassword: '' })

const percent = (v) => `${((v || 0) * 100).toFixed(1)}%`

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (status.value) params.status = status.value
    const data = await userApi.list(params)
    list.value = data.list
    total.value = data.total
    if (sortKey.value) applySort(sortKey.value)
  } finally {
    loading.value = false
  }
}

function applySort(key) {
  list.value = [...list.value].sort((a, b) => (b[key] || 0) - (a[key] || 0))
}

function onSort({ prop }) {
  if (!prop) return
  sortKey.value = prop
  applySort(prop)
}

function search() {
  page.value = 1
  load()
}

function resetFilters() {
  keyword.value = ''
  status.value = ''
  sortKey.value = ''
  search()
}

async function openDetail(row) {
  Object.assign(current, row)
  detailVisible.value = true
  detail.value = { recent_records: [], recent_notes: [] }
  detail.value = await userApi.detail(row.openid)
}

function viewProfile(row) {
  router.push({ name: 'user-profile', params: { openid: row.openid } })
}

function openEdit(row) {
  Object.assign(current, row)
  form.openid = row.openid || ''
  form.account = row.account || ''
  form.nickname = row.nickname === '（未授权资料）' ? '' : (row.nickname || '')
  form.email = row.email || ''
  form.phone = row.phone || ''
  form.address = row.address || ''
  form.status = row.status || 'active'
  form.remark = row.remark || ''
  editVisible.value = true
}

async function submitEdit() {
  saving.value = true
  try {
    await userApi.update(form.openid, {
      nickname: form.nickname,
      status: form.status,
      remark: form.remark,
      email: form.email,
      phone: form.phone,
      address: form.address,
    })
    ElMessage.success('保存成功')
    editVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function handleResetPassword(row) {
  try {
    await ElMessageBox.confirm(
      `确认重置用户「${row.nickname || row.account || row.openid}」的密码？重置后将生成随机临时密码，用户首次登录时需强制修改。`,
      '重置密码',
      { type: 'warning', confirmButtonText: '确认重置', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  const data = await userApi.resetPassword(row.openid)
  resetResult.nickname = row.nickname || row.account || row.openid
  resetResult.tempPassword = data.temp_password || data.tempPassword || ''
  resetResultVisible.value = true
}

function copyTempPassword() {
  const pwd = resetResult.tempPassword
  if (!pwd) return
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(pwd).then(() => {
      ElMessage.success('临时密码已复制到剪贴板')
    }).catch(() => {
      fallbackCopy(pwd)
    })
  } else {
    fallbackCopy(pwd)
  }
}

function fallbackCopy(text) {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    document.execCommand('copy')
    ElMessage.success('临时密码已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本复制')
  }
  document.body.removeChild(textarea)
}

async function removeUser(row) {
  await ElMessageBox.confirm(
    `将删除 ${row.nickname} 的全部答题记录、错题与资料，且不可恢复。确定继续吗？`,
    '高危操作',
    { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
  )
  const data = await userApi.remove(row.openid)
  ElMessage.success(`已删除 ${data.deleted} 条数据`)
  await load()
}

onMounted(load)
</script>

<style scoped>
.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.cell-strong {
  font-weight: 500;
}

.cell-sub {
  font-size: 12px;
}

.contact-cell {
  font-size: 12px;
  line-height: 1.6;
}

.contact-line {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.reset-tip {
  font-size: 13px;
  color: #909399;
  line-height: 1.6;
  margin-top: 4px;
}

.pager {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

.block-title {
  font-size: 14px;
  font-weight: 600;
}
</style>
