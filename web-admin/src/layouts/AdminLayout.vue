<template>
  <div class="admin-shell" :class="{ 'is-mobile': isMobile }">
    <el-container class="admin-container">
      <!-- 侧边栏（桌面端） -->
      <el-aside v-if="!isMobile" :width="collapsed ? '64px' : '230px'" class="admin-aside">
        <div class="brand" :class="{ collapsed }">
          <span class="brand-mark">考</span>
          <span v-if="!collapsed" class="brand-text">考试宝后台</span>
        </div>
        <div class="aside-scroll">
          <el-menu :default-active="activeMenu" router :collapse="collapsed">
          <template v-for="grp in groupedMenu" :key="grp.key">
            <div v-if="!collapsed && grp.label" class="nav-group-label">{{ grp.label }}</div>
            <template v-for="item in grp.items" :key="item.path">
              <el-sub-menu v-if="item.children && item.children.length" :index="item.path">
                <template #title>
                  <el-icon><component :is="item.meta.icon" /></el-icon>
                  <span>{{ item.meta.title }}</span>
                </template>
                <el-menu-item v-for="child in item.children" :key="child.path" :index="child.path">
                  <el-icon v-if="child.meta.icon"><component :is="child.meta.icon" /></el-icon>
                  <template #title>{{ child.meta.title }}</template>
                </el-menu-item>
              </el-sub-menu>
              <el-menu-item v-else :index="item.path">
                <el-icon><component :is="item.meta.icon" /></el-icon>
                <template #title>{{ item.meta.title }}</template>
              </el-menu-item>
            </template>
          </template>
          </el-menu>
        </div>
      </el-aside>

      <!-- 移动端抽屉菜单 -->
      <el-drawer v-model="drawer" direction="ltr" size="230px" :with-header="false">
        <div class="brand brand-drawer">
          <span class="brand-mark">考</span>
          <span class="brand-text">考试宝后台</span>
        </div>
        <div class="aside-scroll">
          <el-menu :default-active="activeMenu" router @select="drawer = false">
            <template v-for="grp in groupedMenu" :key="grp.key">
              <div v-if="grp.label" class="nav-group-label">{{ grp.label }}</div>
              <template v-for="item in grp.items" :key="item.path">
                <el-sub-menu v-if="item.children && item.children.length" :index="item.path">
                  <template #title>
                    <el-icon><component :is="item.meta.icon" /></el-icon>
                    <span>{{ item.meta.title }}</span>
                  </template>
                  <el-menu-item v-for="child in item.children" :key="child.path" :index="child.path">
                    <el-icon v-if="child.meta.icon"><component :is="child.meta.icon" /></el-icon>
                    <template #title>{{ child.meta.title }}</template>
                  </el-menu-item>
                </el-sub-menu>
                <el-menu-item v-else :index="item.path">
                  <el-icon><component :is="item.meta.icon" /></el-icon>
                  <template #title>{{ item.meta.title }}</template>
                </el-menu-item>
              </template>
            </template>
          </el-menu>
        </div>
      </el-drawer>

      <el-container>
        <el-header class="admin-header" height="58px">
          <div class="header-left">
            <el-button text class="mobile-only" @click="drawer = true">
              <el-icon :size="20"><Expand /></el-icon>
            </el-button>
            <el-button v-if="!isMobile" text @click="collapsed = !collapsed">
              <el-icon :size="20"><component :is="collapsed ? 'Expand' : 'Fold'" /></el-icon>
            </el-button>
            <el-breadcrumb separator="/" class="header-crumb">
              <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
              <el-breadcrumb-item v-if="parentTitle">{{ parentTitle }}</el-breadcrumb-item>
              <el-breadcrumb-item>{{ pageTitle }}</el-breadcrumb-item>
            </el-breadcrumb>
          </div>

          <div class="header-right">
            <el-tooltip content="刷新数据" placement="bottom">
              <el-button text @click="refresh">
                <el-icon :size="18"><Refresh /></el-icon>
              </el-button>
            </el-tooltip>
            <el-dropdown @command="onCommand">
              <span class="user-chip">
                <el-avatar :size="30" class="user-avatar">{{ avatarText }}</el-avatar>
                <span class="user-name">{{ user.nickname }}</span>
                <el-tag size="small" type="info" effect="plain">{{ roleName }}</el-tag>
                <el-icon><ArrowDown /></el-icon>
              </span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="profile">
                    <el-icon><User /></el-icon>账号设置
                  </el-dropdown-item>
                  <el-dropdown-item command="password">
                    <el-icon><Key /></el-icon>修改密码
                  </el-dropdown-item>
                  <el-dropdown-item divided command="logout">
                    <el-icon><SwitchButton /></el-icon>退出登录
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </el-header>

        <el-main class="admin-main">
          <router-view v-slot="{ Component }">
            <transition name="fade-slide" mode="out-in">
              <component :is="Component" :key="route.fullPath" />
            </transition>
          </router-view>
        </el-main>
      </el-container>
    </el-container>

    <PasswordDialog v-model="passwordVisible" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Expand, Fold, Refresh, ArrowDown, SwitchButton, User, Key } from '@element-plus/icons-vue'
import { useUserStore } from '../stores/user'
import { routes, navGroups } from '../router'
import PasswordDialog from '../components/PasswordDialog.vue'

const route = useRoute()
const router = useRouter()
const user = useUserStore()

const collapsed = ref(false)
const drawer = ref(false)
const isMobile = ref(window.innerWidth < 768)
const passwordVisible = ref(false)

function handleResize() {
  isMobile.value = window.innerWidth < 768
  if (!isMobile.value) drawer.value = false
}
onMounted(() => window.addEventListener('resize', handleResize))
onUnmounted(() => window.removeEventListener('resize', handleResize))

const menuItems = computed(() => {
  const root = routes.find((r) => r.path === '/')
  if (!root) return []
  const walk = (list, parentPath = '') =>
    list
      .filter((item) => !item.meta?.hidden)
      .filter((item) => !item.meta?.perm || user.hasPerm(item.meta.perm))
      .map((item) => {
        const path = parentPath ? `${parentPath}/${item.path}` : `/${item.path}`
        return {
          path,
          meta: item.meta || {},
          children: item.children ? walk(item.children, path) : [],
        }
      })
  return walk(root.children || [])
})

// 按分组归类菜单
const groupedMenu = computed(() => {
  const items = menuItems.value
  return navGroups.map((grp) => ({
    key: grp.key,
    label: grp.label,
    items: items.filter((i) => (i.meta.group || 'content') === grp.key),
  })).filter((g) => g.items.length > 0)
})

const activeMenu = computed(() => route.path)
const pageTitle = computed(() => route.meta?.title || '')
const parentTitle = computed(() => {
  const item = menuItems.value.find((i) => i.children?.some((c) => c.path === route.path))
  return item?.meta?.title || ''
})
const avatarText = computed(() => (user.nickname || 'U').slice(0, 1).toUpperCase())
const roleName = computed(() => user.profile?.role_name || '未分配')

function refresh() {
  window.dispatchEvent(new CustomEvent('admin:refresh'))
  ElMessage.success('已触发刷新')
}

async function onCommand(cmd) {
  if (cmd === 'logout') {
    await ElMessageBox.confirm('确定退出登录吗？', '提示', { type: 'warning' })
    await user.logout()
    router.replace({ name: 'login' })
  } else if (cmd === 'profile') {
    router.push({ name: 'profile' })
  } else if (cmd === 'password') {
    passwordVisible.value = true
  }
}

watch(isMobile, (v) => {
  if (v) collapsed.value = false
})
</script>

<style scoped>
.admin-shell,
.admin-container {
  height: 100%;
}

.admin-aside {
  background: #1f2937;
  transition: width 0.2s;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.brand {
  height: 58px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  color: #fff;
  font-weight: 600;
  letter-spacing: 1px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.brand.collapsed {
  padding: 0;
  justify-content: center;
}

.brand-drawer {
  color: #303133;
  padding: 0 8px 12px;
  border-bottom: none;
}

.brand-mark {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #4f7cff, #7b5bff);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  box-shadow: 0 2px 8px rgba(79, 124, 255, 0.4);
}

.aside-scroll {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.aside-scroll::-webkit-scrollbar {
  width: 4px;
}

.aside-scroll::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 2px;
}

.admin-aside :deep(.el-menu) {
  border-right: none;
}

.admin-header {
  background: #fff;
  border-bottom: 1px solid var(--admin-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
  z-index: 10;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  outline: none;
  padding: 4px 8px;
  border-radius: 10px;
  transition: background 0.2s;
}

.user-chip:hover {
  background: #f4f6fa;
}

.user-avatar {
  background: linear-gradient(135deg, #4f7cff, #7b5bff);
  color: #fff;
  font-weight: 600;
}

.user-name {
  font-size: 14px;
}

.admin-main {
  padding: 0;
  background: var(--admin-bg);
  overflow: auto;
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.18s ease;
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.fade-slide-leave-to {
  opacity: 0;
}

@media (max-width: 768px) {
  .header-crumb {
    display: none;
  }

  .user-name {
    display: none;
  }
}
</style>
