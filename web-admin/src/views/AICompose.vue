<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><Files /></el-icon></span>
        AI 智能组卷
      </div>
    </div>

    <!-- 组卷配置 -->
    <div class="card-block" v-if="step === 'config'">
      <!-- 组卷模式切换 -->
      <el-radio-group v-model="composeMode" style="margin-bottom: 20px" @change="onModeChange">
        <el-radio-button label="smart">
          <el-icon><MagicStick /></el-icon>&nbsp;智能组卷（三阶段定向）
        </el-radio-button>
        <el-radio-button label="classic">
          <el-icon><Files /></el-icon>&nbsp;经典组卷（LLM 选题）
        </el-radio-button>
      </el-radio-group>

      <el-alert
        v-if="composeMode === 'smart'"
        type="info"
        :closable="false"
        style="margin-bottom: 20px"
      >
        智能组卷通过「知识点掌握度分析 → 考试蓝图生成 → 定向题目检索」三阶段完成组卷，
        不遍历全题库，支持数十万题规模。请确保题目已进行 AI 解析以标注知识点。
      </el-alert>

      <el-form :model="form" label-width="100px" style="max-width: 700px">
        <!-- 考试类型（仅智能模式） -->
        <el-form-item v-if="composeMode === 'smart'" label="考试类型">
          <el-select v-model="form.exam_type" placeholder="选择考试类型" style="width: 100%">
            <el-option label="月考（聚焦薄弱知识点，偏难）" value="monthly" />
            <el-option label="期中考试（薄弱+覆盖均衡）" value="midterm" />
            <el-option label="期末考试（全覆盖，偏基础）" value="final" />
            <el-option label="模拟考试（广覆盖，均衡难度）" value="mock" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>

        <el-form-item label="科目">
          <el-select
            v-model="form.subject_id"
            filterable
            placeholder="选择科目"
            style="width: 100%"
            @change="onSubjectChange"
          >
            <el-option v-for="s in subjects" :key="s._id" :label="s.name || s.code" :value="s._id || s.code" />
          </el-select>
        </el-form-item>

        <!-- 知识点索引统计（仅智能模式，选了科目后显示） -->
        <div v-if="composeMode === 'smart' && form.subject_id && kpIndexStats" class="kp-index-card">
          <div class="kp-index-header">
            <span>
              <el-icon><DataAnalysis /></el-icon>
              知识点索引：{{ kpIndexStats.kp_count }} 个知识点，{{ kpIndexStats.total_questions }} 道题目已索引
            </span>
            <el-button size="small" :loading="rebuildingIndex" @click="rebuildIndex">
              重建索引
            </el-button>
          </div>
          <div v-if="kpIndexStats.kp_count > 0" class="kp-tags">
            <el-tag
              v-for="kp in kpIndexStats.knowledge_points?.slice(0, 15)"
              :key="kp.name"
              size="small"
              effect="plain"
              style="margin: 2px"
            >
              {{ kp.name }} ({{ kp.total_questions }})
            </el-tag>
            <span v-if="kpIndexStats.kp_count > 15" class="kp-more">等 {{ kpIndexStats.kp_count }} 个...</span>
          </div>
          <el-alert v-else type="warning" :closable="false" style="margin-top: 8px">
            该科目暂无知识点索引。组卷时会自动构建，或点击「重建索引」手动构建。
          </el-alert>
        </div>

        <el-divider content-position="left">题型分布</el-divider>
        <el-row :gutter="12">
          <el-col :span="8" v-for="qt in qtypeOptions" :key="qt.key">
            <el-form-item :label="qt.label">
              <el-input-number v-model="form.type_dist[qt.key]" :min="0" :max="100" controls-position="right" style="width: 100%" @change="updateTotal" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">难度比例</el-divider>
        <el-form-item label="难度分布">
          <div class="difficulty-row">
            <div class="diff-item">
              <span class="diff-label">简单</span>
              <el-slider v-model="form.difficulty.easy" :min="0" :max="100" :step="5" style="flex: 1; margin: 0 12px" @change="syncDifficulty" />
              <span class="diff-value">{{ form.difficulty.easy }}%</span>
            </div>
            <div class="diff-item">
              <span class="diff-label">中等</span>
              <el-slider v-model="form.difficulty.medium" :min="0" :max="100" :step="5" style="flex: 1; margin: 0 12px" @change="syncDifficulty" />
              <span class="diff-value">{{ form.difficulty.medium }}%</span>
            </div>
            <div class="diff-item">
              <span class="diff-label">困难</span>
              <el-slider v-model="form.difficulty.hard" :min="0" :max="100" :step="5" style="flex: 1; margin: 0 12px" @change="syncDifficulty" />
              <span class="diff-value">{{ form.difficulty.hard }}%</span>
            </div>
          </div>
          <el-alert v-if="diffSum !== 100" type="warning" :closable="false" style="margin-top: 8px">
            难度比例总和应为 100%，当前 {{ diffSum }}%
          </el-alert>
        </el-form-item>

        <el-divider content-position="left">试卷设置</el-divider>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="题目数量">
              <el-input-number v-model="form.question_count" :min="1" :max="500" controls-position="right" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="总分">
              <el-input-number v-model="form.total_score" :min="1" :max="9999" controls-position="right" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="知识点筛选">
          <el-select v-model="form.knowledge_tags" multiple filterable placeholder="选择知识点（可选，留空则自动分析）" style="width: 100%">
            <el-option v-for="t in knowledgeTags" :key="t.id" :label="t.name" :value="t.name" />
          </el-select>
          <div v-if="composeMode === 'smart'" class="form-hint">
            留空时系统将自动分析所有用户的答题数据，智能确定考试重点；手动指定则跳过掌握度分析。
          </div>
        </el-form-item>

        <!-- LLM 蓝图辅助（仅智能模式） -->
        <el-form-item v-if="composeMode === 'smart'" label="LLM辅助">
          <el-switch v-model="form.use_llm_blueprint" />
          <span class="form-hint" style="margin-left: 12px">
            开启后使用 LLM 辅助生成考试蓝图（仅传递统计数据，不传题目，不会超时）
          </span>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" size="large" :loading="submitting" @click="submitCompose" :disabled="diffSum !== 100">
            <el-icon><MagicStick /></el-icon>
            {{ composeMode === 'smart' ? '开始智能组卷' : '开始组卷' }}
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 组卷进度 -->
    <div class="card-block" v-if="step === 'progress'">
      <div class="progress-area">
        <el-progress :percentage="composePercent" :status="composeStatus" :stroke-width="24" :text-inside="true" />
        <div class="progress-text">{{ composeStatusText }}</div>
        <el-button v-if="!composing" @click="resetToConfig">返回重新配置</el-button>
      </div>
    </div>

    <!-- 组卷结果 -->
    <div class="card-block" v-if="step === 'result' && composeResult">
      <!-- 掌握度分析摘要（仅智能组卷） -->
      <el-card v-if="composeResult.mastery_summary" shadow="hover" style="margin-bottom: 20px">
        <template #header>
          <span><el-icon><DataAnalysis /></el-icon>&nbsp;知识点掌握度分析</span>
        </template>
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="分析知识点数">
            {{ composeResult.mastery_summary.total_kps_analyzed }}
          </el-descriptions-item>
          <el-descriptions-item label="薄弱知识点数">
            <span style="color: #f56c6c; font-weight: bold">{{ composeResult.mastery_summary.weak_kps }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="索引题目数">
            {{ composeResult.index_stats?.indexed_questions || '-' }}
          </el-descriptions-item>
        </el-descriptions>
        <div v-if="composeResult.mastery_summary.top_weak_kps?.length" style="margin-top: 12px">
          <div style="font-size: 13px; color: #909399; margin-bottom: 8px">最薄弱知识点 TOP 5：</div>
          <div v-for="kp in composeResult.mastery_summary.top_weak_kps" :key="kp.name" class="weak-kp-item">
            <span class="weak-kp-name">{{ kp.name }}</span>
            <el-progress
              :percentage="Math.round(kp.mastery_rate * 100)"
              :color="masteryColor(kp.mastery_rate)"
              :stroke-width="14"
              style="flex: 1; margin: 0 12px"
            />
            <span class="weak-kp-rate">{{ Math.round(kp.mastery_rate * 100) }}%（{{ kp.total_answered }}人次）</span>
          </div>
        </div>
      </el-card>

      <!-- 考试蓝图（仅智能组卷） -->
      <el-card v-if="composeResult.blueprint?.sections?.length" shadow="hover" style="margin-bottom: 20px">
        <template #header>
          <span>
            <el-icon><Document /></el-icon>&nbsp;考试蓝图（{{ composeResult.blueprint.exam_type_label || composeResult.blueprint.exam_type }}）
            <el-tag v-if="composeResult.blueprint.blueprint_source === 'llm'" size="small" type="success" style="margin-left: 8px">LLM 辅助</el-tag>
          </span>
        </template>
        <el-table :data="composeResult.blueprint.sections" size="small" border stripe>
          <el-table-column label="知识点" prop="knowledge_point" min-width="160">
            <template #default="{ row }">
              <span>{{ row.knowledge_point }}</span>
              <span v-if="row.reason" class="blueprint-reason">{{ row.reason }}</span>
            </template>
          </el-table-column>
          <el-table-column label="权重" width="80" align="center">
            <template #default="{ row }">{{ (row.weight * 100).toFixed(1) }}%</template>
          </el-table-column>
          <el-table-column label="题数" width="70" align="center" prop="question_count" />
          <el-table-column label="分值" width="70" align="center" prop="total_score" />
          <el-table-column label="题型分布" min-width="200">
            <template #default="{ row }">
              <el-tag
                v-for="qs in row.questions"
                :key="qs.qtype"
                size="small"
                :type="qtypeTag(qs.qtype)"
                style="margin: 2px"
              >
                {{ qtypeLabel(qs.qtype) }}×{{ qs.count }}（{{ qs.score_per_question }}分/题）
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 选题回执（仅智能组卷） -->
      <el-card v-if="composeResult.sections?.length" shadow="hover" style="margin-bottom: 20px">
        <template #header>
          <span><el-icon><CircleCheck /></el-icon>&nbsp;选题回执</span>
        </template>
        <el-table :data="composeResult.sections" size="small" border>
          <el-table-column label="知识点" prop="knowledge_point" min-width="160" />
          <el-table-column label="需求题数" width="90" align="center" prop="requested" />
          <el-table-column label="实际检索" width="90" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.retrieved >= row.requested ? '#67c23a' : '#f56c6c' }">
                {{ row.retrieved }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="是否回退补题" width="110" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.fallback_used" size="small" type="warning">是（放宽条件）</el-tag>
              <el-tag v-else size="small" type="success">否（精准匹配）</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 统计图表 -->
      <el-row :gutter="16" style="margin-bottom: 20px">
        <el-col :xs="24" :sm="12">
          <el-card shadow="hover">
            <template #header>题型分布</template>
            <EChart :option="typeChartOption" height="280px" />
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12">
          <el-card shadow="hover">
            <template #header>难度分布</template>
            <EChart :option="difficultyChartOption" height="280px" />
          </el-card>
        </el-col>
      </el-row>

      <!-- 题目列表 -->
      <el-table :data="composeResult.questions || []" size="small" border stripe style="margin-bottom: 20px">
        <el-table-column type="index" label="题号" width="60" />
        <el-table-column label="题型" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="qtypeTag(row.qtype || row.typecode)">{{ qtypeLabel(row.qtype) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="题干" min-width="300" show-overflow-tooltip>
          <template #default="{ row }">{{ row.title || row.content_md?.slice(0, 60) || '-' }}</template>
        </el-table-column>
        <el-table-column label="难度" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="difficultyTag(row.difficulty)" size="small">{{ difficultyLabel(row.difficulty) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="知识点" min-width="160">
          <template #default="{ row }">
            <el-tag v-if="row.knowledge_point" size="small" effect="plain" style="margin: 2px">{{ row.knowledge_point }}</el-tag>
            <el-tag v-for="(kp, i) in (row.knowledge_points || [])" :key="i" size="small" effect="plain" style="margin: 2px">{{ kp }}</el-tag>
            <span v-if="!row.knowledge_point && !row.knowledge_points?.length">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="score" label="分值" width="70" align="center" />
      </el-table>

      <!-- 确认生成 -->
      <el-divider content-position="left">确认生成试卷</el-divider>
      <el-form :inline="true" :model="confirmForm" style="margin-bottom: 12px">
        <el-form-item label="试卷名称">
          <el-input v-model="confirmForm.exam_name" placeholder="请输入试卷名称" style="width: 300px" />
        </el-form-item>
        <el-form-item>
          <el-button type="success" :loading="confirming" :disabled="!confirmForm.exam_name.trim()" @click="confirmCompose">
            <el-icon><Check /></el-icon>确认生成试卷
          </el-button>
          <el-button @click="resetToConfig">放弃，重新配置</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Files, MagicStick, Check, DataAnalysis, Document, CircleCheck } from '@element-plus/icons-vue'
import { resource, aiApi, tagApi } from '../api'
import EChart from '../components/EChart.vue'

const router = useRouter()
const subjectApi = resource('subjects')

// ---- 步骤控制 ----
const step = ref('config') // config -> progress -> result

// ---- 组卷模式 ----
const composeMode = ref('smart') // smart | classic

// ---- 科目 & 知识点 ----
const subjects = ref([])
const knowledgeTags = ref([])
const kpIndexStats = ref(null)
const rebuildingIndex = ref(false)

async function loadSubjects() {
  try {
    const res = await subjectApi.list({ page: 1, page_size: 200 })
    subjects.value = res?.list || []
  } catch (e) { /* ignore */ }
}

async function loadKnowledgeTags() {
  try {
    const res = await tagApi.list({ category: 'knowledge', page: 1, page_size: 200 })
    knowledgeTags.value = res?.list || []
  } catch (e) { /* ignore */ }
}

async function onSubjectChange() {
  if (composeMode.value === 'smart' && form.value.subject_id) {
    await loadKpStats()
  }
}

async function loadKpStats() {
  if (!form.value.subject_id) {
    kpIndexStats.value = null
    return
  }
  try {
    const res = await aiApi.smartComposeKpStats(form.value.subject_id)
    kpIndexStats.value = res
  } catch (e) {
    kpIndexStats.value = null
  }
}

async function rebuildIndex() {
  if (!form.value.subject_id) return
  rebuildingIndex.value = true
  try {
    const res = await aiApi.smartComposeRebuildIndex(form.value.subject_id)
    ElMessage.success(`索引已重建：${res.kp_count} 个知识点，${res.question_count} 道题目`)
    await loadKpStats()
  } catch (e) {
    // handled by interceptor
  } finally {
    rebuildingIndex.value = false
  }
}

function onModeChange() {
  kpIndexStats.value = null
  if (composeMode.value === 'smart' && form.value.subject_id) {
    loadKpStats()
  }
}

// ---- 题型选项 ----
const qtypeOptions = [
  { key: 'single', label: '单选题' },
  { key: 'multiple', label: '多选题' },
  { key: 'judge', label: '判断题' },
  { key: 'fill', label: '填空题' },
  { key: 'qa', label: '问答题' },
]

const qtypeLabels = { single: '单选题', multiple: '多选题', judge: '判断题', fill: '填空题', qa: '问答题' }
const qtypeTagTypes = { single: 'primary', multiple: 'success', judge: 'warning', fill: 'info', qa: 'danger' }

function qtypeLabel(q) {
  return qtypeLabels[q] || q || '-'
}
function qtypeTag(q) {
  return qtypeTagTypes[q] || 'info'
}

// ---- 表单 ----
const form = ref({
  exam_type: 'final',
  subject_id: '',
  type_dist: { single: 10, multiple: 5, judge: 5, fill: 5, qa: 0 },
  difficulty: { easy: 30, medium: 50, hard: 20 },
  question_count: 25,
  total_score: 100,
  knowledge_tags: [],
  use_llm_blueprint: true,
})

const diffSum = computed(() => {
  return form.value.difficulty.easy + form.value.difficulty.medium + form.value.difficulty.hard
})

function syncDifficulty() {
  // 滑块联动：如果总和不为100，自动调整最大的那个
  const sum = diffSum.value
  if (sum !== 100 && sum > 0) {
    // 不强制修正，仅提示
  }
}

function updateTotal() {
  const sum = Object.values(form.value.type_dist).reduce((a, b) => a + b, 0)
  if (sum > 0) {
    form.value.question_count = sum
  }
}

// ---- 提交组卷 ----
const submitting = ref(false)
const composing = ref(false)
const composePercent = ref(0)
const composeStatus = ref('')
const composeStatusText = ref('')
const composeResult = ref(null)
let composeTimer = null
let currentJobId = ''
let currentJobType = '' // exam_compose | smart_compose

async function submitCompose() {
  if (!form.value.subject_id) {
    ElMessage.warning('请选择科目')
    return
  }
  if (diffSum.value !== 100) {
    ElMessage.warning('难度比例总和必须为 100%')
    return
  }
  const totalQuestions = Object.values(form.value.type_dist).reduce((a, b) => a + b, 0)
  if (totalQuestions === 0) {
    ElMessage.warning('请至少配置一种题型的题目数量')
    return
  }

  submitting.value = true
  try {
    let res
    if (composeMode.value === 'smart') {
      // 智能组卷 V2
      const config = {
        exam_type: form.value.exam_type,
        examid: form.value.subject_id,
        qtype_dist: form.value.type_dist,
        difficulty_dist: form.value.difficulty,
        count: form.value.question_count || totalQuestions,
        total_score: form.value.total_score,
        knowledge_points: form.value.knowledge_tags?.length ? form.value.knowledge_tags : [],
        use_llm_blueprint: form.value.use_llm_blueprint,
      }
      res = await aiApi.smartCompose(config)
      currentJobType = 'smart_compose'
    } else {
      // 经典组卷
      const config = {
        subject_id: form.value.subject_id,
        type_dist: form.value.type_dist,
        difficulty: form.value.difficulty,
        question_count: form.value.question_count || totalQuestions,
        total_score: form.value.total_score,
        knowledge_tags: form.value.knowledge_tags,
      }
      res = await aiApi.compose(config)
      currentJobType = 'exam_compose'
    }

    currentJobId = res?.job_id || res?.jobId
    if (!currentJobId) {
      ElMessage.warning('未返回任务 ID')
      return
    }
    step.value = 'progress'
    composing.value = true
    composePercent.value = 0
    composeStatusText.value = composeMode.value === 'smart'
      ? '智能组卷任务已提交，正在分析知识点掌握数据...'
      : '组卷任务已提交，正在处理...'
    pollComposeJob()
  } catch (e) {
    // handled by interceptor
  } finally {
    submitting.value = false
  }
}

function pollComposeJob() {
  let count = 0
  const maxCount = 240 // 8 分钟超时
  composeTimer = setInterval(async () => {
    count++
    if (count > maxCount) {
      clearComposeTimer()
      composing.value = false
      composeStatus.value = 'exception'
      composeStatusText.value = '组卷超时，请稍后重试'
      return
    }
    try {
      const res = await aiApi.composeStatus(currentJobId)
      const status = res?.status || res?.state || ''
      const progress = res?.progress || 0
      composePercent.value = Math.min(progress, 99)
      composeStatusText.value = res?.progress_text || res?.message || composeStatusMap(status)
      if (status === 'completed' || status === 'success' || status === 'done') {
        clearComposeTimer()
        composePercent.value = 100
        composeStatus.value = 'success'
        composeStatusText.value = '组卷完成，请预览结果'
        // 智能组卷返回完整 result 对象（含 blueprint, sections, mastery_summary）
        // 经典组卷返回 {questions: [...], ...}
        composeResult.value = res?.result || res?.questions || res
        composing.value = false
        step.value = 'result'
        ElMessage.success(composeMode.value === 'smart' ? '智能组卷完成' : 'AI 组卷完成')
      } else if (status === 'failed' || status === 'cancelled' || status === 'canceled') {
        clearComposeTimer()
        composing.value = false
        composeStatus.value = 'exception'
        const errReason = res?.error || res?.message || ''
        composeStatusText.value = `组卷${status === 'failed' ? '失败' : '已取消'}${errReason ? '：' + errReason : ''}`
      }
    } catch (e) {
      // 单次查询失败不中断
    }
  }, 2000)
}

function composeStatusMap(status) {
  const map = { pending: '排队中...', running: '正在组卷...', processing: '正在组卷...' }
  return map[status] || status || '处理中...'
}

function clearComposeTimer() {
  if (composeTimer) {
    clearInterval(composeTimer)
    composeTimer = null
  }
}

function resetToConfig() {
  step.value = 'config'
  composeResult.value = null
  composePercent.value = 0
  composeStatus.value = ''
  composeStatusText.value = ''
}

// ---- 确认生成 ----
const confirmForm = ref({ exam_name: '' })
const confirming = ref(false)

async function confirmCompose() {
  if (!confirmForm.value.exam_name.trim()) {
    ElMessage.warning('请输入试卷名称')
    return
  }
  confirming.value = true
  try {
    await aiApi.composeConfirm(currentJobId, confirmForm.value.exam_name)
    ElMessage.success('试卷已生成')
    router.push('/exams')
  } catch (e) {
    // handled by interceptor
  } finally {
    confirming.value = false
  }
}

// ---- 掌握度颜色 ----
function masteryColor(rate) {
  if (rate >= 0.7) return '#67c23a'
  if (rate >= 0.4) return '#e6a23c'
  return '#f56c6c'
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

// ---- ECharts 配置 ----
const typeChartOption = computed(() => {
  const questions = composeResult.value?.questions || []
  const counts = {}
  questions.forEach((q) => {
    const t = q.qtype || q.typecode || 'unknown'
    counts[t] = (counts[t] || 0) + 1
  })
  const data = Object.entries(counts).map(([k, v]) => ({ name: qtypeLabel(k), value: v }))
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      label: { formatter: '{b}: {c}题' },
      data,
    }],
  }
})

const difficultyChartOption = computed(() => {
  const questions = composeResult.value?.questions || []
  const counts = { easy: 0, medium: 0, hard: 0 }
  questions.forEach((q) => {
    const d = q.difficulty
    if (counts[d] !== undefined) counts[d]++
    else if (d === 1) counts.easy++
    else if (d === 2) counts.medium++
    else if (d === 3) counts.hard++
  })
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ['简单', '中等', '困难'] },
    yAxis: { type: 'value', name: '题数' },
    series: [{
      type: 'bar',
      data: [
        { value: counts.easy, itemStyle: { color: '#67c23a' } },
        { value: counts.medium, itemStyle: { color: '#e6a23c' } },
        { value: counts.hard, itemStyle: { color: '#f56c6c' } },
      ],
      barWidth: '40%',
      label: { show: true, position: 'top' },
    }],
  }
})

onMounted(() => {
  loadSubjects()
  loadKnowledgeTags()
})

onBeforeUnmount(() => {
  clearComposeTimer()
})
</script>

<style scoped>
.difficulty-row {
  width: 100%;
}

.diff-item {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.diff-label {
  font-size: 14px;
  color: #606266;
  min-width: 40px;
}

.diff-value {
  font-size: 14px;
  color: #303133;
  min-width: 40px;
  text-align: right;
}

.progress-area {
  text-align: center;
  padding: 40px 20px;
}

.progress-text {
  margin-top: 16px;
  font-size: 15px;
  color: #606266;
}

.kp-index-card {
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 20px;
}

.kp-index-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 14px;
  color: #303133;
}

.kp-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}

.kp-more {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.5;
}

.weak-kp-item {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.weak-kp-name {
  min-width: 140px;
  font-size: 13px;
  color: #303133;
}

.weak-kp-rate {
  min-width: 120px;
  font-size: 13px;
  color: #606266;
  text-align: right;
}

.blueprint-reason {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}
</style>
