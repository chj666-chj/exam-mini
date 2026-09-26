<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">标签管理</div>
      <div>
        <el-button v-if="canManage" type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>新建标签
        </el-button>
      </div>
    </div>

    <div class="card-block">
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索标签名称" clearable @keyup.enter="search" @clear="search" style="width: 200px" />
        <el-select v-model="filterCategory" placeholder="全部分类" clearable @change="search" style="width: 140px">
          <el-option label="知识点" value="knowledge" />
          <el-option label="难度" value="difficulty" />
          <el-option label="题型" value="qtype" />
          <el-option label="使用场景" value="scene" />
        </el-select>
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="list" size="default" border stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="标签" min-width="160">
          <template #default="{ row }">
            <el-tag :color="row.color || '#909399'" effect="dark" size="small" style="border: none">
              {{ row.name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="120">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="categoryType(row.category)">{{ categoryLabel(row.category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="color" label="颜色" width="80">
          <template #default="{ row }">
            <span class="color-dot" :style="{ background: row.color || '#909399' }"></span>
          </template>
        </el-table-column>
        <el-table-column label="关联题目" width="110" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="showStats(row)">
              <span class="usage-num">{{ row.usage_count || 0 }}</span>
            </el-button>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="showStats(row)">统计</el-button>
            <el-button v-if="canManage" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canManage && !row.is_system" link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="load"
          @size-change="load"
        />
      </div>
    </div>

    <!-- 新建/编辑 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? `编辑标签 #${form.id}` : '新建标签'" width="460px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="标签名称" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width: 100%">
            <el-option label="知识点" value="knowledge" />
            <el-option label="难度" value="difficulty" />
            <el-option label="题型" value="qtype" />
            <el-option label="使用场景" value="scene" />
          </el-select>
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="form.color" />
          <span class="color-hint">用于标签可视化区分</span>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取 消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保 存</el-button>
      </template>
    </el-dialog>

    <!-- 标签使用统计 -->
    <el-dialog v-model="statsVisible" :title="`标签统计 - ${statsData?.tag_name || ''}`" width="720px" top="6vh">
      <div v-loading="statsLoading" class="stats-body">
        <template v-if="statsData">
          <!-- 概览 -->
          <div class="stats-overview">
            <div class="stats-overview-item">
              <span class="stats-overview-label">关联题目总数</span>
              <span class="stats-overview-value">{{ statsData.total_count }}</span>
            </div>
            <div class="stats-overview-divider"></div>
            <div class="stats-overview-item">
              <span class="stats-overview-label">分类</span>
              <el-tag size="small" effect="plain" :type="categoryType(statsData.tag_category)">
                {{ categoryLabel(statsData.tag_category) }}
              </el-tag>
            </div>
          </div>

          <!-- 按学科分布 -->
          <div v-if="Object.keys(statsData.by_subject || {}).length" class="stats-section">
            <div class="stats-section-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px;"><Reading /></el-icon>
              按学科分布
            </div>
            <div class="stats-bar-list">
              <div v-for="(count, subject) in statsData.by_subject" :key="subject" class="stats-bar-item">
                <span class="stats-bar-label">{{ subject }}</span>
                <div class="stats-bar-track">
                  <div class="stats-bar-fill" :style="{ width: barWidth(count, statsData.total_count) }"></div>
                </div>
                <span class="stats-bar-count">{{ count }}</span>
              </div>
            </div>
          </div>

          <!-- 按科目编号分布 -->
          <div v-if="Object.keys(statsData.by_examid || {}).length" class="stats-section">
            <div class="stats-section-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px;"><Collection /></el-icon>
              按科目编号分布
            </div>
            <div class="stats-bar-list">
              <div v-for="(count, examid) in statsData.by_examid" :key="examid" class="stats-bar-item">
                <span class="stats-bar-label">{{ examid }}</span>
                <div class="stats-bar-track">
                  <div class="stats-bar-fill stats-bar-fill-blue" :style="{ width: barWidth(count, statsData.total_count) }"></div>
                </div>
                <span class="stats-bar-count">{{ count }}</span>
              </div>
            </div>
          </div>

          <!-- 按题型分布 -->
          <div v-if="Object.keys(statsData.by_qtype || {}).length" class="stats-section">
            <div class="stats-section-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px;"><Tickets /></el-icon>
              按题型分布
            </div>
            <div class="tag-cloud">
              <el-tag v-for="(count, qtype) in statsData.by_qtype" :key="qtype" :type="qtypeTagType(qtype)" size="small" effect="plain" style="margin: 4px">
                {{ qtypeLabel(qtype) }} <span class="tag-cloud-count">{{ count }}</span>
              </el-tag>
            </div>
          </div>

          <!-- 按难度分布 -->
          <div v-if="Object.keys(statsData.by_difficulty || {}).length" class="stats-section">
            <div class="stats-section-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px;"><Histogram /></el-icon>
              按难度分布
            </div>
            <div class="tag-cloud">
              <el-tag v-for="(count, diff) in statsData.by_difficulty" :key="diff" :type="difficultyTagType(diff)" size="small" effect="plain" style="margin: 4px">
                {{ difficultyLabel(diff) }} <span class="tag-cloud-count">{{ count }}</span>
              </el-tag>
            </div>
          </div>

          <!-- 最近关联题目 -->
          <div v-if="statsData.recent_questions?.length" class="stats-section">
            <div class="stats-section-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px;"><Clock /></el-icon>
              最近关联题目（{{ statsData.recent_questions.length }} 条）
            </div>
            <el-table :data="statsData.recent_questions" size="small" border max-height="200">
              <el-table-column prop="question_id" label="题目ID" width="100" />
              <el-table-column prop="title" label="题干" min-width="240" show-overflow-tooltip />
              <el-table-column prop="examid" label="科目" width="90" />
              <el-table-column label="题型" width="80">
                <template #default="{ row }">{{ qtypeLabel(row.qtype) }}</template>
              </el-table-column>
            </el-table>
          </div>

          <el-empty v-if="statsData.total_count === 0" description="暂无题目使用此标签" />
        </template>
      </div>
      <template #footer>
        <el-button @click="statsVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Reading, Collection, Tickets, Histogram, Clock } from '@element-plus/icons-vue'
import { tagApi } from '../api'
import { useUserStore } from '../stores/user'

const user = useUserStore()
const canManage = user.hasPerm('tag.manage')

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const filterCategory = ref('')

const dialogVisible = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const form = ref({ id: null, name: '', category: 'knowledge', color: '#409eff', description: '' })

// ---- 统计弹窗 ----
const statsVisible = ref(false)
const statsLoading = ref(false)
const statsData = ref(null)

const categoryLabels = { knowledge: '知识点', difficulty: '难度', qtype: '题型', scene: '使用场景' }
const categoryTypes = { knowledge: 'primary', difficulty: 'warning', qtype: 'success', scene: 'info' }
const qtypeLabels = { single: '单选题', multiple: '多选题', judge: '判断题', fill: '填空题', qa: '问答题', multi_part: '一题多问', unknown: '未知' }
const qtypeTagTypes = { single: 'primary', multiple: 'success', judge: 'warning', fill: 'info', qa: 'danger', multi_part: '', unknown: 'info' }

function categoryLabel(c) { return categoryLabels[c] || c }
function categoryType(c) { return categoryTypes[c] || 'info' }
function qtypeLabel(q) { return qtypeLabels[q] || q || '-' }
function qtypeTagType(q) { return qtypeTagTypes[q] || 'info' }
function difficultyLabel(d) {
  const map = { easy: '简单', medium: '中等', hard: '困难', 1: '简单', 2: '中等', 3: '困难' }
  return map[d] || d || '-'
}
function difficultyTagType(d) {
  const map = { easy: 'success', medium: 'warning', hard: 'danger', 1: 'success', 2: 'warning', 3: 'danger' }
  return map[d] || 'info'
}

/** 进度条宽度计算 */
function barWidth(count, total) {
  if (!total) return '0%'
  return Math.max(2, Math.round(count / total * 100)) + '%'
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (filterCategory.value) params.category = filterCategory.value
    const res = await tagApi.list(params)
    list.value = res?.list || []
    total.value = res?.total || 0
  } catch (e) {
    if (e) ElMessage.error(e.message || '标签列表加载失败')
  } finally {
    loading.value = false
  }
}

function search() { page.value = 1; load() }
function reset() { keyword.value = ''; filterCategory.value = ''; page.value = 1; load() }

function openCreate() {
  isEdit.value = false
  form.value = { id: null, name: '', category: 'knowledge', color: '#409eff', description: '' }
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  form.value = { id: row.id, name: row.name, category: row.category, color: row.color || '#409eff', description: row.description || '' }
  dialogVisible.value = true
}

async function submit() {
  if (!form.value.name.trim()) { ElMessage.warning('请填写标签名称'); return }
  saving.value = true
  try {
    if (isEdit.value) {
      await tagApi.update(form.value.id, { name: form.value.name, category: form.value.category, color: form.value.color, description: form.value.description })
    } else {
      await tagApi.create({ name: form.value.name, category: form.value.category, color: form.value.color, description: form.value.description })
    }
    ElMessage.success(isEdit.value ? '已更新' : '已创建')
    dialogVisible.value = false
    load()
  } catch (e) {
    if (e) ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除标签「${row.name}」？关联题目的绑定将一并解除。`, '提示', { type: 'warning' })
  } catch (e) {
    return
  }
  try {
    await tagApi.remove(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    if (e) ElMessage.error(e.message || '删除失败')
  }
}

/** 查看标签使用统计 */
async function showStats(row) {
  statsVisible.value = true
  statsLoading.value = true
  statsData.value = null
  try {
    const res = await tagApi.stats(row.id)
    statsData.value = res
  } catch (e) {
    if (e) ElMessage.error(e.message || '统计数据加载失败')
  } finally {
    statsLoading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.pager { margin-top: 14px; display: flex; justify-content: flex-end; }
.color-dot { display: inline-block; width: 18px; height: 18px; border-radius: 4px; vertical-align: middle; }
.color-hint { margin-left: 8px; font-size: 12px; color: #909399; }
.usage-num { font-weight: 600; }

/* ---- 统计弹窗 ---- */
.stats-body { max-height: 65vh; overflow-y: auto; }
.stats-overview { display: flex; align-items: center; gap: 16px; padding: 12px 16px; background: #f5f7fa; border-radius: 8px; margin-bottom: 4px; }
.stats-overview-item { display: flex; align-items: center; gap: 8px; }
.stats-overview-label { font-size: 13px; color: #909399; white-space: nowrap; }
.stats-overview-value { font-size: 20px; font-weight: 700; color: #303133; }
.stats-overview-divider { width: 1px; height: 24px; background: #dcdfe6; }
.stats-section { margin-top: 18px; }
.stats-section-title { font-size: 14px; font-weight: 600; margin-bottom: 10px; color: #303133; }
.stats-bar-list { display: flex; flex-direction: column; gap: 8px; }
.stats-bar-item { display: flex; align-items: center; gap: 10px; }
.stats-bar-label { font-size: 13px; color: #606266; min-width: 100px; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stats-bar-track { flex: 1; height: 20px; background: #f0f2f5; border-radius: 10px; overflow: hidden; }
.stats-bar-fill { height: 100%; background: linear-gradient(90deg, #409eff, #66b1ff); border-radius: 10px; transition: width 0.3s ease; }
.stats-bar-fill-blue { background: linear-gradient(90deg, #36cfc9, #5cdbd3); }
.stats-bar-count { font-size: 13px; font-weight: 600; color: #303133; min-width: 30px; text-align: left; }
.tag-cloud { display: flex; flex-wrap: wrap; gap: 4px; }
.tag-cloud-count { font-weight: 600; margin-left: 4px; color: #303133; }
</style>
