Component({
  properties: {
    type: {
      type: String,
      value: "primary"
    },
    size: {
      type: String,
      value: "medium"
    },
    block: {
      type: Boolean,
      value: true
    },
    loading: {
      type: Boolean,
      value: false
    },
    disabled: {
      type: Boolean,
      value: false
    }
  },
  methods: {
    handleTap(event) {
      if (this.data.disabled || this.data.loading) {
        return;
      }
      this.triggerEvent("tap", event.detail);
    }
  }
});
