package com.ppgl.analyze.care;

public record PatientFeedbackResponse(
        Long id,
        Long taskId,
        String patientName,
        String patientIdCard,
        String originalFilename,
        String question,
        String status,
        String statusLabel,
        String doctorReply,
        String createdAt,
        String updatedAt
) {
}
