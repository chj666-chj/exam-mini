<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><Setting /></el-icon></span>
        AI 配置
      </div>
      <div>
        <el-button :loading="testing" @click="testConnection">
          <el-icon><Connection /></el-icon>测试连接
        </el-button>
        <el-button type="primary" :loading="saving" @click="saveConfig">
          <el-icon><Check /></el-icon>保存配置
        </el-button>
      </div>
    </div>

    <!-- ============ 1. 全局设置（启用开关 / 系统提示词 / 兼容配置） ============ -->
    <div class="card-block">
      <div class="block-head">
        <span class="section-title">全局设置</span>
        <span class="section-tip">控制 AI 总开关与全局系统提示词；各功能可在下方单独指定模型。</span>
      </div>
      <el-form :model="form" label-width="110px" style="max-width: 760px">
        <el-form-item label="启用 AI">
          <el-switch v-model="form.enabled" active-text="已启用" inactive-text="未启用" />
          <span class="inline-hint">总开关关闭时，所有 AI 功能均不可用。</span>
        </el-form-item>
        <el-form-item label="系统提示词">
          <el-input v-model="form.systemPrompt" type="textarea" :rows="3"
            placeholder="定义 AI 的角色和行为（作为各功能默认系统提示词）" />
        </el-form-item>
      </el-form>

      <el-collapse v-model="legacyOpen" class="legacy-collapse">
        <el-collapse-item name="legacy">
          <template #title>
            <span class="legacy-title">
              <el-icon><Link /></el-icon>
              兼容配置（旧版单配置 · 仅在未添加任何模型时作为兜底）
            </span>
          </template>
          <el-alert type="info" :closable="false" show-icon class="legacy-alert"
            title="下方参数仅在「AI 模型列表」为空时生效；一旦添加了模型，调用将优先使用模型列表中的配置。" />
          <el-form :model="form" label-width="110px" style="max-width: 760px">
            <el-form-item label="API 地址">
              <el-input v-model="form.apiUrl" placeholder="https://api.openai.com/v1/chat/completions" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="form.apiKey" type="password" show-password
                placeholder="sk-...（脱敏格式 ****xxxx 表示保留原值）" />
            </el-form-item>
            <el-form-item label="模型名称">
              <el-input v-model="form.model" placeholder="gpt-4o-mini" />
            </el-form-item>
          </el-form>
        </el-collapse-item>
      </el-collapse>

      <!-- 测试结果 -->
      <div v-if="testResult" class="test-result" :class="testResult.success ? 'test-success' : 'test-fail'">
        <div class="test-result-header">
          <el-icon>
            <CircleCheck v-if="testResult.success" />
            <CircleClose v-else />
          </el-icon>
          {{ testResult.success ? '连接成功' : '连接失败' }}
        </div>
        <div class="test-result-body">{{ testResult.message }}</div>
      </div>
    </div>

    <!-- ============ 2. AI 模型配置（新增 / 编辑表单） ============ -->
    <div class="card-block" id="model-config-block">
      <div class="block-head">
        <span class="section-title">
          AI 模型配置
          <el-tag v-if="editingModelId" type="warning" size="small" effect="light" class="ml8">编辑中</el-tag>
        </span>
        <span class="section-tip">
          填写模型名称、类型、API 地址与密钥后保存，<b>该模型将自动同步到下方「AI 模型列表」</b>。
        </span>
      </div>

      <el-form :model="modelForm" label-width="110px" style="max-width: 860px">
        <el-row :gutter="16">
          <el-col :xs="24" :md="12">
            <el-form-item label="模型名称" required>
              <el-input v-model="modelForm.name" placeholder="便于区分的名称，如：生产-DeepSeek" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="类型">
              <el-select v-model="modelForm.provider" style="width: 100%" @change="onProviderChange">
                <el-option v-for="p in modelPresets" :key="p.key" :label="p.name" :value="p.key" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="API 地址" required>
          <el-input v-model="modelForm.apiUrl" placeholder="https://api.deepseek.com/v1/chat/completions" />
        </el-form-item>

        <el-form-item label="API Key" required>
          <el-input v-model="modelForm.apiKey" type="password" show-password
            placeholder="sk-...（编辑时保留 ****xxxx 表示不修改密钥）" />
        </el-form-item>

        <el-row :gutter="16">
          <el-col :xs="24" :md="12">
            <el-form-item label="模型标识" required>
              <el-select v-model="modelForm.model" filterable allow-create default-first-option
                placeholder="选择或输入模型标识" style="width: 100%">
                <el-option v-for="m in currentPresetModels" :key="m" :label="m" :value="m" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="Max Tokens">
              <el-input-number v-model="modelForm.maxTokens" :min="100" :max="32000" :step="100" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="Temperature">
          <div class="slider-row">
            <el-slider v-model="modelForm.temperature" :min="0" :max="2" :step="0.1"
              style="flex: 1; margin-right: 16px" />
            <span class="slider-value">{{ modelForm.temperature }}</span>
          </div>
        </el-form-item>

        <el-row :gutter="16">
          <el-col :xs="24" :md="12">
            <el-form-item label="启用">
              <el-switch v-model="modelForm.enabled" active-text="已启用" inactive-text="未启用" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="备注">
              <el-input v-model="modelForm.remark" placeholder="可选，便于区分用途" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item>
          <el-button type="primary" :loading="modelSaving" @click="submitModel">
            <el-icon><Check /></el-icon>
            {{ editingModelId ? '保存修改' : '保存并加入模型列表' }}
          </el-button>
          <el-button v-if="editingModelId" @click="resetModelForm">取消编辑</el-button>
          <el-button v-else @click="resetModelForm">重置</el-button>
          <span class="inline-hint">
            已添加 {{ models.length }} / {{ modelLimits.global }} 个全局模型
            <template v-if="models.length >= modelLimits.global">（已达上限，请先删除后再新增）</template>
          </span>
        </el-form-item>
      </el-form>
    </div>

    <!-- ============ 3. AI 模型列表 ============ -->
    <div class="card-block">
      <div class="block-head">
        <span class="section-title">AI 模型列表</span>
        <span class="section-tip">
          已配置模型概要；支持编辑、测试、设为默认与删除。
          <b>生效时机：保存后立即写入数据库，下一次 AI 调用即生效（无需重启）。</b>
        </span>
      </div>

      <div class="model-toolbar">
        <div class="model-usage">
          已添加 <b>{{ models.length }}</b> / {{ modelLimits.global }} 个
          <span v-if="modelMeta.defaultModelId" class="model-default-hint">
            · 全局默认：<b>{{ modelNameById(modelMeta.defaultModelId) }}</b>
          </span>
        </div>
        <div>
          <el-button @click="loadModels">
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
          <el-button type="primary" :disabled="models.length >= modelLimits.global" @click="focusAddForm">
            <el-icon><Plus /></el-icon>新增模型
          </el-button>
        </div>
      </div>

      <el-table :data="models" v-loading="modelsLoading" border style="width: 100%">
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column label="类型" width="130">
          <template #default="{ row }">{{ providerLabel(row.provider) }}</template>
        </el-table-column>
        <el-table-column prop="model" label="模型标识" min-width="150" />
        <el-table-column prop="apiUrl" label="API 地址" min-width="220" show-overflow-tooltip />
        <el-table-column label="API Key" width="120">
          <template #default="{ row }"><span class="mono">{{ row.apiKey }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
              {{ row.enabled ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="默认" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.isDefault" type="warning" size="small">默认</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="editModel(row)">
              <el-icon><Edit /></el-icon>编辑
            </el-button>
            <el-button link type="primary" :loading="testingId === row._id" @click="testModel(row)">
              测试
            </el-button>
            <el-button link type="warning" :disabled="row.isDefault" @click="setDefaultModel(row)">
              <el-icon><Star /></el-icon>设为默认
            </el-button>
            <el-button link type="danger" @click="removeModel(row)">
              <el-icon><Delete /></el-icon>删除
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <div class="table-empty">
            暂无模型，请在上方「AI 模型配置」中新增，保存后会自动出现在这里。
          </div>
        </template>
      </el-table>

      <div class="model-order">
        <b>调用模型解析顺序：</b>
        <span v-for="(step, i) in (modelMeta.resolutionOrder || [])" :key="i" class="order-step">
          {{ i + 1 }}. {{ step }}
        </span>
      </div>
    </div>

    <!-- ============ 4. AI 功能级配置 ============ -->
    <div class="card-block">
      <div class="block-head">
        <span class="section-title">AI 功能级配置</span>
        <span class="section-tip">
          为每个功能模块选择要调用的模型（下拉来自上方「AI 模型列表」）。
          留空则使用默认：<b>用户默认 → 全局默认</b>。修改后点击右上角「保存配置」生效。
        </span>
      </div>

      <el-alert v-if="!models.length" type="warning" :closable="false" show-icon class="feature-alert"
        title="尚未添加任何模型，请先在上方「AI 模型配置」中新增模型，之后即可在此处为各功能选择调用模型。" />

      <el-row :gutter="16">
        <el-col :xs="24" :sm="24" :md="8" v-for="feat in featureCatalog" :key="feat.key">
          <el-card shadow="hover" class="feature-card">
            <template #header>
              <div class="feature-card-header">
                <span class="feature-name">{{ feat.label }}</span>
                <el-switch v-model="featureConfig[feat.key].enabled" active-text="启用" inactive-text="禁用" />
              </div>
            </template>
            <el-form label-width="90px" size="small">
              <el-form-item label="调用模型">
                <el-select v-model="featureConfig[feat.key].model" filterable clearable
                  :placeholder="models.length ? '使用默认（用户/全局）' : '请先新增模型'"
                  style="width: 100%">
                  <el-option v-for="opt in featureOptions(feat.key)" :key="opt.value"
                    :label="opt.label" :value="opt.value" :disabled="opt.disabled" />
                </el-select>
              </el-form-item>
              <el-form-item label="Temperature">
                <div class="slider-row">
                  <el-slider v-model="featureConfig[feat.key].temperature" :min="0" :max="2" :step="0.1"
                    style="flex: 1; margin-right: 12px" />
                  <span class="slider-value">{{ featureConfig[feat.key].temperature }}</span>
                </div>
              </el-form-item>
              <el-form-item label="Max Tokens">
                <el-input-number v-model="featureConfig[feat.key].max_tokens" :min="100" :max="8000"
                  :step="100" controls-position="right" />
              </el-form-item>
            </el-form>
            <div class="feature-desc">
              {{ feat.desc }}
              <div class="feature-model-state">
                当前使用：<b>{{ featureModelName(feat.key) }}</b>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Setting, Check, Connection, CircleCheck, CircleClose,
  Plus, Refresh, Edit, Delete, Star, Link,
} from '@element-plus/icons-vue'
import { aiApi } from '../api'

/* ------------------------------------------------------------------ *
 * 全局设置（兼容旧版单配置）
 * ------------------------------------------------------------------ */
const form = ref({
  apiUrl: 'https://api.openai.com/v1/chat/completions',
  apiKey: '',
  model: 'gpt-4o-mini',
  systemPrompt: '你是一个专业的备考文章写作助手，请根据用户给出的主题，撰写一篇结构清晰、内容充实的 Markdown 格式备考文章。',
  temperature: 0.7,
  maxTokens: 2000,
  enabled: false,
})

const legacyOpen = ref([])
const saving = ref(false)
const testing = ref(false)
const testResult = ref(null)

/* ------------------------------------------------------------------ *
 * 功能级配置
 * ------------------------------------------------------------------ */
/** 后端未返回 features 时的兜底目录（与 settings.AI_FEATURE_CONFIG_DEFAULTS 对齐） */
const FALLBACK_FEATURES = [
  { key: 'question_analyze', label: 'AI 题目解析', desc: '自动分析题目知识点、难度、题型及答案解析' },
  { key: 'exam_compose', label: 'AI 智能组卷', desc: '根据题型分布与难度要求自动生成试卷' },
  { key: 'ai_grade', label: 'AI 智能判卷', desc: '对主观题自动评分并生成评语，低置信度转人工复核' },
  { key: 'exam_analyze', label: 'AI 试卷分析', desc: '汇总考试数据，生成成绩分布与薄弱知识点分析' },
  { key: 'learning_profile', label: 'AI 答题记录分析', desc: '分析个人答题记录，生成学习能力画像' },
  { key: 'review_recommend', label: 'AI 错题复习推荐', desc: '依据错题与掌握度推荐复习顺序与重点' },
  { key: 'article_enhance', label: 'AI 文章撰写增强', desc: '辅助撰写 / 润色备考文章' },
  { key: 'kb_qa', label: 'AI 知识库问答', desc: '基于平台知识库与已索引文章的 RAG 智能问答' },
  { key: 'auto_tag', label: 'AI 题目自动标签', desc: '自动为题目推荐知识点 / 难度 / 题型标签' },
  { key: 'excel_validate', label: 'AI Excel 智能校验', desc: '校对导入数据格式与内容（Excel 导入场景）' },
  { key: 'learning_report', label: 'AI 学习报告', desc: '生成周期性学习报告' },
  { key: 'cs_chat', label: 'AI 智能客服', desc: '解答平台使用与备考常见问题' },
]

const featureCatalog = ref(FALLBACK_FEATURES.map((f) => ({ ...f })))
const rawFeatureConfig = ref({})
const featureConfig = ref({})

function defaultFeatureItem() {
  return { enabled: true, model: '', temperature: 0.7, max_tokens: 2000 }
}

/** 按「功能目录 + 后端已存配置」重建可编辑副本（保留目录顺序） */
function syncFeatureConfig() {
  const next = {}
  for (const feat of featureCatalog.value) {
    const stored = rawFeatureConfig.value?.[feat.key] || {}
    next[feat.key] = {
      enabled: stored.enabled !== false,
      model: stored.model || '',
      temperature: stored.temperature ?? 0.7,
      max_tokens: stored.max_tokens ?? 2000,
    }
  }
  featureConfig.value = next
}

// 先用兜底目录初始化，保证模板中 featureConfig[key] 始终存在；后端返回后再对齐一次
syncFeatureConfig()

/* ------------------------------------------------------------------ *
 * 模型列表 / 元信息
 * ------------------------------------------------------------------ */
const models = ref([])
const modelsLoading = ref(false)
const modelMeta = ref({ limits: {}, defaultModelId: '', resolutionOrder: [], presets: [] })
const modelPresets = ref([])
const modelLimits = computed(() => modelMeta.value.limits || { global: 10, user: 5 })
const testingId = ref('')

/* ------------------------------------------------------------------ *
 * 模型新增 / 编辑表单（内联）
 * ------------------------------------------------------------------ */
const editingModelId = ref('')
const modelSaving = ref(false)
const modelForm = ref(emptyModelForm())

function emptyModelForm() {
  return {
    name: '',
    provider: 'openai',
    apiUrl: 'https://api.openai.com/v1/chat/completions',
    apiKey: '',
    model: 'gpt-4o-mini',
    temperature: 0.7,
    maxTokens: 2000,
    enabled: true,
    remark: '',
  }
}

/** 当前类型（供应商）预置的模型清单（供下拉选择，仍可手动输入） */
const currentPresetModels = computed(() => {
  const preset = modelPresets.value.find((p) => p.key === modelForm.value.provider)
  return (preset && preset.models) || []
})

function providerLabel(key) {
  const preset = modelPresets.value.find((p) => p.key === key)
  if (preset) return preset.name
  if (key === 'legacy') return '旧版单配置'
  return key || '自定义'
}

function modelNameById(id) {
  const item = models.value.find((m) => m._id === id)
  return item ? item.name : '-'
}

function onProviderChange(key) {
  const preset = modelPresets.value.find((p) => p.key === key)
  if (preset && preset.apiUrl) {
    modelForm.value.apiUrl = preset.apiUrl
  }
  if (preset && preset.models && preset.models.length) {
    modelForm.value.model = preset.models[0]
  }
}

function resetModelForm() {
  editingModelId.value = ''
  modelForm.value = emptyModelForm()
}

function focusAddForm() {
  resetModelForm()
  nextTick(() => {
    const el = document.getElementById('model-config-block')
    if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function editModel(row) {
  editingModelId.value = row._id
  modelForm.value = {
    name: row.name || '',
    provider: row.provider || 'custom',
    apiUrl: row.apiUrl || '',
    apiKey: row.apiKey || '', // 脱敏值：原样回传表示保持原 Key
    model: row.model || '',
    temperature: row.temperature ?? 0.7,
    maxTokens: row.maxTokens ?? 2000,
    enabled: row.enabled !== false,
    remark: row.remark || '',
  }
  nextTick(() => {
    const el = document.getElementById('model-config-block')
    if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

async function submitModel() {
  const f = modelForm.value
  if (!f.name.trim()) { ElMessage.warning('请输入模型名称'); return }
  if (!f.apiUrl.trim()) { ElMessage.warning('请输入 API 地址'); return }
  if (!f.apiKey.trim()) { ElMessage.warning('请输入 API Key'); return }
  if (!f.model.trim()) { ElMessage.warning('请输入模型标识'); return }

  modelSaving.value = true
  try {
    const payload = { ...f }
    if (editingModelId.value) {
      await aiApi.modelUpdate(editingModelId.value, payload)
      ElMessage.success('模型已更新，列表已同步')
    } else {
      await aiApi.modelCreate(payload)
      ElMessage.success('模型已添加，已自动同步到「AI 模型列表」')
    }
    resetModelForm()
    await loadModels()
  } catch (e) {
    // handled by interceptor
  } finally {
    modelSaving.value = false
  }
}

/* ------------------------------------------------------------------ *
 * 功能级配置 —— 模型下拉
 * ------------------------------------------------------------------ */
/** 某功能可选的模型（来自「AI 模型列表」），并兼容历史遗留值 */
function featureOptions(featKey) {
  const opts = models.value.map((m) => ({
    value: m._id,
    label: `${m.name} · ${m.model}`,
    disabled: m.enabled === false,
  }))
  const cur = featureConfig.value[featKey]?.model
  if (cur && !opts.some((o) => o.value === cur)) {
    const byRef = models.value.find((m) => m.model === cur || m.name === cur)
    opts.unshift({
      value: cur,
      label: byRef
        ? `${byRef.name} · ${byRef.model}（按标识匹配）`
        : `旧值：${cur}（未登记，将回退默认）`,
    })
  }
  return opts
}

/** 该功能当前实际会使用的模型（用于状态可视化） */
function featureModelName(featKey) {
  const cur = featureConfig.value[featKey]?.model
  if (!cur) {
    return modelMeta.value.defaultModelId
      ? `默认（${modelNameById(modelMeta.value.defaultModelId)}）`
      : '默认（未设置全局默认）'
  }
  const byId = models.value.find((m) => m._id === cur)
  if (byId) return `${byId.name} · ${byId.model}`
  const byRef = models.value.find((m) => m.model === cur || m.name === cur)
  if (byRef) return `${byRef.name} · ${byRef.model}（按标识匹配）`
  return `${cur}（未登记，将回退默认）`
}

/* ------------------------------------------------------------------ *
 * 数据加载 / 保存
 * ------------------------------------------------------------------ */
async function loadConfig() {
  try {
    const res = await aiApi.getConfig()
    if (!res) return
    form.value = {
      apiUrl: res.apiUrl || form.value.apiUrl,
      apiKey: res.apiKey || '',
      model: res.model || form.value.model,
      systemPrompt: res.systemPrompt || form.value.systemPrompt,
      temperature: res.temperature ?? 0.7,
      maxTokens: res.maxTokens ?? 2000,
      enabled: res.enabled ?? false,
    }
    rawFeatureConfig.value = res.feature_config || {}
    syncFeatureConfig()
  } catch (e) {
    // handled by interceptor
  }
}

async function saveConfig() {
  saving.value = true
  try {
    const payload = { ...form.value, feature_config: featureConfig.value }
    await aiApi.saveConfig(payload)
    ElMessage.success('配置已保存')
    await loadConfig()
  } catch (e) {
    // handled by interceptor
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testing.value = true
  testResult.value = null
  try {
    const res = await aiApi.test()
    testResult.value = { success: true, message: res?.response || '连接成功' }
    ElMessage.success('测试连接成功')
  } catch (e) {
    testResult.value = { success: false, message: e?.message || '连接失败' }
  } finally {
    testing.value = false
  }
}

async function loadModels() {
  modelsLoading.value = true
  try {
    const res = await aiApi.modelList()
    models.value = (res && res.list) || []
    if (res && res.meta) {
      modelMeta.value = res.meta
      modelPresets.value = res.meta.presets || []
      const remoteFeatures = res.meta.features
      if (Array.isArray(remoteFeatures) && remoteFeatures.length) {
        const nextKeys = remoteFeatures.map((f) => f.key).join(',')
        const curKeys = featureCatalog.value.map((f) => f.key).join(',')
        if (nextKeys !== curKeys) {
          featureCatalog.value = remoteFeatures
          syncFeatureConfig()
        }
      }
    }
  } catch (e) {
    // handled by interceptor
  } finally {
    modelsLoading.value = false
  }
}

async function testModel(row) {
  testingId.value = row._id
  try {
    const res = await aiApi.modelTest(row._id)
    ElMessage.success(`「${row.name}」连接成功：${(res && res.response) || 'ok'}`)
  } catch (e) {
    ElMessage.error(`「${row.name}」测试失败：${(e && e.message) || '未知错误'}`)
  } finally {
    testingId.value = ''
  }
}

async function setDefaultModel(row) {
  try {
    await aiApi.modelSetDefault(row._id)
    ElMessage.success(`已将「${row.name}」设为全局默认模型`)
    await loadModels()
  } catch (e) {
    // handled by interceptor
  }
}

async function removeModel(row) {
  try {
    await ElMessageBox.confirm(`确定删除模型「${row.name}」吗？`, '确认删除', { type: 'warning' })
  } catch (e) {
    return
  }
  try {
    await aiApi.modelDelete(row._id)
    ElMessage.success('模型已删除')
    if (editingModelId.value === row._id) resetModelForm()
    await loadModels()
  } catch (e) {
    // handled by interceptor
  }
}

onMounted(() => {
  loadConfig()
  loadModels()
})
</script>

<style scoped>
.slider-row {
  display: flex;
  align-items: center;
  width: 100%;
}

.slider-value {
  font-size: 14px;
  color: #606266;
  min-width: 30px;
  text-align: right;
}

.block-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.section-tip {
  font-size: 13px;
  color: #909399;
  line-height: 1.6;
}

.inline-hint {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
}

.ml8 {
  margin-left: 8px;
}

.legacy-collapse {
  max-width: 860px;
  margin-top: 8px;
}

.legacy-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #909399;
}

.legacy-alert {
  margin-bottom: 16px;
}

.test-result {
  margin-top: 20px;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid;
  max-width: 860px;
}

.test-success {
  background: #f0f9eb;
  border-color: #e1f3d8;
  color: #67c23a;
}

.test-fail {
  background: #fef0f0;
  border-color: #fde2e2;
  color: #f56c6c;
}

.test-result-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 8px;
}

.test-result-body {
  font-size: 13px;
  line-height: 1.6;
  padding-left: 22px;
  word-break: break-all;
}

.feature-card {
  margin-bottom: 16px;
}

.feature-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.feature-name {
  font-weight: 600;
  font-size: 14px;
}

.feature-desc {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
  line-height: 1.5;
}

.feature-model-state {
  margin-top: 6px;
  color: #606266;
}

.feature-alert {
  margin-bottom: 16px;
}

.model-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.model-usage {
  font-size: 13px;
  color: #606266;
}

.model-default-hint {
  color: #e6a23c;
}

.table-empty {
  padding: 12px 0;
  color: #909399;
  font-size: 13px;
}

.mono {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #606266;
}

.muted {
  color: #c0c4cc;
}

.model-order {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
  line-height: 1.8;
}

.order-step {
  display: inline-block;
  margin-right: 14px;
}
</style>
