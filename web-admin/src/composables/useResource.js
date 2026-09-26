import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { resource } from '../api'

/**
 * 通用集合资源的列表 / 分页 / 增删改封装。
 * 与后端 /api/admin/<name>/ 接口一一对应，页面只关心字段与表单。
 */
export function useResource(name, defaultFilters = {}) {
  const api = resource(name)
  const list = ref([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)
  const loading = ref(false)
  const keyword = ref('')
  const filters = ref({ ...defaultFilters })

  function buildParams() {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      ...filters.value,
    }
    if (keyword.value) params.keyword = keyword.value
    Object.keys(params).forEach((k) => {
      if (params[k] === '' || params[k] === null || params[k] === undefined) delete params[k]
    })
    return params
  }

  async function load() {
    loading.value = true
    try {
      const data = await api.list(buildParams())
      list.value = data.list || []
      total.value = data.total || 0
    } finally {
      loading.value = false
    }
  }

  function search() {
    page.value = 1
    return load()
  }

  function reset() {
    keyword.value = ''
    filters.value = { ...defaultFilters }
    page.value = 1
    return load()
  }

  async function save(payload, id) {
    let result
    if (id) {
      result = await api.update(id, payload)
    } else {
      result = await api.create(payload)
    }
    ElMessage.success('保存成功')
    await load()
    return result
  }

  async function remove(id, tip = '该记录') {
    await ElMessageBox.confirm(`确定删除${tip}吗？删除后不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await api.remove(id)
    ElMessage.success('已删除')
    await load()
  }

  async function bulkRemove(ids) {
    if (!ids.length) {
      ElMessage.warning('请先选择记录')
      return
    }
    await ElMessageBox.confirm(`确定删除选中的 ${ids.length} 条记录吗？`, '批量删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    const data = await api.bulkDelete(ids)
    ElMessage.success(`已删除 ${data.deleted} 条记录`)
    await load()
  }

  return {
    api, list, total, page, pageSize, loading, keyword, filters,
    load, search, reset, save, remove, bulkRemove,
  }
}
