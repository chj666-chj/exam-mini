<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-title">角色权限</div>
      <div class="text-muted" style="font-size: 13px">按角色分配权限点，后端接口会做同样的校验</div>
    </div>

    <el-row :gutter="14">
      <el-col v-for="role in roles" :key="role.id" :xs="24" :md="12" :lg="8" style="margin-bottom: 14px">
        <div class="card-block role-card">
          <div class="role-head">
            <div>
              <div class="role-name">
                {{ role.name }}
                <el-tag size="small" effect="plain" :type="role.is_system ? 'warning' : 'info'" style="margin-left: 6px">
                  {{ role.is_system ? '内置' : '自定义' }}
                </el-tag>
              </div>
              <div class="text-muted" style="font-size: 12px; margin-top: 4px">
                {{ role.code }} · {{ role.user_count }} 个账号 · {{ role.permissions.length }} 项权限
              </div>
            </div>
            <el-button v-if="canManage" link type="primary" @click="openEdit(role)">配置权限</el-button>
          </div>
          <div class="role-desc">{{ role.description || '暂无说明' }}</div>
          <div class="role-perms">
            <el-tag v-for="p in role.permissions" :key="p" size="small" effect="light" class="perm-tag">
              {{ permName(p) }}
            </el-tag>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-dialog v-model="dialogVisible" :title="`配置权限 · ${current.name}`" width="680px" top="6vh">
      <el-alert
        v-if="current.code === 'superadmin'"
        type="warning"
        :closable="false"
        show-icon
        title="超级管理员默认拥有全部权限，不可修改"
        style="margin-bottom: 12px"
      />
      <el-form label-width="90px">
        <el-form-item label="角色名称">
          <el-input v-model="form.name" :disabled="current.code === 'superadmin'" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" :disabled="current.code === 'superadmin'" />
        </el-form-item>
      </el-form>
      <div v-for="group in permissionGroups" :key="group.group" class="perm-group">
        <div class="perm-group-title">
          <el-checkbox
            :model-value="isGroupChecked(group)"
            :indeterminate="isGroupIndeterminate(group)"
            :disabled="current.code === 'superadmin'"
            @change="(v) => toggleGroup(group, v)"
          >
            {{ group.group }}
          </el-checkbox>
        </div>
        <el-checkbox-group v-model="form.permissions" :disabled="current.code === 'superadmin'">
          <el-checkbox v-for="item in group.items" :key="item.code" :value="item.code">
            {{ item.name }}
          </el-checkbox>
        </el-checkbox-group>
      </div>
      <template #footer>
        <el-button @click="dialogVisible = false">取 消</el-button>
        <el-button type="primary" :loading="saving" :disabled="current.code === 'superadmin'" @click="submit">保 存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { authApi, roleApi } from '../api'
import { useUserStore } from '../stores/user'

const user = useUserStore()
const canManage = user.hasPerm('admin.manage')

const roles = ref([])
const permissionGroups = ref([])
const dialogVisible = ref(false)
const saving = ref(false)
const current = ref({})
const form = reactive({ name: '', description: '', permissions: [] })

const permNameMap = computed(() => {
  const map = {}
  permissionGroups.value.forEach((g) => g.items.forEach((i) => (map[i.code] = i.name)))
  return map
})

const permName = (code) => permNameMap.value[code] || code

async function load() {
  roles.value = await roleApi.list()
}

function openEdit(role) {
  current.value = role
  form.name = role.name
  form.description = role.description
  form.permissions = [...role.permissions]
  dialogVisible.value = true
}

function groupCodes(group) {
  return group.items.map((i) => i.code)
}

function isGroupChecked(group) {
  return groupCodes(group).every((c) => form.permissions.includes(c))
}

function isGroupIndeterminate(group) {
  const hit = groupCodes(group).filter((c) => form.permissions.includes(c)).length
  return hit > 0 && hit < groupCodes(group).length
}

function toggleGroup(group, checked) {
  const codes = groupCodes(group)
  if (checked) {
    codes.forEach((c) => {
      if (!form.permissions.includes(c)) form.permissions.push(c)
    })
  } else {
    form.permissions = form.permissions.filter((c) => !codes.includes(c))
  }
}

async function submit() {
  saving.value = true
  try {
    await roleApi.update(current.value.id, {
      name: form.name,
      description: form.description,
      permissions: form.permissions,
    })
    ElMessage.success('角色权限已保存，相关账号下次请求时生效')
    dialogVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  permissionGroups.value = await authApi.permissions()
  await load()
})
</script>

<style scoped>
.role-card {
  min-height: 190px;
}

.role-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.role-name {
  font-size: 15px;
  font-weight: 600;
}

.role-desc {
  margin: 8px 0 10px;
  font-size: 13px;
  color: var(--admin-text-muted);
}

.role-perms {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.perm-tag {
  margin: 0;
}

.perm-group {
  border-top: 1px solid var(--admin-border);
  padding: 10px 0;
}

.perm-group-title {
  margin-bottom: 6px;
}
</style>
