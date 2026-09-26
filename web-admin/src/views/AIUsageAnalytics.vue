<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <div class="page-title">
          <span class="page-title-icon"><el-icon><MagicStick /></el-icon></span>
          AI 使用分析
        </div>
        <div class="page-subtitle">
          数据基准日 {{ overview.base_date || '-' }} · 统计窗口近 {{ days }} 天 · 更新于 {{ overview.updated_at || '-' }}
        </div>
      </div>
      <div>
        <el-radio-group v-model="days" size="small" @change="loadAll">
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

    <!-- KPI 卡片 -->
    <el-row :gutter="14">
      <el-col v-for="card in kpiCards" :key="card.label" :xs="12" :sm="8" :md="6" :lg="4" style="margin-bottom: 14px">
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

    <!-- 趋势 + 功能分布 -->
    <el-row :gutter="14">
      <el-col :xs="24" :lg="16" style="margin-bottom: 14px">
        <div class="card-block">
          <div class="block-title"><el-icon><TrendCharts /></el-icon>AI 调用与 Token 趋势</div>
          <EChart :option="trendOption" height="340px" />
        </div>
      </el-col>
      <el-col :xs="24" :lg="8" style="margin-bottom: 14px">
        <div class="card-block">
          <div class="block-title"><el-icon><PieChart /></el-icon>调用次数功能分布</div>
          <EChart :option="funcPieOption" height="340px" />
        </div>
      </el-col>
    </el-row>

    <!-- Token 消耗 + 功能分类趋势 -->
    <el-row :gutter="14">
      <el-col :xs="24" :lg="12" style="margin-bottom: 14px">
        <div class="card-block">
          <div class="block-title"><el-icon><Histogram /></el-icon>Token 消耗按功能分布</div>
          <EChart :option="tokenBarOption" height="320px" />
        </div>
      </el-col>
      <el-col :xs="24" :lg="12" style="margin-bottom: 14px">
        <div class="card-block">
          <div class="block-title"><el-icon><DataLine /></el-icon>AI 调用次数按功能分类趋势</div>
          <EChart :option="funcTrendOption" height="320px" />
        </div>
      </el-col>
    </el-row>

    <!-- 功能维度明细表 -->
    <div class="card-block" style="margin-bottom: 14px">
      <div class="block-title"><el-icon><Grid /></el-icon>AI 功能使用明细</div>
      <el-table :data="byFunction.list" size="small" max-height="400">
        <el-table-column type="index" width="50" label="#" />
        <el-table-column prop="func_label" label="AI 功能" min-width="140" show-overflow-tooltip />
        <el-table-column prop="func_name" label="功能标识" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="text-muted">{{ row.func_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="calls" label="调用次数" width="100" align="right" sortable />
        <el-table-column label="成功率" width="100" align="right" sortable :sort-method="(a,b) => a.success_rate - b.success_rate">
          <template #default="{ row }">
            <span :style="{ color: row.success_rate >= 0.9 ? '#1d9e75' : row.success_rate >= 0.7 ? '#e8833a' : '#e64340' }">
              {{ percent(row.success_rate) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="success" label="成功" width="80" align="right" />
        <el-table-column prop="failed" label="失败" width="80" align="right" />
        <el-table-column prop="tokens" label="Token 消耗" width="120" align="right" sortable />
        <el-table-column label="平均耗时" width="100" align="right">
          <template #default="{ row }">{{ row.avg_duration_ms > 0 ? row.avg_duration_ms + 'ms' : '-' }}</template>
        </el-table-column>
        <el-table-column prop="active_users" label="活跃用户" width="90" align="right" sortable />
      </el-table>
    </div>

    <!-- AI 功能清单 + 用户排行 -->
    <el-row :gutter="14">
      <el-col :xs="24" :lg="14" style="margin-bottom: 14px">
        <div class="card-block">
          <div class="block-title"><el-icon><List /></el-icon>AI 功能清单</div>
          <el-table :data="features" size="small" max-height="420">
            <el-table-column type="index" width="50" label="#" />
            <el-table-column prop="label" label="功能名称" min-width="130" show-overflow-tooltip />
            <el-table-column prop="description" label="功能说明" min-width="220" show-overflow-tooltip />
            <el-table-column label="来源" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.source === 'admin' ? 'warning' : 'success'" size="small">
                  {{ row.source === 'admin' ? '管理端' : '小程序' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="模型分级" width="90" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="tierType(row.tier)">{{ tierLabel(row.tier) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="perm" label="权限" width="110" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="text-muted">{{ row.perm }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
      <el-col :xs="24" :lg="10" style="margin-bottom: 14px">
        <div class="card-block">
          <div class="block-title"><el-icon><Trophy /></el-icon>用户 Token 消耗 Top 20</div>
          <el-table :data="byUser.list" size="small" max-height="420">
            <el-table-column type="index" width="50" label="#" />
            <el-table-column label="用户" min-width="120" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.admin_user || row.openid || '未知' }}
              </template>
            </el-table-column>
            <el-table-column label="来源" width="70" align="center">
              <template #default="{ row }">
                <el-tag :type="row.openid ? 'success' : 'warning'" size="small">
                  {{ row.openid ? '小程序' : '管理端' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="calls" label="调用次数" width="90" align="right" sortable />
            <el-table-column prop="tokens" label="Token" width="100" align="right" sortable />
            <el-table-column label="成功率" width="80" align="right">
              <template #default="{ row }">{{ percent(row.calls ? row.success / row.calls : 0) }}</template>
            </el-table-column>
            <el-table-column prop="last_active" label="最近活跃" width="100" />
          </el-table>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Refresh, MagicStick, TrendCharts, PieChart, Histogram, DataLine, Grid, List, Trophy } from '@element-plus/icons-vue'
import EChart from '../components/EChart.vue'
import { dashboardApi } from '../api'

const loading = ref(false)
const days = ref(30)
const overview = ref({})
const trend = ref({ series: [] })
const byFunction = ref({ list: [] })
const byUser = ref({ list: [] })
const funcTrend = ref({ dates: [], functions: {} })
const tokenDist = ref([])
const features = ref([])

const percent = (v) => `${((v || 0) * 100).toFixed(1)}%`

const fmtNum = (v) => {
  if (v == null) return '-'
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M'
  if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K'
  return String(v)
}

const tierLabel = (t) => ({ lite: '轻量', standard: '标准', complex: '复杂' }[t] || t)
const tierType = (t) => ({ lite: 'info', standard: '', complex: 'danger' }[t] || 'info')

// ---- KPI 卡片 ----
const kpiCards = computed(() => {
  const o = overview.value || {}
  return [
    { label: 'AI 调用总量', value: fmtNum(o.total_calls ?? 0), icon: 'MagicStick', color: '#4f7cff', sub: `成功 ${o.success_rate != null ? percent(o.success_rate) : '-'}` },
    { label: 'Token 总消耗', value: fmtNum(o.total_tokens ?? 0), icon: 'Histogram', color: '#8a63f2', sub: `管理端 ${o.by_source?.admin ?? 0} / 小程序 ${o.by_source?.mp ?? 0}` },
    { label: '活跃用户', value: o.active_users ?? 0, icon: 'UserFilled', color: '#1d9e75', sub: `失败 ${o.failed_calls ?? 0} 次` },
    { label: '活跃功能数', value: o.active_features ?? 0, icon: 'Grid', color: '#e8833a', sub: `共 ${features.value.length} 个功能` },
    { label: '平均耗时', value: o.avg_duration_ms ? o.avg_duration_ms + 'ms' : '-', icon: 'Timer', color: '#2f9ee0', sub: '单次 AI 调用' },
    { label: '成功率', value: percent(o.success_rate), icon: 'CircleCheck', color: '#d85a8a', sub: `窗口 ${days.value} 天` },
  ]
})

// ---- 趋势图 ----
const trendOption = computed(() => {
  const series = trend.value.series || []
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['调用次数', 'Token 消耗', '成功', '失败'], top: 0 },
    grid: { left: 50, right: 60, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: series.map((i) => i.date), boundaryGap: false },
    yAxis: [
      { type: 'value', name: '次数', position: 'left' },
      { type: 'value', name: 'Token', position: 'right' },
    ],
    series: [
      { name: '调用次数', type: 'line', smooth: true, areaStyle: { opacity: 0.12 }, data: series.map((i) => i.calls), itemStyle: { color: '#4f7cff' } },
      { name: 'Token 消耗', type: 'bar', yAxisIndex: 1, data: series.map((i) => i.tokens), itemStyle: { color: '#8a63f2', opacity: 0.7 } },
      { name: '成功', type: 'line', smooth: true, data: series.map((i) => i.success), itemStyle: { color: '#1d9e75' } },
      { name: '失败', type: 'line', smooth: true, data: series.map((i) => i.failed), itemStyle: { color: '#e64340' } },
    ],
  }
})

// ---- 功能分布饼图 ----
const funcPieOption = computed(() => {
  const list = byFunction.value.list || []
  const data = list.map((i) => ({ name: i.func_label || i.func_name, value: i.calls }))
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} 次 ({d}%)' },
    legend: { type: 'scroll', bottom: 0 },
    series: [
      {
        type: 'pie',
        radius: ['38%', '64%'],
        center: ['50%', '44%'],
        data: data.length ? data : [{ name: '暂无数据', value: 1 }],
        label: { formatter: '{b}\n{d}%', fontSize: 11 },
      },
    ],
  }
})

// ---- Token 消耗柱状图 ----
const tokenBarOption = computed(() => {
  const list = (tokenDist.value || []).slice(0, 12)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 120, right: 30, top: 20, bottom: 30 },
    xAxis: { type: 'value', name: 'Token' },
    yAxis: {
      type: 'category',
      data: list.map((i) => i.func_label || i.func_name),
      inverse: true,
      axisLabel: { fontSize: 11 },
    },
    series: [
      {
        type: 'bar',
        data: list.map((i) => i.tokens),
        itemStyle: {
          color: (params) => {
            const colors = ['#4f7cff', '#8a63f2', '#1d9e75', '#e8833a', '#2f9ee0', '#d85a8a', '#f0b34a', '#36cfc9', '#597ef7', '#73d13d', '#ff4d4f', '#ffa940']
            return colors[params.dataIndex % colors.length]
          },
        },
        label: { show: true, position: 'right', formatter: (p) => fmtNum(p.value), fontSize: 10 },
      },
    ],
  }
})

// ---- 功能分类趋势堆叠图 ----
const funcTrendOption = computed(() => {
  const ft = funcTrend.value || {}
  const dates = ft.dates || []
  const funcs = ft.functions || {}
  const funcNames = Object.keys(funcs)
  const colors = ['#4f7cff', '#8a63f2', '#1d9e75', '#e8833a', '#2f9ee0', '#d85a8a', '#f0b34a', '#36cfc9', '#597ef7', '#73d13d', '#ff4d4f', '#ffa940', '#13c2c2', '#722ed1']
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { type: 'scroll', top: 0, data: funcNames },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: dates, boundaryGap: false },
    yAxis: { type: 'value', name: '调用次数' },
    series: funcNames.map((name, idx) => ({
      name,
      type: 'line',
      stack: 'total',
      areaStyle: { opacity: 0.3 },
      smooth: true,
      data: funcs[name] || [],
      itemStyle: { color: colors[idx % colors.length] },
    })),
  }
})

// ---- 数据加载 ----
async function loadOverview() {
  overview.value = await dashboardApi.aiUsageOverview(days.value)
}

async function loadTrend() {
  trend.value = await dashboardApi.aiUsageTrend(days.value)
}

async function loadByFunction() {
  byFunction.value = await dashboardApi.aiUsageByFunction(days.value)
}

async function loadByUser() {
  byUser.value = await dashboardApi.aiUsageByUser(days.value, 20)
}

async function loadFuncTrend() {
  funcTrend.value = await dashboardApi.aiUsageFunctionTrend(days.value)
}

async function loadTokenDist() {
  tokenDist.value = await dashboardApi.aiUsageTokenDist(days.value)
}

async function loadFeatures() {
  features.value = await dashboardApi.aiUsageFeatures()
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([
      loadOverview(),
      loadTrend(),
      loadByFunction(),
      loadByUser(),
      loadFuncTrend(),
      loadTokenDist(),
      loadFeatures(),
    ])
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadAll()
  window.addEventListener('admin:refresh', loadAll)
})
</script>

<style scoped>
</style>
