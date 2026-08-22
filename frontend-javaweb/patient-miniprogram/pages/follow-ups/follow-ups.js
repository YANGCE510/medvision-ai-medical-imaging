const api = require("../../utils/api");

Page({
  data: {
    loading: true,
    followUps: []
  },

  onShow() {
    const currentUser = api.getCurrentUser();
    if (!currentUser || !currentUser.id) {
      wx.reLaunch({ url: "/pages/login/login" });
      return;
    }
    this.loadFollowUps();
  },

  async loadFollowUps() {
    this.setData({ loading: true });
    try {
      const followUps = await api.getAllFollowUps();
      this.setData({ followUps });
      api.markFollowUpsSeen(followUps);
      api.refreshCareTabBadges({ followUps });
    } catch (error) {
      wx.showToast({
        title: "回访加载失败",
        icon: "none"
      });
    } finally {
      this.setData({ loading: false });
    }
  },

  openFollowUp(event) {
    const planId = event.currentTarget.dataset.id;
    const taskId = event.currentTarget.dataset.taskId;
    wx.navigateTo({
      url: `/pages/follow-up/follow-up?taskId=${taskId}&planId=${planId}`
    });
  }
});
