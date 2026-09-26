<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><Reading /></el-icon></span>
        知识库管理
      </div>
      <div>
        <el-button v-if="canManage" type="danger" plain :disabled="!selection.length" @click="bulkRemove">
          <el-icon><Delete /></el-icon>批量删除（{{ selection.length }}）
        </el-button>
        <el-button v-if="canManage" type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>新建文档
        </el-button>
      </div>
    </div>

    <!-- RAG 索引状态 -->
    <div class="kb-index-bar">
      <div class="kb-index-stats">
        <div class="kb-index-stat">
          <div class="kb-index-num">{{ kbStats.corpus_size || 0 }}</div>
          <div class="kb-index-label">索引语料</div>
        </div>
        <div class="kb-index-stat">
          <div class="kb-index-num">{{ kbStats.kb_count || 0 }}</div>
          <div class="kb-index-label">知识库文档</div>
        </div>
        <div class="kb-index-stat">
          <div class="kb-index-num">{{ kbStats.article_count || 0 }}</div>
          <div class="kb-index-label">来自文章</div>
        </div>
        <div class="kb-index-stat">
          <div class="kb-index-num">{{ kbStats.cache_count || 0 }}</div>
          <div class="kb-index-label">问答缓存</div>
        </div>
      </div>
      <div class="kb-index-actions">
        <span class="kb-index-time">最近构建：{{ kbStats.last_built_at || '尚未构建' }}</span>
        <el-button link type="primary" @click="openIndexedArticles">
          <el-icon><List /></el-icon>已索引文章（{{ kbStats.article_count || 0 }}）
        </el-button>
        <el-button v-if="canBuildIndex" type="success" plain :loading="rebuilding" @click="rebuildIndex">
          <el-icon><Refresh /></el-icon>构建 RAG 索引
        </el-button>
      </div>
    </div>

    <div class="card-block">
      <!-- 工具栏 -->
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索标题/分类/摘要" clearable style="width: 240px"
          @keyup.enter="load" @clear="load">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="filterType" placeholder="文档类型" clearable style="width: 140px" @change="load">
          <el-option v-for="t in typeOptions" :key="t.value" :label="t.label" :value="t.value" />
        </el-select>
        <el-button type="primary" @click="load"><el-icon><Search /></el-icon>查询</el-button>
        <el-button @click="resetFilters"><el-icon><RefreshLeft /></el-icon>重置</el-button>
      </div>

      <!-- 表格 -->
      <el-table v-loading="loading" :data="list" border stripe size="default" @selection-change="onSelection">
        <el-table-column v-if="canManage" type="selection" width="46" />
        <el-table-column prop="_id" label="文档ID" width="180" show-overflow-tooltip />
        <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="cell-strong">{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag :type="typeTagType(row.type)" size="small">{{ typeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="160" show-overflow-tooltip />
        <el-table-column prop="pages" label="页数" width="70" align="center" />
        <el-table-column prop="views" label="阅读" width="70" align="center" />
        <el-table-column prop="sortWeight" label="权重" width="70" align="center" />
        <el-table-column prop="_updated_at" label="更新时间" width="160" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)"><el-icon><View /></el-icon>详情</el-button>
            <el-button v-if="canManage" link type="primary" @click="openEdit(row)"><el-icon><Edit /></el-icon>编辑</el-button>
            <el-button v-if="canManage" link type="danger" @click="removeOne(row)"><el-icon><Delete /></el-icon>删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @current-change="load"
          @size-change="load"
        />
      </div>
    </div>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑文档' : '新建文档'" width="900px" :close-on-click-modal="false">
      <el-form :model="form" label-width="100px">
        <el-form-item label="文档ID" v-if="!isEdit">
          <el-input v-model="form._id" placeholder="如 KB_RJJS_TB_CH01（留空自动生成）" />
        </el-form-item>
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="文档标题" />
        </el-form-item>
        <el-form-item label="文档类型" required>
          <el-select v-model="form.type" placeholder="选择类型" style="width: 100%">
            <el-option v-for="t in typeOptions" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="form.category" placeholder="如 软件设计师" />
        </el-form-item>
        <el-form-item label="摘要">
          <el-input v-model="form.summary" type="textarea" :rows="2" placeholder="文档摘要简介" />
        </el-form-item>
        <el-form-item label="正文内容">
          <MarkdownEditor
            ref="editorRef"
            v-model="form.content"
            compact
            placeholder="支持 Markdown 格式：# 标题 / ## 二级 / **高亮** / 普通段落（空行分隔）"
          />
        </el-form-item>
        <el-form-item label="页数">
          <el-input-number v-model="form.pages" :min="0" :max="9999" controls-position="right" />
        </el-form-item>
        <el-form-item label="排序权重">
          <el-input-number v-model="form.sortWeight" :min="0" :max="999" controls-position="right" />
        </el-form-item>
        <el-collapse>
          <el-collapse-item title="书籍关联与目录（可选，教材类型使用）" name="book">
            <el-form-item label="书籍ID">
              <el-input v-model="form.bookId" placeholder="如 BK_RJJS" />
            </el-form-item>
            <el-form-item label="书籍名称">
              <el-input v-model="form.bookTitle" placeholder="如 软件设计师教程" />
            </el-form-item>
            <el-form-item label="章节号">
              <el-input-number v-model="form.chapterNo" :min="0" :max="99" controls-position="right" />
            </el-form-item>
            <el-form-item label="章节标题">
              <el-input v-model="form.chapterTitle" placeholder="如 计算机系统基础知识" />
            </el-form-item>

            <!-- TOC 目录编辑区 -->
            <el-divider content-position="left">
              <span class="toc-divider-label">目录结构（TOC）</span>
            </el-divider>
            <div class="toc-editor">
              <div v-if="!form.toc || !form.toc.length" class="toc-empty">
                暂无目录条目，点击下方按钮添加
              </div>

              <!-- 一级目录 -->
              <div v-for="(entry, idx) in form.toc" :key="idx" class="toc-entry toc-l1-item">
                <div class="toc-entry-row">
                  <el-tag size="small" type="warning" class="toc-level-tag">L1</el-tag>
                  <el-input v-model="entry.title" placeholder="一级目录标题，如 1.1 计算机系统组成" size="small" class="toc-title-input" />
                  <el-input-number v-model="entry.page" :min="0" :max="9999" size="small" controls-position="right" class="toc-page-input" placeholder="页码" />
                  <el-button-group class="toc-sort-btns">
                    <el-button size="small" :disabled="idx === 0" @click="moveTocEntry(idx, -1)" title="上移">↑</el-button>
                    <el-button size="small" :disabled="idx === form.toc.length - 1" @click="moveTocEntry(idx, 1)" title="下移">↓</el-button>
                  </el-button-group>
                  <el-button size="small" type="success" plain @click="addTocChild(idx)">+ 子级</el-button>
                  <el-button size="small" type="danger" plain @click="removeTocEntry(idx)">删除</el-button>
                </div>

                <!-- 二级目录 -->
                <div v-if="entry.children && entry.children.length" class="toc-children">
                  <div v-for="(child, cidx) in entry.children" :key="cidx" class="toc-entry toc-l2-item">
                    <div class="toc-entry-row">
                      <el-tag size="small" type="info" class="toc-level-tag">L2</el-tag>
                      <el-input v-model="child.title" placeholder="二级目录标题，如 1.1.1 硬件系统" size="small" class="toc-title-input" />
                      <el-input-number v-model="child.page" :min="0" :max="9999" size="small" controls-position="right" class="toc-page-input" />
                      <el-button-group class="toc-sort-btns">
                        <el-button size="small" :disabled="cidx === 0" @click="moveTocChild(idx, cidx, -1)" title="上移">↑</el-button>
                        <el-button size="small" :disabled="cidx === entry.children.length - 1" @click="moveTocChild(idx, cidx, 1)" title="下移">↓</el-button>
                      </el-button-group>
                      <el-button size="small" type="success" plain @click="addTocGrandchild(idx, cidx)">+ 子级</el-button>
                      <el-button size="small" type="danger" plain @click="removeTocChild(idx, cidx)">删除</el-button>
                    </div>

                    <!-- 三级目录 -->
                    <div v-if="child.children && child.children.length" class="toc-children">
                      <div v-for="(gc, gidx) in child.children" :key="gidx" class="toc-entry toc-l3-item">
                        <div class="toc-entry-row">
                          <el-tag size="small" type="success" class="toc-level-tag">L3</el-tag>
                          <el-input v-model="gc.title" placeholder="三级目录标题" size="small" class="toc-title-input" />
                          <el-input-number v-model="gc.page" :min="0" :max="9999" size="small" controls-position="right" class="toc-page-input" />
                          <el-button-group class="toc-sort-btns">
                            <el-button size="small" :disabled="gidx === 0" @click="moveTocGrandchild(idx, cidx, gidx, -1)" title="上移">↑</el-button>
                            <el-button size="small" :disabled="gidx === child.children.length - 1" @click="moveTocGrandchild(idx, cidx, gidx, 1)" title="下移">↓</el-button>
                          </el-button-group>
                          <el-button size="small" type="danger" plain @click="removeTocGrandchild(idx, cidx, gidx)">删除</el-button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <el-button type="primary" plain size="small" @click="addTocEntry" class="toc-add-btn">
                <el-icon><Plus /></el-icon> 添加一级目录
              </el-button>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取 消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保 存</el-button>
      </template>
    </el-dialog>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="文档详情" width="680px">
      <template v-if="detailDoc">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="文档ID">{{ detailDoc._id }}</el-descriptions-item>
          <el-descriptions-item label="类型">
            <el-tag :type="typeTagType(detailDoc.type)" size="small">{{ typeLabel(detailDoc.type) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="标题" :span="2">{{ detailDoc.title }}</el-descriptions-item>
          <el-descriptions-item label="分类">{{ detailDoc.category || '—' }}</el-descriptions-item>
          <el-descriptions-item label="页数">{{ detailDoc.pages || 0 }}页</el-descriptions-item>
          <el-descriptions-item label="阅读数">{{ detailDoc.views || 0 }}</el-descriptions-item>
          <el-descriptions-item label="排序权重">{{ detailDoc.sortWeight || 0 }}</el-descriptions-item>
          <el-descriptions-item label="书籍" :span="2" v-if="detailDoc.bookTitle">
            {{ detailDoc.bookTitle }} · 第{{ detailDoc.chapterNo || '?' }}章 {{ detailDoc.chapterTitle || '' }}
          </el-descriptions-item>
          <el-descriptions-item label="摘要" :span="2" v-if="detailDoc.summary">{{ detailDoc.summary }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="detailDoc.content" class="detail-content">
          <div class="detail-content-title">正文内容</div>
          <pre class="detail-content-body">{{ detailDoc.content }}</pre>
        </div>
        <div v-if="detailDoc.toc && detailDoc.toc.length" class="detail-toc">
          <div class="detail-content-title">目录结构（{{ tocTotalCount(detailDoc.toc) }} 条）</div>
          <div v-for="(t, ti) in detailDoc.toc" :key="ti" class="toc-line">
            <div class="toc-l1">
              <span class="toc-l1-icon">📖</span>
              <span class="toc-l1-title">{{ t.title }}</span>
              <span v-if="t.page" class="toc-page-tag">P{{ t.page }}</span>
            </div>
            <div v-for="(c, ci) in (t.children || [])" :key="ci" class="toc-l2">
              <span class="toc-l2-title">· {{ c.title }}</span>
              <span v-if="c.page" class="toc-page-tag">P{{ c.page }}</span>
              <div v-for="(gc, gi) in (c.children || [])" :key="gi" class="toc-l3">
                <span class="toc-l3-title">○ {{ gc.title }}</span>
                <span v-if="gc.page" class="toc-page-tag">P{{ gc.page }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 已索引文章（可追溯：文章编码 ↔ 索引条目） -->
    <el-dialog v-model="indexedVisible" title="已纳入索引的文章" width="820px">
      <div class="indexed-tip">
        索引条目 _id 规则为 <code>KB_ART_&lt;文章编码&gt;</code>，可由此双向追溯文章与索引。
      </div>
      <el-table :data="indexedArticles" border stripe size="small" max-height="420">
        <el-table-column prop="article_code" label="文章编码" width="190">
          <template #default="{ row }">
            <el-tag size="small" type="success">{{ row.article_code }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="文章标题" min-width="220" show-overflow-tooltip />
        <el-table-column prop="kb_doc_id" label="索引条目 _id" width="220" show-overflow-tooltip />
        <el-table-column prop="indexed_at" label="加入时间" width="160" />
      </el-table>
      <template #footer>
        <el-button @click="indexedVisible = false">关 闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Reading, Plus, Delete, Edit, Search, RefreshLeft, View, Refresh, List } from '@element-plus/icons-vue'
import { resource, aiApi } from '../api'
import { useUserStore } from '../stores/user'
import MarkdownEditor from '../components/MarkdownEditor.vue'

const user = useUserStore()
const canManage = user.hasPerm('knowledge.manage')
const canBuildIndex = user.hasPerm('ai.config')
const kbApi = resource('knowledge')

const typeOptions = [
  { value: 'textbook', label: '教材' },
  { value: 'summary', label: '总结' },
  { value: 'notes', label: '笔记' },
  { value: 'quickref', label: '速记' },
]

function typeLabel(type) {
  const found = typeOptions.find((t) => t.value === type)
  return found ? found.label : type || '文档'
}

function typeTagType(type) {
  const map = { textbook: 'warning', summary: 'danger', notes: 'info', quickref: 'success' }
  return map[type] || ''
}

// ---- 列表 ----
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const filterType = ref('')
const selection = ref([])

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (filterType.value) params.type = filterType.value
    const res = await kbApi.list(params)
    list.value = res?.list || []
    total.value = res?.total || 0
  } catch (e) {
    // error toast handled by http interceptor
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  keyword.value = ''
  filterType.value = ''
  page.value = 1
  load()
}

function onSelection(rows) {
  selection.value = rows
}

// ---- 新建/编辑 ----
const dialogVisible = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const form = ref({})
const editorRef = ref(null)

function defaultForm() {
  return {
    _id: '',
    title: '',
    type: 'textbook',
    category: '',
    summary: '',
    content: '',
    pages: 0,
    sortWeight: 50,
    bookId: '',
    bookTitle: '',
    chapterNo: 0,
    chapterTitle: '',
    toc: [],
  }
}

function openCreate() {
  isEdit.value = false
  form.value = defaultForm()
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  form.value = {
    _id: row._id,
    title: row.title || '',
    type: row.type || 'textbook',
    category: row.category || '',
    summary: row.summary || '',
    content: row.content || '',
    // el-input-number 需要数字类型，后端可能返回字符串
    pages: Number(row.pages) || 0,
    sortWeight: Number(row.sortWeight) || 0,
    bookId: row.bookId || '',
    bookTitle: row.bookTitle || '',
    chapterNo: Number(row.chapterNo) || 0,
    chapterTitle: row.chapterTitle || '',
    toc: row.toc ? JSON.parse(JSON.stringify(row.toc)) : [],
  }
  dialogVisible.value = true
}

// ---- TOC 目录编辑操作 ----
function addTocEntry() {
  if (!form.value.toc) form.value.toc = []
  form.value.toc.push({ title: '', page: 0, level: 1, children: [] })
}

function removeTocEntry(idx) {
  form.value.toc.splice(idx, 1)
}

function moveTocEntry(idx, dir) {
  const arr = form.value.toc
  const target = idx + dir
  if (target < 0 || target >= arr.length) return
  const tmp = arr[idx]
  arr[idx] = arr[target]
  arr[target] = tmp
}

function addTocChild(idx) {
  const entry = form.value.toc[idx]
  if (!entry.children) entry.children = []
  entry.children.push({ title: '', page: 0, level: 2, children: [] })
}

function removeTocChild(idx, cidx) {
  form.value.toc[idx].children.splice(cidx, 1)
}

function moveTocChild(idx, cidx, dir) {
  const arr = form.value.toc[idx].children
  const target = cidx + dir
  if (target < 0 || target >= arr.length) return
  const tmp = arr[cidx]
  arr[cidx] = arr[target]
  arr[target] = tmp
}

function addTocGrandchild(idx, cidx) {
  const child = form.value.toc[idx].children[cidx]
  if (!child.children) child.children = []
  child.children.push({ title: '', page: 0, level: 3 })
}

function removeTocGrandchild(idx, cidx, gidx) {
  form.value.toc[idx].children[cidx].children.splice(gidx, 1)
}

function moveTocGrandchild(idx, cidx, gidx, dir) {
  const arr = form.value.toc[idx].children[cidx].children
  const target = gidx + dir
  if (target < 0 || target >= arr.length) return
  const tmp = arr[gidx]
  arr[gidx] = arr[target]
  arr[target] = tmp
}

// 统计 TOC 总条目数（含子级）
function tocTotalCount(toc) {
  if (!toc) return 0
  let count = toc.length
  for (const entry of toc) {
    if (entry.children) count += entry.children.length
    for (const child of (entry.children || [])) {
      if (child.children) count += child.children.length
    }
  }
  return count
}

// TOC 表单校验：返回错误信息或 null
function validateToc(toc) {
  if (!toc || !toc.length) return null
  for (let i = 0; i < toc.length; i++) {
    if (!toc[i].title || !toc[i].title.trim()) {
      return `目录第 ${i + 1} 条一级目录标题不能为空`
    }
    if (toc[i].children && toc[i].children.length) {
      for (let j = 0; j < toc[i].children.length; j++) {
        if (!toc[i].children[j].title || !toc[i].children[j].title.trim()) {
          return `目录第 ${i + 1} 条的第 ${j + 1} 个二级子目录标题不能为空`
        }
        if (toc[i].children[j].children && toc[i].children[j].children.length) {
          for (let k = 0; k < toc[i].children[j].children.length; k++) {
            if (!toc[i].children[j].children[k].title || !toc[i].children[j].children[k].title.trim()) {
              return `目录第 ${i + 1} 条的第 ${j + 1} 个子目录的第 ${k + 1} 个三级标题不能为空`
            }
          }
        }
      }
    }
  }
  return null
}

async function submit() {
  if (!form.value.title || !form.value.title.trim()) {
    ElMessage.warning('请填写标题')
    return
  }
  // TOC 校验
  const tocError = validateToc(form.value.toc)
  if (tocError) {
    ElMessage.warning(tocError)
    return
  }
  // 清理空 children 数组，确保数据干净
  const payload = { ...form.value }
  if (payload.toc && payload.toc.length) {
    payload.toc = payload.toc.map((entry) => {
      const clean = { title: entry.title.trim(), page: entry.page || 0, level: entry.level || 1 }
      if (entry.children && entry.children.length) {
        clean.children = entry.children.map((child) => {
          const cleanChild = { title: child.title.trim(), page: child.page || 0, level: child.level || 2 }
          if (child.children && child.children.length) {
            cleanChild.children = child.children.map((gc) => ({
              title: gc.title.trim(), page: gc.page || 0, level: gc.level || 3,
            }))
          }
          return cleanChild
        })
      }
      return clean
    })
  } else {
    payload.toc = []
  }
  if (isEdit.value) delete payload._id
  // 提交时将 Markdown 转换为 HTML 一并持久化存储
  payload.content_html = editorRef.value?.toHtml() || ''
  saving.value = true
  try {
    if (isEdit.value) {
      await kbApi.update(form.value._id, payload)
      ElMessage.success('保存成功')
    } else {
      await kbApi.create(payload)
      ElMessage.success('新建成功')
    }
    dialogVisible.value = false
    load()
  } catch (e) {
    // handled by interceptor
  } finally {
    saving.value = false
  }
}

// ---- 删除 ----
async function removeOne(row) {
  try {
    await ElMessageBox.confirm(`确定删除文档「${row.title}」？删除后不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
    await kbApi.remove(row._id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    // cancelled or error
  }
}

async function bulkRemove() {
  const ids = selection.value.map((r) => r._id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`确定批量删除选中的 ${ids.length} 篇文档？`, '批量删除', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
    })
    await kbApi.bulkDelete(ids)
    ElMessage.success('批量删除成功')
    selection.value = []
    load()
  } catch (e) {
    // cancelled or error
  }
}

// ---- 详情 ----
const detailVisible = ref(false)
const detailDoc = ref(null)

async function openDetail(row) {
  try {
    const res = await kbApi.get(row._id)
    detailDoc.value = res
    detailVisible.value = true
  } catch (e) {
    // handled by interceptor
  }
}

// ---- RAG 索引：统计 / 构建 / 已索引文章 ----
const kbStats = ref({})
const rebuilding = ref(false)
const indexedVisible = ref(false)
const indexedArticles = ref([])

async function loadStats() {
  try {
    const res = await aiApi.kbStats()
    kbStats.value = res || {}
  } catch (e) {
    // handled by interceptor
  }
}

async function rebuildIndex() {
  try {
    await ElMessageBox.confirm(
      '将基于当前知识库（含已加入的文章）重建 RAG 索引，并清空历史问答缓存。确定继续？',
      '构建 RAG 索引',
      { type: 'warning', confirmButtonText: '开始构建', cancelButtonText: '取消' },
    )
  } catch (e) {
    return
  }
  rebuilding.value = true
  try {
    const res = await aiApi.kbRebuild()
    ElMessage.success(
      `索引构建完成：语料 ${res?.corpus_size || 0} 条（知识库 ${res?.kb_count || 0} + 文章 ${res?.article_count || 0}）`,
    )
    await loadStats()
  } catch (e) {
    // handled by interceptor
  } finally {
    rebuilding.value = false
  }
}

async function openIndexedArticles() {
  try {
    const res = await aiApi.kbIndexedArticles()
    indexedArticles.value = res?.list || []
    indexedVisible.value = true
  } catch (e) {
    // handled by interceptor
  }
}

load()
loadStats()
</script>

<style scoped>
.pager {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

/* ---- RAG 索引状态条 ---- */
.kb-index-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 14px;
}

.kb-index-stats {
  display: flex;
  gap: 28px;
}

.kb-index-stat {
  text-align: center;
  min-width: 76px;
}

.kb-index-num {
  font-size: 20px;
  font-weight: 600;
  color: var(--el-color-primary);
  line-height: 1.3;
}

.kb-index-label {
  font-size: 12px;
  color: #909399;
}

.kb-index-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.kb-index-time {
  font-size: 12px;
  color: #909399;
}

.indexed-tip {
  font-size: 12px;
  color: #909399;
  margin-bottom: 10px;
}

.indexed-tip code {
  background: #f5f7fa;
  border-radius: 3px;
  padding: 1px 5px;
  color: #606266;
}

.cell-strong {
  font-weight: 500;
}

/* ---- TOC 编辑器 ---- */
.toc-divider-label {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
}

.toc-editor {
  background: #f9fafb;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px 14px 10px;
  margin-bottom: 12px;
}

.toc-empty {
  text-align: center;
  color: #c0c4cc;
  font-size: 13px;
  padding: 20px 0;
}

.toc-entry {
  margin-bottom: 8px;
}

.toc-l1-item {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 8px 10px;
}

.toc-l2-item {
  margin-top: 6px;
  margin-left: 28px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 5px;
  padding: 6px 8px;
}

.toc-l3-item {
  margin-top: 4px;
  margin-left: 24px;
  background: #f5f7fa;
  border: 1px dashed #e4e7ed;
  border-radius: 4px;
  padding: 4px 8px;
}

.toc-entry-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: nowrap;
}

.toc-level-tag {
  flex-shrink: 0;
  width: 32px;
  text-align: center;
}

.toc-title-input {
  flex: 1;
  min-width: 120px;
}

.toc-page-input {
  flex-shrink: 0;
  width: 100px;
}

.toc-sort-btns {
  flex-shrink: 0;
}

.toc-children {
  margin-top: 4px;
}

.toc-add-btn {
  margin-top: 10px;
  width: 100%;
}

/* ---- 详情弹窗 ---- */
.detail-content {
  margin-top: 20px;
}

.detail-content-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
  padding-left: 8px;
  border-left: 3px solid var(--el-color-primary);
}

.detail-content-body {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 16px;
  font-size: 13px;
  line-height: 1.8;
  color: #606266;
  white-space: pre-wrap;
  word-wrap: break-word;
  max-height: 400px;
  overflow-y: auto;
}

.detail-toc {
  margin-top: 16px;
}

.toc-line {
  margin-bottom: 10px;
  padding: 6px 0;
  border-bottom: 1px dashed #ebeef5;
}

.toc-line:last-child {
  border-bottom: none;
}

.toc-l1 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.toc-l1-icon {
  font-size: 14px;
}

.toc-l1-title {
  flex: 1;
}

.toc-l2 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #606266;
  padding-left: 24px;
  line-height: 1.8;
}

.toc-l2-title {
  flex: 1;
}

.toc-l3 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #909399;
  padding-left: 20px;
  line-height: 1.8;
}

.toc-l3-title {
  flex: 1;
}

.toc-page-tag {
  font-size: 11px;
  color: #909399;
  background: #f0f0f0;
  border-radius: 3px;
  padding: 1px 5px;
  flex-shrink: 0;
}
</style>
