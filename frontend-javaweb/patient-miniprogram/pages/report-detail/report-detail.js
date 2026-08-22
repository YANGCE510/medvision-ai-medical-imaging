const api = require("../../utils/api");

Page({
  data: {
    taskId: "",
    loading: true,
    report: null
  },

  onLoad(options) {
    const currentUser = api.getCurrentUser();
    if (!currentUser || !currentUser.id) {
      wx.redirectTo({ url: "/pages/login/login" });
      return;
    }
    this.setData({ taskId: options.taskId || "" });
    this.loadReport(options.taskId);
  },

  async loadReport(taskId) {
    this.setData({ loading: true });
    try {
      const report = await api.getReport(taskId);
      this.setData({ report });
    } catch (error) {
      wx.showToast({
        title: "报告加载失败",
        icon: "none"
      });
    } finally {
      this.setData({ loading: false });
    }
  },

  openChat() {
    wx.navigateTo({
      url: `/pages/chat/chat?taskId=${this.data.taskId}`
    });
  }
});
