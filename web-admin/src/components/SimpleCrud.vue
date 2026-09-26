<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">
        <span class="page-title-icon"><el-icon><Grid /></el-icon></span>
        {{ title }}
      </div>
      <div>
        <el-button v-if="canManage" type="danger" plain :disabled="!selection.length" @click="bulkRemove(ids)">
          <el-icon><Delete /></el-icon>批量删除（{{ selection.length }}）
        </el-button>
        <el-button v-if="canManage" type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>新建
        </el-button>
      </div>
    </div>

    <div class="card-block">
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索关键字" clearable @keyup.enter="search" @clear="search">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button type="primary" @click="search"><el-icon><Search /></el-icon>查询</el-button>
        <el-button @click="reset"><el-icon><RefreshLeft /></el-icon>重置</el-button>
      </div>

      <el-table v-loading="loading" :data="list" border stripe size="default" @selection-change="onSelection">
        <el-table-column v-if="canManage" type="selection" width="46" />
        <el-table-column v-for="col in columns" :key="col.prop" v-bind="col">
          <template v-if="col.slot" #default="scope">
            <slot :name="col.slot" v-bind="scope" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canManage" link type="primary" @click="openEdit(row)"><el-icon><Edit /></el-icon>编辑</el-button>
            <el-button v-if="canManage" link type="danger" @click="remove(row._id, '该记录')"><el-icon><Delete /></el-icon>删除</el-button>
            <span v-if="!canManage" class="text-muted">只读</span>
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

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑' + title.replace('管理', '') : '新建' + title.replace('管理', '')" width="520px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="记录ID">
          <el-input v-model="form._id" :disabled="isEdit" placeholder="如 001（新建后不可修改）" />
        </el-form-item>
        <el-form-item v-for="field in fields" :key="field.key" :label="field.label">
          <el-input
            v-if="field.type !== 'textarea'"
            v-model="form[field.key]"
            :placeholder="field.placeholder"
          />
          <el-input
            v-else
            v-model="form[field.key]"
            type="textarea"
            :rows="field.rows || 3"
            :placeholder="field.placeholder"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取 消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保 存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Delete, Edit, Search, RefreshLeft, Grid } from '@element-plus/icons-vue'
import { useResource } from '../composables/useResource'
import { useUserStore } from '../stores/user'

const props = defineProps({
  title: { type: String, required: true },
  resourceName: { type: String, required: true },
  managePerm: { type: String, required: true },
  columns: { type: Array, required: true },
  fields: { type: Array, required: true },
  defaultModel: { type: Object, default: () => ({}) },
})

const user = useUserStore()
const canManage = user.hasPerm(props.managePerm)

const { list, total, page, pageSize, loading, keyword, load, search, reset, save, remove, bulkRemove } =
  useResource(props.resourceName)

const selection = ref([])
const ids = computed(() => selection.value.map((r) => r._id))
const onSelection = (rows) => (selection.value = rows)

const dialogVisible = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const form = ref({ _id: '', ...props.defaultModel })

function openCreate() {
  isEdit.value = false
  form.value = { _id: '', ...props.defaultModel }
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  const model = { _id: row._id }
  props.fields.forEach((f) => {
    model[f.key] = row[f.key] ?? ''
  })
  form.value = model
  dialogVisible.value = true
}

async function submit() {
  if (!form.value._id || !String(form.value._id).trim()) {
    ElMessage.warning('请填写记录ID')
    return
  }
  const payload = { ...form.value }
  if (isEdit.value) delete payload._id
  saving.value = true
  try {
    await save(payload, isEdit.value ? form.value._id : null)
    dialogVisible.value = false
  } finally {
    saving.value = false
  }
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
