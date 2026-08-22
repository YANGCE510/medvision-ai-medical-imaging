const api = require("../../utils/api");

Page({
  typingTimer: null,

  data: {
    taskId: "",
    report: null,
    reportLoading: true,
    draft: "",
    canSend: false,
    sending: false,
    scrollIntoView: "bottom",
    suggestedQuestions: [
      "各项指标是什么意思",
      "关键指标有哪些，合理值是多少",
      "这份报告主要说明什么",
      "复诊前需要准备什么"
    ],
    messages: []
  },

  onLoad(options) {
    const currentUser = api.getCurrentUser();
    if (!currentUser || !currentUser.id) {
      wx.redirectTo({ url: "/pages/login/login" });
      return;
    }
    this.setData({ taskId: options.taskId || "" });
    this.loadReport(options.taskId || "");
    this.loadHistory(options.taskId || "");
  },

  onUnload() {
    this.stopTyping();
  },

  async loadHistory(taskId) {
    try {
      const history = await api.getChatHistory(taskId);
      if (history.length) {
        this.setData({
          messages: history.map((item, index) => ({
            id: Date.now() + index,
            role: item.role,
            content: item.content,
            thinking: false
          }))
        });
        this.scrollToBottom();
      }
    } catch (error) {
      wx.showToast({
        title: "聊天记录加载失败",
        icon: "none"
      });
    }
  },

  async loadReport(taskId) {
    this.setData({ reportLoading: true });
    try {
      const report = await api.getReport(taskId);
      this.setData({ report });
    } catch (error) {
      wx.showToast({
        title: "病例信息加载失败",
        icon: "none"
      });
    } finally {
      this.setData({ reportLoading: false });
    }
  },

  onInput(event) {
    const draft = event.detail.value || "";
    this.setData({
      draft,
      canSend: Boolean(draft.trim())
    });
  },

  sendMessage() {
    const question = this.data.draft.trim();
    if (!question || this.data.sending) {
      return;
    }
    this.submitQuestion(question);
  },

  useSuggestion(event) {
    const question = event.currentTarget.dataset.question || "";
    this.setData({
      draft: question,
      canSend: Boolean(question.trim())
    });
  },

  async submitQuestion(question) {
    const userMessage = {
      id: Date.now(),
      role: "user",
      content: question,
      thinking: false
    };
    const thinkingMessage = {
      id: Date.now() + 1,
      role: "assistant",
      content: "",
      thinking: true
    };
    const messages = this.data.messages.concat(userMessage, thinkingMessage);
    this.setData({
      messages,
      draft: "",
      canSend: false,
      sending: true
    });
    this.scrollToBottom();

    try {
      const reply = await api.sendChatMessage(this.data.taskId, question, messages);
      await this.typeAssistantMessage(thinkingMessage.id, reply.content || "我暂时没有生成有效回复，请稍后再试。");
    } catch (error) {
      this.replaceMessage(thinkingMessage.id, "暂时无法连接 AI 服务。你可以稍后再试，或直接向医生咨询这份报告。");
    } finally {
      this.setData({ sending: false });
      this.scrollToBottom();
    }
  },

  typeAssistantMessage(messageId, fullText) {
    this.stopTyping();
    this.replaceMessage(messageId, "", true);
    return new Promise((resolve) => {
      const chars = Array.from(fullText);
      let index = 0;
      const step = () => {
        index += 1;
        this.replaceMessage(messageId, chars.slice(0, index).join(""), false);
        this.scrollToBottom();
        if (index >= chars.length) {
          this.typingTimer = null;
          resolve();
          return;
        }
        this.typingTimer = setTimeout(step, 28);
      };
      this.typingTimer = setTimeout(step, 180);
    });
  },

  replaceMessage(messageId, content, thinking = false) {
    const messages = this.data.messages.map((message) => {
      if (message.id !== messageId) {
        return message;
      }
      return {
        ...message,
        content,
        thinking
      };
    });
    this.setData({ messages });
  },

  stopTyping() {
    if (this.typingTimer) {
      clearTimeout(this.typingTimer);
      this.typingTimer = null;
    }
  },

  scrollToBottom() {
    setTimeout(() => {
      this.setData({ scrollIntoView: "bottom" });
    }, 80);
  }
});
