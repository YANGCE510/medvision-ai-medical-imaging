const api = require("../../utils/api");

Page({
  data: {
    planId: "",
    taskId: "",
    submitting: false,
    symptomOptions: [
      { value: "头痛", label: "头痛" },
      { value: "心悸", label: "心悸" },
      { value: "出汗", label: "出汗" },
      { value: "血压波动", label: "血压波动" },
      { value: "无明显症状", label: "无明显症状" }
    ],
    symptoms: [],
    bloodPressure: "",
    heartRate: "",
    treatmentStatus: "",
    newExamResults: "",
    patientNote: ""
  },

  onLoad(options) {
    this.setData({
      planId: options.planId || "",
      taskId: options.taskId || ""
    });
  },

  onSymptomsChange(event) {
    this.setData({ symptoms: event.detail.value || [] });
  },

  onInput(event) {
    const field = event.currentTarget.dataset.field;
    this.setData({ [field]: event.detail.value || "" });
  },

  async submit() {
    if (this.data.submitting) {
      return;
    }
    if (!this.data.planId) {
      wx.showToast({ title: "回访计划不存在", icon: "none" });
      return;
    }
    this.setData({ submitting: true });
    try {
      await api.submitFollowUp(this.data.planId, {
        symptoms: this.data.symptoms,
        bloodPressure: this.data.bloodPressure.trim(),
        heartRate: this.data.heartRate.trim(),
        treatmentStatus: this.data.treatmentStatus.trim(),
        newExamResults: this.data.newExamResults.trim(),
        patientNote: this.data.patientNote.trim()
      });
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
