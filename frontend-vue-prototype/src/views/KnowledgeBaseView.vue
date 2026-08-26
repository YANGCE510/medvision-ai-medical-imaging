<template>
  <div class="page-shell knowledge-page">
    <div class="page-header">
      <div>
        <h2>PPGL 医学知识库</h2>
        <p>BGE-M3 语义检索 · Qdrant 本地索引 · Qwen3-32B 带引用问答</p>
      </div>
      <div class="header-tags">
        <el-tag v-if="caseId" type="warning" effect="dark">当前病例：{{ caseId }}</el-tag>
        <el-tag type="success" effect="dark">Hybrid RAG 已启用</el-tag>
      </div>
    </div>

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
            <span>{{ metadata.retrieval || 'Hybrid RAG' }} · {{ totalLatencyText }}</span>
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
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
import { useRoute } from 'vue-router'

import { queryCaseKnowledge, queryKnowledge } from '../api/ragApi'

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
const caseId = computed(() => String(route.query.caseId || '').trim())
const evidenceAssessment = computed(() => metadata.value?.evidence_assessment || null)
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
</script>

<style scoped>
.knowledge-page {
  min-height: 100%;
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
