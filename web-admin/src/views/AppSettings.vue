<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><Setting /></el-icon></span>
        应用设置
      </div>
      <div>
        <el-button type="primary" :loading="saving" @click="saveAll">
          <el-icon><Check /></el-icon>保存全部
        </el-button>
      </div>
    </div>

    <div class="card-block">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="关于我们" name="about">
          <el-form :model="aboutForm" label-width="100px">
            <el-form-item label="配置标识">
              <el-input v-model="aboutForm.doc_id" disabled style="width: 200px" />
            </el-form-item>
            <el-form-item label="标题">
              <el-input v-model="aboutForm.title" placeholder="关于我们" />
            </el-form-item>
            <el-form-item label="正文内容">
              <el-input v-model="aboutForm.content" type="textarea" :rows="8"
                placeholder="输入关于我们页面的展示内容" />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="考试规则" name="rules">
          <el-form :model="rulesForm" label-width="100px">
            <el-form-item label="配置标识">
              <el-input v-model="rulesForm.doc_id" disabled style="width: 200px" />
            </el-form-item>
            <el-form-item label="标题">
              <el-input v-model="rulesForm.title" placeholder="使用说明" />
            </el-form-item>
            <el-form-item label="规则条目">
              <div class="rules-editor">
                <div v-for="(item, idx) in rulesForm.items" :key="idx" class="rule-row">
                  <span class="rule-num">{{ idx + 1 }}</span>
                  <el-input v-model="rulesForm.items[idx]" placeholder="输入规则内容" style="flex: 1" />
                  <el-button type="danger" text @click="removeRule(idx)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>
                <el-button type="primary" plain @click="addRule" style="margin-top: 12px">
                  <el-icon><Plus /></el-icon>添加条目
                </el-button>
              </div>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting, Check, Delete, Plus } from '@element-plus/icons-vue'
import { resource } from '../api'

const appSettingsApi = resource('app-settings')
const activeTab = ref('about')
const saving = ref(false)

const aboutForm = ref({
  doc_id: 'about',
  title: '关于我们',
  content:
    '考试宝是一款专注于在线模拟考试与学习测评的教育辅助平台，致力于为考生提供高效、便捷的备考体验。\n\n' +
    '【系统简介】\n' +
    '本系统涵盖多学科题库资源，支持单题练习、模拟考试、错题回顾、智能组卷等多种学习模式。通过AI技术赋能，系统可为每位考生生成个性化学习画像、复习计划与能力分析报告，助力精准提分。\n\n' +
    '【服务宗旨】\n' +
    '以考生为中心，以技术为驱动，提供专业、公正、智能的在线考试与学习服务，帮助每一位用户高效备考、稳步提升。\n\n' +
    '【团队介绍】\n' +
    '我们的团队由资深教育专家与技术开发人员组成，拥有丰富的题库建设、考试系统设计与AI应用经验。团队成员持续优化系统功能与内容质量，确保为用户提供可靠、专业的学习平台。\n\n' +
    '【联系方式】\n' +
    '如有任何疑问或建议，欢迎通过小程序内"意见反馈"功能与我们取得联系，我们将及时为您解答。',
  _id: '',
})

const rulesForm = ref({
  doc_id: 'rules',
  title: '考试规则',
  items: [
    '【考试流程】进入考试前，请确保网络连接稳定，建议在WiFi环境下进行，以获得流畅的答题体验。',
    '【考试流程】系统提供"单题模式"与"列表模式"两种答题方式，考生可根据个人习惯自行选择。',
    '【考试流程】每场考试共10道题目，每题1分，满分10分，请在规定时间内完成全部作答。',
    '【考试流程】答题过程中可随时切换题目，系统自动保存已作答内容，支持中途退出后断点续答。',
    '【考试流程】提交试卷后，系统将自动生成成绩报告，并支持查看每道题的详细解析与知识点关联。',
    '【评分标准】客观题（单选题、多选题、判断题）由系统自动评阅，答案完全匹配方可得分。',
    '【评分标准】主观题（填空题、简答题）采用AI智能评分与人工复核相结合的方式，确保评分结果公正客观。',
    '【评分标准】每场考试成绩即时生成并记录，历史成绩可在"答题记录"模块中随时查阅。',
    '【评分标准】系统将根据答题正确率、答题用时等维度综合评估学习水平，自动生成个性化学习画像。',
    '【违规处理】考试过程中如检测到异常行为（如频繁切屏、使用外部辅助工具等），系统将自动记录并发出警告。',
    '【违规处理】多次违规者，管理员有权暂停其考试权限；情节严重者，账号将被永久封禁。',
    '【违规处理】对考试成绩或评分结果有异议者，可在考试结束后通过"错题笔记"功能提交复核申请。',
    '【注意事项】请勿在考试期间强制退出小程序或关闭页面，以免造成答题数据丢失或考试异常。',
    '【注意事项】考试成绩和错题记录将自动同步至个人账户，可在"错题本"中复习巩固薄弱知识点。',
    '【注意事项】建议定期进行模拟考试，结合系统提供的AI分析与复习推荐，持续提升备考效果。',
    '【注意事项】如遇系统异常或技术问题，请及时通过"意见反馈"功能联系我们，我们将尽快处理。',
  ],
  _id: '',
})

async function loadSettings() {
  // 加载"关于我们"
  try {
    const res = await appSettingsApi.list({ doc_id: 'about' })
    const list = res?.list || []
    if (list.length > 0) {
      const item = list[0]
      // 显式映射字段，避免后端额外字段（_created_at/_updated_at 等）污染表单
      aboutForm.value = {
        doc_id: item.doc_id || 'about',
        title: item.title || '关于我们',
        content: item.content || '',
        _id: item._id || item.id || '',
      }
    }
  } catch (e) {
    // 接口不存在或无权限时静默处理，保留默认值
  }

  // 加载"考试规则"
  try {
    const res = await appSettingsApi.list({ doc_id: 'rules' })
    const list = res?.list || []
    if (list.length > 0) {
      const item = list[0]
      // 确保 items 始终为数组，兼容后端返回 null/undefined 的情况
      const items = Array.isArray(item.items) ? item.items.filter((s) => s != null) : []
      rulesForm.value = {
        doc_id: item.doc_id || 'rules',
        title: item.title || '考试规则',
        items: items.length > 0 ? items : rulesForm.value.items,
        _id: item._id || item.id || '',
      }
    }
  } catch (e) {
    // 接口不存在或无权限时静默处理，保留默认值
  }
}

function addRule() {
  rulesForm.value.items.push('')
}

function removeRule(idx) {
  rulesForm.value.items.splice(idx, 1)
}

async function saveAll() {
  saving.value = true
  try {
    // Save about —— 仅提交业务字段，排除后端额外字段
    const aboutData = {
      doc_id: aboutForm.value.doc_id,
      title: aboutForm.value.title,
      content: aboutForm.value.content,
    }
    if (aboutForm.value._id) {
      await appSettingsApi.update(aboutForm.value._id, aboutData)
    } else {
      const res = await appSettingsApi.create(aboutData)
      if (res._id) aboutForm.value._id = res._id
    }

    // Save rules —— 仅提交业务字段
    const rulesData = {
      doc_id: rulesForm.value.doc_id,
      title: rulesForm.value.title,
      items: rulesForm.value.items.filter((s) => s != null && s !== ''),
    }
    if (rulesForm.value._id) {
      await appSettingsApi.update(rulesForm.value._id, rulesData)
    } else {
      const res = await appSettingsApi.create(rulesData)
      if (res._id) rulesForm.value._id = res._id
    }

    ElMessage.success('设置已保存')
  } catch (e) {
    ElMessage.error('保存失败：' + (e.message || '未知错误'))
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadSettings()
})
</script>

<style scoped>
.rules-editor {
  width: 100%;
}

.rule-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.rule-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #4a90f3;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}
</style>
