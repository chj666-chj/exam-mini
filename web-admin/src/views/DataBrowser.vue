<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">数据浏览</div>
      <div class="text-muted" style="font-size: 13px">直接查看底层文档集合，便于排查数据问题</div>
    </div>

    <div class="card-block">
      <div class="toolbar">
        <el-select v-model="current" placeholder="选择集合" style="width: 200px" @change="onChange">
          <el-option v-for="c in collections" :key="c.name" :label="`${c.name}（${c.count}）`" :value="c.name" />
        </el-select>
        <el-input v-model="keyword" placeholder="全文关键字" clearable @keyup.enter="search" @clear="search" />
        <el-button type="primary" @click="search">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="list" border stripe height="560">
        <el-table-column type="expand">
          <template #default="{ row }">
            <pre class="json-view">{{ pretty(row) }}</pre>
          </template>
        </el-table-column>
        <el-table-column prop="_id" label="_id" min-width="220" show-overflow-tooltip />
        <el-table-column label="摘要" min-width="280" show-overflow-tooltip>
          <template #default="{ row }">{{ summary(row) }}</template>
        </el-table-column>
        <el-table-column prop="_created_at" label="创建时间" width="170" />
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @current-change="loadDocs"
          @size-change="loadDocs"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { collectionApi } from '../api'

const collections = ref([])
const current = ref('')
const keyword = ref('')
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const loading = ref(false)

async function loadCollections() {
  collections.value = await collectionApi.index()
  if (!current.value && collections.value.length) {
    current.value = collections.value[0].name
    await loadDocs()
  }
}

async function loadDocs() {
  if (!current.value) return
  loading.value = true
  try {
    const data = await collectionApi.docs(current.value, {
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value,
    })
    list.value = data.list
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onChange() {
  page.value = 1
  keyword.value = ''
  loadDocs()
}

function search() {
  page.value = 1
  loadDocs()
}

function pretty(row) {
  const copy = { ...row }
  delete copy._created_at
  delete copy._updated_at
  return JSON.stringify(copy, null, 2)
}

function summary(row) {
  for (const key of ['title', 'name', 'ordernum', '_openid', 'typename', 'createTime']) {
    if (row[key]) return String(row[key])
  }
  return Object.keys(row).filter((k) => !k.startsWith('_')).join(', ')
}

onMounted(loadCollections)
</script>

<style scoped>
.pager {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

.json-view {
  margin: 0;
  padding: 10px 12px;
  background: #f7f8fa;
  border-radius: 6px;
  max-height: 320px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.6;
}
</style>
