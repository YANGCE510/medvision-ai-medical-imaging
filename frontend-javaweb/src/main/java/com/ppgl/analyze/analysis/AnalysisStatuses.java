package com.ppgl.analyze.analysis;

final class AnalysisStatuses {

    static final String CT_QUEUED = "排队中";
    static final String CT_RUNNING = "分析中";
    static final String CT_DONE = "已分析";
    static final String CT_FAILED = "分析失败";
    static final String CT_PENDING = "未分析";

    static final String TASK_QUEUED = "排队中";
    static final String TASK_PREPROCESSING = "预处理中";
    static final String TASK_UPLOADING = "上传中";
    static final String TASK_WAITING_JETSON = "等待 Jetson";
    static final String TASK_RUNNING = "分析中";
    static final String TASK_POSTPROCESSING = "后处理中";
    static final String TASK_DONE = "已完成";
    static final String TASK_FAILED = "分析失败";

    private AnalysisStatuses() {
    }
}
