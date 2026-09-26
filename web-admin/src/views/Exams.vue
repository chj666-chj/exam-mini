<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><Files /></el-icon></span>
        考试管理
      </div>
      <div>
        <el-button v-if="canManage" type="danger" plain :disabled="!selection.length" @click="bulkRemove">
          <el-icon><Delete /></el-icon>批量删除（{{ selection.length }}）
        </el-button>
        <el-button v-if="canManage" type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>新建考试
        </el-button>
      </div>
    </div>

    <div class="card-block">
      <!-- 工具栏 -->
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索考试名称/编码/说明" clearable style="width: 240px"
          @keyup.enter="load" @clear="load">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="filterStatus" placeholder="考试状态" clearable style="width: 140px" @change="load">
          <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-button type="primary" @click="load"><el-icon><Search /></el-icon>查询</el-button>
        <el-button @click="resetFilters"><el-icon><RefreshLeft /></el-icon>重置</el-button>
      </div>

      <!-- 表格 -->
      <el-table v-loading="loading" :data="list" border stripe size="default" @selection-change="onSelection">
        <el-table-column v-if="canManage" type="selection" width="46" />
        <el-table-column prop="_id" label="考试ID" width="120" show-overflow-tooltip />
        <el-table-column prop="name" label="考试名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="cell-strong">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="编码" width="100" />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="时长" width="80" align="center">
          <template #default="{ row }">{{ row.duration ? row.duration + 'min' : '—' }}</template>
        </el-table-column>
        <el-table-column label="总分" width="70" align="center">
          <template #default="{ row }">{{ row.totalScore || '—' }}</template>
        </el-table-column>
        <el-table-column label="及格分" width="80" align="center">
          <template #default="{ row }">{{ row.passScore || '—' }}</template>
        </el-table-column>
        <el-table-column label="题量" width="70" align="center">
          <template #default="{ row }">{{ row.questionCount || '—' }}</template>
        </el-table-column>
        <el-table-column label="评分方式" width="100" align="center">
          <template #default="{ row }">{{ scoringLabel(row.scoringType) }}</template>
        </el-table-column>
        <el-table-column prop="_updated_at" label="更新时间" width="160" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
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
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑考试' : '新建考试'" width="640px" :close-on-click-modal="false">
      <el-form :model="form" label-width="100px">
        <el-form-item label="考试ID" v-if="!isEdit">
          <el-input v-model="form._id" placeholder="如 EXAM_001（留空自动生成）" />
        </el-form-item>
        <el-form-item label="考试名称" required>
          <el-input v-model="form.name" placeholder="如 软件设计师模拟考试" />
        </el-form-item>
        <el-form-item label="考试编码">
          <el-input v-model="form.code" placeholder="如 001" />
        </el-form-item>
        <el-form-item label="考试状态">
          <el-select v-model="form.status" placeholder="选择状态" style="width: 100%">
            <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="考试说明">
          <el-input v-model="form.desc" type="textarea" :rows="2" placeholder="考试简介（可选）" />
        </el-form-item>
        <el-divider content-position="left">考试配置</el-divider>
        <el-form-item label="考试时长">
          <el-input-number v-model="form.duration" :min="0" :max="600" controls-position="right" />
          <span class="form-hint">分钟（0 = 不限时）</span>
        </el-form-item>
        <el-form-item label="题目数量">
          <el-input-number v-model="form.questionCount" :min="0" :max="500" controls-position="right" />
        </el-form-item>
        <el-form-item label="总分">
          <el-input-number v-model="form.totalScore" :min="0" :max="9999" controls-position="right" />
        </el-form-item>
        <el-form-item label="及格分">
          <el-input-number v-model="form.passScore" :min="0" :max="9999" controls-position="right" />
          <span class="form-hint">不超过总分</span>
        </el-form-item>
        <el-form-item label="评分方式">
          <el-select v-model="form.scoringType" placeholder="选择评分方式" style="width: 200px">
            <el-option v-for="s in scoringOptions" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
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
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Files, Plus, Delete, Edit, Search, RefreshLeft } from '@element-plus/icons-vue'
import { resource } from '../api'
import { useUserStore } from '../stores/user'

const user = useUserStore()
const canManage = user.hasPerm('exam.manage')
const examApi = resource('exams')

const statusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'published', label: '已发布' },
  { value: 'archived', label: '已归档' },
]

const scoringOptions = [
  { value: 'auto', label: '自动评分' },
  { value: 'manual', label: '手动评分' },
  { value: 'hybrid', label: '混合评分' },
]

function statusLabel(status) {
  const found = statusOptions.find((s) => s.value === status)
  return found ? found.label : status || '草稿'
}

function statusTagType(status) {
  const map = { draft: 'info', published: 'success', archived: 'warning' }
  return map[status] || 'info'
}

function scoringLabel(type) {
  const found = scoringOptions.find((s) => s.value === type)
  return found ? found.label : type || '—'
}

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
    const res = await examApi.list(params)
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
  filterStatus.value = ''
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
    name: '',
    code: '',
    desc: '',
    status: 'draft',
    duration: 0,
    questionCount: 0,
    totalScore: 100,
    passScore: 60,
    scoringType: 'auto',
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
    name: row.name || '',
    code: row.code || '',
    desc: row.desc || '',
    status: row.status || 'draft',
    // el-input-number 需要数字类型，后端可能返回字符串
    duration: Number(row.duration) || 0,
    questionCount: Number(row.questionCount) || 0,
    totalScore: Number(row.totalScore) || 100,
    passScore: Number(row.passScore) || 60,
    scoringType: row.scoringType || 'auto',
  }
  dialogVisible.value = true
}

async function submit() {
  if (!form.value.name || !form.value.name.trim()) {
    ElMessage.warning('请填写考试名称')
    return
  }
  if (form.value.passScore > form.value.totalScore) {
    ElMessage.warning('及格分不能超过总分')
    return
  }
  const payload = { ...form.value }
  if (isEdit.value) delete payload._id
  saving.value = true
  try {
    if (isEdit.value) {
      await examApi.update(form.value._id, payload)
      ElMessage.success('保存成功')
    } else {
      await examApi.create(payload)
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
    await ElMessageBox.confirm(`确定删除考试「${row.name}」？删除后不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
    await examApi.remove(row._id)
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
    await ElMessageBox.confirm(`确定批量删除选中的 ${ids.length} 场考试？`, '批量删除', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
    await examApi.bulkDelete(ids)
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

.cell-strong {
  font-weight: 500;
}

.form-hint {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}
</style>
