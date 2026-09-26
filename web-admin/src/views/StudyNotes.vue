<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><EditPen /></el-icon></span>
        学习笔记
      </div>
      <div>
        <el-button v-if="canManage" type="danger" plain :disabled="!selection.length" @click="bulkRemove">
          <el-icon><Delete /></el-icon>批量删除（{{ selection.length }}）
        </el-button>
        <el-button v-if="canManage" type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>新建笔记
        </el-button>
      </div>
    </div>

    <div class="card-block">
      <!-- 工具栏 -->
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索标题/分类/标签/正文" clearable style="width: 260px"
          @keyup.enter="load" @clear="load">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="filterCategory" placeholder="分类筛选" clearable style="width: 160px" @change="load">
          <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
        </el-select>
        <el-button type="primary" @click="load"><el-icon><Search /></el-icon>查询</el-button>
        <el-button @click="resetFilters"><el-icon><RefreshLeft /></el-icon>重置</el-button>
      </div>

      <!-- 表格 -->
      <el-table v-loading="loading" :data="list" border stripe size="default" @selection-change="onSelection">
        <el-table-column v-if="canManage" type="selection" width="46" />
        <el-table-column prop="_id" label="笔记ID" width="160" show-overflow-tooltip />
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="cell-strong">{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="120">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.category || '未分类' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标签" width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.tags" class="tags-cell">{{ row.tags }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
        <el-table-column prop="_updated_at" label="更新时间" width="160" />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)"><el-icon><View /></el-icon>详情</el-button>
            <el-button v-if="canManage" link type="primary" @click="openEdit(row)"><el-icon><Edit /></el-icon>编辑</el-button>
            <el-button v-if="canManage" link type="danger" @click="removeOne(row)"><el-icon><Delete /></el-icon>删除</el-button>
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

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑笔记' : '新建笔记'" width="680px" :close-on-click-modal="false">
      <el-form :model="form" label-width="80px">
        <el-form-item label="笔记ID" v-if="!isEdit">
          <el-input v-model="form._id" placeholder="如 SN_001（留空自动生成）" />
        </el-form-item>
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="笔记标题" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="form.category" placeholder="如 软件设计师/数据结构" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="form.tags" placeholder="多个标签用逗号分隔，如 重点,必考,易错" />
        </el-form-item>
        <el-form-item label="摘要">
          <el-input v-model="form.summary" type="textarea" :rows="2" placeholder="笔记摘要（可选）" />
        </el-form-item>
        <el-form-item label="正文内容">
          <el-input v-model="form.content" type="textarea" :rows="10"
            placeholder="支持 Markdown 风格：# 标题 / ## 二级 / **高亮** / 普通段落（空行分隔）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取 消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保 存</el-button>
      </template>
    </el-dialog>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="笔记详情" width="680px">
      <template v-if="detailDoc">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="笔记ID">{{ detailDoc._id }}</el-descriptions-item>
          <el-descriptions-item label="分类">
            <el-tag size="small" type="info">{{ detailDoc.category || '未分类' }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="标题" :span="2">{{ detailDoc.title }}</el-descriptions-item>
          <el-descriptions-item label="标签" :span="2" v-if="detailDoc.tags">{{ detailDoc.tags }}</el-descriptions-item>
          <el-descriptions-item label="摘要" :span="2" v-if="detailDoc.summary">{{ detailDoc.summary }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="detailDoc.content" class="detail-content">
          <div class="detail-content-title">正文内容</div>
          <pre class="detail-content-body">{{ detailDoc.content }}</pre>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { EditPen, Plus, Delete, Edit, Search, RefreshLeft, View } from '@element-plus/icons-vue'
import { resource } from '../api'
import { useUserStore } from '../stores/user'

const user = useUserStore()
const canManage = user.hasPerm('studynote.manage')
const snApi = resource('studynotes')

const categoryOptions = ['软件设计师', '信息系统项目管理师', '数据结构', '软件工程', '计算机网络', '其他']

// ---- 列表 ----
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const filterCategory = ref('')
const selection = ref([])

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (filterCategory.value) params.category = filterCategory.value
    const res = await snApi.list(params)
    list.value = res?.list || []
    total.value = res?.total || 0
  } catch (e) {
    // handled by interceptor
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  keyword.value = ''
  filterCategory.value = ''
  page.value = 1
  load()
}

function onSelection(rows) {
  selection.value = rows
}

// ---- 新建/编辑 ----
const dialogVisible = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const form = ref({})

function defaultForm() {
  return {
    _id: '',
    title: '',
    category: '',
    tags: '',
    summary: '',
    content: '',
  }
}

function openCreate() {
  isEdit.value = false
  form.value = defaultForm()
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  form.value = {
    _id: row._id,
    title: row.title || '',
    category: row.category || '',
    tags: row.tags || '',
    summary: row.summary || '',
    content: row.content || '',
  }
  dialogVisible.value = true
}

async function submit() {
  if (!form.value.title || !form.value.title.trim()) {
    ElMessage.warning('请填写笔记标题')
    return
  }
  const payload = { ...form.value }
  if (isEdit.value) delete payload._id
  saving.value = true
  try {
    if (isEdit.value) {
      await snApi.update(form.value._id, payload)
      ElMessage.success('保存成功')
    } else {
      await snApi.create(payload)
      ElMessage.success('新建成功')
    }
    dialogVisible.value = false
    load()
  } catch (e) {
    // handled by interceptor
  } finally {
    saving.value = false
  }
}

// ---- 删除 ----
async function removeOne(row) {
  try {
    await ElMessageBox.confirm(`确定删除笔记「${row.title}」？删除后不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
    await snApi.remove(row._id)
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
    await ElMessageBox.confirm(`确定批量删除选中的 ${ids.length} 篇笔记？`, '批量删除', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
    await snApi.bulkDelete(ids)
    ElMessage.success('批量删除成功')
    selection.value = []
    load()
  } catch (e) {
    // cancelled or error
  }
}

// ---- 详情 ----
const detailVisible = ref(false)
const detailDoc = ref(null)

async function openDetail(row) {
  try {
    const res = await snApi.get(row._id)
    detailDoc.value = res
    detailVisible.value = true
  } catch (e) {
    // handled by interceptor
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

.cell-strong {
  font-weight: 500;
}

.tags-cell {
  font-size: 12px;
  color: #606266;
}

.text-muted {
  color: #c0c4cc;
}

.detail-content {
  margin-top: 20px;
}

.detail-content-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
  padding-left: 8px;
  border-left: 3px solid var(--el-color-primary);
}

.detail-content-body {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 16px;
  font-size: 13px;
  line-height: 1.8;
  color: #606266;
  white-space: pre-wrap;
  word-wrap: break-word;
  max-height: 400px;
  overflow-y: auto;
}
</style>
