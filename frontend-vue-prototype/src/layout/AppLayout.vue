<template>
  <el-container class="app-layout">
    <el-aside width="240px" class="sidebar">
      <div class="logo">
        <div class="logo-mark">P</div>
        <div>
          <div class="logo-title">PPGL-AI</div>
          <div class="logo-subtitle">智能影像工作站</div>
        </div>
      </div>

      <el-menu
        :default-active="activeMenu"
        class="side-menu"
        background-color="transparent"
        text-color="#b8c3cf"
        active-text-color="#ffffff"
        @select="handleMenuSelect"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataBoard /></el-icon>
          <span>系统首页</span>
        </el-menu-item>

        <el-menu-item index="/cases">
          <el-icon><FolderOpened /></el-icon>
          <span>病例管理</span>
        </el-menu-item>

        <el-menu-item index="/upload">
          <el-icon><UploadFilled /></el-icon>
          <span>上传病例</span>
        </el-menu-item>

        <el-menu-item index="/knowledge">
          <el-icon><Reading /></el-icon>
          <span>PPGL 医学知识库</span>
        </el-menu-item>

        <el-menu-item index="case-result">
          <el-icon><View /></el-icon>
          <span>分割结果示例</span>
        </el-menu-item>

        <el-menu-item index="case-3d">
          <el-icon><DataAnalysis /></el-icon>
          <span>2D / 3D 联合阅片</span>
        </el-menu-item>

        <el-menu-item index="case-report">
          <el-icon><Document /></el-icon>
          <span>AI 辅助报告</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div class="topbar-title">
          <strong>PPGL 术前 CT 智能分割与辅助分析系统</strong>
          <span>Segmentation / 3D Reconstruction / RAG / AI Report</span>
        </div>
        <div class="user-info">
          <span class="status-dot"></span>
          医生工作台
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import {
  DataAnalysis,
  DataBoard,
  Document,
  FolderOpened,
  Reading,
  UploadFilled,
  View
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

const activeMenu = computed(() => {
  if (route.path.endsWith('/3d')) return 'case-3d'
  if (route.path.endsWith('/report')) return 'case-report'
  if (/^\/cases\/[^/]+(?:\/2d)?$/.test(route.path)) return 'case-result'
  return route.path
})

function handleMenuSelect(index) {
  const caseTargets = {
    'case-result': '',
    'case-3d': '/3d',
    'case-report': '/report'
  }

  if (Object.prototype.hasOwnProperty.call(caseTargets, index)) {
    const caseId = route.params.caseId
    if (!caseId || caseId === 'demo-case') {
      ElMessage.warning('未选择任何病例，请选择一个病例')
      router.push('/cases')
      return
    }
    router.push(`/cases/${encodeURIComponent(String(caseId))}${caseTargets[index]}`)
    return
  }

  router.push(index)
}
</script>

<style scoped>
.app-layout {
  height: 100vh;
  background: var(--ppgl-bg);
}

.sidebar {
  background: linear-gradient(180deg, #081522 0%, #07111d 100%);
  color: #ffffff;
  border-right: 1px solid rgba(148, 163, 184, 0.13);
  position: relative;
  overflow: hidden;
}

.logo {
  height: 78px;
  padding: 16px 18px;
  box-sizing: border-box;
  border-bottom: 1px solid rgba(148, 163, 184, 0.13);
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-mark {
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: #0f766e;
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 800;
}

.logo-title {
  font-size: 21px;
  font-weight: 800;
  line-height: 1;
}

.logo-subtitle {
  font-size: 13px;
  color: var(--ppgl-muted);
  margin-top: 6px;
}

.side-menu {
  border-right: none;
  padding: 12px 10px;
}

.side-menu :deep(.el-menu-item) {
  height: 44px;
  margin-bottom: 2px;
  border-radius: 8px;
  font-weight: 650;
  border: 0;
  position: relative;
  z-index: 1;
}

.side-menu :deep(.el-menu-item:hover) {
  background: rgba(148, 163, 184, 0.08);
}

.side-menu :deep(.el-menu-item.is-active) {
  background: rgba(32, 224, 196, 0.1);
  box-shadow: inset 3px 0 0 var(--ppgl-primary);
}

.topbar {
  height: 62px;
  background: rgba(7, 18, 30, 0.94);
  border-bottom: 1px solid rgba(148, 163, 184, 0.13);
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--ppgl-text);
  backdrop-filter: blur(18px);
}

.topbar-title {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.topbar-title strong {
  font-size: 16px;
  font-weight: 800;
  color: var(--ppgl-text);
}

.topbar-title span {
  color: var(--ppgl-muted);
  font-size: 12px;
}

.user-info {
  height: 34px;
  padding: 0 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.07);
  color: #b9f8f1;
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 650;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #10b981;
  box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.1);
}

.main-content {
  background:
    linear-gradient(90deg, rgba(148, 163, 184, 0.022) 1px, transparent 1px),
    linear-gradient(180deg, rgba(148, 163, 184, 0.018) 1px, transparent 1px),
    var(--ppgl-bg);
  background-size: 44px 44px, 44px 44px, auto;
  padding: 24px;
  overflow: auto;
  position: relative;
}

@media (max-width: 900px) {
  .sidebar {
    width: 76px !important;
  }

  .logo {
    justify-content: center;
    padding: 16px 10px;
  }

  .logo > div:last-child,
  .side-menu :deep(.el-menu-item span) {
    display: none;
  }

  .side-menu {
    padding: 10px;
  }

  .side-menu :deep(.el-menu-item) {
    justify-content: center;
    padding: 0;
  }

  .topbar-title span {
    display: none;
  }

  .main-content {
    padding: 16px;
  }

}
</style>
