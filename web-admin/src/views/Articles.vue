<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><Document /></el-icon></span>
        文章管理
      </div>
      <div>
        <el-button v-if="canManage" type="success" plain :disabled="!selection.length" @click="bulkToKnowledge">
          <el-icon><Collection /></el-icon>批量加入知识库（{{ selection.length }}）
        </el-button>
        <el-button v-if="canManage" type="danger" plain :disabled="!selection.length" @click="bulkRemove">
          <el-icon><Delete /></el-icon>批量删除（{{ selection.length }}）
        </el-button>
        <el-button v-if="canManage" type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>新建文章
        </el-button>
      </div>
    </div>

    <div class="card-block">
      <!-- 工具栏 -->
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索标题/作者/编码" clearable style="width: 240px"
          @keyup.enter="load" @clear="load">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="filterStatus" placeholder="状态筛选" clearable style="width: 140px" @change="load">
          <el-option label="全部" value="" />
          <el-option label="待审核" value="pending" />
          <el-option label="已发布" value="published" />
          <el-option label="已驳回" value="rejected" />
          <el-option label="已下架" value="taken_down" />
        </el-select>
        <el-button type="primary" @click="load"><el-icon><Search /></el-icon>查询</el-button>
        <el-button @click="resetFilters"><el-icon><RefreshLeft /></el-icon>重置</el-button>
      </div>

      <!-- 表格 -->
      <el-table v-loading="loading" :data="list" border stripe size="default" @selection-change="onSelection">
        <el-table-column v-if="canManage" type="selection" width="46" />
        <el-table-column label="标题" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" :underline="false" @click="openEdit(row)">{{ row.title }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="编码" width="185">
          <template #default="{ row }">
            <el-tag v-if="row.code" size="small" type="success" class="code-tag">{{ row.code }}</el-tag>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="知识库" width="92" align="center">
          <template #default="{ row }">
            <el-tag v-if="isIndexed(row)" size="small" type="warning">已索引</el-tag>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="author" label="作者" width="100" show-overflow-tooltip />
        <el-table-column label="标签" width="200">
          <template #default="{ row }">
            <div v-if="row.tags && row.tags.length" class="tags-cell">
              <el-tag v-for="(tag, i) in row.tags.slice(0, 3)" :key="i" size="small" class="tag-item">{{ tag }}</el-tag>
            </div>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="views" label="浏览量" width="90" align="center" />
        <el-table-column prop="createTime" label="创建时间" width="160" />
        <el-table-column label="操作" width="380" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canAudit && canAuditStatus(row.status)" link type="success" @click="auditArticle(row, 'publish')">
              <el-icon><CircleCheck /></el-icon>通过
            </el-button>
            <el-button v-if="canAudit && canAuditStatus(row.status)" link type="danger" @click="rejectArticle(row)">
              <el-icon><CircleClose /></el-icon>驳回
            </el-button>
            <el-button v-if="canAudit && row.status === 'published'" link type="warning" @click="auditArticle(row, 'takedown')">
              <el-icon><Warning /></el-icon>下架
            </el-button>
            <el-button v-if="canManage && isIndexed(row)" link type="warning" @click="removeFromKnowledge(row)">
              <el-icon><Remove /></el-icon>移出知识库
            </el-button>
            <el-button v-else-if="canManage" link type="success" @click="addToKnowledge(row)">
              <el-icon><Collection /></el-icon>加入知识库
            </el-button>
            <el-button v-if="canManage" link type="primary" @click="openEdit(row)">
              <el-icon><Edit /></el-icon>编辑
            </el-button>
            <el-button v-if="canManage" link type="danger" @click="removeOne(row)">
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
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Document, Plus, Delete, Edit, Search, RefreshLeft,
  CircleCheck, CircleClose, Warning, Collection, Remove,
} from '@element-plus/icons-vue'
import { articleApi, aiApi } from '../api'
import { useUserStore } from '../stores/user'

const router = useRouter()
const user = useUserStore()
const canManage = user.hasPerm('article.manage')
const canAudit = user.hasPerm('article.audit')

// ---- 列表 ----
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const filterStatus = ref('')
const selection = ref([])

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (filterStatus.value) params.status = filterStatus.value
    const res = await articleApi.list(params)
    list.value = res?.list || []
    total.value = res?.total || 0
    await loadIndexed()
  } catch (e) {
    // handled by interceptor
  } finally {
    loading.value = false
  }
}

// ---- 知识库索引状态（按文章编码追溯）----
const indexedCodes = ref(new Set())

async function loadIndexed() {
  try {
    const res = await aiApi.kbIndexedArticles()
    indexedCodes.value = new Set((res?.list || []).map((x) => x.article_code))
  } catch (e) {
    indexedCodes.value = new Set()
  }
}

function isIndexed(row) {
  return !!(row.code && indexedCodes.value.has(row.code))
}

async function addToKnowledge(row) {
  try {
    const res = await aiApi.articleToKnowledge(row._id)
    ElMessage.success(`已加入知识库：${res?.article_code || row.code || ''}`)
    await loadIndexed()
  } catch (e) {
    // handled by interceptor
  }
}

async function removeFromKnowledge(row) {
  try {
    await ElMessageBox.confirm(
      `确定将文章「${row.title}」从知识库索引中移出？`,
      '移出知识库',
      { type: 'warning', confirmButtonText: '确定移出', cancelButtonText: '取消' },
    )
    await aiApi.articleFromKnowledge(row._id)
    ElMessage.success('已从知识库索引移出')
    await loadIndexed()
  } catch (e) {
    // cancelled or handled by interceptor
  }
}

async function bulkToKnowledge() {
  const ids = selection.value.map((r) => r._id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(
      `确定将选中的 ${ids.length} 篇文章加入知识库索引？将自动为其生成唯一编码。`,
      '批量加入知识库',
      { type: 'warning', confirmButtonText: '确定加入', cancelButtonText: '取消' },
    )
    const res = await aiApi.articlesToKnowledgeBatch(ids, 'add')
    ElMessage.success(
      `批量加入完成：成功 ${res?.success_count || 0} 篇，失败 ${res?.failed_count || 0} 篇`,
    )
    selection.value = []
    await load()
  } catch (e) {
    // cancelled or handled by interceptor
  }
}

function resetFilters() {
  keyword.value = ''
  filterStatus.value = ''
  page.value = 1
  load()
}

function onSelection(rows) {
  selection.value = rows
}

// ---- 状态映射 ----
function statusType(status) {
  const map = { pending: 'warning', published: 'success', rejected: 'danger', taken_down: 'info' }
  return map[status] || 'info'
}

function statusLabel(status) {
  const map = { pending: '待审核', published: '已发布', rejected: '已驳回', taken_down: '已下架' }
  return map[status] || status
}

function canAuditStatus(status) {
  return status === 'pending' || status === 'rejected' || status === 'taken_down'
}

// ---- 审核操作 ----
async function auditArticle(row, action) {
  const actionLabel = { publish: '通过', reject: '驳回', takedown: '下架' }[action]
  try {
    await ElMessageBox.confirm(`确定${actionLabel}文章「${row.title}」？`, '审核确认', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    await articleApi.audit(row._id, action)
    ElMessage.success(`${actionLabel}成功`)
    load()
  } catch (e) {
    // cancelled or error
  }
}

async function rejectArticle(row) {
  try {
    const { value } = await ElMessageBox.prompt('请输入驳回原因', '驳回文章', {
      confirmButtonText: '确定驳回',
      cancelButtonText: '取消',
      inputPlaceholder: '请输入驳回原因（可选）',
    })
    await articleApi.audit(row._id, 'reject', value || '')
    ElMessage.success('已驳回')
    load()
  } catch (e) {
    // cancelled or error
  }
}

// ---- 新建/编辑 ----
function openCreate() {
  router.push('/articles/create')
}

function openEdit(row) {
  router.push(`/articles/${row._id}/edit`)
}

// ---- 删除 ----
async function removeOne(row) {
  try {
    await ElMessageBox.confirm(`确定删除文章「${row.title}」？删除后不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
    await articleApi.remove(row._id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    // cancelled or error
  }
}

async function bulkRemove() {
  const ids = selection.value.map((r) => r._id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`确定批量删除选中的 ${ids.length} 篇文章？`, '批量删除', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
    await articleApi.bulkDelete(ids)
    ElMessage.success('批量删除成功')
    selection.value = []
    load()
  } catch (e) {
    // cancelled or error
  }
}

load()
</script>

<style scoped>
.pager {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

.tags-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.tag-item {
  margin: 0;
}

.code-tag {
  font-family: Consolas, Monaco, 'Courier New', monospace;
  letter-spacing: 0.2px;
}

.text-muted {
  color: #c0c4cc;
}
</style>
