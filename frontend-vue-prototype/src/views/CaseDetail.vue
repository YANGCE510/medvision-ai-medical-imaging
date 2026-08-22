<template>
  <div class="page-shell case-detail-page">
    <div class="page-header">
      <div>
        <h2>病例详情</h2>
        <p>病例编号：{{ caseId }}</p>
      </div>

      <div class="page-header-actions">
        <el-button @click="refresh">刷新</el-button>
        <el-button v-if="canStart" type="warning" @click="startCurrentSegmentation">启动分割</el-button>
        <el-button @click="go3D">查看三维重建</el-button>
        <el-button type="primary" @click="goReport">查看 AI 报告</el-button>
      </div>
    </div>

    <el-alert
      v-if="status.status === 'failed'"
      class="status-alert"
      :title="status.error || status.message || 'AI 分割失败'"
      type="error"
      show-icon
    />

    <el-row :gutter="20">
      <el-col :xs="24" :lg="16">
        <el-card class="viewer-card" shadow="never">
          <template #header>
            <div class="section-header">
              <div>
                <strong>二维关键切片</strong>
                <p>自动选取肿瘤和关键结构所在层面</p>
              </div>
            </div>
          </template>

          <div v-if="sliceCards.length" class="slice-gallery">
            <div
              v-for="item in sliceCards"
              :key="item.filename"
              class="slice-tile"
            >
              <img :src="item.url" :alt="item.title" />
              <div class="slice-caption">
                <strong>{{ item.title }}</strong>
                <span>{{ planeText(item.plane) }} · 第 {{ item.index }} 层</span>
              </div>
            </div>
          </div>

          <div v-else-if="overlaySrc" class="image-viewer">
            <img :src="overlaySrc" alt="Segmentation overlay" />
          </div>
          <div v-else class="image-placeholder">
            <div>
              <p>{{ status.message || '等待分割结果' }}</p>
              <el-progress :percentage="status.progress || 0" />
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="8">
        <el-card class="metric-card" shadow="never">
          <template #header>
            <div class="section-header">
              <div>
                <strong>量化指标</strong>
                <p>由分割结果自动计算</p>
              </div>
            </div>
          </template>

          <el-descriptions :column="1" border>
            <el-descriptions-item label="分割状态">
              <el-tag :type="statusTagType">
                {{ statusText }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="进度">
              {{ status.progress || 0 }}%
            </el-descriptions-item>
            <el-descriptions-item label="肿瘤体积">
              {{ formatNumber(summary.tumor_volume_ml) }} ml
            </el-descriptions-item>
            <el-descriptions-item label="最大径">
              {{ formatNumber(maxDiameter) }} mm
            </el-descriptions-item>
            <el-descriptions-item label="中心点">
              {{ centroidText }}
            </el-descriptions-item>
            <el-descriptions-item label="距腹主动脉">
              {{ formatNumber(aortaDistance) }} mm
            </el-descriptions-item>
            <el-descriptions-item label="左右侧">
              {{ summary.tumor_side_by_nearest_kidney || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="分割标签数">
              {{ result?.segmentation?.label_count || '-' }}
            </el-descriptions-item>
          </el-descriptions>

          <div class="actions">
            <el-button v-if="status.status === 'completed'" type="primary" @click="downloadMask">
              下载 mask.nii.gz
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header">
          <div>
            <strong>处理流程</strong>
            <p>病例从上传到结果整理的当前节点</p>
          </div>
        </div>
      </template>

      <el-steps :active="activeStep" align-center>
        <el-step title="已上传" />
        <el-step title="AI 分割" />
        <el-step title="后处理" />
        <el-step title="结果整理" />
        <el-step title="完成" />
      </el-steps>
    </el-card>

    <el-card v-if="labelNames.length" class="section-card" shadow="never">
      <template #header>
        <div class="section-header">
          <div>
            <strong>分割类别</strong>
            <p>当前病例输出的可展示标签</p>
          </div>
        </div>
      </template>
      <el-tag v-for="name in labelNames" :key="name" class="label-tag">
        {{ name }}
      </el-tag>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import {
  getCaseResult,
  getCaseStatus,
  getSliceGallery,
  getSliceImageUrl,
  JETSON_TRT_SEGMENTATION_PARAMS,
  getMaskUrl,
  getOverlayUrl,
  startSegmentation
} from '../api/caseApi'

const route = useRoute()
const router = useRouter()

const caseId = route.params.caseId
const status = ref({ status: 'loading', message: '正在加载病例状态', progress: 0 })
const result = ref(null)
const sliceGallery = ref([])
const overlayVersion = ref(Date.now())
let pollTimer = null

const summary = computed(() => result.value?.summary || {})
const statusTagType = computed(() => {
  const map = {
    uploaded: 'info',
    queued: 'warning',
    running: 'warning',
    completed: 'success',
    failed: 'danger',
    loading: 'info'
  }
  return map[status.value.status] || 'info'
})
const statusText = computed(() => {
  const map = {
    uploaded: '已上传',
    queued: '排队中',
    running: '分割中',
    completed: '已完成',
    failed: '失败',
    loading: '加载中'
  }
  return map[status.value.status] || status.value.status
})
const activeStep = computed(() => {
  const map = {
    uploaded: 1,
    queued: 2,
    running: 2,
    failed: 2,
    completed: 5
  }
  return map[status.value.status] || 1
})
const canStart = computed(() => ['uploaded', 'queued', 'failed'].includes(status.value.status))
const overlaySrc = computed(() => {
  if (status.value.status !== 'completed') return ''
  return `${getOverlayUrl(caseId)}?t=${overlayVersion.value}`
})
const sliceCards = computed(() => {
  if (status.value.status !== 'completed') return []
  return sliceGallery.value.map(item => ({
    ...item,
    url: `${getSliceImageUrl(caseId, item.filename)}?t=${overlayVersion.value}`
  }))
})
const maxDiameter = computed(() => {
  const bbox = summary.value.largest_component_bbox_size_mm
  return Array.isArray(bbox) && bbox.length ? Math.max(...bbox) : null
})
const aortaDistance = computed(() => summary.value.anchor_distances_mm?.aorta)
const centroidText = computed(() => {
  const centroid = summary.value.largest_component_centroid_mm
  if (!Array.isArray(centroid)) return '-'
  return `[${centroid.map(v => formatNumber(v)).join(', ')}]`
})
const labelNames = computed(() => {
  const labelMap = result.value?.segmentation?.label_map || {}
  return Object.values(labelMap).filter(name => name !== 'background')
})

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(2)
}

function planeText(plane) {
  const map = {
    axial: '轴位',
    coronal: '冠状位',
    sagittal: '矢状位'
  }
  return map[plane] || plane
}

function clearPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function ensurePolling() {
  if (pollTimer) return
  pollTimer = setInterval(loadStatus, 3000)
}

async function loadStatus() {
  try {
    status.value = await getCaseStatus(caseId)
    if (status.value.status === 'completed') {
      clearPoll()
      await loadResult()
    } else if (status.value.status === 'queued' || status.value.status === 'running') {
      ensurePolling()
    } else if (status.value.status === 'failed') {
      clearPoll()
    }
  } catch (err) {
    clearPoll()
    ElMessage.error(err?.response?.data?.detail || '病例状态加载失败')
  }
}

async function loadResult() {
  try {
    result.value = await getCaseResult(caseId)
    overlayVersion.value = Date.now()
    await loadSliceGallery()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '分割结果加载失败')
  }
}

async function loadSliceGallery() {
  try {
    const payload = await getSliceGallery(caseId)
    sliceGallery.value = payload.slices || []
  } catch (err) {
    sliceGallery.value = []
  }
}

async function refresh() {
  await loadStatus()
}

async function startCurrentSegmentation() {
  try {
    await startSegmentation(caseId, JETSON_TRT_SEGMENTATION_PARAMS)
    ElMessage.success('已启动智能分割任务')
    await loadStatus()
    ensurePolling()
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '启动分割失败')
  }
}

function downloadMask() {
  window.open(getMaskUrl(caseId), '_blank')
}

function go3D() {
  router.push(`/cases/${caseId}/3d`)
}

function goReport() {
  router.push(`/cases/${caseId}/report`)
}

onMounted(loadStatus)
onUnmounted(clearPoll)
</script>

<style scoped>
.case-detail-page {
  min-height: 100%;
}

.status-alert {
  margin-bottom: 18px;
}

.viewer-card,
.metric-card,
.section-card {
  border-radius: var(--ppgl-radius);
  border-color: rgba(93, 235, 219, 0.22);
  background: rgba(8, 23, 36, 0.78);
}

.metric-card {
  min-height: 100%;
}

.image-placeholder,
.image-viewer {
  height: 430px;
  background:
    linear-gradient(90deg, rgba(93, 235, 219, 0.06) 1px, transparent 1px),
    linear-gradient(180deg, rgba(93, 235, 219, 0.045) 1px, transparent 1px),
    #050b13;
  background-size: 24px 24px;
  border-radius: var(--ppgl-radius);
  color: #cbd5e1;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  border: 1px solid rgba(93, 235, 219, 0.24);
  overflow: hidden;
}

.slice-gallery {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.slice-tile {
  overflow: hidden;
  border: 1px solid rgba(93, 235, 219, 0.24);
  border-radius: var(--ppgl-radius);
  background: #050b13;
  box-shadow: 0 16px 34px rgba(0, 0, 0, 0.24), 0 0 18px rgba(32, 224, 196, 0.08);
  transition: transform 0.2s ease, border-color 0.2s ease;
}

.slice-tile:hover {
  transform: translateY(-2px);
  border-color: rgba(93, 235, 219, 0.48);
}

.slice-tile img {
  display: block;
  width: 100%;
  height: 300px;
  object-fit: contain;
  background: #020617;
}

.slice-caption {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  background: rgba(8, 23, 36, 0.96);
  color: #e5edf5;
  border-top: 1px solid rgba(93, 235, 219, 0.18);
}

.slice-caption strong {
  font-size: 14px;
}

.slice-caption span {
  flex: 0 0 auto;
  color: #9fb0c2;
  font-size: 12px;
}

.image-viewer img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.actions {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
}

.section-card {
  margin-top: 24px;
}

.label-tag {
  margin: 0 8px 8px 0;
}

:deep(.el-descriptions__label.el-descriptions__cell) {
  width: 112px;
  color: #b9f8f1;
  background: rgba(32, 224, 196, 0.08) !important;
  font-weight: 800;
}

:deep(.el-step__title) {
  font-weight: 700;
  color: var(--ppgl-text);
}

:deep(.el-step__line) {
  background-color: rgba(93, 235, 219, 0.18);
}

:deep(.el-step__head.is-process),
:deep(.el-step__head.is-finish) {
  color: var(--ppgl-primary);
  border-color: var(--ppgl-primary);
}

@media (max-width: 1100px) {
  .slice-gallery {
    grid-template-columns: 1fr;
  }
}
</style>
