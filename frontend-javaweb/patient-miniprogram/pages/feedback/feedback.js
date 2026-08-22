const api = require("../../utils/api");

Page({
  data: {
    taskId: "",
    question: "",
    submitting: false
  },

  onLoad(options) {
    this.setData({ taskId: options.taskId || "" });
  },

  onInput(event) {
    this.setData({ question: event.detail.value || "" });
  },

  async submit() {
    const question = this.data.question.trim();
    if (!question) {
      wx.showToast({ title: "请填写问题", icon: "none" });
      return;
    }
    if (this.data.submitting) {
      return;
    }
    this.setData({ submitting: true });
    try {
      await api.submitFeedback(this.data.taskId, question);
      wx.showToast({ title: "已提交", icon: "success" });
      setTimeout(() => wx.navigateBack(), 600);
    } catch (error) {
      wx.showToast({
        title: error.message || "提交失败",
        icon: "none"
      });
    } finally {
      this.setData({ submitting: false });
    }
  }
});
