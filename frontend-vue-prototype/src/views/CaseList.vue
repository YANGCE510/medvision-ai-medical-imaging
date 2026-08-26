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

        <el-table-column label="独立任务状态" width="190">
          <template #default="{ row }">
            <div class="task-statuses">
              <span>全器官 <el-tag size="small" :type="getStatusType(row.organ_status?.status)">{{ getStatusText(row.organ_status?.status) }}</el-tag></span>
              <span>PPGL <el-tag size="small" :type="getStatusType(row.ppgl_status?.status)">{{ getStatusText(row.ppgl_status?.status) }}</el-tag></span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="独立进度" width="180">
          <template #default="{ row }">
            <div class="task-progresses">
              <span>全器官 <el-progress :percentage="row.organ_status?.progress || 0" :show-text="false" /></span>
              <span>PPGL <el-progress :percentage="row.ppgl_status?.progress || 0" :show-text="false" /></span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="状态说明" min-width="210">
          <template #default="{ row }">
            <div class="task-messages">
              <span>全器官：{{ row.organ_status?.message || '-' }}</span>
              <span>PPGL：{{ row.ppgl_status?.message || '-' }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="560">
          <template #default="{ row }">
            <el-button size="small" :icon="View" @click="goDetail(row.case_id)">结果</el-button>
            <el-button
              size="small"
              :icon="Edit"
              :disabled="isCaseActive(row)"
              @click="renameCase(row)"
            >
              修改编号
            </el-button>
            <el-button
              v-if="canStartTask(row.organ_status?.status)"
              size="small"
              :icon="VideoPlay"
              @click="segmentOrgans(row.case_id)"
            >
              全器官
            </el-button>
            <el-button
              v-if="canStartTask(row.ppgl_status?.status)"
              size="small"
              type="warning"
              :icon="VideoPlay"
              @click="segmentPpgl(row.case_id)"
            >
              PPGL
            </el-button>
            <el-button size="small" type="primary" :icon="DataAnalysis" @click="go3D(row.case_id)">联合阅片</el-button>
            <el-button size="small" type="success" :icon="Document" @click="goReport(row.case_id)">报告</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import {
  DataAnalysis,
  Document,
  Edit,
  Refresh,
  UploadFilled,
  VideoPlay,
  View
} from '@element-plus/icons-vue'
import {
  TOTALSEGMENTATOR_PARAMS,
  getCaseList,
  startOrganSegmentation,
  startPpglSegmentation,
  updateCaseId
} from '../api/caseApi'

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
  return cases.value.some(isCaseActive)
}

function isTaskActive(status) {
  return status === 'queued' || status === 'running'
}

function isCaseActive(row) {
  return isTaskActive(row.organ_status?.status) || isTaskActive(row.ppgl_status?.status)
}

function canStartTask(status) {
  return !status || status === 'uploaded' || status === 'failed'
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

function caseRoute(caseId) {
  return encodeURIComponent(caseId)
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

async function renameCase(row) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新的病例编号', '修改病例编号', {
      customClass: 'rename-case-message-box',
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: row.case_id,
      inputPattern: /^[^/\\]+$/,
      inputErrorMessage: '病例编号不能为空，且不能包含 / 或 \\'
    })
    const newCaseId = value.trim()
    if (!newCaseId) {
      ElMessage.warning('病例编号不能为空')
      return
    }
    await updateCaseId(row.case_id, newCaseId)
    ElMessage.success('病例编号已修改')
    await loadCases()
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err?.response?.data?.detail || '修改病例编号失败')
  }
}

async function segmentOrgans(caseId) {
  try {
    await startOrganSegmentation(caseId, TOTALSEGMENTATOR_PARAMS)
    ElMessage.success('已启动全器官分割')
    await loadCases()
    router.push(`/cases/${caseRoute(caseId)}`)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '启动全器官分割失败')
  }
}

async function segmentPpgl(caseId) {
  try {
    await startPpglSegmentation(caseId, { device: 'cuda:0' })
    ElMessage.success('已启动 PPGL 肿瘤分割')
    await loadCases()
    router.push(`/cases/${caseRoute(caseId)}`)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '启动 PPGL 分割失败')
  }
}

function goDetail(caseId) {
  router.push(`/cases/${caseRoute(caseId)}`)
}

function go3D(caseId) {
  router.push(`/cases/${caseRoute(caseId)}/3d`)
}

function goReport(caseId) {
  router.push(`/cases/${caseRoute(caseId)}/report`)
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

.task-statuses {
  display: grid;
  gap: 6px;
}

.task-statuses span {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.task-progresses,
.task-messages {
  display: grid;
  gap: 6px;
}

.task-progresses span {
  display: grid;
  grid-template-columns: 48px 1fr;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

:deep(.el-progress-bar__outer) {
  background-color: rgba(93, 235, 219, 0.12);
}

:deep(.el-progress-bar__inner) {
  background: linear-gradient(90deg, var(--ppgl-primary), var(--ppgl-accent));
  box-shadow: 0 0 16px rgba(32, 224, 196, 0.34);
}
</style>
