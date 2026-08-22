<template>
  <div class="page-shell dashboard-page">
    <section class="overview-intro">
      <div class="intro-copy">
        <div class="section-kicker">Clinical Imaging AI Workbench</div>
        <h1>PPGL 术前 CT 智能分割与辅助分析</h1>
        <p>
          面向 PPGL 术前影像评估，整合 CT 上传、肿瘤与器官分割、量化指标、三维重建和 AI 辅助报告。
        </p>

        <div class="intro-actions">
          <el-button type="primary" size="large" :icon="UploadFilled" @click="goPage('/upload')">
            上传 CT
          </el-button>
          <el-button size="large" @click="goPage('/cases')">
            查看病例队列
          </el-button>
        </div>
      </div>

      <ClinicalPreviewPanel
        class="intro-preview"
        :image-url="previewImageUrl"
        :case-id="previewCaseId"
        :slice-title="previewSliceTitle"
        :loading="previewLoading"
      />
    </section>

    <StatsBar :stats="stats" />

    <section class="workbench-grid">
      <div class="workflow-main">
        <PrimaryActionPanel
          :actions="secondaryActions"
          @primary-action="goPage('/upload')"
          @action="goPage"
        />
        <WorkflowStepper :steps="workflowSteps" />
      </div>

      <SystemStatusPanel />
    </section>

    <RecentCasesTable
      :cases="recentCases"
      @open-case="handleRecentCase"
    />
  </div>
</template>

<script setup>
import { markRaw, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  DataAnalysis,
  Document,
  Files,
  UploadFilled,
  View
} from '@element-plus/icons-vue'
import ClinicalPreviewPanel from '../components/dashboard/ClinicalPreviewPanel.vue'
import PrimaryActionPanel from '../components/dashboard/PrimaryActionPanel.vue'
import RecentCasesTable from '../components/dashboard/RecentCasesTable.vue'
import StatsBar from '../components/dashboard/StatsBar.vue'
import SystemStatusPanel from '../components/dashboard/SystemStatusPanel.vue'
import WorkflowStepper from '../components/dashboard/WorkflowStepper.vue'
import { getCaseList, getSliceGallery, getSliceImageUrl } from '../api/caseApi'

const router = useRouter()
const previewImageUrl = ref('')
const previewCaseId = ref('')
const previewSliceTitle = ref('')
const previewLoading = ref(false)

const stats = [
  {
    title: '累计病例',
    value: 12,
    desc: '较昨日新增 2 例'
  },
  {
    title: '已完成分割',
    value: 9,
    desc: '完成率 75%'
  },
  {
    title: '处理中任务',
    value: 2,
    desc: '等待 AI 分析'
  },
  {
    title: 'AI 辅助报告',
    value: 7,
    desc: '结构化报告已生成'
  }
]

const secondaryActions = [
  {
    title: '病例管理',
    desc: '查看病例列表',
    path: '/cases',
    icon: markRaw(Files)
  },
  {
    title: '分割结果',
    desc: '查看 mask 叠加',
    path: '/cases/demo-case',
    icon: markRaw(View)
  },
  {
    title: '三维重建',
    desc: '查看 3D 模型',
    path: '/cases/demo-case/3d',
    icon: markRaw(DataAnalysis)
  },
  {
    title: 'AI 报告',
    desc: '查看辅助分析',
    path: '/cases/demo-case/report',
    icon: markRaw(Document)
  }
]

const workflowSteps = [
  {
    title: '上传 CT',
    desc: '导入患者影像',
    active: true
  },
  {
    title: 'AI 分割',
    desc: '肿瘤及多器官自动分割',
    active: true,
    current: true
  },
  {
    title: '量化分析',
    desc: '计算体积、距离等指标',
    active: true
  },
  {
    title: '三维重建',
    desc: '生成三维可视化结果',
    active: true
  },
  {
    title: '辅助报告',
    desc: '输出结构化辅助分析报告',
    active: false
  }
]

const recentCases = [
  {
    caseId: 'PPGL-001',
    source: 'NIfTI CT',
    status: '已完成',
    statusType: 'success',
    progress: 100,
    reportStatus: '已生成',
    updatedAt: '2026-05-23 14:20',
    path: '/cases/demo-case'
  },
  {
    caseId: 'PPGL-002',
    source: 'NIfTI CT',
    status: '分割中',
    statusType: 'warning',
    progress: 64,
    reportStatus: '待生成',
    updatedAt: '2026-05-23 13:48',
    path: '/cases/demo-case'
  },
  {
    caseId: 'PPGL-003',
    source: '外部 TotalSeg',
    status: '后处理',
    statusType: 'info',
    progress: 82,
    reportStatus: '待审核',
    updatedAt: '2026-05-22 18:11',
    path: '/cases/demo-case/report'
  }
]

function goPage(path) {
  router.push(path)
}

function handleRecentCase(row) {
  if (row.path) {
    router.push(row.path)
  }
}

function pickPreviewSlice(slices = []) {
  return (
    slices.find(item => item.plane === 'axial' && /tumor|肿瘤/i.test(item.title || '')) ||
    slices.find(item => item.plane === 'axial') ||
    slices[0]
  )
}

async function loadClinicalPreview() {
  previewLoading.value = true
  try {
    const payload = await getCaseList()
    const caseRows = payload.cases || []
    const candidateIds = [
      ...caseRows.filter(item => item.status === 'completed').map(item => item.case_id),
      'demo-case'
    ].filter(Boolean)

    for (const caseId of candidateIds) {
      try {
        const gallery = await getSliceGallery(caseId)
        const slice = pickPreviewSlice(gallery.slices || [])
        if (slice?.filename) {
          previewCaseId.value = caseId
          previewSliceTitle.value = slice.title || `${slice.plane || 'slice'} ${slice.index || ''}`
          previewImageUrl.value = `${getSliceImageUrl(caseId, slice.filename)}?t=${Date.now()}`
          return
        }
      } catch (err) {
        // Try the next candidate; fallback illustration remains visible if none is available.
      }
    }
  } finally {
    previewLoading.value = false
  }
}

onMounted(loadClinicalPreview)
</script>

<style scoped>
.dashboard-page {
  max-width: 1560px;
  min-height: 100%;
  margin: 0 auto;
}

.overview-intro {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 36px;
  align-items: center;
  padding: 18px 0 28px;
}

.section-kicker {
  margin-bottom: 10px;
  color: #7fb4ad;
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}

.intro-copy h1 {
  max-width: 860px;
  margin: 0;
  color: #f8fafc;
  font-size: 34px;
  font-weight: 900;
  line-height: 1.22;
  letter-spacing: 0;
}

.intro-copy p {
  max-width: 780px;
  margin: 14px 0 22px;
  color: #9aafbf;
  font-size: 15px;
  line-height: 1.75;
}

.intro-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.workbench-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
}

.workflow-main {
  min-width: 0;
  padding-right: 24px;
}

@media (max-width: 1180px) {
  .overview-intro,
  .workbench-grid {
    grid-template-columns: 1fr;
  }

  .intro-preview {
    max-width: 420px;
  }

  .workflow-main {
    padding-right: 0;
  }
}
</style>
