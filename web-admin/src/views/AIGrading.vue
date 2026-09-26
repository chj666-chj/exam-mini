<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><DocumentChecked /></el-icon></span>
        AI 判卷复核
      </div>
    </div>

    <!-- 批量判卷入口 -->
    <div class="card-block">
      <el-divider content-position="left">
        <span class="section-title">批量判卷</span>
      </el-divider>
      <el-form :inline="true" :model="batchForm">
        <el-form-item label="答题记录 ID">
          <el-input v-model="batchForm.history_id" placeholder="输入 history_id" style="width: 240px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="batchGrading" @click="startBatchGrade">
            <el-icon><MagicStick /></el-icon>开始判卷
          </el-button>
        </el-form-item>
      </el-form>

      <!-- 批量判卷进度 -->
      <div v-if="batchGrading || batchPercent > 0" class="batch-grade-progress">
        <el-progress :percentage="batchPercent" :status="batchStatus" :stroke-width="18" :text-inside="true" />
        <div class="batch-grade-text">{{ batchStatusText }}</div>
      </div>
    </div>

    <!-- 待复核列表 -->
    <div class="card-block">
      <el-divider content-position="left">
        <span class="section-title">待人工复核列表</span>
      </el-divider>

      <div class="toolbar">
        <el-button type="primary" @click="loadReviewList">刷新</el-button>
      </div>

      <el-table v-loading="reviewLoading" :data="reviewList" size="default" border stripe>
        <el-table-column prop="history_id" label="记录 ID" width="120" show-overflow-tooltip />
        <el-table-column label="考生" width="140">
          <template #default="{ row }">
            <span>{{ maskOpenid(row.openid || row.user_id) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="题目摘要" min-width="250" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.question_title || row.content_md?.slice(0, 50) || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="AI 评分" width="90" align="center">
          <template #default="{ row }">
            <span class="score-text">{{ row.ai_score ?? row.score ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="confidenceTag(row.confidence)" size="small">
              {{ formatConfidence(row.confidence) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="AI 评语" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            {{ (row.feedback_md || row.feedback || '').slice(0, 80) || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openReview(row)">复核</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination v-model:current-page="reviewPage" v-model:page-size="reviewPageSize" :total="reviewTotal" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" background @current-change="loadReviewList" @size-change="loadReviewList" />
      </div>
    </div>

    <!-- 复核详情弹窗 -->
    <el-dialog v-model="reviewDialogVisible" title="人工复核" width="780px" top="4vh" :close-on-click-modal="false">
      <div v-loading="reviewSaving" class="review-detail">
        <template v-if="currentReview">
          <!-- 题目内容 -->
          <div class="review-section">
            <div class="block-title">题目内容</div>
            <MarkdownRenderer :content="currentReview.question_content || currentReview.content_md || currentReview.question_title || '-'" />
          </div>

          <!-- 考生作答 -->
          <div class="review-section">
            <div class="block-title">考生作答</div>
            <div class="answer-box">{{ currentReview.answer_text || currentReview.user_answer || '-' }}</div>
          </div>

          <!-- AI 评分 & 评语 -->
          <el-row :gutter="16" style="margin-bottom: 16px">
            <el-col :span="12">
              <el-card shadow="never">
                <div class="ai-score-label">AI 评分</div>
                <div class="ai-score-value">{{ currentReview.ai_score ?? currentReview.score ?? '-' }} / {{ currentReview.max_score ?? '-' }}</div>
                <div class="confidence-row">
                  置信度：
                  <el-tag :type="confidenceTag(currentReview.confidence)" size="small">
                    {{ formatConfidence(currentReview.confidence) }}
                  </el-tag>
                </div>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card shadow="never">
                <div class="ai-score-label">AI 评语</div>
                <MarkdownRenderer :content="currentReview.feedback_md || currentReview.feedback || '暂无评语'" />
              </el-card>
            </el-col>
          </el-row>

          <!-- 人工调整 -->
          <el-divider content-position="left">人工复核</el-divider>
          <el-form :model="adjustForm" label-width="100px">
            <el-form-item label="题目索引">
              <el-input-number v-model="adjustForm.item_index" :min="0" :max="999" controls-position="right" />
              <span class="form-hint">第几题（0 开始）</span>
            </el-form-item>
            <el-form-item label="调整分数">
              <el-input-number v-model="adjustForm.adjusted_score" :min="0" :max="currentReview.max_score || 100" :precision="1" controls-position="right" />
              <span class="form-hint">满分 {{ currentReview.max_score || '-' }}</span>
            </el-form-item>
            <el-form-item label="人工反馈">
              <el-input v-model="adjustForm.feedback" type="textarea" :rows="3" placeholder="人工反馈（可选）" />
            </el-form-item>
          </el-form>
        </template>
      </div>
      <template #footer>
        <el-button @click="reviewDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="reviewSaving" @click="submitReview">确认复核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentChecked, MagicStick } from '@element-plus/icons-vue'
import { aiApi } from '../api'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'

// ---- 批量判卷 ----
const batchForm = ref({ history_id: '' })
const batchGrading = ref(false)
const batchPercent = ref(0)
const batchStatus = ref('')
const batchStatusText = ref('')
let batchTimer = null

async function startBatchGrade() {
  if (!batchForm.value.history_id.trim()) {
    ElMessage.warning('请输入答题记录 ID')
    return
  }
  batchGrading.value = true
  batchPercent.value = 0
  batchStatus.value = ''
  batchStatusText.value = '正在提交批量判卷任务...'
  try {
    const res = await aiApi.gradeBatch(batchForm.value.history_id.trim())
    const jobId = res?.job_id || res?.jobId
    if (!jobId) {
      ElMessage.warning('未返回任务 ID')
      batchGrading.value = false
      return
    }
    batchStatusText.value = `判卷任务已提交（ID: ${jobId}），正在处理...`
    pollBatchGrade(jobId)
  } catch (e) {
    batchGrading.value = false
    batchStatus.value = 'exception'
    batchStatusText.value = '批量判卷提交失败'
  }
}

function pollBatchGrade(jobId) {
  let count = 0
  const maxCount = 150 // 5 分钟超时
  batchTimer = setInterval(async () => {
    count++
    if (count > maxCount) {
      clearBatchTimer()
      batchGrading.value = false
      batchStatus.value = 'exception'
      batchStatusText.value = '判卷超时，请稍后查看'
      return
    }
    try {
      const res = await aiApi.jobStatus(jobId)
      const status = res?.status || res?.state || ''
      const progress = res?.progress || 0
      batchPercent.value = Math.min(progress, 99)
      batchStatusText.value = res?.message || statusMap(status)
      if (status === 'completed' || status === 'success' || status === 'done') {
        clearBatchTimer()
        batchPercent.value = 100
        batchStatus.value = 'success'
        batchStatusText.value = '批量判卷完成'
        batchGrading.value = false
        ElMessage.success('批量判卷完成')
        loadReviewList()
      } else if (status === 'failed' || status === 'cancelled' || status === 'canceled') {
        clearBatchTimer()
        batchGrading.value = false
        batchStatus.value = 'exception'
        batchStatusText.value = `判卷${status === 'failed' ? '失败' : '已取消'}`
      }
    } catch (e) {
      // 单次查询失败不中断
    }
  }, 2000)
}

function statusMap(status) {
  const map = { pending: '排队中...', running: '正在判卷...', processing: '正在判卷...' }
  return map[status] || status || '处理中...'
}

function clearBatchTimer() {
  if (batchTimer) {
    clearInterval(batchTimer)
    batchTimer = null
  }
}

// ---- 待复核列表 ----
const reviewList = ref([])
const reviewTotal = ref(0)
const reviewPage = ref(1)
const reviewPageSize = ref(20)
const reviewLoading = ref(false)

async function loadReviewList() {
  reviewLoading.value = true
  try {
    const res = await aiApi.gradeReviewList({
      page: reviewPage.value,
      page_size: reviewPageSize.value,
    })
    if (Array.isArray(res)) {
      reviewList.value = res
      reviewTotal.value = res.length
    } else {
      reviewList.value = res?.list || []
      reviewTotal.value = res?.total || 0
    }
  } catch (e) {
    // handled by interceptor
  } finally {
    reviewLoading.value = false
  }
}

// ---- 复核详情 ----
const reviewDialogVisible = ref(false)
const reviewSaving = ref(false)
const currentReview = ref(null)
const adjustForm = ref({ item_index: 0, adjusted_score: 0, feedback: '' })

function openReview(row) {
  currentReview.value = row
  adjustForm.value = {
    item_index: row.item_index ?? 0,
    adjusted_score: row.ai_score ?? row.score ?? 0,
    feedback: '',
  }
  reviewDialogVisible.value = true
}

async function submitReview() {
  if (!currentReview.value) return
  const historyId = currentReview.value.history_id || currentReview.value.historyId || currentReview.value._id
  if (!historyId) {
    ElMessage.warning('缺少记录 ID')
    return
  }
  reviewSaving.value = true
  try {
    await aiApi.gradeReview(historyId, {
      item_index: adjustForm.value.item_index,
      adjusted_score: adjustForm.value.adjusted_score,
      feedback: adjustForm.value.feedback || undefined,
    })
    ElMessage.success('复核已提交')
    reviewDialogVisible.value = false
    loadReviewList()
  } catch (e) {
    // handled by interceptor
  } finally {
    reviewSaving.value = false
  }
}

// ---- 工具函数 ----
function maskOpenid(openid) {
  if (!openid) return '-'
  const s = String(openid)
  if (s.length <= 4) return s[0] + '****'
  return s.slice(0, 2) + '****' + s.slice(-4)
}

function formatConfidence(c) {
  if (c === null || c === undefined) return '-'
  const v = typeof c === 'number' ? c : parseFloat(c)
  if (isNaN(v)) return '-'
  return (v * 100).toFixed(0) + '%'
}

function confidenceTag(c) {
  if (c === null || c === undefined) return 'info'
  const v = typeof c === 'number' ? c : parseFloat(c)
  if (isNaN(v)) return 'info'
  if (v < 0.6) return 'danger'
  if (v < 0.8) return 'warning'
  return 'success'
}

onMounted(() => {
  loadReviewList()
})

onBeforeUnmount(() => {
  clearBatchTimer()
})
</script>

<style scoped>
.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.pager {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

.score-text {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.batch-grade-progress {
  margin-top: 16px;
}

.batch-grade-text {
  margin-top: 8px;
  font-size: 14px;
  color: #606266;
}

.review-detail {
  max-height: 65vh;
  overflow-y: auto;
}

.review-section {
  margin-bottom: 16px;
}

.block-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #303133;
}

.answer-box {
  background: #f4f6fa;
  border-radius: 6px;
  padding: 12px;
  font-size: 14px;
  line-height: 1.7;
  color: #606266;
  white-space: pre-wrap;
}

.ai-score-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 4px;
}

.ai-score-value {
  font-size: 24px;
  font-weight: 700;
  color: #409eff;
}

.confidence-row {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  display: flex;
  align-items: center;
  gap: 4px;
}

.form-hint {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}
</style>
