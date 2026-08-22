Component({
  options: {
    multipleSlots: true
  },
  properties: {
    title: {
      type: String,
      value: ""
    },
    subtitle: {
      type: String,
      value: ""
    },
    showBack: {
      type: Boolean,
      value: false
    }
  },
  methods: {
    handleBack() {
      this.triggerEvent("back");
      wx.navigateBack({ delta: 1 });
    }
  }
});
