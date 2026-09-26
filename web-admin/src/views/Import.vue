<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">批量导入题目</div>
    </div>

    <!-- 导入表单 -->
    <div class="card-block" style="margin-bottom: 16px">
      <el-alert type="info" :closable="false" style="margin-bottom: 16px">
        支持单选题、多选题、判断题、填空题、问答题五种题型。题目正文支持 Markdown 格式（**加粗**、==高亮**、图片等）。
        <br />Excel 导入：按题型下载对应模板 → 填写数据 → 上传导入，系统逐行校验并反馈明细。
      </el-alert>

      <el-form label-width="120px">
        <el-form-item label="导入模式">
          <el-radio-group v-model="mode">
            <el-radio value="excel">Excel 导入</el-radio>
            <el-radio value="json">JSON 粘贴</el-radio>
            <el-radio value="file">JSON 文件</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- Excel 导入模式 -->
        <template v-if="mode === 'excel'">
          <el-form-item label="题型选择">
            <el-select v-model="excelQtype" placeholder="请选择题型" style="width: 200px" @change="onQtypeChange">
              <el-option v-for="t in templateList" :key="t.qtype" :label="t.typename" :value="t.qtype" />
            </el-select>
            <el-button type="primary" plain style="margin-left: 12px" :disabled="!excelQtype" :loading="downloading" @click="downloadTemplate">
              <el-icon><Download /></el-icon>下载模板
            </el-button>
          </el-form-item>

          <el-form-item v-if="excelQtype" label="模板字段">
            <div class="template-fields">
              <el-tag v-for="f in currentTemplateFields" :key="f" :type="isRequiredField(f) ? 'danger' : 'info'" size="small" style="margin: 2px">
                {{ f }}{{ isRequiredField(f) ? '*' : '' }}
              </el-tag>
            </div>
          </el-form-item>

          <el-form-item label="Excel 文件">
            <el-upload
              :auto-upload="false"
              accept=".xlsx,.xls"
              :on-change="onExcelFileChange"
              :on-remove="() => { excelFile = null }"
              :limit="1"
              drag
            >
              <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
              <div class="el-upload__text">将 Excel 文件拖到此处，或<em>点击选择</em></div>
              <template #tip>
                <div class="el-upload__tip">仅支持 .xlsx 格式，请先下载对应题型模板填写数据</div>
              </template>
            </el-upload>
          </el-form-item>
        </template>

        <!-- JSON 粘贴模式 -->
        <template v-else-if="mode === 'json'">
          <el-form-item label="题目数据">
            <el-input
              v-model="jsonText"
              type="textarea"
              :rows="14"
              placeholder='{"items":[{"qtype":"single","title":"**加粗**题干","examid":"001001","options":[{"code":"A","content":"选项A","is_correct":true},{"code":"B","content":"选项B","is_correct":false}],"tags":["单选题"]}]}'
              style="font-family: monospace; font-size: 13px"
            />
          </el-form-item>
          <el-form-item>
            <el-button @click="fillSample">填充示例</el-button>
            <el-button @click="validateJson">校验 JSON</el-button>
          </el-form-item>
        </template>

        <!-- JSON 文件模式 -->
        <template v-else>
          <el-form-item label="JSON 文件">
            <el-upload
              :auto-upload="false"
              accept=".json"
              :on-change="onFileChange"
              :on-remove="() => (fileContent = null)"
              :limit="1"
            >
              <el-button type="primary" plain>
                <el-icon><Upload /></el-icon>选择 JSON 文件
              </el-button>
            </el-upload>
          </el-form-item>
        </template>

        <!-- 公共选项 -->
        <el-form-item label="重复处理策略">
          <el-radio-group v-model="onDuplicate">
            <el-radio value="skip">跳过已存在</el-radio>
            <el-radio value="overwrite">覆盖已存在</el-radio>
            <el-radio value="error">报错中止</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="默认科目编号">
          <el-input v-model="defaultExamid" placeholder="如 001001（题目未指定 examid 时使用）" style="width: 240px" />
        </el-form-item>

        <el-form-item label="批量标签">
          <el-select v-model="batchTags" multiple filterable placeholder="为本次导入的所有题目附加标签" style="width: 100%">
            <el-option v-for="t in allTags" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>

        <el-form-item label="异步处理">
          <el-switch v-model="isAsync" />
          <span class="hint">大批量导入（>50题）建议开启，避免请求超时</span>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" size="large" :loading="importing" :disabled="!canSubmit" @click="doImport">
            <el-icon><Upload /></el-icon>开始导入
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 导入结果 -->
    <div v-if="importResult" class="card-block">
      <div class="result-header">
        <span class="result-title">导入结果</span>
        <el-tag :type="statusType(importResult.status)" effect="dark">
          {{ importResult.status_text || statusTextMap[importResult.status] || importResult.status }}
        </el-tag>
      </div>

      <!-- 统计概览 -->
      <el-row :gutter="16" style="margin-bottom: 16px">
        <el-col :span="mode === 'excel' ? 5 : 6"><el-statistic title="总数" :value="importResult.total || importResult.total_rows || 0" /></el-col>
        <el-col :span="mode === 'excel' ? 5 : 6"><el-statistic title="成功" :value="importResult.succeeded || 0" /></el-col>
        <el-col :span="mode === 'excel' ? 5 : 6"><el-statistic title="失败" :value="importResult.failed || 0" /></el-col>
        <el-col :span="mode === 'excel' ? 5 : 6"><el-statistic title="跳过" :value="importResult.skipped || 0" /></el-col>
        <el-col v-if="mode === 'excel'" :span="4">
          <el-statistic title="校验无效行" :value="importResult.invalid_count || 0" />
        </el-col>
      </el-row>

      <!-- Excel 额外信息 -->
      <template v-if="importResult.source === 'excel'">
        <el-descriptions :column="3" border size="small" style="margin-bottom: 16px">
          <el-descriptions-item label="题型">{{ importResult.qtype || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Excel 总行数">{{ importResult.total_rows || 0 }}</el-descriptions-item>
          <el-descriptions-item label="有效行数">{{ importResult.valid_count || 0 }}</el-descriptions-item>
        </el-descriptions>
      </template>

      <!-- 异步任务进度 -->
      <template v-if="importResult.mode === 'async' && importResult.status === 'processing'">
        <el-progress :percentage="importResult.progress" :status="'active'" style="margin-bottom: 16px" />
        <el-button size="small" @click="pollJob(importResult.id)">刷新进度</el-button>
      </template>

      <!-- 校验错误明细（Excel） -->
      <template v-if="importResult.excel_errors && importResult.excel_errors.length">
        <div class="block-title" style="margin-bottom: 8px; color: #f56c6c">
          <el-icon><WarningFilled /></el-icon> 校验错误明细（{{ importResult.excel_errors.length }} 处）
        </div>
        <el-table :data="importResult.excel_errors" size="small" border stripe max-height="300" style="margin-bottom: 16px">
          <el-table-column prop="row" label="行号" width="70" align="center" />
          <el-table-column prop="field" label="字段" width="120" />
          <el-table-column prop="message" label="错误原因" min-width="300" show-overflow-tooltip />
        </el-table>
      </template>

      <!-- 校验警告（Excel） -->
      <template v-if="importResult.excel_warnings && importResult.excel_warnings.length">
        <div class="block-title" style="margin-bottom: 8px; color: #e6a23c">
          <el-icon><Warning /></el-icon> 警告（{{ importResult.excel_warnings.length }} 处，不影响导入）
        </div>
        <el-table :data="importResult.excel_warnings" size="small" border stripe max-height="200" style="margin-bottom: 16px">
          <el-table-column prop="row" label="行号" width="70" align="center" />
          <el-table-column prop="field" label="字段" width="120" />
          <el-table-column prop="message" label="警告原因" min-width="300" show-overflow-tooltip />
        </el-table>
      </template>

      <!-- 逐题结果 -->
      <el-table v-if="importResult.results && importResult.results.length" :data="importResult.results" size="small" border stripe max-height="400">
        <el-table-column prop="index" label="#" width="50" />
        <el-table-column prop="title" label="题干" min-width="200" show-overflow-tooltip />
        <el-table-column prop="qtype" label="题型" width="90" />
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="resultTagType(row.status)" size="small">{{ resultStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="_id" label="题目ID" width="90" />
        <el-table-column label="错误信息" min-width="200">
          <template #default="{ row }">
            <span v-if="row.errors && row.errors.length" class="err-text">{{ row.errors.join('；') }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 历史任务 -->
    <div class="card-block">
      <div class="block-title" style="margin-bottom: 12px">导入历史</div>
      <el-table v-loading="historyLoading" :data="history" size="small" border stripe>
        <el-table-column prop="id" label="#" width="50" />
        <el-table-column prop="created_by" label="操作人" width="90" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status_text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="80" align="center">
          <template #default="{ row }">{{ row.succeeded }}/{{ row.total }}</template>
        </el-table-column>
        <el-table-column prop="mode" label="模式" width="70" />
        <el-table-column prop="created_at" label="创建时间" width="160" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewJob(row.id)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, Download, UploadFilled, WarningFilled, Warning } from '@element-plus/icons-vue'
import { importApi, tagApi } from '../api'
import { useUserStore } from '../stores/user'

const user = useUserStore()
const canImport = user.hasPerm('question.import')

const mode = ref('excel')
const jsonText = ref('')
const fileContent = ref(null)
const onDuplicate = ref('skip')
const defaultExamid = ref('')
const batchTags = ref([])
const isAsync = ref(false)
const importing = ref(false)
const importResult = ref(null)

// Excel 相关
const excelQtype = ref('')
const excelFile = ref(null)
const downloading = ref(false)
const templateList = ref([])

const allTags = ref([])
const history = ref([])
const historyLoading = ref(false)

const statusTextMap = {
  success: '全部成功',
  partial: '部分成功',
  failed: '失败',
  processing: '处理中',
  pending: '排队中',
  validation_failed: '校验失败',
}

const currentTemplateFields = computed(() => {
  const tmpl = templateList.value.find(t => t.qtype === excelQtype.value)
  return tmpl ? tmpl.columns : []
})

const canSubmit = computed(() => {
  if (mode.value === 'excel') return !!excelFile.value && !!excelQtype.value
  if (mode.value === 'json') return !!jsonText.value.trim()
  if (mode.value === 'file') return !!fileContent.value
  return false
})

function isRequiredField(fieldName) {
  const tmpl = templateList.value.find(t => t.qtype === excelQtype.value)
  if (!tmpl) return false
  return tmpl.required_columns.includes(fieldName)
}

const sampleJson = JSON.stringify({
  items: [
    {
      qtype: 'single',
      title: '**加粗题干**：以下哪个是 ==面向对象== 编程的三大特性之一？',
      examid: '001001',
      options: [
        { code: 'A', content: '封装', is_correct: true },
        { code: 'B', content: '编译', is_correct: false },
        { code: 'C', content: '链接', is_correct: false },
        { code: 'D', content: '加载', is_correct: false },
      ],
      tags: ['单选题', '基础知识'],
    },
    {
      qtype: 'multiple',
      title: '下列哪些是 ==JavaScript== 的数据类型？',
      examid: '001001',
      options: [
        { code: 'A', content: 'String', is_correct: true },
        { code: 'B', content: 'Number', is_correct: true },
        { code: 'C', content: 'List', is_correct: false },
        { code: 'D', content: 'Boolean', is_correct: true },
      ],
      tags: ['多选题'],
    },
    {
      qtype: 'judge',
      title: 'Python 是一种 ==解释型== 编程语言。',
      examid: '001001',
      answer: true,
      tags: ['判断题'],
    },
    {
      qtype: 'fill',
      title: '中国的首都是____，最大的城市是____。',
      examid: '001001',
      blanks: [['北京', 'Beijing'], ['上海', 'Shanghai']],
      tags: ['填空题'],
    },
    {
      qtype: 'qa',
      title: '请论述 ==微服务架构== 的优缺点。',
      examid: '001001',
      ai_grading: { enabled: true, rubric: '要点：独立性、可扩展性、运维复杂度', model: 'gpt-4', max_score: 10 },
      tags: ['问答题'],
    },
  ],
}, null, 2)

function fillSample() {
  jsonText.value = sampleJson
}

function validateJson() {
  try {
    const parsed = JSON.parse(jsonText.value)
    if (!parsed.items || !Array.isArray(parsed.items)) {
      ElMessage.warning('JSON 需包含 items 数组')
      return
    }
    ElMessage.success(`校验通过：${parsed.items.length} 道题目`)
  } catch (e) {
    ElMessage.error(`JSON 格式错误：${e.message}`)
  }
}

// ---- Excel 相关 ----
async function loadTemplates() {
  try {
    const res = await importApi.templates()
    templateList.value = res?.templates || []
    // 默认选中第一个
    if (templateList.value.length && !excelQtype.value) {
      excelQtype.value = templateList.value[0].qtype
    }
  } catch (e) {
    ElMessage.error('获取模板列表失败')
  }
}

function onQtypeChange() {
  excelFile.value = null
  importResult.value = null
}

async function downloadTemplate() {
  if (!excelQtype.value) {
    ElMessage.warning('请先选择题型')
    return
  }
  downloading.value = true
  try {
    const { blob, filename } = await importApi.downloadTemplate(excelQtype.value)
    // 触发浏览器下载
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success(`模板已下载：${filename}`)
  } catch (e) {
    ElMessage.error(e.message || '模板下载失败')
  } finally {
    downloading.value = false
  }
}

function onExcelFileChange(file) {
  excelFile.value = file.raw
}

// ---- 导入 ----
async function doImport() {
  if (mode.value === 'excel') {
    await doExcelImport()
  } else {
    await doJsonImport()
  }
}

async function doExcelImport() {
  if (!excelFile.value) { ElMessage.warning('请选择 Excel 文件'); return }
  if (!excelQtype.value) { ElMessage.warning('请选择题型'); return }

  importing.value = true
  try {
    const res = await importApi.importExcel(excelFile.value, {
      qtype: excelQtype.value,
      on_duplicate: onDuplicate.value,
      default_examid: defaultExamid.value,
      tags: batchTags.value.join(','),
      async: isAsync.value,
    })
    importResult.value = res

    if (res?.status === 'validation_failed') {
      ElMessage.error(`校验失败：${res.errors?.length || 0} 处错误，请修正后重新上传`)
    } else if (res?.mode === 'async') {
      ElMessage.success('导入任务已创建，正在后台处理')
      startPolling(res.id)
    } else {
      if (res?.status === 'success') ElMessage.success(`导入完成：${res.succeeded} 道成功`)
      else if (res?.status === 'partial') ElMessage.warning(`部分成功：${res.succeeded} 成功 / ${res.failed} 失败`)
      else ElMessage.error(`导入失败：${res?.failed || 0} 道题目未导入`)
    }
    loadHistory()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || e.message || '导入失败')
  } finally {
    importing.value = false
  }
}

async function doJsonImport() {
  let payload
  if (mode.value === 'json') {
    try {
      payload = JSON.parse(jsonText.value)
    } catch (e) {
      ElMessage.error(`JSON 格式错误：${e.message}`)
      return
    }
  } else {
    if (!fileContent.value) { ElMessage.warning('请选择 JSON 文件'); return }
    try { payload = JSON.parse(fileContent.value) } catch (e) { ElMessage.error(`文件 JSON 格式错误：${e.message}`); return }
  }

  if (!payload.items || !Array.isArray(payload.items) || !payload.items.length) {
    ElMessage.warning('items 不能为空')
    return
  }

  importing.value = true
  try {
    const res = await importApi.create({
      items: payload.items,
      async: isAsync.value,
      on_duplicate: onDuplicate.value,
      default_examid: defaultExamid.value,
      tags: batchTags.value,
    })
    importResult.value = res
    if (res?.mode === 'async') {
      ElMessage.success('导入任务已创建，正在后台处理')
      startPolling(res.id)
    } else {
      if (res?.status === 'success') ElMessage.success(`导入完成：${res.succeeded} 道成功`)
      else if (res?.status === 'partial') ElMessage.warning(`部分成功：${res.succeeded} 成功 / ${res.failed} 失败`)
      else ElMessage.error(`导入失败：${res?.failed || 0} 道题目未导入`)
    }
    loadHistory()
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '导入失败')
  } finally {
    importing.value = false
  }
}

// ---- 轮询 ----
let pollTimer = null
function startPolling(jobId) {
  stopPolling()
  pollTimer = setInterval(async () => {
    await pollJob(jobId)
    if (importResult.value && importResult.value.status !== 'processing') {
      stopPolling()
    }
  }, 2000)
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

async function pollJob(jobId) {
  try {
    const res = await importApi.detail(jobId)
    // 保留 Excel 特有的字段
    if (importResult.value && importResult.value.source === 'excel' && res) {
      res.source = 'excel'
      res.qtype = importResult.value.qtype
      res.total_rows = importResult.value.total_rows
      res.valid_count = importResult.value.valid_count
      res.invalid_count = importResult.value.invalid_count
      res.excel_errors = importResult.value.excel_errors
      res.excel_warnings = importResult.value.excel_warnings
    }
    importResult.value = res
  } catch (e) { stopPolling() }
}

async function viewJob(jobId) {
  try {
    const res = await importApi.detail(jobId)
    importResult.value = res
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (e) { ElMessage.error('获取详情失败') }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const res = await importApi.list({ page: 1, page_size: 10 })
    history.value = res?.list || []
  } finally {
    historyLoading.value = false
  }
}

async function loadTags() {
  try {
    const res = await tagApi.list({ page: 1, page_size: 200 })
    allTags.value = res?.list || []
  } catch (e) { /* ignore */ }
}

function onFileChange(file) {
  const reader = new FileReader()
  reader.onload = (e) => { fileContent.value = e.target.result }
  reader.readAsText(file.raw)
}

function statusType(s) {
  return { success: 'success', partial: 'warning', failed: 'danger', processing: 'primary', pending: 'info', validation_failed: 'danger' }[s] || 'info'
}
function resultTagType(s) {
  return { success: 'success', overwritten: 'warning', skipped: 'info', failed: 'danger' }[s] || 'info'
}
function resultStatusText(s) {
  return { success: '成功', overwritten: '覆盖', skipped: '跳过', failed: '失败' }[s] || s
}

onMounted(() => {
  loadTemplates()
  loadTags()
  loadHistory()
})
</script>

<style scoped>
.result-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.result-title { font-size: 16px; font-weight: 600; }
.block-title { font-size: 15px; font-weight: 600; display: flex; align-items: center; gap: 4px; }
.hint { margin-left: 8px; font-size: 12px; color: #909399; }
.err-text { color: #f56c6c; font-size: 12px; }
.template-fields { display: flex; flex-wrap: wrap; gap: 2px; }
</style>
