<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">操作日志</div>
      <el-button :loading="loading" @click="load"><el-icon><Refresh /></el-icon></el-button>
    </div>

    <div class="card-block">
      <div class="toolbar">
        <el-input v-model="username" placeholder="操作账号" clearable @keyup.enter="search" @clear="search" />
        <el-input v-model="action" placeholder="动作，如 question.update" clearable @keyup.enter="search" @clear="search" />
        <el-button type="primary" @click="search">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="list" border stripe size="default">
        <el-table-column prop="id" label="#" width="70" />
        <el-table-column prop="username" label="操作账号" width="140" />
        <el-table-column prop="action" label="动作" width="180" />
        <el-table-column prop="target" label="对象" min-width="180" show-overflow-tooltip />
        <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
        <el-table-column prop="ip" label="IP" width="130" />
        <el-table-column prop="created_at" label="时间" width="170" />
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @current-change="load"
          @size-change="load"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { dashboardApi } from '../api'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const username = ref('')
const action = ref('')

async function load() {
  loading.value = true
  try {
    const data = await dashboardApi.logs({
      page: page.value,
      page_size: pageSize.value,
      username: username.value,
      action: action.value,
    })
    list.value = data.list
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

load()
</script>

<style scoped>
.pager {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}
</style>
