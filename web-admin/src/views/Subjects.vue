<template>
  <SimpleCrud
    title="科目管理"
    resource-name="subjects"
    manage-perm="subject.manage"
    :columns="columns"
    :fields="fields"
    :default-model="{ name: '', pid: '', code: '' }"
  >
    <template #subjectName="{ row }">
      <span class="cell-strong">{{ row.name }}</span>
    </template>
  </SimpleCrud>
</template>

<script setup>
import SimpleCrud from '../components/SimpleCrud.vue'

const columns = [
  { prop: '_id', label: '科目ID', width: '120' },
  { prop: 'name', label: '科目名称', minWidth: '180', slot: 'subjectName' },
  { prop: 'pid', label: '所属考试', width: '120' },
  { prop: 'code', label: '科目编码', width: '120' },
  { prop: '_updated_at', label: '更新时间', width: '170' },
]

const fields = [
  { key: 'name', label: '科目名称', placeholder: '如 微信测评一' },
  { key: 'pid', label: '所属考试ID', placeholder: '如 001' },
  { key: 'code', label: '科目编码', placeholder: '如 001001' },
]
</script>

<style scoped>
.cell-strong {
  font-weight: 500;
}
</style>
