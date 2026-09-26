<template>
  <div class="md-editor" :class="{ 'md-editor--compact': compact }">
    <!-- 工具栏 -->
    <div class="md-toolbar">
      <div class="md-toolbar-group">
        <button class="md-btn" title="一级标题" @click="prefixLine('# ')"><span class="md-btn-label">H1</span></button>
        <button class="md-btn" title="二级标题" @click="prefixLine('## ')"><span class="md-btn-label">H2</span></button>
        <button class="md-btn" title="三级标题" @click="prefixLine('### ')"><span class="md-btn-label">H3</span></button>
      </div>
      <span class="md-toolbar-sep"></span>
      <div class="md-toolbar-group">
        <button class="md-btn" title="加粗" @click="wrap('**', '**', '加粗文本')"><strong>B</strong></button>
        <button class="md-btn" title="斜体" @click="wrap('*', '*', '斜体文本')"><em>I</em></button>
        <button class="md-btn" title="删除线" @click="wrap('~~', '~~', '删除线文本')"><s>S</s></button>
        <button class="md-btn" title="行内代码" @click="wrap('`', '`', 'code')"><code style="font-size:11px">{ }</code></button>
      </div>
      <span class="md-toolbar-sep"></span>
      <div class="md-toolbar-group">
        <button class="md-btn" title="无序列表" @click="prefixLine('- ')">&#8226; 列表</button>
        <button class="md-btn" title="有序列表" @click="prefixLine('1. ')">1. 列表</button>
        <button class="md-btn" title="任务列表" @click="prefixLine('- [ ] ')">&#9744; 任务</button>
      </div>
      <span class="md-toolbar-sep"></span>
      <div class="md-toolbar-group">
        <button class="md-btn" title="引用" @click="prefixLine('> ')">&#8220; 引用</button>
        <button class="md-btn" title="代码块" @click="insertCodeBlock()">&#9116; 代码块</button>
        <button class="md-btn" title="表格" @click="insertTable()">&#9638; 表格</button>
        <button class="md-btn" title="分割线" @click="insertHr()">&#8213; 分割线</button>
      </div>
      <span class="md-toolbar-sep"></span>
      <div class="md-toolbar-group">
        <button class="md-btn" title="链接" @click="insertLink()">&#128279; 链接</button>
        <button v-if="uploadFn" class="md-btn" title="上传图片" @click="triggerUpload()">&#128247; 图片</button>
      </div>
      <div class="md-toolbar-spacer"></div>
      <button class="md-btn md-btn--toggle" :class="{ active: previewMode }" title="切换预览" @click="previewMode = !previewMode">
        {{ previewMode ? '编辑' : '预览' }}
      </button>
    </div>

    <!-- 编辑区 + 预览区 -->
    <div class="md-body">
      <textarea
        v-show="!previewMode"
        ref="taRef"
        v-model="innerContent"
        class="md-textarea"
        :placeholder="placeholder"
        :rows="rows"
        :style="{ height: compact ? '240px' : '500px' }"
        @input="onInput"
        @keydown.tab="onTab"
        @dragover.prevent="onDragOver"
        @drop.prevent="onDrop"
      ></textarea>
      <div v-show="previewMode" class="md-preview" :style="{ height: compact ? '240px' : '500px' }">
        <MarkdownRenderer :content="innerContent" />
      </div>
    </div>

    <!-- 隐藏的文件上传 -->
    <input v-if="uploadFn" ref="fileRef" type="file" accept="image/*" style="display:none" @change="onFileSelected" />
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import MarkdownRenderer from './MarkdownRenderer.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '请输入 Markdown 内容...' },
  rows: { type: Number, default: 18 },
  compact: { type: Boolean, default: false },
  uploadFn: { type: Function, default: null },
})

const emit = defineEmits(['update:modelValue', 'change'])

const taRef = ref(null)
const fileRef = ref(null)
const previewMode = ref(false)
const innerContent = ref(props.modelValue || '')

// 同步外部变化 -> 内部
watch(() => props.modelValue, (val) => {
  if (val !== innerContent.value) {
    innerContent.value = val || ''
  }
})

// 同步内部变化 -> 外部
function onInput() {
  emit('update:modelValue', innerContent.value)
  emit('change', innerContent.value)
}

// ---- 工具栏操作 ----

/** 包裹选中文本 */
function wrap(before, after, placeholder) {
  const ta = taRef.value
  if (!ta) return
  const start = ta.selectionStart
  const end = ta.selectionEnd
  const selected = innerContent.value.substring(start, end) || placeholder
  const replacement = before + selected + after
  innerContent.value = innerContent.value.substring(0, start) + replacement + innerContent.value.substring(end)
  emit('update:modelValue', innerContent.value)
  nextTick(() => {
    ta.focus()
    ta.setSelectionRange(start + before.length, start + before.length + selected.length)
  })
}

/** 行首添加前缀 */
function prefixLine(prefix) {
  const ta = taRef.value
  if (!ta) return
  const start = ta.selectionStart
  const lineStart = innerContent.value.lastIndexOf('\n', start - 1) + 1
  const newText = innerContent.value.substring(0, lineStart) + prefix + innerContent.value.substring(lineStart)
  innerContent.value = newText
  emit('update:modelValue', innerContent.value)
  nextTick(() => {
    ta.focus()
    ta.setSelectionRange(start + prefix.length, start + prefix.length)
  })
}

/** 插入代码块 */
function insertCodeBlock() {
  const ta = taRef.value
  if (!ta) return
  const start = ta.selectionStart
  const block = '\n```\n代码内容\n```\n'
  innerContent.value = innerContent.value.substring(0, start) + block + innerContent.value.substring(start)
  emit('update:modelValue', innerContent.value)
  nextTick(() => {
    ta.focus()
    const cursor = start + 5 // 定位到"代码内容"处
    ta.setSelectionRange(cursor, cursor + 4)
  })
}

/** 插入表格 */
function insertTable() {
  const ta = taRef.value
  if (!ta) return
  const start = ta.selectionStart
  const table = '\n| 列1 | 列2 | 列3 |\n|------|------|------|\n| 内容 | 内容 | 内容 |\n'
  innerContent.value = innerContent.value.substring(0, start) + table + innerContent.value.substring(start)
  emit('update:modelValue', innerContent.value)
  nextTick(() => {
    ta.focus()
    ta.setSelectionRange(start + table.length, start + table.length)
  })
}

/** 插入分割线 */
function insertHr() {
  const ta = taRef.value
  if (!ta) return
  const start = ta.selectionStart
  const hr = '\n---\n'
  innerContent.value = innerContent.value.substring(0, start) + hr + innerContent.value.substring(start)
  emit('update:modelValue', innerContent.value)
  nextTick(() => {
    ta.focus()
    ta.setSelectionRange(start + hr.length, start + hr.length)
  })
}

/** 插入链接 */
function insertLink() {
  const ta = taRef.value
  if (!ta) return
  const start = ta.selectionStart
  const end = ta.selectionEnd
  const selected = innerContent.value.substring(start, end) || '链接文字'
  const link = `[${selected}](https://)`
  innerContent.value = innerContent.value.substring(0, start) + link + innerContent.value.substring(end)
  emit('update:modelValue', innerContent.value)
  nextTick(() => {
    ta.focus()
    // 选中 URL 部分
    const urlStart = start + selected.length + 3
    ta.setSelectionRange(urlStart, urlStart + 8)
  })
}

// ---- Tab 键支持 ----
function onTab(e) {
  e.preventDefault()
  const ta = taRef.value
  if (!ta) return
  const start = ta.selectionStart
  const end = ta.selectionEnd
  innerContent.value = innerContent.value.substring(0, start) + '  ' + innerContent.value.substring(end)
  emit('update:modelValue', innerContent.value)
  nextTick(() => {
    ta.setSelectionRange(start + 2, start + 2)
  })
}

// ---- 图片上传 ----
function triggerUpload() {
  fileRef.value?.click()
}

async function onFileSelected(e) {
  const file = e.target.files?.[0]
  if (!file || !props.uploadFn) return
  try {
    const res = await props.uploadFn(file)
    const url = res?.url || res?.data?.url || ''
    if (url) {
      insertImage(url, file.name)
    }
  } catch (err) {
    // handled by caller
  } finally {
    e.target.value = '' // reset for re-upload
  }
}

function insertImage(url, alt) {
  const ta = taRef.value
  if (!ta) return
  const start = ta.selectionStart
  const img = `\n![${alt || '图片'}](${url})\n`
  innerContent.value = innerContent.value.substring(0, start) + img + innerContent.value.substring(start)
  emit('update:modelValue', innerContent.value)
  nextTick(() => {
    ta.focus()
    ta.setSelectionRange(start + img.length, start + img.length)
  })
}

// ---- 拖拽上传 ----
function onDragOver() {
  // placeholder for visual feedback
}

async function onDrop(e) {
  if (!props.uploadFn) return
  const file = e.dataTransfer?.files?.[0]
  if (!file || !file.type.startsWith('image/')) return
  try {
    const res = await props.uploadFn(file)
    const url = res?.url || res?.data?.url || ''
    if (url) insertImage(url, file.name)
  } catch (err) {
    // handled by caller
  }
}

// ---- 导出 HTML 转换方法 ----
defineExpose({
  /** 将当前 Markdown 转换为 HTML（用于提交时持久化） */
  toHtml() {
    const raw = innerContent.value || ''
    if (!raw.trim()) return ''
    const rendered = marked.parse(raw, { breaks: true, gfm: true })
    return DOMPurify.sanitize(rendered, { ADD_TAGS: ['mark'], ADD_ATTR: ['target'] })
  },
  /** 获取纯 Markdown */
  toMarkdown() {
    return innerContent.value || ''
  },
})
</script>

<style scoped>
.md-editor {
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.md-editor--compact {
  border-radius: 6px;
}

/* 工具栏 */
.md-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 6px 8px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
  flex-wrap: wrap;
}

.md-toolbar-group {
  display: flex;
  align-items: center;
  gap: 2px;
}

.md-toolbar-sep {
  width: 1px;
  height: 18px;
  background: #dcdfe6;
  margin: 0 4px;
}

.md-toolbar-spacer {
  flex: 1;
}

.md-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 28px;
  padding: 0 6px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  color: #606266;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
}

.md-btn:hover {
  background: #e8eaed;
  color: #303133;
}

.md-btn.active {
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
}

.md-btn--toggle {
  font-weight: 500;
  border: 1px solid #dcdfe6;
  padding: 0 12px;
}

.md-btn-label {
  font-weight: 600;
  font-size: 12px;
}

/* 编辑区 + 预览区 */
.md-body {
  display: flex;
  width: 100%;
  background: #fff;
}

.md-textarea {
  flex: 1;
  width: 100%;
  border: none;
  outline: none;
  resize: vertical;
  padding: 14px 16px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.7;
  color: #303133;
  background: #fff;
}

.md-textarea::placeholder {
  color: #c0c4cc;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.md-preview {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
  border-left: 1px solid #ebeef5;
  background: #fafbfc;
}
</style>
