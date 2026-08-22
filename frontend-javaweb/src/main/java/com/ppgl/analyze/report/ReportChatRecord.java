package com.ppgl.analyze.report;

import java.time.LocalDateTime;

public record ReportChatRecord(
        Long id,
        Long taskId,
        Long doctorId,
        String role,
        String content,
        LocalDateTime createdAt
) {
}
