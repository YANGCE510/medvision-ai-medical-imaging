<template>
  <div class="page-shell report-page">
    <div class="page-header">
      <div>
        <h2>AI 辅助分析报告</h2>
        <p>病例编号：{{ caseId }}</p>
      </div>

      <div class="page-header-actions">
        <el-button @click="goBack">返回病例详情</el-button>
        <el-button
          type="success"
          :loading="generating"
          @click="generateReport"
        >
          生成 AI 报告
        </el-button>
        <el-button type="primary" @click="loadReport">刷新报告</el-button>
      </div>
    </div>

    <div class="report-grid">
      <el-card class="report-card" v-loading="loading" shadow="never">
        <template #header>
          <div class="section-header">
            <div>
              <strong>初步影像辅助分析报告</strong>
              <p>可由医生审核、修订后导出</p>
            </div>
            <el-button-group>
              <el-button :type="reportMode === 'preview' ? 'primary' : ''" @click="reportMode = 'preview'">
                预览
              </el-button>
              <el-button :type="reportMode === 'edit' ? 'primary' : ''" @click="reportMode = 'edit'">
                编辑
              </el-button>
            </el-button-group>
          </div>
        </template>

        <div
          v-if="reportMode === 'preview'"
          class="report-markdown"
          v-html="renderMarkdown(report)"
        ></div>
        <el-input
          v-else
          v-model="report"
          type="textarea"
          :rows="24"
        />

        <div class="actions">
          <el-button>保存修改</el-button>
          <el-button type="success">医生审核通过</el-button>
          <el-button type="primary">导出 PDF</el-button>
        </div>
      </el-card>

      <el-card class="chat-card" shadow="never">
        <template #header>
          <div class="section-header">
            <div>
              <strong>基于报告的 AI 问答</strong>
              <p>围绕当前报告和分割指标追问</p>
            </div>
          </div>
        </template>

        <div ref="chatMessagesEl" class="chat-messages" v-loading="chatLoading">
          <div v-if="chatMessages.length === 0" class="empty-chat">
            暂无对话，请先生成 AI 报告后再提问。
          </div>
          <div
            v-for="(message, index) in chatMessages"
            :key="index"
            class="chat-message"
            :class="[message.role, { streaming: message.streaming }]"
          >
            <div class="chat-role">
              {{ message.role === 'user' ? '医生提问' : 'AI 回答' }}
            </div>
            <div class="chat-content">
              <div class="markdown-content" v-html="renderMarkdown(message.content)"></div>
              <span v-if="message.streaming" class="typing-cursor"></span>
            </div>
          </div>
        </div>

        <div class="chat-input">
          <el-input
            v-model="chatQuestion"
            type="textarea"
            :rows="3"
            maxlength="1000"
            show-word-limit
            placeholder="输入想基于当前 AI 报告追问的问题"
            @keydown="handleChatKeydown"
          />
          <el-button
            type="primary"
            :loading="chatSending"
            @click="sendChat"
          >
            发送
          </el-button>
        </div>
      </el-card>
    </div>

    <el-alert
      class="disclaimer"
      title="本报告由 AI 系统基于自动分割结果生成，仅供医生辅助参考，不作为最终诊断或治疗依据。"
      type="warning"
      show-icon
    />
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
import { useRoute, useRouter } from 'vue-router'
import {
  generateAiReport,
  getAiReportChat,
  getReport,
  streamAiReportChat
} from '../api/reportApi'

const route = useRoute()
const router = useRouter()
const markdown = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: false
})

const caseId = route.params.caseId
const loading = ref(false)
const generating = ref(false)
const report = ref('')
const reportMode = ref('preview')
const chatLoading = ref(false)
const chatSending = ref(false)
const chatQuestion = ref('')
const chatMessages = ref([])
const chatMessagesEl = ref(null)

function renderMarkdown(content) {
  return markdown.render(String(content || ''))
}

async function scrollChatToBottom() {
  await nextTick()
  if (chatMessagesEl.value) {
    chatMessagesEl.value.scrollTop = chatMessagesEl.value.scrollHeight
  }
}

async function loadReport() {
  loading.value = true
  try {
    report.value = await getReport(caseId)
  } catch (err) {
    report.value = ''
    ElMessage.error(err?.response?.data?.detail || '报告加载失败，请先完成分割')
  } finally {
    loading.value = false
  }
}

async function generateReport() {
  generating.value = true
  try {
    const payload = await generateAiReport(caseId)
    report.value = payload.report_markdown || ''
    await loadChat()
    ElMessage.success('AI 报告已生成')
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || 'AI 报告生成失败')
  } finally {
    generating.value = false
  }
}

async function loadChat() {
  chatLoading.value = true
  try {
    const payload = await getAiReportChat(caseId)
    chatMessages.value = payload.messages || []
    await scrollChatToBottom()
  } catch (err) {
    chatMessages.value = []
  } finally {
    chatLoading.value = false
  }
}

async function sendChat() {
  const question = chatQuestion.value.trim()
  if (!question) {
    ElMessage.warning('请输入问题')
    return
  }

  chatSending.value = true
  try {
    const history = chatMessages.value
      .slice(-8)
      .map(message => ({
        role: message.role,
        content: message.content
      }))

    const assistantMessage = {
      role: 'assistant',
      content: '',
      streaming: true
    }
    chatMessages.value.push({
      role: 'user',
      content: question
    })
    chatMessages.value.push(assistantMessage)
    chatQuestion.value = ''
    await scrollChatToBottom()

    const payload = await streamAiReportChat(caseId, question, history, async delta => {
      assistantMessage.content += delta
      chatMessages.value = [...chatMessages.value]
      await scrollChatToBottom()
    })

    assistantMessage.streaming = false
    if (payload?.messages) {
      chatMessages.value = payload.messages
    } else {
      chatMessages.value = [...chatMessages.value]
    }
    await scrollChatToBottom()
  } catch (err) {
    const lastMessage = chatMessages.value[chatMessages.value.length - 1]
    if (lastMessage?.streaming) {
      lastMessage.streaming = false
      lastMessage.content = lastMessage.content || 'AI 问答失败'
      chatMessages.value = [...chatMessages.value]
    }
    ElMessage.error(err?.message || err?.response?.data?.detail || 'AI 问答失败')
  } finally {
    chatSending.value = false
  }
}

function handleChatKeydown(event) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) {
    return
  }
  event.preventDefault()
  if (!chatSending.value) {
    sendChat()
  }
}

function goBack() {
  router.push(`/cases/${caseId}`)
}

onMounted(() => {
  loadReport()
  loadChat()
})
</script>

<style scoped>
.report-page {
  min-height: 100%;
}

.report-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(380px, 0.9fr);
  gap: 20px;
  align-items: start;
}

.report-card,
.chat-card {
  border-radius: var(--ppgl-radius);
  border-color: rgba(93, 235, 219, 0.22);
  background: rgba(8, 23, 36, 0.78);
}

.report-card :deep(.el-textarea__inner) {
  min-height: 560px !important;
  padding: 16px;
  background:
    linear-gradient(90deg, rgba(93, 235, 219, 0.045) 1px, transparent 1px),
    rgba(5, 16, 26, 0.72);
  background-size: 28px 28px;
  color: var(--ppgl-text);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 13px;
}

.report-markdown {
  min-height: 560px;
  max-height: 760px;
  overflow: auto;
  padding: 18px 22px;
  border: 1px solid rgba(93, 235, 219, 0.22);
  border-radius: var(--ppgl-radius);
  background:
    linear-gradient(90deg, rgba(93, 235, 219, 0.045) 1px, transparent 1px),
    rgba(5, 16, 26, 0.72);
  background-size: 28px 28px;
  color: var(--ppgl-text);
  line-height: 1.7;
}

.report-markdown :deep(> :first-child) {
  margin-top: 0;
}

.report-markdown :deep(> :last-child) {
  margin-bottom: 0;
}

.report-markdown :deep(h1),
.report-markdown :deep(h2),
.report-markdown :deep(h3),
.report-markdown :deep(h4) {
  margin: 22px 0 12px;
  color: #ffffff;
}

.report-markdown :deep(p),
.report-markdown :deep(ul),
.report-markdown :deep(ol) {
  margin: 0 0 12px;
}

.report-markdown :deep(ul),
.report-markdown :deep(ol) {
  padding-left: 24px;
}

.report-markdown :deep(table) {
  width: 100%;
  margin: 14px 0 20px;
  border-collapse: collapse;
  background: rgba(5, 16, 26, 0.82);
  font-size: 13px;
}

.report-markdown :deep(th),
.report-markdown :deep(td) {
  padding: 9px 12px;
  border: 1px solid rgba(93, 235, 219, 0.25);
  text-align: left;
  vertical-align: top;
}

.report-markdown :deep(th) {
  background: rgba(32, 224, 196, 0.12);
  color: #ffffff;
}

.report-markdown :deep(tr:nth-child(even)) {
  background: rgba(93, 235, 219, 0.035);
}

.report-markdown :deep(code) {
  padding: 2px 5px;
  border-radius: 4px;
  background: rgba(93, 235, 219, 0.1);
}

.actions {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.chat-messages {
  height: 560px;
  overflow-y: auto;
  border: 1px solid rgba(93, 235, 219, 0.22);
  border-radius: var(--ppgl-radius);
  padding: 14px;
  background:
    linear-gradient(90deg, rgba(93, 235, 219, 0.045) 1px, transparent 1px),
    rgba(5, 16, 26, 0.66);
  background-size: 28px 28px;
}

.empty-chat {
  color: var(--ppgl-muted);
  font-size: 14px;
}

.chat-message {
  max-width: 90%;
  margin-bottom: 14px;
  padding: 12px 14px;
  border-radius: var(--ppgl-radius);
  background: rgba(8, 23, 36, 0.94);
  border: 1px solid rgba(93, 235, 219, 0.18);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.24);
}

.chat-message.user {
  margin-left: auto;
  background: rgba(32, 224, 196, 0.12);
  border-color: rgba(93, 235, 219, 0.34);
}

.chat-message.streaming {
  border-color: var(--ppgl-primary);
  box-shadow: 0 0 22px rgba(32, 224, 196, 0.14);
}

.chat-role {
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--ppgl-muted);
}

.chat-content {
  line-height: 1.65;
  color: var(--ppgl-text);
}

.chat-content :deep(.markdown-content > :first-child) {
  margin-top: 0;
}

.chat-content :deep(.markdown-content > :last-child) {
  margin-bottom: 0;
}

.chat-content :deep(p),
.chat-content :deep(ul),
.chat-content :deep(ol) {
  margin: 0 0 10px;
}

.chat-content :deep(ul),
.chat-content :deep(ol) {
  padding-left: 24px;
}

.chat-content :deep(strong) {
  color: #ffffff;
}

.typing-cursor {
  display: inline-block;
  width: 7px;
  height: 1em;
  margin-left: 3px;
  vertical-align: -2px;
  background: var(--ppgl-primary);
  animation: blink 1s steps(2, start) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.chat-input {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 82px;
  gap: 12px;
  align-items: end;
  margin-top: 14px;
}

.chat-input .el-button {
  height: 76px;
}

.disclaimer {
  margin-top: 20px;
}

@media (max-width: 1280px) {
  .report-grid {
    grid-template-columns: 1fr;
  }

  .chat-messages {
    height: 420px;
  }
}

@media (max-width: 720px) {
  .chat-message {
    max-width: 100%;
  }

  .chat-input {
    grid-template-columns: 1fr;
  }

  .chat-input .el-button {
    height: 40px;
  }
}
</style>
