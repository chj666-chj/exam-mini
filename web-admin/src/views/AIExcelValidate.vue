<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><CircleCheck /></el-icon></span>
        AI 数据校验
      </div>
    </div>

    <!-- 输入区 -->
    <div class="card-block" style="margin-bottom: 16px">
      <el-alert type="info" :closable="false" style="margin-bottom: 16px">
        粘贴待校验的题目数据，AI 将逐行检查题干、答案、解析的完整性与规范性问题，并给出纠错建议。
        <br />支持两种格式：① JSON 数组（每个元素为一个字段字典）；② 每行一段「题干|答案|解析」纯文本。
      </el-alert>

      <el-form label-width="90px">
        <el-form-item label="题型">
          <el-select v-model="qtype" placeholder="请选择题型" style="width: 200px">
            <el-option label="单选题" value="single" />
            <el-option label="多选题" value="multiple" />
            <el-option label="判断题" value="judge" />
            <el-option label="填空题" value="fill" />
            <el-option label="问答题" value="qa" />
          </el-select>
          <el-button type="primary" plain style="margin-left: 12px" @click="fillSample">
            <el-icon><DocumentAdd /></el-icon>填充示例
          </el-button>
          <el-button plain @click="clearAll">
            <el-icon><Delete /></el-icon>清空
          </el-button>
        </el-form-item>

        <el-form-item label="数据内容">
          <el-input
            v-model="rawText"
            type="textarea"
            :rows="12"
            placeholder='粘贴 JSON 数组：[{"题干":"中国的首都是哪里？","答案":"北京","解析":"常识题"}]&#10;或每行一段文本：中国的首都是哪里？|北京|常识题'
            style="font-family: monospace; font-size: 13px"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" size="large" :loading="validating" :disabled="!rawText.trim() || !qtype" @click="startValidate">
            <el-icon><MagicStick /></el-icon>开始校验
          </el-button>
          <span v-if="parsedCount" class="hint">已解析 {{ parsedCount }} 行数据</span>
        </el-form-item>
      </el-form>

      <!-- 校验进度 -->
      <div v-if="validating || validatePercent > 0" class="validate-progress">
        <el-progress :percentage="validatePercent" :status="progressStatus" :stroke-width="18" :text-inside="true" />
        <div class="progress-text">{{ progressText }}</div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!result && !validating" class="card-block">
      <el-empty description="粘贴数据并选择题型后，点击「开始校验」查看 AI 校验结果" />
    </div>

    <!-- 结果区 -->
    <template v-if="result">
      <div class="card-block" style="margin-bottom: 16px">
        <div class="result-header">
          <span class="result-title">校验结果</span>
          <el-tag v-if="result.errorCount" type="danger" effect="dark">存在 {{ result.errorCount }} 处错误</el-tag>
          <el-tag v-else type="success" effect="dark">校验通过</el-tag>
        </div>

        <!-- 统计卡片 -->
        <el-row :gutter="16">
          <el-col :xs="12" :sm="6">
            <el-card shadow="hover" class="stat-card">
              <el-statistic title="总行数" :value="result.total" />
            </el-card>
          </el-col>
          <el-col :xs="12" :sm="6">
            <el-card shadow="hover" class="stat-card">
              <el-statistic title="通过" :value="result.validCount" />
            </el-card>
          </el-col>
          <el-col :xs="12" :sm="6">
            <el-card shadow="hover" class="stat-card">
              <el-statistic title="错误" :value="result.errorCount" :value-style="{ color: '#f56c6c' }" />
            </el-card>
          </el-col>
          <el-col :xs="12" :sm="6">
            <el-card shadow="hover" class="stat-card">
              <el-statistic title="警告" :value="result.warningCount" :value-style="{ color: '#e6a23c' }" />
            </el-card>
          </el-col>
        </el-row>

        <!-- 列映射 -->
        <template v-if="columnMappingEntries.length">
          <div class="block-title" style="margin-top: 18px">列映射识别</div>
          <div class="tag-list">
            <el-tag v-for="([src, target], i) in columnMappingEntries" :key="i" size="small" effect="plain" style="margin: 2px">
              {{ src }} → {{ target }}
            </el-tag>
          </div>
        </template>
      </div>

      <!-- 问题明细 -->
      <div class="card-block">
        <div class="result-header">
          <span class="result-title">问题明细</span>
          <el-button type="primary" plain size="small" :disabled="!result.errors.length" @click="copyCorrected">
            <el-icon><CopyDocument /></el-icon>复制修正后数据
          </el-button>
        </div>

        <el-table v-if="result.errors.length" :data="result.errors" size="small" border stripe max-height="440">
          <el-table-column label="行号" width="80" align="center">
            <template #default="{ row }">{{ displayRowNo(row.row) }}</template>
          </el-table-column>
          <el-table-column prop="field" label="字段" width="140">
            <template #default="{ row }">{{ row.field || '-' }}</template>
          </el-table-column>
          <el-table-column label="级别" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="levelTagType(row.level)" size="small">{{ levelText(row.level) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="问题" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">{{ row.message || '-' }}</template>
          </el-table-column>
          <el-table-column label="建议" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">{{ row.suggestion || '-' }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="未发现问题，数据质量良好" :image-size="80" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck, MagicStick, DocumentAdd, Delete, CopyDocument } from '@element-plus/icons-vue'
import { aiApi } from '../api'

// ---- 输入 ----
const qtype = ref('single')
const rawText = ref('')
const parsedCount = ref(0)

const sampleText = JSON.stringify(
  [
    { 题干: '中国的首都是哪里？', 答案: '北京', 解析: '常识题，首都是北京。' },
    { 题干: '下列哪个是面向对象的特征', 答案: '封装', 解析: '应为"封装、继承、多态"。' },
    { 题干: 'Python 是解释型语言吗？', 答案: '对', 解析: '' },
  ],
  null,
  2
)

function fillSample() {
  rawText.value = sampleText
  parsedCount.value = 3
}

function clearAll() {
  rawText.value = ''
  parsedCount.value = 0
  result.value = null
  validatePercent.value = 0
  progressText.value = ''
}

/**
 * 将粘贴文本解析为 rows 数组。
 * 支持：① JSON 数组 / {rows:[]} / {items:[]}；② 每行「题干|答案|解析」文本。
 * @param {string} text
 * @returns {Array<Object>}
 */
function parseRows(text) {
  const trimmed = (text || '').trim()
  if (!trimmed) throw new Error('请先粘贴题目数据')

  // JSON 模式
  if (trimmed.startsWith('[') || trimmed.startsWith('{')) {
    let parsed
    try {
      parsed = JSON.parse(trimmed)
    } catch (e) {
      throw new Error(`JSON 格式错误：${e.message}`)
    }
    let arr = parsed
    if (!Array.isArray(parsed)) {
      if (Array.isArray(parsed.rows)) arr = parsed.rows
      else if (Array.isArray(parsed.items)) arr = parsed.items
      else throw new Error('JSON 需为数组，或包含 rows / items 数组字段')
    }
    return arr.map((item) => {
      if (item && typeof item === 'object' && !Array.isArray(item)) return item
      return { 题干: String(item) }
    })
  }

  // 文本行模式：题干|答案|解析
  const lines = trimmed.split('\n').map((l) => l.trim()).filter(Boolean)
  return lines.map((line) => {
    const parts = line.split('|')
    return {
      题干: (parts[0] || '').trim(),
      答案: (parts[1] || '').trim(),
      解析: (parts[2] || '').trim(),
    }
  })
}

// ---- 校验状态 ----
const validating = ref(false)
const validatePercent = ref(0)
const progressStatus = ref('')
const progressText = ref('')
const result = ref(null)
let validateTimer = null
let currentRows = []

const columnMappingEntries = computed(() => {
  const map = result.value?.columnMapping || {}
  return Object.entries(map)
})

async function startValidate() {
  if (!qtype.value) {
    ElMessage.warning('请先选择题型')
    return
  }
  let rows
  try {
    rows = parseRows(rawText.value)
  } catch (e) {
    ElMessage.error(e.message)
    return
  }
  if (!rows.length) {
    ElMessage.warning('未解析到有效数据行')
    return
  }
  currentRows = rows
  parsedCount.value = rows.length

  validating.value = true
  validatePercent.value = 0
  progressStatus.value = ''
  progressText.value = '正在提交校验任务...'
  result.value = null
  try {
    const res = await aiApi.excelValidate({ rows, qtype: qtype.value })
    const jobId = res?.job_id || res?.jobId
    if (!jobId) {
      // 同步返回结果
      if (res && (res.total != null || res.errors)) {
        applyResult(res)
        validating.value = false
        validatePercent.value = 100
        progressStatus.value = 'success'
        progressText.value = '校验完成'
        return
      }
      ElMessage.warning('未返回任务 ID')
      validating.value = false
      return
    }
    progressText.value = `校验任务已提交（ID: ${jobId}），正在处理...`
    pollValidateJob(jobId)
  } catch (e) {
    validating.value = false
    progressStatus.value = 'exception'
    progressText.value = '校验任务提交失败'
  }
}

function pollValidateJob(jobId) {
  let count = 0
  const maxCount = 150 // 2 秒 * 150 = 5 分钟超时
  validateTimer = setInterval(async () => {
    count++
    if (count > maxCount) {
      clearValidateTimer()
      validating.value = false
      progressStatus.value = 'exception'
      progressText.value = '校验超时，请稍后重试'
      return
    }
    try {
      const res = await aiApi.jobStatus(jobId)
      const status = res?.status || res?.state || ''
      const progress = res?.progress || 0
      validatePercent.value = Math.min(progress, 99)
      progressText.value = res?.message || statusText(status)
      if (status === 'completed' || status === 'success' || status === 'done') {
        clearValidateTimer()
        validatePercent.value = 100
        progressStatus.value = 'success'
        progressText.value = '校验完成'
        validating.value = false
        applyResult(res?.result || res)
        ElMessage.success('AI 校验完成')
      } else if (status === 'failed' || status === 'cancelled' || status === 'canceled') {
        clearValidateTimer()
        validating.value = false
        progressStatus.value = 'exception'
        progressText.value = `校验${status === 'failed' ? '失败' : '已取消'}：${res?.message || ''}`
      }
    } catch (e) {
      // 单次查询失败不中断轮询
    }
  }, 2000)
}

/** 归一化后端返回结果 */
function applyResult(raw) {
  const r = raw || {}
  const errors = Array.isArray(r.errors) ? r.errors : []
  const warningCount = errors.filter((e) => e.level === 'warning').length
  result.value = {
    total: r.total ?? currentRows.length,
    validCount: r.valid_count ?? 0,
    errorCount: r.error_count ?? errors.filter((e) => e.level !== 'warning').length,
    warningCount,
    errors,
    corrections: Array.isArray(r.corrections) ? r.corrections : [],
    columnMapping: r.column_mapping || {},
  }
}

function statusText(status) {
  const map = { pending: '排队中...', running: '正在校验...', processing: '正在校验...' }
  return map[status] || status || '处理中...'
}

function clearValidateTimer() {
  if (validateTimer) {
    clearInterval(validateTimer)
    validateTimer = null
  }
}

// ---- 结果展示工具 ----
function levelTagType(level) {
  return level === 'warning' ? 'warning' : 'danger'
}
function levelText(level) {
  return level === 'warning' ? '警告' : '错误'
}
/** 行号展示：优先按 1 基展示 */
function displayRowNo(rowNo) {
  const n = Number(rowNo)
  if (isNaN(n)) return '-'
  return n
}

/** 将 0 基 / 1 基行号统一定位到 rows 下标 */
function resolveIndex(idx, len) {
  const n = Number(idx)
  if (isNaN(n)) return -1
  if (n >= 0 && n < len) return n
  if (n - 1 >= 0 && n - 1 < len) return n - 1
  return -1
}

async function copyCorrected() {
  const data = currentRows.map((r) => ({ ...r }))
  const len = data.length
  result.value?.corrections.forEach((c) => {
    const idx = resolveIndex(c.row, len)
    if (idx >= 0 && c.field) {
      data[idx][c.field] = c.corrected
    }
  })
  const text = JSON.stringify(data, null, 2)
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      fallbackCopy(text)
    }
    ElMessage.success('已复制修正后数据到剪贴板')
  } catch (e) {
    fallbackCopy(text)
    ElMessage.success('已复制修正后数据到剪贴板')
  }
}

function fallbackCopy(text) {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  try {
    document.execCommand('copy')
  } finally {
    document.body.removeChild(ta)
  }
}

onBeforeUnmount(() => {
  clearValidateTimer()
})
</script>

<style scoped>
.hint {
  margin-left: 12px;
  font-size: 13px;
  color: #909399;
}

.validate-progress {
  margin-top: 16px;
}

.progress-text {
  margin-top: 8px;
  font-size: 14px;
  color: #606266;
  text-align: center;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.result-title {
  font-size: 16px;
  font-weight: 600;
}

.stat-card {
  text-align: center;
}

.block-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #303133;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
