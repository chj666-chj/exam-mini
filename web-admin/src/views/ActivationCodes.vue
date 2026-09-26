<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><Key /></el-icon></span>
        激活码管理
      </div>
      <div>
        <el-button type="danger" plain :disabled="!selection.length" @click="bulkRemove(ids)">
          <el-icon><Delete /></el-icon>批量删除（{{ selection.length }}）
        </el-button>
        <el-button type="primary" @click="openGenerate">
          <el-icon><MagicStick /></el-icon>批量生成
        </el-button>
      </div>
    </div>

    <div class="card-block">
      <!-- 统计卡片 -->
      <div class="stats-row">
        <div class="stat-card stat-total">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">总激活码</div>
        </div>
        <div class="stat-card stat-active">
          <div class="stat-value">{{ stats.active }}</div>
          <div class="stat-label">可用</div>
        </div>
        <div class="stat-card stat-used">
          <div class="stat-value">{{ stats.used }}</div>
          <div class="stat-label">已使用</div>
        </div>
        <div class="stat-card stat-disabled">
          <div class="stat-value">{{ stats.disabled }}</div>
          <div class="stat-label">已停用</div>
        </div>
      </div>

      <!-- 搜索 + 筛选 -->
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索激活码 / 使用者 / 备注" clearable
          @keyup.enter="search" @clear="search" style="width: 280px">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="statusFilter" placeholder="状态筛选" clearable @change="search" style="width: 140px">
          <el-option label="全部" value="" />
          <el-option label="可用" value="active" />
          <el-option label="已使用" value="used" />
          <el-option label="已停用" value="disabled" />
        </el-select>
        <el-button type="primary" @click="search"><el-icon><Search /></el-icon>查询</el-button>
        <el-button @click="reset"><el-icon><RefreshLeft /></el-icon>重置</el-button>
      </div>

      <!-- 表格 -->
      <el-table v-loading="loading" :data="list" border stripe size="default" @selection-change="onSelection">
        <el-table-column type="selection" width="46" />
        <el-table-column label="激活码" width="140">
          <template #default="{ row }">
            <div class="code-cell">
              <span class="code-text" @click="copyCode(row.code)">{{ row.code }}</span>
              <el-icon class="copy-icon" @click="copyCode(row.code)"><CopyDocument /></el-icon>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="VIP天数" width="100">
          <template #default="{ row }">
            {{ row.vipDuration > 0 ? row.vipDuration + ' 天' : '永久' }}
          </template>
        </el-table-column>
        <el-table-column label="过期时间" width="170">
          <template #default="{ row }">
            <span v-if="row.expireAt" :class="{ 'text-warning': isExpired(row.expireAt) }">{{ row.expireAt }}</span>
            <span v-else class="text-muted">永不过期</span>
          </template>
        </el-table-column>
        <el-table-column label="使用者" width="160">
          <template #default="{ row }">
            <span v-if="row.usedBy" class="text-muted">{{ shortOpenid(row.usedBy) }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="使用时间" width="170">
          <template #default="{ row }">
            <span v-if="row.usedAt">{{ row.usedAt }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <span>{{ row.note || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            <span class="text-muted">{{ row.createdAt || row._created_at }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'active'" link type="warning" @click="toggleDisable(row)">
              停用
            </el-button>
            <el-button v-if="row.status === 'disabled'" link type="success" @click="toggleEnable(row)">
              启用
            </el-button>
            <el-button link type="danger" @click="remove(row._id, '激活码 ' + row.code)">
              <el-icon><Delete /></el-icon>删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @current-change="load"
          @size-change="load"
        />
      </div>
    </div>

    <!-- 生成弹窗 -->
    <el-dialog v-model="genDialogVisible" title="批量生成激活码" width="480px">
      <el-form :model="genForm" label-width="100px">
        <el-form-item label="生成数量">
          <el-input-number v-model="genForm.count" :min="1" :max="500" style="width: 200px" />
        </el-form-item>
        <el-form-item label="VIP天数">
          <el-input-number v-model="genForm.vipDuration" :min="0" :max="3650" style="width: 200px" />
          <span class="form-hint">0 = 永久</span>
        </el-form-item>
        <el-form-item label="过期时间">
          <el-date-picker
            v-model="genForm.expireAt"
            type="datetime"
            placeholder="选择激活码过期时间（留空=永不过期）"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 300px"
            :disabled-date="disabledPastDate"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="genForm.note" placeholder="可选，如：活动赠送" maxlength="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="genDialogVisible = false">取 消</el-button>
        <el-button type="primary" :loading="generating" @click="doGenerate">生成</el-button>
      </template>
    </el-dialog>

    <!-- 生成结果弹窗 -->
    <el-dialog v-model="resultDialogVisible" title="生成结果" width="520px">
      <el-alert :title="`成功生成 ${generatedCodes.length} 个激活码`" type="success" :closable="false" style="margin-bottom: 16px" />
      <div class="generated-codes">
        <div v-for="item in generatedCodes" :key="item.code" class="generated-code-row" @click="copyCode(item.code)">
          <span class="code-text">{{ item.code }}</span>
          <span class="code-meta">{{ item.vipDuration > 0 ? item.vipDuration + '天' : '永久' }}</span>
          <el-icon class="copy-icon"><CopyDocument /></el-icon>
        </div>
      </div>
      <template #footer>
        <el-button @click="copyAllCodes">复制全部</el-button>
        <el-button type="primary" @click="resultDialogVisible = false">完成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Key, Delete, Search, RefreshLeft, CopyDocument, MagicStick } from '@element-plus/icons-vue'
import { activationCodeApi } from '../api'
import { useUserStore } from '../stores/user'

const user = useUserStore()
const canManage = user.hasPerm('admin.manage')

// ---- 列表数据 ----
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const statusFilter = ref('')
const selection = ref([])
const ids = computed(() => selection.value.map((r) => r._id))

function onSelection(rows) {
  selection.value = rows
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (statusFilter.value) params.status = statusFilter.value
    const data = await activationCodeApi.list(params)
    list.value = data.list || []
    total.value = data.total || 0
    updateStats(data.list || [])
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function reset() {
  keyword.value = ''
  statusFilter.value = ''
  page.value = 1
  load()
}

// ---- 统计（基于当前页估算，加载时更新）----
const stats = ref({ total: 0, active: 0, used: 0, disabled: 0 })

async function updateStats(currentList) {
  // 加载全部统计（单独请求一次不分页）
  try {
    const allData = await activationCodeApi.list({ page: 1, page_size: 1 })
    stats.value.total = allData.total || 0
  } catch (e) {
    // ignore
  }
  // 从当前页数据估算状态分布
  const s = { total: stats.value.total, active: 0, used: 0, disabled: 0 }
  for (const row of currentList) {
    if (row.status === 'active') s.active++
    else if (row.status === 'used') s.used++
    else if (row.status === 'disabled') s.disabled++
  }
  stats.value = s
}

// ---- 状态标签 ----
function statusTagType(status) {
  if (status === 'active') return 'success'
  if (status === 'used') return 'info'
  if (status === 'disabled') return 'danger'
  return 'info'
}

function statusLabel(status) {
  if (status === 'active') return '可用'
  if (status === 'used') return '已使用'
  if (status === 'disabled') return '已停用'
  return status || '未知'
}

function isExpired(expireAt) {
  if (!expireAt) return false
  return new Date(expireAt) < new Date()
}

function shortOpenid(openid) {
  if (!openid) return '—'
  return openid.length > 12 ? openid.slice(-8) : openid
}

// ---- 复制 ----
async function copyCode(code) {
  try {
    await navigator.clipboard.writeText(code)
    ElMessage.success(`已复制：${code}`)
  } catch (e) {
    ElMessage.warning('复制失败，请手动选择')
  }
}

async function copyAllCodes() {
  const text = generatedCodes.value.map((c) => c.code).join('\n')
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(`已复制 ${generatedCodes.value.length} 个激活码`)
  } catch (e) {
    ElMessage.warning('复制失败')
  }
}

// ---- 启用/停用 ----
async function toggleDisable(row) {
  await ElMessageBox.confirm(`确定停用激活码 ${row.code} 吗？停用后将无法被使用。`, '停用确认', {
    type: 'warning',
    confirmButtonText: '停用',
    cancelButtonText: '取消',
  })
  await activationCodeApi.update(row._id, { status: 'disabled' })
  ElMessage.success('已停用')
  load()
}

async function toggleEnable(row) {
  await activationCodeApi.update(row._id, { status: 'active' })
  ElMessage.success('已启用')
  load()
}

// ---- 删除 ----
async function remove(id, tip) {
  await ElMessageBox.confirm(`确定删除${tip}吗？删除后不可恢复。`, '删除确认', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
  await activationCodeApi.remove(id)
  ElMessage.success('已删除')
  load()
}

async function bulkRemove(ids) {
  if (!ids.length) {
    ElMessage.warning('请先选择记录')
    return
  }
  await ElMessageBox.confirm(`确定删除选中的 ${ids.length} 条激活码吗？`, '批量删除', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
  const data = await activationCodeApi.bulkDelete(ids)
  ElMessage.success(`已删除 ${data.deleted} 条`)
  load()
}

// ---- 生成 ----
const genDialogVisible = ref(false)
const generating = ref(false)
const genForm = ref({
  count: 10,
  vipDuration: 30,
  expireAt: '',
  note: '',
})

const resultDialogVisible = ref(false)
const generatedCodes = ref([])

function openGenerate() {
  genForm.value = { count: 10, vipDuration: 30, expireAt: '', note: '' }
  genDialogVisible.value = true
}

function disabledPastDate(date) {
  return date.getTime() < Date.now() - 86400000
}

async function doGenerate() {
  if (genForm.value.count < 1) {
    ElMessage.warning('生成数量至少为 1')
    return
  }
  generating.value = true
  try {
    const data = await activationCodeApi.generate({
      count: genForm.value.count,
      vipDuration: genForm.value.vipDuration,
      expireAt: genForm.value.expireAt || '',
      note: genForm.value.note || '',
    })
    generatedCodes.value = data.codes || []
    genDialogVisible.value = false
    resultDialogVisible.value = true
    load()
  } catch (e) {
    ElMessage.error('生成失败：' + (e.message || '未知错误'))
  } finally {
    generating.value = false
  }
}

onMounted(() => {
  load()
})
</script>

<style scoped>
.stats-row {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}
.stat-card {
  flex: 1;
  padding: 16px 20px;
  border-radius: 10px;
  text-align: center;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
}
.stat-label {
  font-size: 13px;
  color: #999;
  margin-top: 4px;
}
.stat-total { background: #f0f5ff; }
.stat-total .stat-value { color: #409eff; }
.stat-active { background: #f0f9eb; }
.stat-active .stat-value { color: #67c23a; }
.stat-used { background: #f4f4f5; }
.stat-used .stat-value { color: #909399; }
.stat-disabled { background: #fef0f0; }
.stat-disabled .stat-value { color: #f56c6c; }

.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.pager {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

.code-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.code-text {
  font-family: 'Courier New', monospace;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 2px;
  color: #333;
}
.copy-icon {
  color: #409eff;
  cursor: pointer;
  font-size: 14px;
}

.text-muted { color: #c0c0c0; }
.text-warning { color: #e6a23c; }

.form-hint {
  margin-left: 10px;
  color: #999;
  font-size: 13px;
}

.generated-codes {
  max-height: 360px;
  overflow-y: auto;
}
.generated-code-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background 0.2s;
}
.generated-code-row:hover {
  background: #f5f7fa;
}
.generated-code-row .code-meta {
  font-size: 12px;
  color: #999;
}
</style>
