const api = require("../../utils/api");

Page({
  data: {
    loading: true,
    currentUser: null,
    reports: []
  },

  onShow() {
    const currentUser = api.getCurrentUser();
    if (!currentUser || !currentUser.id) {
      wx.reLaunch({ url: "/pages/login/login" });
      return;
    }
    this.setData({ currentUser });
    this.loadReports();
    api.refreshCareTabBadges();
  },

  async loadReports() {
    this.setData({ loading: true });
    try {
      const reports = await api.getReports();
      this.setData({ reports });
    } catch (error) {
      wx.showToast({
        title: "报告加载失败",
        icon: "none"
      });
    } finally {
      this.setData({ loading: false });
    }
  },

  openReport(event) {
    const taskId = event.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/report-detail/report-detail?taskId=${taskId}`
    });
  },

  logout() {
    api.clearCurrentUser();
    wx.reLaunch({ url: "/pages/login/login" });
  }
});
