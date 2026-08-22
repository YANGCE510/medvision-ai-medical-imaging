const api = require("../../utils/api");

Page({
  data: {
    mode: "login",
    loading: false,
    message: "演示账号：zhangsan / 123456，或手机号 13600010001。",
    account: "",
    username: "",
    displayName: "",
    phone: "",
    patientIdCard: "",
    password: ""
  },

  onLoad() {
    const user = api.getCurrentUser();
    if (user && user.id) {
      wx.switchTab({ url: "/pages/reports/reports" });
    }
  },

  switchMode(event) {
    const mode = event.currentTarget.dataset.mode || "login";
    this.setData({
      mode,
      message: mode === "login"
        ? "演示账号：zhangsan / 123456，或手机号 13600010001。"
        : ""
    });
  },

  onInput(event) {
    const field = event.currentTarget.dataset.field;
    this.setData({
      [field]: event.detail.value || ""
    });
  },

  async submit() {
    if (this.data.loading) {
      return;
    }
    this.setData({ loading: true, message: "正在提交..." });
    try {
      if (this.data.mode === "login") {
        await api.login(this.data.account.trim(), this.data.password);
      } else {
        await api.register({
          username: this.data.username.trim(),
          displayName: this.data.displayName.trim(),
          phone: this.data.phone.trim(),
          patientIdCard: this.data.patientIdCard.trim(),
          password: this.data.password
        });
      }
      wx.switchTab({ url: "/pages/reports/reports" });
    } catch (error) {
      this.setData({
        message: error.message || "操作失败，请稍后再试"
      });
    } finally {
      this.setData({ loading: false });
    }
  }
});
