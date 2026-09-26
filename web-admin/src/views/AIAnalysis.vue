<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><DataLine /></el-icon></span>
        AI 题目解析
      </div>
      <div>
        <el-button type="primary" plain :disabled="!selection.length" :loading="batchLoading" @click="startBatchAnalyze">
          <el-icon><MagicStick /></el-icon>批量 AI 解析（{{ selection.length }}）
        </el-button>
      </div>
    </div>

    <div class="card-block">
      <!-- 工具栏 -->
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索题干" clearable @keyup.enter="search" @clear="search" />
        <el-input v-model="filters.examid" placeholder="科目编号" clearable style="width: 160px" @keyup.enter="search" @clear="search" />
        <el-select v-model="filters.qtype" placeholder="题型" clearable style="width: 120px" @change="search">
          <el-option label="单选题" value="single" />
          <el-option label="多选题" value="multiple" />
          <el-option label="判断题" value="judge" />
          <el-option label="填空题" value="fill" />
          <el-option label="问答题" value="qa" />
          <el-option label="一题多问" value="multi_part" />
        </el-select>
        <el-select v-model="filterAnalysis" placeholder="解析状态" clearable style="width: 120px" @change="search">
          <el-option label="已解析" value="analyzed" />
          <el-option label="未解析" value="pending" />
        </el-select>
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="filteredList" size="default" border stripe @selection-change="(rows) => (selection = rows)">
        <el-table-column type="selection" width="46" />
        <el-table-column prop="_id" label="ID" width="80" />
        <el-table-column label="题型" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="qtypeTag(row.qtype || row.typecode)">{{ row.typename || qtypeLabel(row.qtype) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="题干" min-width="280" show-overflow-tooltip>
          <template #default="{ row }">{{ row.title || row.content_md?.slice(0, 60) || '-' }}</template>
        </el-table-column>
        <el-table-column prop="examid" label="科目" width="100" />
        <el-table-column label="解析状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="hasAnalysis(row)" type="success" size="small">已解析</el-tag>
            <el-tag v-else type="info" size="small">未解析</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :loading="analyzingId === row._id" @click="analyzeOne(row)">AI 解析</el-button>
            <el-button v-if="hasAnalysis(row)" link type="success" @click="showResult(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next, jumper" background @current-change="load" @size-change="load" />
      </div>
    </div>

    <!-- 批量解析进度 -->
    <el-dialog v-model="batchDialogVisible" title="批量 AI 解析" width="500px" :close-on-click-modal="false" :close-on-press-escape="!batchLoading">
      <div class="batch-progress">
        <el-progress :percentage="batchPercent" :status="batchStatus" :stroke-width="20" :text-inside="true" />
        <div class="batch-status-text">{{ batchStatusText }}</div>
        <div v-if="batchResult" class="batch-result">
          <el-alert v-if="batchResult.success_count" type="success" :title="`成功解析 ${batchResult.success_count} 题`" :closable="false" style="margin-bottom: 8px" />
          <el-alert v-if="batchResult.fail_count" type="warning" :title="`失败 ${batchResult.fail_count} 题`" :closable="false" style="margin-bottom: 8px" />
        </div>
      </div>
      <template #footer>
        <el-button v-if="!batchLoading" type="primary" @click="batchDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 解析结果弹窗 -->
    <el-dialog v-model="resultDialogVisible" title="AI 解析结果" width="760px" top="4vh" :close-on-click-modal="false">
      <div v-loading="resultLoading" class="analysis-result">
        <template v-if="analysisResult">
          <!-- 题型与难度概览卡片 -->
          <div class="overview-card">
            <div class="overview-item">
              <span class="overview-label">题型</span>
              <el-tag :type="qtypeTag(analysisResult.qtype_detected || analysisResult.qtype || currentRow?.qtype)" size="small">
                {{ qtypeLabel(analysisResult.qtype_detected || analysisResult.qtype || currentRow?.qtype) }}
              </el-tag>
            </div>
            <div class="overview-divider"></div>
            <div class="overview-item">
              <span class="overview-label">难度</span>
              <el-tag :type="difficultyTag(analysisResult.difficulty)" size="small">
                {{ difficultyLabel(analysisResult.difficulty) }}
              </el-tag>
            </div>
            <div v-if="analysisResult.difficulty_score" class="overview-divider"></div>
            <div v-if="analysisResult.difficulty_score" class="overview-item">
              <span class="overview-label">难度分值</span>
              <span class="overview-value">{{ analysisResult.difficulty_score }} / 10</span>
            </div>
          </div>

          <!-- 知识点 + 题型难度关联区 -->
          <div v-if="kpItems.length" class="result-section">
            <div class="block-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px;"><Connection /></el-icon>
              知识点关联
              <span class="block-subtitle">题型 {{ qtypeLabel(analysisResult.qtype_detected || analysisResult.qtype || currentRow?.qtype) }} · 难度 {{ difficultyLabel(analysisResult.difficulty) }}</span>
            </div>
            <div class="kp-grid">
              <div v-for="(kp, i) in kpItems" :key="i" class="kp-card">
                <div class="kp-name">{{ kp.name || kp }}</div>
                <span v-if="kp.confidence != null" class="kp-confidence-value">{{ (kp.confidence * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>

          <!-- 推荐标签 -->
          <div v-if="analysisResult.recommended_tags?.length || analysisResult.suggested_tags?.length" class="result-section">
            <div class="block-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px;"><PriceTag /></el-icon>
              推荐标签
            </div>
            <div class="tag-list">
              <el-tag
                v-for="(tag, i) in (analysisResult.suggested_tags || analysisResult.recommended_tags || [])"
                :key="i"
                type="warning"
                size="small"
                effect="plain"
                style="margin: 2px"
              >{{ typeof tag === 'object' ? (tag.name || '-') : tag }}</el-tag>
            </div>
          </div>

          <!-- 核心概念 -->
          <div v-if="analysisResult.core_concepts?.length || analysisResult.key_concepts?.length" class="result-section">
            <div class="block-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px;"><Key /></el-icon>
              核心概念
            </div>
            <div class="concept-chips">
              <span v-for="(c, i) in (analysisResult.key_concepts || analysisResult.core_concepts || [])" :key="i" class="concept-chip">{{ c }}</span>
            </div>
          </div>

          <!-- 常见错误 -->
          <div v-if="analysisResult.common_mistakes?.length" class="result-section">
            <div class="block-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px; color: #E24B4A;"><WarningFilled /></el-icon>
              常见错误
              <span class="block-subtitle">{{ analysisResult.common_mistakes.length }} 项</span>
            </div>
            <div class="mistake-list">
              <div v-for="(m, i) in analysisResult.common_mistakes" :key="i" class="mistake-item">
                <div class="mistake-index">{{ i + 1 }}</div>
                <div class="mistake-content">{{ typeof m === 'object' ? (m.description || m.mistake || m.text || JSON.stringify(m)) : m }}</div>
              </div>
            </div>
          </div>

          <!-- 答案解析 -->
          <div v-if="analysisResult.answer_analysis || analysisResult.answer_analysis_md || analysisResult.analysis_md" class="result-section">
            <div class="block-title">
              <el-icon style="vertical-align: -2px; margin-right: 4px;"><Document /></el-icon>
              答案解析
            </div>
            <MarkdownRenderer :content="analysisResult.answer_analysis || analysisResult.answer_analysis_md || analysisResult.analysis_md" />
          </div>

          <!-- 元数据 -->
          <div v-if="analysisResult.model || analysisResult.analyzed_at" class="result-meta">
            <span v-if="analysisResult.model">模型: {{ analysisResult.model }}</span>
            <span v-if="analysisResult.analyzed_at">解析时间: {{ formatTime(analysisResult.analyzed_at) }}</span>
          </div>
        </template>
        <el-empty v-else description="暂无解析结果" />
      </div>
      <template #footer>
        <el-button @click="resultDialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="resultLoading" @click="reanalyze">重新解析</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { DataLine, MagicStick, Connection, PriceTag, Key, WarningFilled, Document } from '@element-plus/icons-vue'
import { resource, aiApi } from '../api'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'

const questionApi = resource('questions')

// ---- 列表数据 ----
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const filters = ref({ examid: '', qtype: '' })
const filterAnalysis = ref('')
const selection = ref([])

const qtypeLabels = { single: '单选题', multiple: '多选题', judge: '判断题', fill: '填空题', qa: '问答题', multi_part: '一题多问' }
const qtypeTagTypes = { single: 'primary', multiple: 'success', judge: 'warning', fill: 'info', qa: 'danger', multi_part: '' }

function qtypeLabel(q) {
  return qtypeLabels[q] || q || '-'
}
function qtypeTag(q) {
  return qtypeTagTypes[q] || 'info'
}

/** 判断题目是否已有 AI 解析缓存（兼容 answer_analysis_md / answer_analysis 两种字段名） */
function hasAnalysis(row) {
  return !!(row.ai_analysis && (row.ai_analysis.knowledge_points?.length || row.ai_analysis.answer_analysis_md || row.ai_analysis.answer_analysis || row.ai_analysis.difficulty))
}

/** 前端过滤解析状态（后端列表可能不直接支持该筛选参数） */
const filteredList = computed(() => {
  if (!filterAnalysis.value) return list.value
  return list.value.filter((row) => {
    const analyzed = hasAnalysis(row)
    return filterAnalysis.value === 'analyzed' ? analyzed : !analyzed
  })
})

function buildParams() {
  const params = {
    page: page.value,
    page_size: pageSize.value,
    ...filters.value,
  }
  if (keyword.value) params.keyword = keyword.value
  Object.keys(params).forEach((k) => {
    if (params[k] === '' || params[k] === null || params[k] === undefined) delete params[k]
  })
  return params
}

async function load() {
  loading.value = true
  try {
    const data = await questionApi.list(buildParams())
    list.value = data.list || []
    total.value = data.total || 0
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
  keyword.value = ''
  filters.value = { examid: '', qtype: '' }
  filterAnalysis.value = ''
  page.value = 1
  load()
}

// ---- 单题解析 ----
const analyzingId = ref('')
const resultDialogVisible = ref(false)
const resultLoading = ref(false)
const analysisResult = ref(null)
const currentRow = ref(null)

async function analyzeOne(row) {
  analyzingId.value = row._id
  try {
    const res = await aiApi.analyzeQuestion(row._id)
    if (res) {
      analysisResult.value = res.analysis || res.ai_analysis || res
      currentRow.value = row
      resultDialogVisible.value = true
      ElMessage.success('AI 解析完成')
      // 更新行内缓存状态
      row.ai_analysis = res.analysis || res.ai_analysis || res
      await load()
    }
  } catch (e) {
    // handled by interceptor
  } finally {
    analyzingId.value = ''
  }
}

function showResult(row) {
  currentRow.value = row
  analysisResult.value = row.ai_analysis || null
  resultDialogVisible.value = true
}

async function reanalyze() {
  if (!currentRow.value) return
  resultLoading.value = true
  try {
    const res = await aiApi.analyzeQuestion(currentRow.value._id)
    if (res) {
      analysisResult.value = res.analysis || res.ai_analysis || res
      currentRow.value.ai_analysis = analysisResult.value
      ElMessage.success('重新解析完成')
    }
  } catch (e) {
    // handled by interceptor
  } finally {
    resultLoading.value = false
  }
}

// ---- 批量解析 ----
const batchLoading = ref(false)
const batchDialogVisible = ref(false)
const batchPercent = ref(0)
const batchStatusText = ref('')
const batchStatus = ref('')
const batchResult = ref(null)
let batchTimer = null

async function startBatchAnalyze() {
  if (!selection.value.length) {
    ElMessage.warning('请先选择要解析的题目')
    return
  }
  const ids = selection.value.map((r) => r._id)
  batchLoading.value = true
  batchDialogVisible.value = true
  batchPercent.value = 0
  batchStatus.value = ''
  batchStatusText.value = '正在提交批量解析任务...'
  batchResult.value = null
  try {
    const res = await aiApi.analyzeBatch(ids)
    const jobId = res?.job_id || res?.jobId
    if (!jobId) {
      ElMessage.warning('未返回任务 ID')
      batchLoading.value = false
      return
    }
    batchStatusText.value = `任务已提交（ID: ${jobId}），正在解析...`
    pollBatchJob(jobId)
  } catch (e) {
    batchLoading.value = false
    batchStatus.value = 'exception'
    batchStatusText.value = '批量解析提交失败'
  }
}

function pollBatchJob(jobId) {
  let count = 0
  const maxCount = 150 // 5 分钟超时
  batchTimer = setInterval(async () => {
    count++
    if (count > maxCount) {
      clearBatchTimer()
      batchLoading.value = false
      batchStatus.value = 'exception'
      batchStatusText.value = '解析超时，请稍后查看任务列表'
      return
    }
    try {
      const res = await aiApi.jobStatus(jobId)
      const status = res?.status || res?.state || ''
      const progress = res?.progress || 0
      batchPercent.value = Math.min(progress, 99)
      batchStatusText.value = res?.message || statusText(status)
      if (status === 'completed' || status === 'success' || status === 'done') {
        clearBatchTimer()
        batchPercent.value = 100
        batchStatus.value = 'success'
        batchStatusText.value = '批量解析完成'
        batchResult.value = {
          success_count: res?.success_count ?? res?.total ?? selection.value.length,
          fail_count: res?.fail_count ?? 0,
        }
        batchLoading.value = false
        ElMessage.success('批量 AI 解析完成')
        await load()
      } else if (status === 'failed' || status === 'cancelled' || status === 'canceled') {
        clearBatchTimer()
        batchStatus.value = 'exception'
        batchStatusText.value = `任务${status === 'failed' ? '失败' : '已取消'}`
        batchResult.value = { success_count: 0, fail_count: res?.fail_count ?? selection.value.length }
        batchLoading.value = false
      }
    } catch (e) {
      // 单次查询失败不中断轮询
    }
  }, 2000)
}

function statusText(status) {
  const map = { pending: '排队中...', running: '正在解析...', processing: '正在解析...' }
  return map[status] || status || '处理中...'
}

function clearBatchTimer() {
  if (batchTimer) {
    clearInterval(batchTimer)
    batchTimer = null
  }
}

// ---- 难度标签 ----
function difficultyLabel(d) {
  const map = { easy: '简单', medium: '中等', hard: '困难', 1: '简单', 2: '中等', 3: '困难' }
  return map[d] || d || '-'
}
function difficultyTag(d) {
  const map = { easy: 'success', medium: 'warning', hard: 'danger', 1: 'success', 2: 'warning', 3: 'danger' }
  return map[d] || 'info'
}

// ---- 知识点结构化 ----
/** 将 knowledge_points 统一规整为 [{name, confidence}] 形态 */
const kpItems = computed(() => {
  if (!analysisResult.value) return []
  const kps = analysisResult.value.knowledge_points || []
  return kps.map((kp) => {
    if (typeof kp === 'string') return { name: kp, confidence: null }
    if (typeof kp === 'object' && kp) return { name: kp.name || kp.knowledge_point || '-', confidence: kp.confidence ?? null }
    return { name: String(kp), confidence: null }
  })
})

/** 格式化时间 */
function formatTime(ts) {
  if (!ts) return '-'
  try {
    const d = new Date(ts)
    return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return ts
  }
}

onMounted(() => {
  load()
})

onBeforeUnmount(() => {
  clearBatchTimer()
})
</script>

<style scoped>
.pager {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.batch-progress {
  text-align: center;
  padding: 20px 0;
}

.batch-status-text {
  margin-top: 12px;
  font-size: 14px;
  color: #606266;
}

.batch-result {
  margin-top: 16px;
  text-align: left;
}

.analysis-result {
  max-height: 65vh;
  overflow-y: auto;
}

/* 概览卡片 */
.overview-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 4px;
}

.overview-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.overview-label {
  font-size: 13px;
  color: #909399;
  white-space: nowrap;
}

.overview-value {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.overview-divider {
  width: 1px;
  height: 20px;
  background: #dcdfe6;
}

/* 结果分区 */
.result-section {
  margin-top: 16px;
}

.block-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
  color: #303133;
  display: flex;
  align-items: center;
}

.block-subtitle {
  font-size: 12px;
  font-weight: 400;
  color: #909399;
  margin-left: 8px;
}

/* 知识点网格 */
.kp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px;
}

.kp-card {
  padding: 10px 14px;
  background: #f0f5ff;
  border: 1px solid #d6e4ff;
  border-radius: 8px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.kp-name {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  flex: 1;
  min-width: 0;
  word-break: break-word;
  line-height: 1.6;
}

.kp-confidence-value {
  font-size: 11px;
  font-weight: 400;
  color: #c0c4cc;
  flex-shrink: 0;
  white-space: nowrap;
  line-height: 1.6;
}

/* 标签列表 */
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* 核心概念 chips */
.concept-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.concept-chip {
  display: inline-block;
  padding: 4px 12px;
  font-size: 13px;
  color: #606266;
  background: #f4f4f5;
  border-radius: 12px;
  line-height: 1.6;
}

/* 常见错误列表 */
.mistake-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mistake-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  background: #fef0f0;
  border-left: 3px solid #f56c6c;
  border-radius: 0 6px 6px 0;
}

.mistake-index {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #f56c6c;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.mistake-content {
  font-size: 13px;
  color: #606266;
  line-height: 1.7;
  flex: 1;
}

/* 元数据 */
.result-meta {
  margin-top: 20px;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #c0c4cc;
}

/* 兼容旧样式 */
.concept-list {
  padding-left: 20px;
  margin: 6px 0;
  line-height: 1.8;
  font-size: 14px;
  color: #606266;
}
</style>
