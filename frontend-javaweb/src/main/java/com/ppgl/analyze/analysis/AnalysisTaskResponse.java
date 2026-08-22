package com.ppgl.analyze.analysis;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Map;

public record AnalysisTaskResponse(
        Long id,
        Long ctImageId,
        Long doctorId,
        String doctorName,
        String patientName,
        String patientIdCard,
        String originalFilename,
        String jetsonCaseId,
        String mode,
        String device,
        String status,
        String statusClass,
        int progress,
        String stage,
        String message,
        String failedReason,
        Integer queuePosition,
        String createdAt,
        String startedAt,
        String completedAt
) {
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");

    static AnalysisTaskResponse from(AnalysisTask task, Map<Long, Integer> queuePositions) {
        return new AnalysisTaskResponse(
                task.id(),
                task.ctImageId(),
                task.doctorId(),
                task.doctorName(),
                task.patientName(),
                task.patientIdCard(),
                task.originalFilename(),
                task.jetsonCaseId(),
                task.mode(),
                task.device(),
                task.status(),
                statusClass(task.status()),
                task.progress(),
                task.stage(),
                task.message(),
                task.failedReason(),
                queuePositions.get(task.id()),
                format(task.createdAt()),
                format(task.startedAt()),
                format(task.completedAt())
        );
    }

    private static String statusClass(String status) {
        return switch (status) {
            case AnalysisStatuses.TASK_DONE -> "success";
            case AnalysisStatuses.TASK_PREPROCESSING,
                    AnalysisStatuses.TASK_UPLOADING,
                    AnalysisStatuses.TASK_WAITING_JETSON,
                    AnalysisStatuses.TASK_RUNNING,
                    AnalysisStatuses.TASK_POSTPROCESSING -> "info";
            case AnalysisStatuses.TASK_FAILED -> "warn";
            default -> "muted";
        };
    }

    private static String format(LocalDateTime value) {
        return value == null ? "" : value.format(FORMATTER);
    }
}
