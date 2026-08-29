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

        <el-menu-item index="/gpu-workbench">
          <el-icon><DataAnalysis /></el-icon>
          <span>GPU 工作台</span>
        </el-menu-item>

        <el-menu-item index="/ai-traces">
          <el-icon><DataAnalysis /></el-icon>
          <span>AI Trace 中心</span>
        </el-menu-item>

        <el-menu-item index="/cases">
          <el-icon><FolderOpened /></el-icon>
          <span>病例管理</span>
        </el-menu-item>

        <el-sub-menu index="case-upload">
          <template #title>
            <el-icon><UploadFilled /></el-icon>
            <span>上传病例</span>
          </template>
          <el-menu-item index="/upload">上传 CT</el-menu-item>
          <el-menu-item index="/glioma/upload">上传 MRI</el-menu-item>
        </el-sub-menu>

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
          <strong>医学影像智能分割与辅助分析系统</strong>
          <span>CT / MRI / Segmentation / 3D Reconstruction / AI Report</span>
        </div>
        <div class="topbar-actions">
          <button
            class="gpu-status"
            :class="`gpu-status--${gpuStatusTone}`"
            type="button"
            title="查看 GPU 资源调度台"
            @click="openGpuWorkbench"
          >
            <span class="gpu-status-dot"></span>
            <span class="gpu-status-copy">
              <strong>{{ gpuStatusLabel }}</strong>
              <small>{{ gpuStatusDetail }}</small>
            </span>
            <span class="gpu-status-refresh">自动更新 {{ nextRefreshSeconds }} 秒</span>
          </button>
          <div class="user-info">
            <span class="status-dot"></span>
            医生工作台
          </div>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { useGpuRuntimeStatus } from '../composables/useGpuRuntimeStatus'
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
const {
  status: gpuRuntimeStatus,
  lastError: gpuStatusError,
  nextRefreshSeconds,
  startPolling: startGpuStatusPolling,
  stopPolling: stopGpuStatusPolling
} = useGpuRuntimeStatus()

const gpuPrimary = computed(() => gpuRuntimeStatus.value.gpu?.primary || {})
const gpuActivity = computed(() => gpuRuntimeStatus.value.activity || {})
const gpuStatusTone = computed(() => {
  if (gpuStatusError.value || gpuRuntimeStatus.value.gpu?.available === false) return 'danger'
  return {
    running: 'running',
    waiting_for_gpu: 'warning',
    queued: 'warning',
    ready: 'ready',
    idle: 'idle'
  }[gpuActivity.value.state] || 'idle'
})
const gpuStatusLabel = computed(() => {
  if (gpuStatusError.value) return 'GPU 状态暂时不可用'
  if (!gpuRuntimeStatus.value.generated_at) return '正在读取 GPU 状态'
  return gpuActivity.value.label || 'GPU 空闲'
})
const gpuStatusDetail = computed(() => {
  if (gpuStatusError.value) return '点击查看资源调度台'
  const used = formatMemory(gpuPrimary.value.memory_used_mb)
  const total = formatMemory(gpuPrimary.value.memory_total_mb)
  return used === '—' || total === '—' ? '正在读取显存遥测' : `${used} / ${total}`
})

const activeMenu = computed(() => {
  if (/^\/glioma\/cases\/[^/]+$/.test(route.path)) return '/cases'
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

function openGpuWorkbench() {
  router.push('/gpu-workbench')
}

function formatMemory(value) {
  const memory = Number(value)
  if (!Number.isFinite(memory) || memory <= 0) return '—'
  return memory >= 1024 ? `${(memory / 1024).toFixed(1)} GB` : `${memory} MB`
}

onMounted(startGpuStatusPolling)
onBeforeUnmount(stopGpuStatusPolling)
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

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.gpu-status {
  min-width: 276px;
  height: 40px;
  padding: 0 12px;
  border: 1px solid rgba(93, 235, 219, 0.22);
  border-radius: 9px;
  background: rgba(8, 31, 45, 0.7);
  color: var(--ppgl-text);
  display: flex;
  align-items: center;
  gap: 9px;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.18s ease, background 0.18s ease, transform 0.18s ease;
}

.gpu-status:hover {
  border-color: rgba(93, 235, 219, 0.54);
  background: rgba(17, 55, 70, 0.75);
  transform: translateY(-1px);
}

.gpu-status-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--ppgl-primary);
  box-shadow: 0 0 0 4px rgba(32, 224, 196, 0.12);
}

.gpu-status-copy {
  min-width: 0;
  display: grid;
  gap: 1px;
}

.gpu-status-copy strong {
  overflow: hidden;
  color: var(--ppgl-text);
  font-size: 12px;
  font-weight: 760;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gpu-status-copy small,
.gpu-status-refresh {
  color: var(--ppgl-muted);
  font-size: 11px;
  line-height: 1.15;
  white-space: nowrap;
}

.gpu-status-refresh {
  margin-left: auto;
  color: #86d9d0;
}

.gpu-status--running .gpu-status-dot {
  background: var(--ppgl-accent);
  box-shadow: 0 0 0 4px rgba(106, 169, 255, 0.14), 0 0 12px rgba(106, 169, 255, 0.72);
}

.gpu-status--warning .gpu-status-dot {
  background: var(--ppgl-warning);
  box-shadow: 0 0 0 4px rgba(255, 209, 102, 0.14), 0 0 12px rgba(255, 209, 102, 0.52);
}

.gpu-status--danger .gpu-status-dot {
  background: var(--ppgl-danger);
  box-shadow: 0 0 0 4px rgba(255, 107, 107, 0.14);
}

.gpu-status--ready .gpu-status-dot {
  background: var(--ppgl-success);
  box-shadow: 0 0 0 4px rgba(77, 241, 161, 0.12);
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

  .gpu-status {
    min-width: 0;
  }

  .gpu-status-refresh {
    display: none;
  }

  .main-content {
    padding: 16px;
  }

}

@media (max-width: 620px) {
  .gpu-status {
    width: 42px;
    min-width: 42px;
    justify-content: center;
    padding: 0;
  }

  .gpu-status-copy,
  .user-info {
    display: none;
  }
}
</style>
