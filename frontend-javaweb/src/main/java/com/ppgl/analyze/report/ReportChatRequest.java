package com.ppgl.analyze.report;

import java.util.List;

public record ReportChatRequest(
        String question,
        List<ReportChatMessage> history,
        Integer maxTokens,
        Boolean includeReportContext
) {
}
