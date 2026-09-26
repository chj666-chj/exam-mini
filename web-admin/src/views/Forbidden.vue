<template>
  <div class="state-page">
    <el-result icon="warning" title="403" sub-title="当前角色没有访问该页面的权限，请联系超级管理员">
      <template #extra>
        <el-button type="primary" @click="$router.push('/dashboard')">返回数据看板</el-button>
      </template>
    </el-result>
  </div>
</template>

<style scoped>
.state-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}
</style>
