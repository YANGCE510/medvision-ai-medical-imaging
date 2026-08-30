<template>
  <div class="page-shell knowledge-page">
    <div class="page-header">
      <div>
        <h2>PPGL 医学知识库</h2>
        <p>本地向量检索 · 可追溯文献证据 · 带引用医学知识问答</p>
      </div>
      <div class="header-tags">
        <el-tag v-if="caseId" type="warning" effect="dark">当前病例：{{ caseId }}</el-tag>
        <el-tag :type="catalog.index?.ready ? 'success' : 'warning'" effect="dark">
          {{ catalog.index?.ready ? `索引就绪 · ${catalog.index.points || 0} 条向量` : '索引待初始化' }}
        </el-tag>
      </div>
    </div>

    <el-card class="asset-card" shadow="never">
      <template #header>
        <div class="card-title">
          <div>
            <strong>知识库资产与评测</strong>
            <span>展示当前运行时索引，以及已记录的 20 题脱敏评测结果</span>
          </div>
          <el-button :loading="assetsLoading" @click="loadKnowledgeAssets">刷新状态</el-button>
        </div>
      </template>

      <el-alert
        v-if="catalogError"
        :title="catalogError"
        type="warning"
        show-icon
        :closable="false"
      />

      <el-row :gutter="12" class="asset-metric-grid">
        <el-col :xs="12" :sm="6">
          <div class="asset-metric"><span>已纳入文献</span><strong>{{ catalog.document_count || 0 }}</strong><small>来自已构建切块</small></div>
        </el-col>
        <el-col :xs="12" :sm="6">
          <div class="asset-metric"><span>知识切块</span><strong>{{ catalog.chunk_count || 0 }}</strong><small>用于检索的证据单元</small></div>
        </el-col>
        <el-col :xs="12" :sm="6">
          <div class="asset-metric"><span>索引向量</span><strong>{{ catalog.index?.points || 0 }}</strong><small>{{ catalog.index?.vector_size ? `${catalog.index.vector_size} 维` : '等待初始化' }}</small></div>
        </el-col>
        <el-col :xs="12" :sm="6">
          <div class="asset-metric"><span>最新评测命中</span><strong>{{ formatPercent(catalog.latest_evaluation?.summary?.retrieval_hit_rate) }}</strong><small>{{ catalog.latest_evaluation?.summary?.total || 0 }} 题评测集</small></div>
        </el-col>
      </el-row>

      <el-descriptions :column="3" border class="asset-descriptions">
        <el-descriptions-item label="向量提供方">{{ catalog.embedding?.provider || '—' }}</el-descriptions-item>
        <el-descriptions-item label="向量模型">{{ catalog.embedding?.model || '—' }}</el-descriptions-item>
        <el-descriptions-item label="索引状态">{{ catalog.index?.message || '—' }}</el-descriptions-item>
      </el-descriptions>

      <el-collapse v-model="activeManagementPanels" class="management-collapse">
        <el-collapse-item name="documents">
          <template #title>
            <strong>文献来源与切块清单（{{ catalog.document_count || 0 }} 篇）</strong>
          </template>
          <el-table :data="catalog.documents || []" max-height="280" empty-text="尚未发现知识库切块，请先完成知识库初始化。">
            <el-table-column prop="title" label="文献" min-width="340" show-overflow-tooltip />
            <el-table-column prop="document_id" label="来源编号" min-width="150" show-overflow-tooltip />
            <el-table-column prop="year" label="年份" width="90" />
            <el-table-column prop="chunks" label="切块数" width="94" />
            <el-table-column label="原始来源" width="104">
              <template #default="scope">
                <a v-if="scope.row.source_url" :href="scope.row.source_url" target="_blank" rel="noreferrer">查看</a>
                <span v-else>—</span>
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>

        <el-collapse-item name="evaluations">
          <template #title>
            <strong>20 题检索与引用评测（{{ evaluations.length }} 个版本）</strong>
          </template>
          <div class="evaluation-toolbar">
            <el-select v-model="selectedEvaluationId" class="evaluation-select" placeholder="选择评测版本">
              <el-option
                v-for="evaluation in evaluations"
                :key="evaluation.evaluation_id"
                :label="`${evaluation.evaluation_id} · ${formatTime(evaluation.generated_at)}`"
                :value="evaluation.evaluation_id"
              />
            </el-select>
            <span v-if="selectedEvaluation" class="muted">
              {{ selectedEvaluation.retrieval_mode }} · top {{ selectedEvaluation.top_k }} / {{ selectedEvaluation.retrieve_k }}
            </span>
          </div>
          <el-row v-if="selectedEvaluation" :gutter="12" class="evaluation-metric-grid">
            <el-col :xs="12" :sm="6"><div class="evaluation-metric"><span>检索命中</span><strong>{{ formatPercent(selectedEvaluation.summary?.retrieval_hit_rate) }}</strong></div></el-col>
            <el-col :xs="12" :sm="6"><div class="evaluation-metric"><span>目标文献引用</span><strong>{{ formatPercent(selectedEvaluation.summary?.expected_source_cited_rate) }}</strong></div></el-col>
            <el-col :xs="12" :sm="6"><div class="evaluation-metric"><span>有效引用</span><strong>{{ formatPercent(selectedEvaluation.summary?.valid_citation_rate) }}</strong></div></el-col>
            <el-col :xs="12" :sm="6"><div class="evaluation-metric"><span>P95 耗时</span><strong>{{ formatSeconds(selectedEvaluation.summary?.p95_wall_time_s) }}</strong></div></el-col>
          </el-row>
          <el-table :data="selectedEvaluation?.cases || []" max-height="360" empty-text="未发现评测明细。">
            <el-table-column prop="id" label="题号" width="90" />
            <el-table-column prop="question" label="脱敏评测问题" min-width="340" show-overflow-tooltip />
            <el-table-column label="检索命中" width="104"><template #default="scope"><el-tag size="small" :type="resultTagType(scope.row.retrieval_hit)">{{ resultText(scope.row.retrieval_hit) }}</el-tag></template></el-table-column>
            <el-table-column label="目标引用" width="104"><template #default="scope"><el-tag size="small" :type="resultTagType(scope.row.expected_source_cited)">{{ resultText(scope.row.expected_source_cited) }}</el-tag></template></el-table-column>
            <el-table-column label="耗时" width="96"><template #default="scope">{{ formatSeconds(scope.row.wall_time_s) }}</template></el-table-column>
            <el-table-column label="操作" width="88" fixed="right"><template #default="scope"><el-button link type="primary" @click="useEvaluationQuestion(scope.row.question)">用于问答</el-button></template></el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <div class="knowledge-layout">
      <el-card class="query-card" shadow="never">
        <template #header>
          <div class="card-title">
            <strong>知识库问答</strong>
            <span>回答仅使用检索到的指南、共识和论文证据</span>
          </div>
        </template>

        <el-alert
          v-if="caseId"
          class="case-alert"
          :title="`已绑定病例 ${caseId}：回答将同时使用病例分割数据和医学知识库`"
          type="warning"
          show-icon
          :closable="false"
        />

        <div class="example-list">
          <el-button
            v-for="example in exampleQuestions"
            :key="example"
            size="small"
            plain
            @click="question = example"
          >
            {{ example }}
          </el-button>
        </div>

        <el-input
          v-model="question"
          type="textarea"
          :rows="4"
          maxlength="1000"
          show-word-limit
          placeholder="例如：PPGL 的 CT 影像表现和术前血管评估要点是什么？"
          @keydown="handleKeydown"
        />

        <div class="query-actions">
          <span>Ctrl / Cmd + Enter 提交</span>
          <el-button type="primary" :loading="loading" @click="askKnowledgeBase">
            {{ loading ? '正在检索并生成' : '开始问答' }}
          </el-button>
        </div>

        <div v-if="answer" class="answer-panel">
          <div class="answer-heading">
            <strong>AI 回答</strong>
            <span>{{ metadata.retrieval || '本地语义检索' }} · {{ totalLatencyText }}</span>
          </div>
          <div v-if="caseContext" class="case-facts">
            <el-tag size="small">器官 {{ caseContext.segmentation?.organ_count ?? '-' }}</el-tag>
            <el-tag size="small">标签 {{ caseContext.segmentation?.label_count ?? '-' }}</el-tag>
            <el-tag
              size="small"
              :type="caseContext.segmentation?.tumor_analysis_available ? 'success' : 'warning'"
            >
              {{ caseContext.segmentation?.tumor_analysis_available ? '已有肿瘤量化' : '无肿瘤量化' }}
            </el-tag>
          </div>
          <div v-if="evidenceAssessment" class="evidence-assessment">
            <div class="assessment-header">
              <el-tag size="small" :type="assessmentTagType">
                {{ evidenceAssessment.level_text || '证据评估' }}
              </el-tag>
              <span>
                已引用 {{ evidenceAssessment.cited_count || 0 }} / {{ evidenceAssessment.retrieved_count || 0 }} 条证据
              </span>
            </div>
            <el-progress
              :percentage="assessmentCoveragePercent"
              :show-text="false"
              :status="assessmentProgressStatus"
            />
            <ul v-if="evidenceAssessment.warnings?.length" class="assessment-warnings">
              <li v-for="warning in evidenceAssessment.warnings" :key="warning">{{ warning }}</li>
            </ul>
          </div>
          <div class="markdown-content" v-html="renderMarkdown(answer)"></div>
        </div>

        <el-empty
          v-else-if="!loading"
          description="输入问题后，系统将先检索医学证据，再生成带引用的回答"
        />
      </el-card>

      <el-card class="evidence-card" shadow="never">
        <template #header>
          <div class="card-title">
            <strong>检索证据</strong>
            <span>{{ citations.length ? `共 ${citations.length} 条` : '等待检索' }}</span>
          </div>
        </template>

        <el-scrollbar class="evidence-list">
          <article
            v-for="citation in citations"
            :key="citation.id"
            class="evidence-item"
          >
            <div class="evidence-header">
              <span class="citation-number">[{{ citation.id }}]</span>
              <el-tag size="small" type="info">
                {{ scoreText(citation.score) }}
              </el-tag>
            </div>
            <div class="score-details">
              <span>向量 {{ compactScore(citation.dense_score) }}</span>
              <span>BM25 {{ compactScore(citation.bm25_score) }}</span>
              <span>RRF {{ compactScore(citation.rrf_score) }}</span>
              <span>重排 {{ compactScore(citation.reranker_score) }}</span>
            </div>
            <strong>{{ citation.title }}</strong>
            <p class="section-name">{{ citation.section }}</p>
            <p class="evidence-content">{{ citation.content }}</p>
            <div class="source-links">
              <a
                v-if="citation.source_url"
                :href="citation.source_url"
                target="_blank"
                rel="noreferrer"
              >
                查看来源
              </a>
              <a
                v-if="citation.doi"
                :href="`https://doi.org/${citation.doi}`"
                target="_blank"
                rel="noreferrer"
              >
                DOI: {{ citation.doi }}
              </a>
            </div>
          </article>

          <el-empty v-if="!citations.length" description="暂无检索证据" />
        </el-scrollbar>
      </el-card>
    </div>

    <el-alert
      class="disclaimer"
      title="RAG 回答仅用于医学知识检索和辅助阅读，不代替临床诊断、用药或治疗决策。"
      type="warning"
      show-icon
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
import { useRoute } from 'vue-router'

import { getKnowledgeCatalog, getKnowledgeEvaluations, queryCaseKnowledge, queryKnowledge } from '../api/ragApi'

const route = useRoute()

const markdown = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: false
})

const exampleQuestions = [
  'PPGL 的 CT 影像表现和术前血管评估要点是什么？',
  '嗜铬细胞瘤手术前为什么需要使用 alpha 受体阻滞？',
  'SDHx 突变携带者应该如何筛查和随访？',
  'TotalSegmentator 可以自动分割多少种 CT 解剖结构？'
]

const question = ref('')
const loading = ref(false)
const answer = ref('')
const citations = ref([])
const metadata = ref({})
const caseContext = ref(null)
const assetsLoading = ref(false)
const catalogError = ref('')
const catalog = ref({ documents: [], document_count: 0, chunk_count: 0, index: {}, embedding: {}, latest_evaluation: null })
const evaluations = ref([])
const selectedEvaluationId = ref('')
const activeManagementPanels = ref(['documents', 'evaluations'])
const caseId = computed(() => String(route.query.caseId || '').trim())
const evidenceAssessment = computed(() => metadata.value?.evidence_assessment || null)
const selectedEvaluation = computed(() => evaluations.value.find(item => item.evaluation_id === selectedEvaluationId.value) || null)
const totalLatencyText = computed(() => {
  const value = Number(metadata.value?.retrieval_latency_ms?.total)
  return Number.isFinite(value) ? `检索 ${(value / 1000).toFixed(1)}s` : (metadata.value.model || 'Qwen3-32B')
})
const assessmentCoveragePercent = computed(() => {
  const value = Number(evidenceAssessment.value?.citation_coverage)
  return Number.isFinite(value) ? Math.max(0, Math.min(100, Math.round(value * 100))) : 0
})
const assessmentTagType = computed(() => {
  const level = evidenceAssessment.value?.level
  if (level === 'high') return 'success'
  if (level === 'medium') return 'warning'
  return 'danger'
})
const assessmentProgressStatus = computed(() => {
  const level = evidenceAssessment.value?.level
  if (level === 'high') return 'success'
  if (level === 'low') return 'exception'
  return 'warning'
})

function renderMarkdown(content) {
  return markdown.render(String(content || ''))
}

function scoreText(score) {
  return `相关度 ${(Number(score || 0) * 100).toFixed(1)}%`
}

function compactScore(score) {
  const value = Number(score)
  return Number.isFinite(value) ? value.toFixed(3) : '-'
}

function formatPercent(value) {
  const number = Number(value)
  return Number.isFinite(number) ? `${Math.round(number * 100)}%` : '—'
}

function formatSeconds(value) {
  const number = Number(value)
  return Number.isFinite(number) ? `${number.toFixed(2)} 秒` : '—'
}

function formatTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function resultText(value) {
  return value ? '通过' : '未通过'
}

function resultTagType(value) {
  return value ? 'success' : 'warning'
}

function useEvaluationQuestion(value) {
  question.value = String(value || '')
  ElMessage.success('已填入评测问题，可直接发起知识库问答')
}

async function loadKnowledgeAssets() {
  assetsLoading.value = true
  catalogError.value = ''
  try {
    const [catalogPayload, evaluationPayload] = await Promise.all([
      getKnowledgeCatalog(),
      getKnowledgeEvaluations()
    ])
    catalog.value = catalogPayload || catalog.value
    evaluations.value = evaluationPayload.evaluations || []
    if (!evaluations.value.some(item => item.evaluation_id === selectedEvaluationId.value)) {
      selectedEvaluationId.value = evaluations.value[0]?.evaluation_id || ''
    }
  } catch (error) {
    catalogError.value = error?.response?.data?.detail || '知识库资产状态读取失败'
  } finally {
    assetsLoading.value = false
  }
}

async function askKnowledgeBase() {
  const cleanQuestion = question.value.trim()
  if (!cleanQuestion) {
    ElMessage.warning('请输入问题')
    return
  }

  loading.value = true
  answer.value = ''
  citations.value = []
  metadata.value = {}
  caseContext.value = null
  try {
    const payload = caseId.value
      ? await queryCaseKnowledge(caseId.value, cleanQuestion)
      : await queryKnowledge(cleanQuestion)
    answer.value = payload.answer || ''
    citations.value = payload.citations || []
    metadata.value = payload.metadata || {}
    caseContext.value = payload.case_context || null
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '知识库问答失败')
  } finally {
    loading.value = false
  }
}

function handleKeydown(event) {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    if (!loading.value) askKnowledgeBase()
  }
}

onMounted(loadKnowledgeAssets)
</script>

<style scoped>
.knowledge-page {
  min-height: 100%;
}

.asset-card {
  margin-bottom: 20px;
  border-color: rgba(93, 235, 219, 0.22);
  background: rgba(8, 23, 36, 0.78);
}

.asset-metric-grid,
.evaluation-metric-grid {
  margin-bottom: 16px;
}

.asset-metric,
.evaluation-metric {
  display: grid;
  min-height: 94px;
  padding: 14px;
  border: 1px solid rgba(93, 235, 219, 0.15);
  border-radius: 12px;
  background: rgba(5, 16, 26, 0.56);
}

.asset-metric span,
.asset-metric small,
.evaluation-metric span,
.muted {
  color: var(--ppgl-muted);
  font-size: 12px;
}

.asset-metric strong,
.evaluation-metric strong {
  color: var(--ppgl-text);
  font-size: 24px;
}

.asset-descriptions {
  margin-bottom: 16px;
}

.management-collapse :deep(.el-collapse-item__header),
.management-collapse :deep(.el-collapse-item__wrap) {
  background: transparent;
  border-color: rgba(93, 235, 219, 0.14);
}

.management-collapse :deep(.el-collapse-item__content) {
  padding: 14px 0;
}

.evaluation-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 14px;
}

.evaluation-select {
  width: min(100%, 430px);
}

.knowledge-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(360px, 0.75fr);
  gap: 20px;
}

.header-tags,
.case-facts,
.score-details {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.case-alert {
  margin-bottom: 16px;
}

.query-card,
.evidence-card {
  border-color: rgba(93, 235, 219, 0.22);
  background: rgba(8, 23, 36, 0.78);
}

.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.card-title strong {
  color: var(--ppgl-text);
}

.card-title span {
  color: var(--ppgl-muted);
  font-size: 13px;
}

.example-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.example-list :deep(.el-button) {
  height: auto;
  margin-left: 0;
  padding: 7px 10px;
  white-space: normal;
  text-align: left;
}

.query-card :deep(.el-textarea__inner) {
  background: rgba(5, 16, 26, 0.72);
  color: var(--ppgl-text);
}

.query-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
}

.query-actions span {
  color: var(--ppgl-muted);
  font-size: 12px;
}

.answer-panel {
  margin-top: 22px;
  padding: 18px 20px;
  border: 1px solid rgba(93, 235, 219, 0.24);
  border-radius: var(--ppgl-radius);
  background: rgba(5, 16, 26, 0.72);
  color: var(--ppgl-text);
}

.answer-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  color: #ffffff;
}

.answer-heading span {
  color: var(--ppgl-muted);
  font-size: 12px;
}

.markdown-content {
  line-height: 1.75;
}

.case-facts {
  margin-bottom: 14px;
}

.evidence-assessment {
  padding: 12px;
  margin-bottom: 14px;
  border: 1px solid rgba(93, 235, 219, 0.18);
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.62);
}

.assessment-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  color: var(--ppgl-muted);
  font-size: 12px;
}

.assessment-warnings {
  padding-left: 18px;
  margin: 10px 0 0;
  color: #fbbf24;
  font-size: 12px;
  line-height: 1.6;
}

.markdown-content :deep(> :first-child) {
  margin-top: 0;
}

.markdown-content :deep(> :last-child) {
  margin-bottom: 0;
}

.evidence-list {
  height: 650px;
}

.evidence-item {
  padding: 14px;
  margin-bottom: 12px;
  border: 1px solid rgba(93, 235, 219, 0.18);
  border-radius: var(--ppgl-radius);
  background: rgba(5, 16, 26, 0.66);
}

.evidence-header,
.source-links {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.citation-number {
  color: var(--ppgl-primary);
  font-weight: 800;
}

.score-details {
  margin-top: 8px;
  color: #94a3b8;
  font-size: 11px;
}

.evidence-item > strong {
  display: block;
  margin-top: 10px;
  color: #ffffff;
  line-height: 1.45;
}

.section-name {
  color: #5eead4;
  font-size: 12px;
  line-height: 1.5;
}

.evidence-content {
  display: -webkit-box;
  overflow: hidden;
  color: var(--ppgl-muted);
  font-size: 13px;
  line-height: 1.6;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 6;
}

.source-links {
  justify-content: flex-start;
  flex-wrap: wrap;
  font-size: 12px;
}

.source-links a {
  color: var(--ppgl-primary);
}

.disclaimer {
  margin-top: 20px;
}

@media (max-width: 1100px) {
  .knowledge-layout {
    grid-template-columns: 1fr;
  }

  .evidence-list {
    height: 460px;
  }
}
</style>
