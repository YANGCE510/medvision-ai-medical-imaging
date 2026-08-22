package com.ppgl.analyze.care;

public record FollowUpPlanResponse(
        Long id,
        Long taskId,
        String patientName,
        String patientIdCard,
        String originalFilename,
        String riskLevel,
        String followUpDate,
        String reason,
        String preparation,
        String status,
        String statusLabel,
        boolean overdue,
        String createdAt,
        FollowUpSubmissionResponse latestSubmission
) {
}
