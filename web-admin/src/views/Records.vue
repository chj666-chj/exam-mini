<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">答题记录</div>
      <el-button :loading="loading" @click="load"><el-icon><Refresh /></el-icon></el-button>
    </div>

    <div class="card-block">
      <div class="toolbar">
        <el-input v-model="filters._openid" placeholder="按 OpenID 查询" clearable @keyup.enter="search" @clear="search" />
        <el-input v-model="keyword" placeholder="搜索关键字" clearable @keyup.enter="search" @clear="search" />
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="list" border stripe size="default">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="json-block">
              <div class="block-title">答题明细</div>
              <el-table :data="questionRows(row)" size="small" border max-height="300">
                <el-table-column prop="code" label="题号" width="80" />
                <el-table-column prop="title" label="题干" min-width="240" show-overflow-tooltip />
                <el-table-column prop="myCode" label="我的答案" width="100" />
                <el-table-column prop="rightCode" label="正确答案" width="100" />
                <el-table-column label="结果" width="90" align="center">
                  <template #default="{ row: q }">
                    <el-tag :type="q.right ? 'success' : 'danger'" size="small" effect="plain">
                      {{ q.right ? '正确' : '错误' }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="_id" label="批次号" width="160" />
        <el-table-column label="用户" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row._openid || '-' }}</template>
        </el-table-column>
        <el-table-column label="科目" width="140">
          <template #default="{ row }">{{ subjectName(row) }}</template>
        </el-table-column>
        <el-table-column label="成绩" width="120" align="center">
          <template #default="{ row }">
            {{ scoreText(row) }}
          </template>
        </el-table-column>
        <el-table-column label="正确率" width="100" align="right">
          <template #default="{ row }">{{ percent(accuracy(row)) }}</template>
        </el-table-column>
        <el-table-column prop="time" label="用时" width="90" />
        <el-table-column label="答题时间" width="160">
          <template #default="{ row }">{{ row.createTime || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="canManage" label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="remove(row._id, '这条答题记录')">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

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
  </div>
</template>

<script setup>
import { Refresh } from '@element-plus/icons-vue'
import { useResource } from '../composables/useResource'
import { useUserStore } from '../stores/user'

const user = useUserStore()
const canManage = user.hasPerm('record.manage')

const { list, total, page, pageSize, loading, keyword, filters, load, search, reset, remove } =
  useResource('records', { _openid: '' })

const percent = (v) => (v === null || v === undefined ? '-' : `${(v * 100).toFixed(1)}%`)

function asObject(value) {
  if (!value) return null
  if (typeof value === 'object') return value
  try {
    return JSON.parse(String(value).replace(/'/g, '"'))
  } catch (e) {
    return null
  }
}

function subjectName(row) {
  const subject = asObject(row.subject)
  return subject?.name || row.subject || '-'
}

function scoreText(row) {
  const items = Array.isArray(row.items) ? row.items : asObject(row.items) || []
  const right = Number(row.rightNum ?? 0)
  return `${right} / ${items.length || '-'}`
}

function accuracy(row) {
  const items = Array.isArray(row.items) ? row.items : asObject(row.items) || []
  if (!items.length) return null
  return Number(row.rightNum ?? 0) / items.length
}

function questionRows(row) {
  const questions = Array.isArray(row.questions) ? row.questions : asObject(row.questions) || []
  return questions.map((q, idx) => {
    const options = Array.isArray(q.options) ? q.options : []
    const selected = options.filter((o) => o.selected).map((o) => o.code).join('')
    const correct = options.filter((o) => String(o.value) === '1').map((o) => o.code).join('')
    return {
      code: q._id || idx + 1,
      title: q.title,
      myCode: selected || '-',
      rightCode: correct || '-',
      right: !!selected && selected === correct,
    }
  })
}

load()
</script>

<style scoped>
.pager {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

.json-block {
  padding: 8px 12px;
}

.block-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}
</style>
