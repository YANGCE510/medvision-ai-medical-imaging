package com.ppgl.analyze.report;

public record ReportChatResponse(
        String role,
        String content,
        String createdAt
) {
    public static ReportChatResponse from(ReportChatRecord record) {
        return new ReportChatResponse(record.role(), record.content(), record.createdAt().toString());
    }
}
