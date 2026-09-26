<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><Histogram /></el-icon></span>
        AI 试卷分析
      </div>
    </div>

    <!-- 考试选择 -->
    <div class="card-block">
      <el-form :inline="true" :model="selectForm">
        <el-form-item label="选择考试">
          <el-select
            v-model="selectForm.examId"
            filterable
            placeholder="请选择已发布的考试"
            style="width: 320px"
            :loading="examLoading"
            @change="onExamChange"
          >
            <el-option
              v-for="exam in publishedExams"
              :key="exam._id"
              :label="exam.name || exam.code || exam._id"
              :value="exam._id"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="default"
            :loading="analyzing"
            :disabled="!selectForm.examId"
            @click="startAnalyze"
          >
            <el-icon><MagicStick /></el-icon>AI 分析
          </el-button>
          <el-button
            v-if="analysisResult"
            type="warning"
            plain
            :loading="analyzing"
            :disabled="!selectForm.examId"
            @click="startAnalyze"
          >
            重新分析
          </el-button>
        </el-form-item>
      </el-form>

      <!-- 缓存标识 -->
      <div v-if="analysisResult" class="cache-badge">
        <el-tag type="success" effect="dark" size="small">
          <el-icon><CircleCheck /></el-icon>&nbsp;已分析
        </el-tag>
        <span v-if="analysisResult.analyzed_at" class="cache-time">
          上次分析时间：{{ formatTime(analysisResult.analyzed_at) }}
        </span>
      </div>

      <!-- 分析进度 -->
      <div v-if="analyzing || analyzePercent > 0" class="analyze-progress">
        <el-progress
          :percentage="analyzePercent"
          :status="analyzeStatus"
          :stroke-width="20"
          :text-inside="true"
        />
        <div class="analyze-progress-text">{{ analyzeStatusText }}</div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!analysisResult && !analyzing" class="card-block">
      <el-empty description="请选择一场考试并点击「AI 分析」按钮开始分析" />
    </div>

    <!-- 分析结果 -->
    <template v-if="analysisResult">
      <!-- 试卷质量评估 -->
      <div class="card-block">
        <el-divider content-position="left">
          <span class="section-title">试卷质量评估</span>
        </el-divider>

        <el-row :gutter="16">
          <!-- 知识点覆盖度 -->
          <el-col :xs="24" :sm="8">
            <el-card shadow="hover" class="metric-card">
              <template #header>知识点覆盖度</template>
              <div class="metric-center">
                <el-progress
                  type="dashboard"
                  :percentage="knowledgeCoveragePercent"
                  :color="coverageColor"
                  :width="120"
                />
                <div class="metric-desc">{{ coverageLevel }}</div>
              </div>
            </el-card>
          </el-col>

          <!-- 难度分布 -->
          <el-col :xs="24" :sm="8">
            <el-card shadow="hover">
              <template #header>难度分布</template>
              <EChart :option="difficultyPieOption" height="260px" />
            </el-card>
          </el-col>

          <!-- 区分度分析 -->
          <el-col :xs="24" :sm="8">
            <el-card shadow="hover">
              <template #header>区分度分析</template>
              <div class="discrimination-stats">
                <div class="discrim-item">
                  <span class="discrim-label">平均区分度</span>
                  <span class="discrim-value" :class="discrimClass(avgDiscrimination)">
                    {{ formatPercent(avgDiscrimination) }}
                  </span>
                </div>
                <div class="discrim-row">
                  <div class="discrim-bar-item">
                    <div class="discrim-bar-label">高区分度</div>
                    <div class="discrim-bar-value good">{{ discriminationHigh }}</div>
                  </div>
                  <div class="discrim-bar-item">
                    <div class="discrim-bar-label">中区分度</div>
                    <div class="discrim-bar-value warn">{{ discriminationMedium }}</div>
                  </div>
                  <div class="discrim-bar-item">
                    <div class="discrim-bar-label">低区分度</div>
                    <div class="discrim-bar-value bad">{{ discriminationLow }}</div>
                  </div>
                </div>
                <div v-if="discriminationAnalysis" class="discrim-text">
                  {{ discriminationAnalysis }}
                </div>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </div>

      <!-- 学生作答分析 -->
      <div class="card-block">
        <el-divider content-position="left">
          <span class="section-title">学生作答分析</span>
        </el-divider>

        <el-row :gutter="16" style="margin-bottom: 16px">
          <!-- 得分分布 -->
          <el-col :xs="24" :sm="12">
            <el-card shadow="hover">
              <template #header>得分分布</template>
              <EChart :option="scoreDistOption" height="280px" />
            </el-card>
          </el-col>

          <!-- 常见错误模式 -->
          <el-col :xs="24" :sm="12">
            <el-card shadow="hover">
              <template #header>常见错误模式</template>
              <div v-if="commonErrors.length" class="error-pattern-list">
                <div v-for="(err, idx) in commonErrors" :key="idx" class="error-pattern-item">
                  <div class="error-pattern-header">
                    <el-tag type="danger" size="small" effect="plain">{{ idx + 1 }}</el-tag>
                    <span class="error-pattern-name">{{ err.pattern || err.type || '未知错误' }}</span>
                    <el-tag v-if="err.frequency != null" type="warning" size="small">
                      出现 {{ err.frequency }} 次
                    </el-tag>
                  </div>
                  <div v-if="err.description" class="error-pattern-desc">{{ err.description }}</div>
                </div>
              </div>
              <el-empty v-else description="暂无常见错误模式数据" :image-size="60" />
            </el-card>
          </el-col>
        </el-row>

        <!-- 改进建议 -->
        <el-card shadow="hover" v-if="improvementSuggestions.length">
          <template #header>改进建议</template>
          <div class="suggestion-list">
            <div v-for="(sug, idx) in improvementSuggestions" :key="idx" class="suggestion-item">
              <el-icon class="suggestion-icon"><Promotion /></el-icon>
              <span class="suggestion-text">{{ typeof sug === 'string' ? sug : (sug.content || sug.text || sug.suggestion || '-') }}</span>
            </div>
          </div>
        </el-card>
      </div>

      <!-- 低质量题目预警 -->
      <div class="card-block" v-if="lowQualityQuestions.length">
        <el-divider content-position="left">
          <span class="section-title">
            低质量题目预警
            <el-tag type="danger" size="small" style="margin-left: 8px">{{ lowQualityQuestions.length }} 题</el-tag>
          </span>
        </el-divider>

        <el-table :data="lowQualityQuestions" size="small" border stripe>
          <el-table-column type="index" label="序号" width="60" align="center" />
          <el-table-column label="题号" width="80" align="center">
            <template #default="{ row }">
              <span class="warning-text">第 {{ row.index != null ? row.index + 1 : '-' }} 题</span>
            </template>
          </el-table-column>
          <el-table-column label="题目摘要" min-width="300" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.title || row.content_md?.slice(0, 80) || row.summary || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="区分度" width="100" align="center">
            <template #default="{ row }">
              <el-tag type="danger" size="small">{{ formatPercent(row.discrimination) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="难度" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="difficultyTagType(row.difficulty)" size="small">
                {{ difficultyLabel(row.difficulty) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="预警原因" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="warning-text">{{ row.reason || '区分度过低，建议优化或替换' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { Histogram, MagicStick, CircleCheck, Promotion } from '@element-plus/icons-vue'
import { resource, aiApi } from '../api'
import EChart from '../components/EChart.vue'

const examApi = resource('exams')

// ---- 考试选择 ----
const selectForm = ref({ examId: '' })
const examList = ref([])
const examLoading = ref(false)

const publishedExams = computed(() => {
  return examList.value.filter((e) => e.status === 'published' || e.status === 1 || e.status === '1')
})

async function loadExams() {
  examLoading.value = true
  try {
    const res = await examApi.list({ page: 1, page_size: 500 })
    examList.value = res?.list || res || []
  } catch (e) {
    // handled by interceptor
  } finally {
    examLoading.value = false
  }
}

// ---- 分析状态 ----
const analyzing = ref(false)
const analyzePercent = ref(0)
const analyzeStatus = ref('')
const analyzeStatusText = ref('')
const analysisResult = ref(null)
let analyzeTimer = null
let currentJobId = ''

// 选中考试后尝试加载已有结果
async function onExamChange(examId) {
  analysisResult.value = null
  analyzePercent.value = 0
  analyzeStatus.value = ''
  analyzeStatusText.value = ''
  if (!examId) return
  try {
    const res = await aiApi.examAnalysisResult(examId)
    if (res && (res.quality || res.student_analysis || res.analyzed_at)) {
      analysisResult.value = res
    }
  } catch (e) {
    // 无缓存结果，静默处理
  }
}

// 触发分析
async function startAnalyze() {
  if (!selectForm.value.examId) {
    ElMessage.warning('请先选择一场考试')
    return
  }
  analyzing.value = true
  analyzePercent.value = 0
  analyzeStatus.value = ''
  analyzeStatusText.value = '正在提交分析任务...'
  analysisResult.value = null
  try {
    const res = await aiApi.examAnalyze(selectForm.value.examId)
    currentJobId = res?.job_id || res?.jobId
    if (!currentJobId) {
      // 如果直接返回了结果（同步模式）
      if (res && (res.quality || res.student_analysis)) {
        analysisResult.value = res
        analyzing.value = false
        analyzePercent.value = 100
        analyzeStatus.value = 'success'
        ElMessage.success('分析完成')
        return
      }
      ElMessage.warning('未返回任务 ID')
      analyzing.value = false
      return
    }
    analyzeStatusText.value = `分析任务已提交（ID: ${currentJobId}），正在处理...`
    pollAnalyzeJob()
  } catch (e) {
    analyzing.value = false
    analyzeStatus.value = 'exception'
    analyzeStatusText.value = '分析任务提交失败'
  }
}

function pollAnalyzeJob() {
  let count = 0
  const maxCount = 150 // 2秒 * 150 = 5分钟超时
  analyzeTimer = setInterval(async () => {
    count++
    if (count > maxCount) {
      clearAnalyzeTimer()
      analyzing.value = false
      analyzeStatus.value = 'exception'
      analyzeStatusText.value = '分析超时，请稍后重试'
      return
    }
    try {
      const res = await aiApi.jobStatus(currentJobId)
      const status = res?.status || res?.state || ''
      const progress = res?.progress || 0
      analyzePercent.value = Math.min(progress, 99)
      analyzeStatusText.value = res?.message || statusMap(status)
      if (status === 'completed' || status === 'success' || status === 'done') {
        clearAnalyzeTimer()
        analyzePercent.value = 100
        analyzeStatus.value = 'success'
        analyzeStatusText.value = '分析完成'
        analyzing.value = false
        ElMessage.success('AI 试卷分析完成')
        // 加载分析结果
        try {
          const result = await aiApi.examAnalysisResult(selectForm.value.examId)
          if (result) {
            analysisResult.value = result
          }
        } catch (e) {
          // 如果获取结果失败，尝试用 job 返回的 result
          if (res?.result) {
            analysisResult.value = res.result
          }
        }
      } else if (status === 'failed' || status === 'cancelled' || status === 'canceled') {
        clearAnalyzeTimer()
        analyzing.value = false
        analyzeStatus.value = 'exception'
        analyzeStatusText.value = `分析${status === 'failed' ? '失败' : '已取消'}：${res?.message || ''}`
      }
    } catch (e) {
      // 单次查询失败不中断轮询
    }
  }, 2000)
}

function statusMap(status) {
  const map = { pending: '排队中...', running: '正在分析...', processing: '正在分析...' }
  return map[status] || status || '处理中...'
}

function clearAnalyzeTimer() {
  if (analyzeTimer) {
    clearInterval(analyzeTimer)
    analyzeTimer = null
  }
}

// ---- 结果数据计算 ----
const quality = computed(() => analysisResult.value?.quality || {})
const studentAnalysis = computed(() => analysisResult.value?.student_analysis || {})

// 知识点覆盖度
const knowledgeCoveragePercent = computed(() => {
  const v = quality.value.knowledge_coverage
  if (v == null) return 0
  const num = typeof v === 'number' ? v : parseFloat(v)
  if (isNaN(num)) return 0
  return Math.round(num <= 1 ? num * 100 : num)
})

const coverageColor = computed(() => {
  const p = knowledgeCoveragePercent.value
  if (p >= 80) return '#67c23a'
  if (p >= 60) return '#e6a23c'
  return '#f56c6c'
})

const coverageLevel = computed(() => {
  const p = knowledgeCoveragePercent.value
  if (p >= 80) return '覆盖度良好'
  if (p >= 60) return '覆盖度一般'
  if (p > 0) return '覆盖度不足'
  return '暂无数据'
})

// 区分度
const avgDiscrimination = computed(() => {
  const d = quality.value.discrimination
  if (d == null) return 0
  if (typeof d === 'number') return d
  if (typeof d === 'object') return d.avg ?? d.average ?? d.mean ?? 0
  return 0
})

const discriminationHigh = computed(() => {
  const d = quality.value.discrimination
  if (typeof d === 'object') return d.high ?? d.good ?? 0
  return 0
})

const discriminationMedium = computed(() => {
  const d = quality.value.discrimination
  if (typeof d === 'object') return d.medium ?? d.moderate ?? 0
  return 0
})

const discriminationLow = computed(() => {
  const d = quality.value.discrimination
  if (typeof d === 'object') return d.low ?? d.poor ?? 0
  return 0
})

const discriminationAnalysis = computed(() => {
  return quality.value.discrimination_analysis || quality.value.discrimination?.analysis || ''
})

// 常见错误
const commonErrors = computed(() => {
  return studentAnalysis.value.common_errors || studentAnalysis.value.error_patterns || []
})

// 改进建议
const improvementSuggestions = computed(() => {
  return studentAnalysis.value.improvement_suggestions || studentAnalysis.value.suggestions || []
})

// 低质量题目
const lowQualityQuestions = computed(() => {
  return analysisResult.value?.low_quality_questions || quality.value.low_quality_questions || []
})

// ---- ECharts 配置 ----
// 难度分布饼图
const difficultyPieOption = computed(() => {
  const dist = quality.value.difficulty_distribution || quality.value.difficulty || {}
  let easy = 0, medium = 0, hard = 0
  if (Array.isArray(dist)) {
    dist.forEach((d, i) => {
      if (i === 0) easy = d
      else if (i === 1) medium = d
      else if (i === 2) hard = d
    })
  } else if (typeof dist === 'object') {
    easy = dist.easy ?? dist.easy_count ?? 0
    medium = dist.medium ?? dist.medium_count ?? 0
    hard = dist.hard ?? dist.hard_count ?? 0
  }
  const data = [
    { name: '简单', value: easy, itemStyle: { color: '#67c23a' } },
    { name: '中等', value: medium, itemStyle: { color: '#e6a23c' } },
    { name: '困难', value: hard, itemStyle: { color: '#f56c6c' } },
  ].filter((d) => d.value > 0)
  if (!data.length) {
    data.push({ name: '暂无数据', value: 1, itemStyle: { color: '#dcdfe6' } })
  }
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c}题 ({d}%)' },
    legend: { bottom: 0, textStyle: { fontSize: 12 } },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '45%'],
      label: { formatter: '{b}\n{c}题', fontSize: 11 },
      data,
    }],
  }
})

// 得分分布柱状图
const scoreDistOption = computed(() => {
  const dist = studentAnalysis.value.score_distribution || {}
  let ranges = [], counts = []
  if (Array.isArray(dist)) {
    ranges = dist.map((d) => d.range || d.label || d.name || '')
    counts = dist.map((d) => d.count ?? d.value ?? 0)
  } else if (dist.ranges && dist.counts) {
    ranges = dist.ranges
    counts = dist.counts
  } else if (dist.labels && dist.values) {
    ranges = dist.labels
    counts = dist.values
  }
  if (!ranges.length) {
    ranges = ['0-59', '60-69', '70-79', '80-89', '90-100']
    counts = [0, 0, 0, 0, 0]
  }
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ranges, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', name: '人数' },
    grid: { left: '8%', right: '5%', bottom: '10%', top: '12%' },
    series: [{
      type: 'bar',
      data: counts.map((v, i) => ({
        value: v,
        itemStyle: {
          color: i < 2 ? '#f56c6c' : i < 4 ? '#e6a23c' : '#67c23a',
        },
      })),
      barWidth: '50%',
      label: { show: true, position: 'top', fontSize: 11 },
    }],
  }
})

// ---- 工具函数 ----
function formatTime(t) {
  if (!t) return '-'
  try {
    const d = new Date(t)
    const pad = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch (e) {
    return String(t)
  }
}

function formatPercent(v) {
  if (v == null) return '-'
  const num = typeof v === 'number' ? v : parseFloat(v)
  if (isNaN(num)) return '-'
  if (num <= 1) return (num * 100).toFixed(1) + '%'
  return num.toFixed(1) + '%'
}

function discrimClass(v) {
  if (v >= 0.4) return 'good'
  if (v >= 0.2) return 'warn'
  return 'bad'
}

function difficultyLabel(d) {
  const map = { easy: '简单', medium: '中等', hard: '困难', 1: '简单', 2: '中等', 3: '困难', 0.3: '简单', 0.6: '中等', 0.9: '困难' }
  return map[d] || d || '-'
}

function difficultyTagType(d) {
  const map = { easy: 'success', medium: 'warning', hard: 'danger', 1: 'success', 2: 'warning', 3: 'danger' }
  return map[d] || 'info'
}

onMounted(() => {
  loadExams()
})

onBeforeUnmount(() => {
  clearAnalyzeTimer()
})
</script>

<style scoped>
.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.cache-badge {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}

.cache-time {
  font-size: 13px;
  color: #909399;
}

.analyze-progress {
  margin-top: 20px;
}

.analyze-progress-text {
  margin-top: 8px;
  font-size: 14px;
  color: #606266;
  text-align: center;
}

.metric-card {
  text-align: center;
}

.metric-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 0;
}

.metric-desc {
  margin-top: 12px;
  font-size: 14px;
  color: #606266;
  font-weight: 500;
}

.discrimination-stats {
  padding: 8px 0;
}

.disc-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.discrim-label {
  font-size: 14px;
  color: #606266;
}

.discrim-value {
  font-size: 20px;
  font-weight: 700;
}

.discrim-value.good {
  color: #67c23a;
}

.discrim-value.warn {
  color: #e6a23c;
}

.discrim-value.bad {
  color: #f56c6c;
}

.discrim-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.discrim-bar-item {
  flex: 1;
  text-align: center;
  background: #f4f6fa;
  border-radius: 8px;
  padding: 12px 8px;
}

.discrim-bar-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.discrim-bar-value {
  font-size: 22px;
  font-weight: 700;
}

.discrim-bar-value.good {
  color: #67c23a;
}

.discrim-bar-value.warn {
  color: #e6a23c;
}

.discrim-bar-value.bad {
  color: #f56c6c;
}

.discrim-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  background: #f4f6fa;
  border-radius: 6px;
  padding: 10px;
}

.error-pattern-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.error-pattern-item {
  background: #fef0f0;
  border-radius: 8px;
  padding: 12px;
  border: 1px solid #fde2e2;
}

.error-pattern-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.error-pattern-name {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  flex: 1;
}

.error-pattern-desc {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  padding-left: 4px;
}

.suggestion-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.suggestion-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  background: #f0f9ff;
  border-radius: 8px;
  padding: 10px 14px;
}

.suggestion-icon {
  color: #409eff;
  font-size: 16px;
  margin-top: 2px;
  flex-shrink: 0;
}

.suggestion-text {
  font-size: 14px;
  color: #303133;
  line-height: 1.6;
}

.warning-text {
  color: #f56c6c;
  font-weight: 500;
}
</style>
