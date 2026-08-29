<template>
  <section class="page-shell trace-center-page">
    <div class="page-header">
      <div>
        <div class="section-kicker">LOCAL AI OBSERVABILITY</div>
        <h2>AI Trace 与评测中心</h2>
        <p>追踪本地 AI 请求的阶段、模型、检索证据、GPU 等待与失败原因；不保存原始影像或原始问答内容。</p>
      </div>
      <div class="page-header-actions">
        <span class="updated-at">最近同步 {{ formatTime(lastUpdatedAt) }}</span>
        <el-button :loading="loading" @click="loadAll">立即刷新</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="Trace 记录仅保存任务元数据、耗时、模型和证据标识；病例仅使用内部编号，原始影像、问题与回答不会写入 Trace。"
    />

    <el-row :gutter="16" class="metric-grid">
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="metric-card">
          <span>最近调用</span>
          <strong>{{ summary.total ?? 0 }}</strong>
          <small>当前账号可查看的 Trace</small>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="metric-card success">
          <span>完成成功率</span>
          <strong>{{ formatPercent(summary.success_rate) }}</strong>
          <small>{{ summary.succeeded ?? 0 }} 次成功 / {{ summary.completed ?? 0 }} 次完成</small>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="metric-card warning">
          <span>失败调用</span>
          <strong>{{ summary.failed ?? 0 }}</strong>
          <small>失败原因可在链路详情查看</small>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="metric-card">
          <span>平均端到端耗时</span>
          <strong>{{ formatDuration(summary.average_duration_ms) }}</strong>
          <small>包含检索、模型、GPU 等待和后处理</small>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <strong>最近 AI 调用</strong>
          <div class="filters">
            <el-select v-model="operationFilter" placeholder="全部类型" clearable @change="loadTraces" style="width: 174px">
              <el-option v-for="item in operationOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-select v-model="statusFilter" placeholder="全部状态" clearable @change="loadTraces" style="width: 128px">
              <el-option label="运行中" value="running" />
              <el-option label="完成" value="completed" />
              <el-option label="失败" value="failed" />
              <el-option label="已取消" value="cancelled" />
            </el-select>
          </div>
        </div>
      </template>
      <el-table :data="traces" empty-text="尚无 AI Trace；运行 RAG 问答、AI 报告问答或分割任务后会自动出现。">
        <el-table-column label="类型" min-width="150">
          <template #default="scope">{{ operationLabel(scope.row.operation) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="104">
          <template #default="scope"><el-tag :type="statusType(scope.row.status)">{{ statusLabel(scope.row.status) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="模型 / 任务" min-width="190" show-overflow-tooltip>
          <template #default="scope">{{ traceModel(scope.row) }}</template>
        </el-table-column>
        <el-table-column label="证据与结果" min-width="155" show-overflow-tooltip>
          <template #default="scope">{{ traceResult(scope.row) }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="118">
          <template #default="scope">{{ formatDuration(scope.row.duration_ms) }}</template>
        </el-table-column>
        <el-table-column label="开始时间" min-width="166">
          <template #default="scope">{{ formatTime(scope.row.started_at) }}</template>
        </el-table-column>
        <el-table-column label="链路" width="94" fixed="right">
          <template #default="scope"><el-button link type="primary" @click="selectTrace(scope.row.trace_id)">查看</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="selectedTrace" shadow="never" class="section-card trace-detail-card">
      <template #header>
        <div class="section-header">
          <strong>调用链路详情</strong>
          <el-button link @click="selectedTrace = null">收起</el-button>
        </div>
      </template>
      <div class="trace-identity">
        <span>Trace ID：{{ selectedTrace.trace_id }}</span>
        <el-tag :type="statusType(selectedTrace.status)">{{ statusLabel(selectedTrace.status) }}</el-tag>
        <span>{{ operationLabel(selectedTrace.operation) }}</span>
      </div>
      <el-descriptions :column="3" border class="trace-descriptions">
        <el-descriptions-item label="模型 / 任务">{{ traceModel(selectedTrace) }}</el-descriptions-item>
        <el-descriptions-item label="端到端耗时">{{ formatDuration(selectedTrace.duration_ms) }}</el-descriptions-item>
        <el-descriptions-item label="病例内部编号">{{ selectedTrace.metadata?.case_id || '—' }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ formatTime(selectedTrace.started_at) }}</el-descriptions-item>
        <el-descriptions-item label="结束时间">{{ formatTime(selectedTrace.completed_at) }}</el-descriptions-item>
        <el-descriptions-item label="证据等级">{{ selectedTrace.result?.evidence_level || '—' }}</el-descriptions-item>
      </el-descriptions>
      <el-table :data="selectedTrace.events || []" class="event-table" empty-text="暂无阶段事件">
        <el-table-column label="阶段" min-width="180"><template #default="scope">{{ stageLabel(scope.row.stage) }}</template></el-table-column>
        <el-table-column label="状态" width="116"><template #default="scope"><el-tag :type="statusType(scope.row.status)">{{ statusLabel(scope.row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="耗时" width="118"><template #default="scope">{{ formatDuration(scope.row.duration_ms) }}</template></el-table-column>
        <el-table-column label="时间" min-width="170"><template #default="scope">{{ formatTime(scope.row.at) }}</template></el-table-column>
        <el-table-column label="摘要" min-width="240" show-overflow-tooltip><template #default="scope">{{ detailText(scope.row.details) }}</template></el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <strong>已记录的 RAG 评测版本</strong>
          <span class="muted">读取仓库中的脱敏评测结果，用于比较检索配置调整前后的质量与延迟。</span>
        </div>
      </template>
      <el-table :data="evaluations" empty-text="未发现已记录的 RAG 评测结果。">
        <el-table-column prop="evaluation_id" label="评测版本" min-width="280" show-overflow-tooltip />
        <el-table-column label="检索命中" width="120"><template #default="scope">{{ formatPercent(scope.row.summary?.retrieval_hit_rate) }}</template></el-table-column>
        <el-table-column label="目标文献引用" width="140"><template #default="scope">{{ formatPercent(scope.row.summary?.expected_source_cited_rate) }}</template></el-table-column>
        <el-table-column label="有效引用" width="118"><template #default="scope">{{ formatPercent(scope.row.summary?.valid_citation_rate) }}</template></el-table-column>
        <el-table-column label="平均耗时" width="120"><template #default="scope">{{ formatSeconds(scope.row.summary?.average_wall_time_s) }}</template></el-table-column>
        <el-table-column label="P95 耗时" width="118"><template #default="scope">{{ formatSeconds(scope.row.summary?.p95_wall_time_s) }}</template></el-table-column>
        <el-table-column label="检索参数" min-width="170"><template #default="scope">{{ scope.row.retrieval_mode }} · top {{ scope.row.top_k }} / {{ scope.row.retrieve_k }}</template></el-table-column>
      </el-table>
    </el-card>
  </section>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getTraceDetail, getTraceEvaluations, getTraceList } from '../api/traceApi'

const traces = ref([])
const summary = ref({})
const evaluations = ref([])
const selectedTrace = ref(null)
const loading = ref(false)
const operationFilter = ref('')
const statusFilter = ref('')
const lastUpdatedAt = ref('')
let refreshTimer = null

const operationOptions = [
  { value: 'rag_query', label: '医学知识库问答' },
  { value: 'case_rag_query', label: '病例知识库问答' },
  { value: 'llm_chat', label: 'AI 问答' },
  { value: 'report_chat', label: 'AI 报告问答' },
  { value: 'organ_segmentation', label: '全器官分割' },
  { value: 'ppgl_segmentation', label: 'PPGL 肿瘤分割' },
  { value: 'glioma_segmentation', label: '脑胶质瘤分割' },
  { value: 'organ_result_normalization', label: '全器官结果整理' }
]

async function loadTraces(silent = false) {
  try {
    const payload = await getTraceList({
      limit: 80,
      operation: operationFilter.value || undefined,
      status: statusFilter.value || undefined
    })
    traces.value = payload.traces || []
    summary.value = payload.summary || {}
    lastUpdatedAt.value = new Date().toISOString()
  } catch (error) {
    if (!silent) ElMessage.error(error?.response?.data?.detail || 'AI Trace 读取失败')
  }
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([
      loadTraces(),
      getTraceEvaluations().then(payload => {
        evaluations.value = payload.evaluations || []
      })
    ])
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '评测数据读取失败')
  } finally {
    loading.value = false
  }
}

async function selectTrace(traceId) {
  try {
    selectedTrace.value = await getTraceDetail(traceId)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '调用链路详情读取失败')
  }
}

function operationLabel(value) {
  return operationOptions.find(item => item.value === value)?.label || value || '未知任务'
}

function stageLabel(value) {
  return {
    request_received: 'AI 服务接收请求',
    task_queued: '任务进入队列',
    gpu_admission: 'GPU 准入与排队',
    retrieval_and_rerank: '检索与重排',
    model_generation: '本地模型生成',
    model_inference: '影像模型推理',
    result_normalization: '结果整理',
    request_finished: '请求完成',
    task_finished: '任务完成'
  }[value] || value || '未知阶段'
}

function statusLabel(value) {
  return {
    running: '运行中',
    completed: '完成',
    failed: '失败',
    cancelled: '已取消',
    queued: '排队中'
  }[value] || value || '未知'
}

function statusType(value) {
  return {
    running: 'primary',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info',
    queued: 'warning'
  }[value] || 'info'
}

function traceModel(trace) {
  return trace.result?.model || trace.metadata?.model || trace.metadata?.task || '—'
}

function traceResult(trace) {
  if (trace.error?.type) return `${trace.error.type}：${trace.error.message || '失败'}`
  if (trace.result?.evidence_level) return `证据：${trace.result.evidence_level} · 引用 ${trace.result.citation_count || 0} 篇`
  return trace.result?.task || trace.metadata?.case_id || '—'
}

function detailText(details) {
  if (!details || typeof details !== 'object') return '—'
  return Object.entries(details)
    .filter(([, value]) => value !== null && value !== '' && value !== undefined)
    .map(([key, value]) => `${key}=${Array.isArray(value) ? value.join(', ') : typeof value === 'object' ? JSON.stringify(value) : value}`)
    .join(' · ') || '—'
}

function formatPercent(value) {
  const number = Number(value)
  return Number.isFinite(number) ? `${Math.round(number * 100)}%` : '—'
}

function formatDuration(value) {
  const milliseconds = Number(value)
  if (!Number.isFinite(milliseconds)) return '—'
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`
  return `${(milliseconds / 1000).toFixed(2)} 秒`
}

function formatSeconds(value) {
  const seconds = Number(value)
  return Number.isFinite(seconds) ? `${seconds.toFixed(2)} 秒` : '—'
}

function formatTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(() => {
  loadAll()
  refreshTimer = window.setInterval(() => loadTraces(true), 8000)
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<style scoped>
.trace-center-page { max-width: 1560px; margin: 0 auto; }
.section-kicker { margin-bottom: 8px; color: #7fb4ad; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.page-header p { max-width: 820px; }
.updated-at, .muted { color: var(--ppgl-muted); font-size: 12px; }
.metric-grid { margin-bottom: 16px; }
.metric-card { min-height: 126px; display: grid; align-content: center; gap: 6px; }
.metric-card span, .metric-card small { color: var(--ppgl-muted); }
.metric-card strong { color: var(--ppgl-text); font-size: 28px; }
.metric-card.success strong { color: var(--ppgl-success); }
.metric-card.warning strong { color: var(--ppgl-warning); }
.section-card { margin-bottom: 16px; }
.section-header, .filters, .trace-identity { display: flex; align-items: center; gap: 10px; }
.section-header { justify-content: space-between; }
.section-header strong { color: var(--ppgl-text); }
.trace-identity { flex-wrap: wrap; margin-bottom: 16px; color: var(--ppgl-muted); font-size: 13px; }
.trace-descriptions { margin-bottom: 16px; }
.event-table { margin-top: 12px; }
:deep(.el-alert) { margin-bottom: 16px; background: rgba(32, 224, 196, 0.08); border: 1px solid rgba(93, 235, 219, 0.2); }
:deep(.el-select__wrapper) { background: rgba(4, 15, 25, 0.72); }
@media (max-width: 880px) {
  .section-header { align-items: flex-start; flex-direction: column; }
  .filters { width: 100%; flex-wrap: wrap; }
}
</style>
