<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><EditPen /></el-icon></span>
        {{ isEdit ? '编辑文章' : '新建文章' }}
      </div>
      <div>
        <el-button @click="goBack"><el-icon><Back /></el-icon>返回</el-button>
        <el-button v-if="canUseAI" type="success" :loading="aiLoading" @click="aiAssist">
          <el-icon><MagicStick /></el-icon>AI 辅助撰写
        </el-button>
        <el-button type="primary" :loading="saving" @click="submit">
          <el-icon><Check /></el-icon>保存
        </el-button>
      </div>
    </div>

    <div class="card-block" v-loading="pageLoading">
      <el-form :model="form" label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="请输入文章标题" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="作者">
          <el-input v-model="form.author" placeholder="请输入作者名称" />
        </el-form-item>
        <el-form-item label="摘要">
          <el-input v-model="form.summary" type="textarea" :rows="2" placeholder="文章摘要（可选）" />
        </el-form-item>
        <el-form-item label="正文内容" required>
          <MarkdownEditor
            ref="editorRef"
            v-model="form.content"
            :upload-fn="uploadImage"
            placeholder="支持 Markdown 格式：# 标题 / ## 二级标题 / **加粗** / *斜体* / - 列表 / > 引用 / `代码` / | 表格 |"
          />
        </el-form-item>
        <el-form-item label="图片">
          <el-upload
            :file-list="fileList"
            list-type="picture-card"
            :auto-upload="true"
            :http-request="customUpload"
            :limit="3"
            :on-exceed="onExceed"
            :on-remove="onRemoveImage"
            accept="image/*"
          >
            <el-icon><Plus /></el-icon>
          </el-upload>
          <div class="upload-tip">最多上传 3 张图片（也可在正文编辑器中直接插入图片）</div>
        </el-form-item>
        <el-form-item label="标签">
          <el-select v-model="form.tags" multiple filterable allow-create
            :multiple-limit="5" placeholder="输入标签后回车，最多 5 个" style="width: 100%">
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 200px">
            <el-option label="待审核" value="pending" />
            <el-option label="已发布" value="published" />
            <el-option label="已驳回" value="rejected" />
            <el-option label="已下架" value="taken_down" />
          </el-select>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { EditPen, Back, Check, Plus, MagicStick } from '@element-plus/icons-vue'
import { articleApi, aiApi, uploadApi } from '../api'
import { useUserStore } from '../stores/user'
import MarkdownEditor from '../components/MarkdownEditor.vue'

const route = useRoute()
const router = useRouter()
const user = useUserStore()
const canUseAI = user.hasPerm('ai.use') || user.hasPerm('ai.config')

const editId = computed(() => route.params.id || '')
const isEdit = computed(() => !!editId.value)

const editorRef = ref(null)

const form = ref({
  title: '',
  author: '考试宝',
  summary: '',
  content: '',
  images: [],
  tags: [],
  status: 'pending',
})

const fileList = ref([])
const saving = ref(false)
const aiLoading = ref(false)
const pageLoading = ref(false)

// ---- 图片上传（编辑器内调用）----
async function uploadImage(file) {
  const res = await uploadApi.image(file)
  return res
}

// ---- 图片上传（el-upload 组件调用）----
async function customUpload(options) {
  try {
    const res = await uploadApi.image(options.file)
    const url = res?.url || res?.data?.url || ''
    if (url) {
      form.value.images.push(url)
      fileList.value.push({ name: options.file.name, url: url })
    } else {
      ElMessage.error('上传失败：未返回图片地址')
    }
  } catch (e) {
    ElMessage.error('图片上传失败')
  }
}

function onExceed() {
  ElMessage.warning('最多上传 3 张图片')
}

function onRemoveImage(file) {
  const url = file.url || file?.response?.url
  const idx = form.value.images.indexOf(url)
  if (idx > -1) {
    form.value.images.splice(idx, 1)
  }
}

// ---- AI 辅助 ----
async function aiAssist() {
  if (!form.value.title || !form.value.title.trim()) {
    ElMessage.warning('请先输入文章标题')
    return
  }
  aiLoading.value = true
  try {
    const res = await aiApi.assist({ prompt: form.value.title, context: form.value.summary })
    if (res?.content) {
      form.value.content = res.content
      ElMessage.success('AI 生成成功')
    } else {
      ElMessage.warning('AI 未返回内容')
    }
  } catch (e) {
    // 拦截器已统一提示业务错误；此处兜底防止无 response 的网络异常静默失败
    if (e && !e.response && !e.code) {
      ElMessage.error('AI 辅助请求失败，请检查网络后重试')
    }
  } finally {
    aiLoading.value = false
  }
}

// ---- 保存 ----
async function submit() {
  if (!form.value.title || !form.value.title.trim()) {
    ElMessage.warning('请填写文章标题')
    return
  }
  if (!form.value.content || !form.value.content.trim()) {
    ElMessage.warning('请填写文章正文内容')
    return
  }
  saving.value = true
  try {
    const payload = { ...form.value }
    // 提交时将 Markdown 转换为 HTML 一并持久化存储
    payload.content_html = editorRef.value?.toHtml() || ''
    if (isEdit.value) {
      await articleApi.update(editId.value, payload)
      ElMessage.success('保存成功')
    } else {
      await articleApi.create(payload)
      ElMessage.success('新建成功')
    }
    router.push('/articles')
  } catch (e) {
    // handled by interceptor
  } finally {
    saving.value = false
  }
}

function goBack() {
  router.push('/articles')
}

// ---- 加载已有文章 ----
async function loadArticle() {
  if (!editId.value) return
  pageLoading.value = true
  try {
    const res = await articleApi.get(editId.value)
    if (res) {
      form.value = {
        title: res.title || '',
        author: res.author || '考试宝',
        summary: res.summary || '',
        // 兼容字段：优先 content（Markdown 原文），回退 content_md
        content: res.content || res.content_md || '',
        images: Array.isArray(res.images) ? res.images : [],
        tags: Array.isArray(res.tags) ? res.tags : [],
        status: res.status || 'pending',
      }
      fileList.value = (form.value.images).map((url, i) => ({ name: `image-${i + 1}`, url }))
    }
  } catch (e) {
    // handled by interceptor
  } finally {
    pageLoading.value = false
  }
}

onMounted(() => {
  loadArticle()
})
</script>

<style scoped>
.upload-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
