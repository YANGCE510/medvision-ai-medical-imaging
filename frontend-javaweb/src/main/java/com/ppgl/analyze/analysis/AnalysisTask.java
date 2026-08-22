package com.ppgl.analyze.analysis;

import java.time.LocalDateTime;

record AnalysisTask(
        Long id,
        Long ctImageId,
        Long doctorId,
        Long requesterId,
        String doctorName,
        String patientName,
        String patientIdCard,
        String originalFilename,
        String filePath,
        String jetsonCaseId,
        String mode,
        String device,
        String status,
        int progress,
        String stage,
        String message,
        String failedReason,
        LocalDateTime createdAt,
        LocalDateTime startedAt,
        LocalDateTime completedAt
) {
}
