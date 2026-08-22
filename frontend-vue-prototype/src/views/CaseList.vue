<template>
  <div class="page-shell case-list-page">
    <div class="page-header">
      <div>
        <h2>病例管理</h2>
        <p>查看病例上传、分割进度、三维重建和 AI 报告状态</p>
      </div>
      <div class="page-header-actions">
        <el-button :icon="Refresh" @click="loadCases">刷新</el-button>
        <el-button type="primary" :icon="UploadFilled" @click="goUpload">上传新病例</el-button>
      </div>
    </div>

    <el-card class="case-table-card" shadow="never">
      <el-table v-loading="loading" :data="cases" style="width: 100%">
        <el-table-column prop="case_id" label="病例编号" min-width="180" />
        <el-table-column prop="created_at" label="上传时间" width="180" />

        <el-table-column label="分割状态" width="140">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="进度" width="140">
          <template #default="{ row }">
            <el-progress :percentage="row.progress || 0" :show-text="false" />
          </template>
        </el-table-column>

        <el-table-column prop="message" label="状态说明" min-width="180" />

        <el-table-column label="操作" width="340">
          <template #default="{ row }">
            <el-button size="small" :icon="View" @click="goDetail(row.case_id)">结果</el-button>
            <el-button
              v-if="row.status === 'uploaded' || row.status === 'queued' || row.status === 'failed'"
              size="small"
              type="warning"
              :icon="VideoPlay"
              @click="segment(row.case_id)"
            >
              分割
            </el-button>
            <el-button size="small" type="primary" :icon="DataAnalysis" @click="go3D(row.case_id)">三维</el-button>
            <el-button size="small" type="success" :icon="Document" @click="goReport(row.case_id)">报告</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import {
  DataAnalysis,
  Document,
  Refresh,
  UploadFilled,
  VideoPlay,
  View
} from '@element-plus/icons-vue'
import { JETSON_TRT_SEGMENTATION_PARAMS, getCaseList, startSegmentation } from '../api/caseApi'

const router = useRouter()

const cases = ref([])
const loading = ref(false)
let pollTimer = null

function getStatusType(status) {
  const map = {
    uploaded: 'info',
    queued: 'warning',
    running: 'warning',
    completed: 'success',
    failed: 'danger'
  }
  return map[status] || 'info'
}

function getStatusText(status) {
  const map = {
    uploaded: '已上传',
    queued: '排队中',
    running: '分割中',
    completed: '已完成',
    failed: '失败'
  }
  return map[status] || status
}

function hasActiveCase() {
  return cases.value.some(row => row.status === 'queued' || row.status === 'running')
}

function clearPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function ensurePolling() {
  if (pollTimer) return
  pollTimer = setInterval(() => loadCases(true), 3000)
}

function goUpload() {
  router.push('/upload')
}

async function loadCases(silent = false) {
  if (!silent) loading.value = true
  try {
    const res = await getCaseList()
    cases.value = res.cases || []
    if (hasActiveCase()) {
      ensurePolling()
    } else {
      clearPoll()
    }
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '病例列表加载失败')
  } finally {
    if (!silent) loading.value = false
  }
}

async function segment(caseId) {
  try {
    await startSegmentation(caseId, JETSON_TRT_SEGMENTATION_PARAMS)
    ElMessage.success('已启动智能分割任务')
    await loadCases()
    router.push(`/cases/${caseId}`)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '启动分割失败')
  }
}

function goDetail(caseId) {
  router.push(`/cases/${caseId}`)
}

function go3D(caseId) {
  router.push(`/cases/${caseId}/3d`)
}

function goReport(caseId) {
  router.push(`/cases/${caseId}/report`)
}

onMounted(() => loadCases())
onUnmounted(clearPoll)
</script>

<style scoped>
.case-list-page {
  min-height: 100%;
}

.case-table-card {
  border-radius: var(--ppgl-radius);
  border-color: rgba(93, 235, 219, 0.22);
  background: rgba(8, 23, 36, 0.78);
}

:deep(.el-progress-bar__outer) {
  background-color: rgba(93, 235, 219, 0.12);
}

:deep(.el-progress-bar__inner) {
  background: linear-gradient(90deg, var(--ppgl-primary), var(--ppgl-accent));
  box-shadow: 0 0 16px rgba(32, 224, 196, 0.34);
}
</style>
