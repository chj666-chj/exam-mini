<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><Notebook /></el-icon></span>
        错题笔记
      </div>
      <div>
        <el-button :loading="loading" @click="load"><el-icon><Refresh /></el-icon>刷新</el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row" v-if="stats">
      <div class="stat-card">
        <div class="stat-value">{{ stats.total }}</div>
        <div class="stat-label">错题总数</div>
      </div>
      <div class="stat-card" v-for="(count, status) in stats.by_review_status" :key="status">
        <div class="stat-value" :class="'stat-' + reviewStatusColor(status)">{{ count }}</div>
        <div class="stat-label">{{ reviewStatusLabel(status) }}</div>
      </div>
      <div class="stat-card stat-categories">
        <div class="stat-value">{{ Object.keys(stats.by_category).length }}</div>
        <div class="stat-label">分类数</div>
      </div>
    </div>

    <div class="card-block">
      <!-- 工具栏 -->
      <div class="toolbar">
        <el-input v-model="filters._openid" placeholder="按 OpenID 查询" clearable style="width: 180px"
          @keyup.enter="search" @clear="search" />
        <el-input v-model="filters.ordernum" placeholder="按批次号查询" clearable style="width: 160px"
          @keyup.enter="search" @clear="search" />
        <el-select v-model="filters.reviewStatus" placeholder="复习状态" clearable style="width: 140px" @change="search">
          <el-option v-for="s in reviewStatusOptions" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-input v-model="filters.category" placeholder="按分类查询" clearable style="width: 140px"
          @keyup.enter="search" @clear="search" />
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <!-- 表格 -->
      <el-table v-loading="loading" :data="list" border stripe size="default">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-block">
              <div class="block-title">题目内容</div>
              <div class="note-title">{{ titleOf(row) }}</div>
              <el-table :data="optionsOf(row)" size="small" border>
                <el-table-column prop="code" label="选项" width="80" />
                <el-table-column prop="content" label="内容" />
                <el-table-column label="正确" width="90" align="center">
                  <template #default="{ row: o }">
                    <el-tag :type="String(o.value) === '1' ? 'success' : 'info'" size="small" effect="plain">
                      {{ String(o.value) === '1' ? '正确' : '' }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
              <div v-if="row.note" class="note-content">
                <div class="block-title">用户笔记</div>
                <div class="note-text">{{ row.note }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="_id" label="笔记ID" min-width="180" show-overflow-tooltip />
        <el-table-column prop="ordernum" label="批次号" width="140" />
        <el-table-column label="用户" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row._openid || '-' }}</template>
        </el-table-column>
        <el-table-column label="题目" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ titleOf(row) }}</template>
        </el-table-column>
        <el-table-column label="分类" width="100">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.category || '未分类' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="复习状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="reviewStatusTagType(row.reviewStatus)" size="small">
              {{ reviewStatusLabel(row.reviewStatus) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="错误次数" width="80" align="center">
          <template #default="{ row }">{{ row.errorCount || 1 }}</template>
        </el-table-column>
        <el-table-column v-if="canManage" label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="markReviewed(row)">标记已复习</el-button>
            <el-button link type="danger" @click="remove(row._id, '这条错题记录')">删除</el-button>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Notebook } from '@element-plus/icons-vue'
import { resource } from '../api'
import http from '../api/http'
import { useUserStore } from '../stores/user'

const user = useUserStore()
const canManage = user.hasPerm('note.manage')
const noteApi = resource('notes')

const reviewStatusOptions = [
  { value: 'pending', label: '待复习' },
  { value: 'reviewing', label: '复习中' },
  { value: 'mastered', label: '已掌握' },
  { value: 'difficult', label: '困难' },
]

function reviewStatusLabel(status) {
  const found = reviewStatusOptions.find((s) => s.value === status)
  return found ? found.label : '待复习'
}

function reviewStatusTagType(status) {
  const map = { pending: 'warning', reviewing: 'primary', mastered: 'success', difficult: 'danger' }
  return map[status] || 'warning'
}

function reviewStatusColor(status) {
  const map = { pending: 'warn', reviewing: 'primary', mastered: 'success', difficult: 'danger' }
  return map[status] || 'warn'
}

// ---- 统计 ----
const stats = ref(null)

async function loadStats() {
  try {
    const res = await http.get('/notes/stats/')
    stats.value = res
  } catch (e) {
    // non-critical
  }
}

// ---- 列表 ----
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const filters = ref({ _openid: '', ordernum: '', reviewStatus: '', category: '' })

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    Object.entries(filters.value).forEach(([k, v]) => {
      if (v) params[k] = v
    })
    const res = await noteApi.list(params)
    list.value = res?.list || []
    total.value = res?.total || 0
  } catch (e) {
    // handled by interceptor
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function reset() {
  filters.value = { _openid: '', ordernum: '', reviewStatus: '', category: '' }
  page.value = 1
  load()
}

// ---- 标记已复习 ----
async function markReviewed(row) {
  try {
    await noteApi.update(row._id, { reviewStatus: 'mastered' })
    ElMessage.success('已标记为已掌握')
    load()
    loadStats()
  } catch (e) {
    // handled by interceptor
  }
}

// ---- 删除 ----
async function remove(id, tip) {
  try {
    await ElMessageBox.confirm(`确定删除${tip}吗？删除后不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await noteApi.remove(id)
    ElMessage.success('已删除')
    load()
    loadStats()
  } catch (e) {
    // cancelled or error
  }
}

// ---- 辅助函数 ----
function titleOf(row) {
  const q = row.question
  if (!q) return '-'
  if (typeof q === 'string') {
    try {
      return JSON.parse(q).title
    } catch (e) {
      return q.slice(0, 40)
    }
  }
  return q.title || '-'
}

function optionsOf(row) {
  const q = typeof row.question === 'string' ? safeParse(row.question) : row.question
  return Array.isArray(q?.options) ? q.options : []
}

function safeParse(text) {
  try {
    return JSON.parse(text)
  } catch (e) {
    return null
  }
}

onMounted(() => {
  load()
  loadStats()
})
</script>

<style scoped>
.pager {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

.stats-row {
  display: flex;
  gap: 14px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.stat-card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 16px 20px;
  text-align: center;
  min-width: 110px;
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
}

.stat-label {
  font-size: 12px;
  color: #909399;
  margin-top: 6px;
}

.stat-warn { color: #e6a23c; }
.stat-primary { color: #409eff; }
.stat-success { color: #67c23a; }
.stat-danger { color: #f56c6c; }

.stat-categories {
  max-width: 130px;
}

.expand-block {
  padding: 8px 12px;
}

.block-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

.note-title {
  margin-bottom: 8px;
  line-height: 1.6;
}

.note-content {
  margin-top: 12px;
}

.note-text {
  background: #f5f7fa;
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 13px;
  line-height: 1.8;
  color: #606266;
}
</style>
