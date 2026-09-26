<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <div class="page-title">
          <span class="page-title-icon"><el-icon><DataAnalysis /></el-icon></span>
          数据看板
        </div>
        <div class="page-subtitle">
          数据基准日 {{ overview.base_date || '-' }} · 更新于 {{ overview.updated_at || '-' }}
        </div>
      </div>
      <div>
        <el-radio-group v-model="days" size="small" @change="loadTrend">
          <el-radio-button :value="7">近 7 天</el-radio-button>
          <el-radio-button :value="14">近 14 天</el-radio-button>
          <el-radio-button :value="30">近 30 天</el-radio-button>
          <el-radio-button :value="60">近 60 天</el-radio-button>
        </el-radio-group>
        <el-button style="margin-left: 8px" :loading="loading" @click="loadAll">
          <el-icon><Refresh /></el-icon>
        </el-button>
      </div>
    </div>

    <!-- 核心指标 -->
    <el-row :gutter="14">
      <el-col v-for="card in kpiCards" :key="card.label" :xs="12" :sm="8" :md="8" :lg="4" style="margin-bottom: 14px">
        <div class="kpi-card">
          <div class="kpi-icon" :style="{ background: card.color }">
            <el-icon><component :is="card.icon" /></el-icon>
          </div>
          <div>
            <div class="kpi-value">{{ card.value }}</div>
            <div class="kpi-label">{{ card.label }}</div>
            <div v-if="card.sub" class="kpi-sub">{{ card.sub }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="14">
      <el-col :xs="24" :lg="16" style="margin-bottom: 14px">
        <div class="card-block">
          <div class="block-title"><el-icon><TrendCharts /></el-icon>答题与活跃趋势</div>
          <EChart :option="trendOption" height="320px" />
        </div>
      </el-col>
      <el-col :xs="24" :lg="8" style="margin-bottom: 14px">
        <div class="card-block">
          <div class="block-title"><el-icon><PieChart /></el-icon>科目答题分布</div>
          <EChart :option="subjectOption" height="320px" />
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="14">
      <el-col :xs="24" :lg="14">
        <div class="card-block" style="margin-bottom: 14px">
          <div class="block-title"><el-icon><Trophy /></el-icon>活跃用户 Top 10</div>
          <el-table :data="ranking.top_users" size="small" max-height="360">
            <el-table-column type="index" width="50" label="#" />
            <el-table-column prop="nickname" label="用户" min-width="140" show-overflow-tooltip />
            <el-table-column prop="openid" label="OpenID" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="text-muted">{{ row.openid }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="records" label="答题次数" width="100" align="right" />
            <el-table-column prop="notes" label="错题数" width="90" align="right" />
            <el-table-column label="正确率" width="110" align="right">
              <template #default="{ row }">{{ percent(row.accuracy) }}</template>
            </el-table-column>
            <el-table-column prop="last_active" label="最近活跃" width="110" />
          </el-table>
        </div>
      </el-col>
      <el-col :xs="24" :lg="10">
        <div class="card-block" style="margin-bottom: 14px">
          <div class="block-title"><el-icon><Calendar /></el-icon>窗口指标</div>
          <el-table :data="windowRows" size="small">
            <el-table-column prop="label" label="时间窗口" width="110" />
            <el-table-column prop="records" label="答题次数" align="right" />
            <el-table-column prop="active_users" label="活跃用户" align="right" />
            <el-table-column prop="new_users" label="新增用户" align="right" />
            <el-table-column label="正确率" align="right">
              <template #default="{ row }">{{ percent(row.avg_accuracy) }}</template>
            </el-table-column>
          </el-table>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            style="margin-top: 12px"
            title="演示数据说明"
            description="当前库中的数据来自开源仓库导出的 2020 年真实答题样本，因此窗口指标以数据最后一天为基准日计算；接入真实业务后即为自然日口径。"
          />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Refresh, DataAnalysis, TrendCharts, PieChart, Trophy, Calendar } from '@element-plus/icons-vue'
import EChart from '../components/EChart.vue'
import { dashboardApi } from '../api'

const loading = ref(false)
const days = ref(30)
const overview = ref({})
const trend = ref({ series: [] })
const ranking = ref({ top_users: [], subjects: [] })

const percent = (v) => `${((v || 0) * 100).toFixed(1)}%`

const kpiCards = computed(() => {
  const t = overview.value.totals || {}
  const last7 = overview.value.last7 || {}
  return [
    { label: '累计用户', value: t.users ?? '-', icon: 'UserFilled', color: '#4f7cff', sub: `近7日活跃 ${last7.active_users ?? 0}` },
    { label: '答题记录', value: t.records ?? '-', icon: 'Document', color: '#1d9e75', sub: `近7日 ${last7.records ?? 0} 次` },
    { label: '错题笔记', value: t.notes ?? '-', icon: 'Notebook', color: '#e8833a', sub: `近7日 ${last7.notes ?? 0} 条` },
    { label: '题库题目', value: t.questions ?? '-', icon: 'Tickets', color: '#8a63f2', sub: `科目 ${t.subjects ?? 0} 个` },
    { label: '平均正确率', value: percent(overview.value.avg_accuracy), icon: 'DataAnalysis', color: '#2f9ee0', sub: '全量答题记录' },
    { label: '平均用时', value: `${overview.value.avg_duration ?? 0}s`, icon: 'Timer', color: '#d85a8a', sub: '单次答题' },
  ]
})

const windowRows = computed(() => [
  { label: '基准日当天', ...(overview.value.today || {}) },
  { label: '近 7 天', ...(overview.value.last7 || {}) },
  { label: '近 30 天', ...(overview.value.last30 || {}) },
])

const trendOption = computed(() => {
  const series = trend.value.series || []
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['答题次数', '活跃用户', '新增用户', '错题数'], top: 0 },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: series.map((i) => i.date), boundaryGap: false },
    yAxis: { type: 'value' },
    series: [
      { name: '答题次数', type: 'line', smooth: true, areaStyle: { opacity: 0.12 }, data: series.map((i) => i.records), itemStyle: { color: '#4f7cff' } },
      { name: '活跃用户', type: 'line', smooth: true, data: series.map((i) => i.active_users), itemStyle: { color: '#1d9e75' } },
      { name: '新增用户', type: 'bar', data: series.map((i) => i.new_users), itemStyle: { color: '#f0b34a' } },
      { name: '错题数', type: 'line', smooth: true, data: series.map((i) => i.notes), itemStyle: { color: '#e8833a' } },
    ],
  }
})

const subjectOption = computed(() => {
  const list = ranking.value.subjects || []
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} 次 ({d}%)' },
    legend: { bottom: 0 },
    series: [
      {
        type: 'pie',
        radius: ['42%', '66%'],
        center: ['50%', '44%'],
        data: list.map((i) => ({ name: i.name, value: i.records })),
        label: { formatter: '{b}\n{d}%' },
      },
    ],
  }
})

async function loadOverview() {
  overview.value = await dashboardApi.overview()
}

async function loadTrend() {
  trend.value = await dashboardApi.trend(days.value)
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadOverview(), loadTrend(), loadRanking()])
  } finally {
    loading.value = false
  }
}

async function loadRanking() {
  ranking.value = await dashboardApi.ranking()
}

onMounted(async () => {
  await loadAll()
  window.addEventListener('admin:refresh', loadAll)
})
</script>

<style scoped>
</style>
