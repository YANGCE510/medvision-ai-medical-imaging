package com.ppgl.analyze.care;

public record FollowUpSubmissionResponse(
        Long id,
        Long planId,
        Long taskId,
        Long patientUserId,
        String symptoms,
        String bloodPressure,
        String heartRate,
        String treatmentStatus,
        String newExamResults,
        String patientNote,
        String createdAt
) {
}
