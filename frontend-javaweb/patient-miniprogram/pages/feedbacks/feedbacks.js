const api = require("../../utils/api");

Page({
  data: {
    loading: true,
    submitting: false,
    reports: [],
    reportOptions: [],
    selectedReportIndex: -1,
    selectedTaskId: "",
    selectedReportLabel: "",
    question: "",
    feedbacks: [],
    pendingFeedbackCount: 0,
    feedbackLimitReached: false
  },

  onShow() {
    const currentUser = api.getCurrentUser();
    if (!currentUser || !currentUser.id) {
      wx.reLaunch({ url: "/pages/login/login" });
      return;
    }
    this.loadPage();
  },

  async loadPage() {
    this.setData({ loading: true });
    try {
      const [reports, feedbacks] = await Promise.all([
        api.getReports(),
        api.getFeedbacks()
      ]);
      const reportOptions = reports.map((item) => `${item.patientName || "影像报告"} · ${item.originalFilename || item.createdAt}`);
      const pendingFeedbackCount = feedbacks.filter((item) => item.status === "PENDING").length;
      this.setData({
        reports,
        feedbacks,
        reportOptions,
        pendingFeedbackCount,
        feedbackLimitReached: pendingFeedbackCount >= 3
      });
      api.markFeedbackRepliesSeen(feedbacks);
      api.refreshCareTabBadges({ feedbacks });
    } catch (error) {
      wx.showToast({
        title: "反馈加载失败",
        icon: "none"
      });
    } finally {
      this.setData({ loading: false });
    }
  },

  onReportChange(event) {
    const selectedReportIndex = Number(event.detail.value);
    const report = this.data.reports[selectedReportIndex];
    this.setData({
      selectedReportIndex,
      selectedTaskId: report ? report.taskId : "",
      selectedReportLabel: this.data.reportOptions[selectedReportIndex] || ""
    });
  },

  onInput(event) {
    this.setData({ question: event.detail.value || "" });
  },

  async submit() {
    const question = this.data.question.trim();
    if (!this.data.selectedTaskId) {
      wx.showToast({ title: "请选择关联报告", icon: "none" });
      return;
    }
    if (!question) {
      wx.showToast({ title: "请填写问题", icon: "none" });
      return;
    }
    if (this.data.feedbackLimitReached) {
      wx.showToast({ title: "已有 3 个未回复反馈", icon: "none" });
      return;
    }
    if (this.data.submitting) {
      return;
    }
    this.setData({ submitting: true });
    try {
      await api.submitFeedback(this.data.selectedTaskId, question);
      wx.showToast({ title: "已提交", icon: "success" });
      this.setData({ question: "" });
      await this.loadPage();
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
