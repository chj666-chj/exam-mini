<template>
  <div class="page-container">
    <!-- 顶部导航 -->
    <div class="page-header">
      <div class="profile-header">
        <el-button text @click="goBack">
          <el-icon><ArrowLeft /></el-icon>返回用户列表
        </el-button>
      </div>
      <el-button :loading="loading" @click="load">
        <el-icon><Refresh /></el-icon>
      </el-button>
    </div>

    <div v-loading="loading">
      <!-- 用户信息卡 -->
      <div class="card-block profile-card" v-if="data.user">
        <div class="profile-user">
          <el-avatar :size="64" :src="data.user.avatar">{{ (data.user.nickname || 'U').slice(0, 1) }}</el-avatar>
          <div class="profile-user-info">
            <div class="profile-user-name">{{ data.user.nickname }}</div>
            <div class="profile-user-meta">
              <el-tag size="small" :type="data.user.status === 'disabled' ? 'danger' : 'success'" effect="plain">
                {{ data.user.status === 'disabled' ? '已停用' : '正常' }}
              </el-tag>
              <span class="text-muted" v-if="data.user.city">{{ data.user.city }}</span>
              <span class="text-muted" v-if="data.user.last_active">最近活跃：{{ data.user.last_active }}</span>
            </div>
            <div class="profile-user-meta">
              <span class="text-muted openid-text">{{ data.user.openid }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 模块1：题目作答情况 -->
      <div class="section-title">
        <el-icon><Document /></el-icon>
        <span>题目作答情况</span>
      </div>
      <el-row :gutter="14" style="margin-bottom: 14px">
        <el-col :xs="12" :sm="6" v-for="card in answerCards" :key="card.label" style="margin-bottom: 10px">
          <div class="kpi-card">
            <div class="kpi-icon" :style="{ background: card.color }">
              <el-icon><component :is="card.icon" /></el-icon>
            </div>
            <div>
              <div class="kpi-value">{{ card.value }}</div>
              <div class="kpi-label">{{ card.label }}</div>
            </div>
          </div>
        </el-col>
      </el-row>
      <el-row :gutter="14" style="margin-bottom: 14px">
        <el-col :xs="24" :lg="16">
          <div class="card-block">
            <div class="block-title">作答趋势</div>
            <EChart :option="answerTrendOption" height="300px" />
          </div>
        </el-col>
        <el-col :xs="24" :lg="8">
          <div class="card-block">
            <div class="block-title">最近作答记录</div>
            <el-table :data="data.answer?.recent || []" size="small" max-height="280" stripe>
              <el-table-column prop="date" label="日期" width="100" />
              <el-table-column prop="subject" label="科目" min-width="100" show-overflow-tooltip />
              <el-table-column label="成绩" width="80" align="center">
                <template #default="{ row }">{{ row.right }}/{{ row.total }}</template>
              </el-table-column>
              <el-table-column label="正确率" width="80" align="center">
                <template #default="{ row }">
                  <span :style="{ color: accColor(row.accuracy) }">{{ pct(row.accuracy) }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-col>
      </el-row>

      <!-- 模块2：考试情况 -->
      <div class="section-title">
        <el-icon><Files /></el-icon>
        <span>考试情况</span>
      </div>
      <el-row :gutter="14" style="margin-bottom: 14px">
        <el-col :xs="12" :sm="6" v-for="card in examCards" :key="card.label" style="margin-bottom: 10px">
          <div class="kpi-card">
            <div class="kpi-icon" :style="{ background: card.color }">
              <el-icon><component :is="card.icon" /></el-icon>
            </div>
            <div>
              <div class="kpi-value">{{ card.value }}</div>
              <div class="kpi-label">{{ card.label }}</div>
            </div>
          </div>
        </el-col>
      </el-row>
      <el-row :gutter="14" style="margin-bottom: 14px">
        <el-col :xs="24" :lg="14">
          <div class="card-block">
            <div class="block-title">成绩变化趋势</div>
            <EChart :option="scoreTrendOption" height="280px" />
          </div>
        </el-col>
        <el-col :xs="24" :lg="10">
          <div class="card-block">
            <div class="block-title">考试记录明细</div>
            <el-table :data="data.exam?.records || []" size="small" max-height="260" stripe>
              <el-table-column prop="date" label="日期" width="100" />
              <el-table-column prop="subject" label="科目" min-width="100" show-overflow-tooltip />
              <el-table-column label="得分" width="70" align="center">
                <template #default="{ row }">{{ row.right }}/{{ row.total }}</template>
              </el-table-column>
              <el-table-column label="得分率" width="80" align="center">
                <template #default="{ row }">
                  <span :style="{ color: accColor(row.score_pct) }">{{ pct(row.score_pct) }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-col>
      </el-row>

      <!-- 模块3：知识点掌握情况 -->
      <div class="section-title">
        <el-icon><DataAnalysis /></el-icon>
        <span>知识点掌握情况</span>
      </div>
      <el-row :gutter="14" style="margin-bottom: 14px">
        <el-col :xs="24" :lg="12">
          <div class="card-block">
            <div class="block-title">掌握度雷达图</div>
            <EChart v-if="hasKnowledgeData" :option="knowledgeRadarOption" height="340px" />
            <el-empty v-else description="暂无知识点数据" :image-size="80" />
          </div>
        </el-col>
        <el-col :xs="24" :lg="12">
          <div class="card-block">
            <div class="block-title">各知识点掌握详情</div>
            <div class="knowledge-list">
              <div v-for="kp in data.knowledge || []" :key="kp.name" class="knowledge-item">
                <div class="knowledge-head">
                  <span class="knowledge-name">{{ kp.name }}</span>
                  <el-tag size="small" :style="{ color: kp.mastery_color, borderColor: kp.mastery_color }" effect="plain">
                    {{ kp.mastery_label }}
                  </el-tag>
                </div>
                <el-progress
                  :percentage="kp.mastery_pct"
                  :color="kp.mastery_color"
                  :stroke-width="10"
                  :show-text="false"
                  style="flex: 1; margin: 0 12px"
                />
                <span class="knowledge-pct">{{ pct(kp.accuracy) }}</span>
                <span class="knowledge-meta text-muted">{{ kp.right_questions }}/{{ kp.total_questions }}题</span>
              </div>
              <el-empty v-if="!(data.knowledge || []).length" description="暂无知识点数据" :image-size="60" />
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- 模块4：薄弱情况 -->
      <div class="section-title">
        <el-icon><WarningFilled /></el-icon>
        <span>薄弱情况分析</span>
      </div>
      <el-row :gutter="14" style="margin-bottom: 14px">
        <el-col :xs="24" :lg="12">
          <div class="card-block">
            <div class="block-title">薄弱知识点（正确率 < 60%）</div>
            <div v-if="(data.weakness?.weak_subjects || []).length" class="weak-list">
              <div v-for="ws in data.weakness.weak_subjects" :key="ws.name" class="weak-item">
                <div class="weak-head">
                  <el-icon color="#f56c6c"><Warning /></el-icon>
                  <span class="weak-name">{{ ws.name }}</span>
                </div>
                <div class="weak-detail">
                  <span class="weak-err">错误率 {{ pct(ws.error_rate) }}</span>
                  <span class="text-muted">答错 {{ ws.wrong_questions }}/{{ ws.total_questions }} 题</span>
                </div>
                <el-progress :percentage="Math.round(ws.error_rate * 100)" color="#f56c6c" :stroke-width="8" :show-text="false" style="width: 100%; margin-top: 4px" />
              </div>
            </div>
            <el-alert v-else type="success" :closable="false" show-icon title="暂无薄弱知识点" description="当前所有科目正确率均在 60% 以上" />
          </div>
        </el-col>
        <el-col :xs="24" :lg="12">
          <div class="card-block">
            <div class="block-title">各题型错误率</div>
            <EChart :option="typeErrorOption" height="240px" />
          </div>
        </el-col>
      </el-row>

      <!-- 高频错题 -->
      <div class="card-block" v-if="(data.weakness?.frequent_errors || []).length" style="margin-bottom: 14px">
        <div class="block-title">高频错题 Top 10</div>
        <el-table :data="data.weakness.frequent_errors" size="small" stripe max-height="300">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column prop="title" label="题目" min-width="300" show-overflow-tooltip />
          <el-table-column prop="typename" label="题型" width="90" />
          <el-table-column prop="error_count" label="出错次数" width="100" align="center">
            <template #default="{ row }">
              <el-tag type="danger" size="small" effect="dark">{{ row.error_count }} 次</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft, Document, Files, DataAnalysis, WarningFilled, Warning, Refresh,
  UserFilled, Tickets, Timer, TrendCharts, Trophy, Medal,
} from '@element-plus/icons-vue'
import EChart from '../components/EChart.vue'
import { userApi } from '../api'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const data = ref({})

const pct = (v) => `${((v || 0) * 100).toFixed(1)}%`
const accColor = (v) => {
  if (v >= 0.85) return '#67c23a'
  if (v >= 0.70) return '#409eff'
  if (v >= 0.60) return '#e6a23c'
  return '#f56c6c'
}

const answerCards = computed(() => {
  const a = data.value.answer || {}
  return [
    { label: '作答总次数', value: a.total_records ?? 0, icon: 'Document', color: '#4f7cff' },
    { label: '作答总题数', value: a.total_questions ?? 0, icon: 'Tickets', color: '#1d9e75' },
    { label: '平均正确率', value: pct(a.avg_accuracy), icon: 'TrendCharts', color: '#2f9ee0' },
    { label: '平均用时', value: `${a.avg_duration ?? 0}s`, icon: 'Timer', color: '#d85a8a' },
  ]
})

const examCards = computed(() => {
  const e = data.value.exam || {}
  return [
    { label: '参与考试次数', value: e.total_exams ?? 0, icon: 'Files', color: '#4f7cff' },
    { label: '平均得分率', value: pct(e.avg_score), icon: 'TrendCharts', color: '#1d9e75' },
    { label: '最佳得分率', value: pct(e.best_score), icon: 'Trophy', color: '#e8833a' },
    { label: '用户排名', value: e.rank ? `#${e.rank}/${e.total_users}` : '-', icon: 'Medal', color: '#8a63f2' },
  ]
})

const answerTrendOption = computed(() => {
  const series = data.value.answer?.trend || []
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['答题次数', '答题数', '正确率'], top: 0 },
    grid: { left: 50, right: 50, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: series.map((i) => i.date), boundaryGap: false },
    yAxis: [
      { type: 'value', name: '次数', position: 'left' },
      { type: 'value', name: '正确率', position: 'right', min: 0, max: 1, axisLabel: { formatter: (v) => `${(v * 100).toFixed(0)}%` } },
    ],
    series: [
      { name: '答题次数', type: 'bar', data: series.map((i) => i.records), itemStyle: { color: '#4f7cff' } },
      { name: '答题数', type: 'line', smooth: true, data: series.map((i) => i.questions), itemStyle: { color: '#1d9e75' } },
      { name: '正确率', type: 'line', smooth: true, yAxisIndex: 1, data: series.map((i) => i.accuracy), itemStyle: { color: '#e8833a' }, areaStyle: { opacity: 0.1 } },
    ],
  }
})

const scoreTrendOption = computed(() => {
  const series = data.value.exam?.score_trend || []
  return {
    tooltip: { trigger: 'axis', formatter: (params) => {
      let html = params[0].axisValue + '<br/>'
      params.forEach((p) => {
        html += `${p.marker} ${p.seriesName}: ${(p.value * 100).toFixed(1)}%<br/>`
      })
      return html
    }},
    legend: { data: ['得分率'], top: 0 },
    grid: { left: 50, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: series.map((i) => i.date), boundaryGap: false },
    yAxis: { type: 'value', min: 0, max: 1, axisLabel: { formatter: (v) => `${(v * 100).toFixed(0)}%` } },
    series: [
      {
        name: '得分率', type: 'line', smooth: true, data: series.map((i) => i.score),
        itemStyle: { color: '#4f7cff' }, areaStyle: { opacity: 0.15 },
        markLine: { silent: true, data: [{ yAxis: 0.6, lineStyle: { color: '#f56c6c', type: 'dashed' }, label: { formatter: '及格线' } }] },
      },
    ],
  }
})

const hasKnowledgeData = computed(() => (data.value.knowledge || []).length > 0)

const knowledgeRadarOption = computed(() => {
  const list = (data.value.knowledge || []).slice(0, 8)
  return {
    tooltip: { trigger: 'item' },
    radar: {
      indicator: list.map((i) => ({ name: i.name, max: 1 })),
      shape: 'polygon',
      radius: '65%',
      splitNumber: 4,
      axisName: { color: '#606266', fontSize: 12 },
      splitLine: { lineStyle: { color: '#dcdfe6' } },
      splitArea: { areaStyle: { color: ['#fafafa', '#fff'] } },
    },
    series: [
      {
        type: 'radar',
        data: [{ value: list.map((i) => i.accuracy), name: '掌握度', areaStyle: { opacity: 0.2 } }],
        itemStyle: { color: '#4f7cff' },
        lineStyle: { color: '#4f7cff', width: 2 },
      },
    ],
  }
})

const typeErrorOption = computed(() => {
  const list = data.value.weakness?.type_weakness || []
  return {
    tooltip: { trigger: 'axis', formatter: (params) => {
      const p = params[0]
      return `${p.name}<br/>错误率: ${(p.value * 100).toFixed(1)}%<br/>答错: ${list[p.dataIndex]?.wrong || 0}/${list[p.dataIndex]?.total || 0} 题`
    }},
    grid: { left: 80, right: 30, top: 20, bottom: 20 },
    xAxis: { type: 'value', min: 0, max: 1, axisLabel: { formatter: (v) => `${(v * 100).toFixed(0)}%` } },
    yAxis: { type: 'category', data: list.map((i) => i.typename), inverse: true },
    series: [
      {
        type: 'bar', data: list.map((i) => i.error_rate),
        itemStyle: { color: (p) => {
          const rate = list[p.dataIndex]?.error_rate || 0
          if (rate >= 0.5) return '#f56c6c'
          if (rate >= 0.3) return '#e6a23c'
          return '#67c23a'
        }},
        barWidth: '50%',
        label: { show: true, position: 'right', formatter: (p) => `${(p.value * 100).toFixed(0)}%` },
      },
    ],
  }
})

function goBack() {
  router.push({ name: 'users' })
}

async function load() {
  const openid = route.params.openid
  if (!openid) {
    ElMessage.error('缺少用户标识')
    return
  }
  loading.value = true
  try {
    data.value = await userApi.profile(openid)
  } catch (e) {
    ElMessage.error(e.message || '获取用户画像失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.profile-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.profile-card {
  margin-bottom: 14px;
}

.profile-user {
  display: flex;
  align-items: center;
  gap: 16px;
}

.profile-user-info {
  flex: 1;
}

.profile-user-name {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 6px;
}

.profile-user-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  margin-bottom: 4px;
}

.openid-text {
  font-size: 12px;
  word-break: break-all;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 16px;
  font-weight: 600;
  margin: 20px 0 12px;
  color: #303133;
}

.block-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
}

.knowledge-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 340px;
  overflow-y: auto;
}

.knowledge-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.knowledge-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 140px;
  flex-shrink: 0;
}

.knowledge-name {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-pct {
  font-size: 13px;
  font-weight: 600;
  width: 50px;
  text-align: right;
}

.knowledge-meta {
  font-size: 12px;
  width: 70px;
  text-align: right;
  flex-shrink: 0;
}

.weak-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.weak-item {
  padding: 10px 12px;
  background: #fef0f0;
  border-radius: 8px;
  border: 1px solid #fde2e2;
}

.weak-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.weak-name {
  font-size: 14px;
  font-weight: 600;
  color: #f56c6c;
}

.weak-detail {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
}

.weak-err {
  color: #f56c6c;
  font-weight: 600;
}

@media (max-width: 768px) {
  .knowledge-head {
    width: 100px;
  }
  .knowledge-meta {
    display: none;
  }
}
</style>
