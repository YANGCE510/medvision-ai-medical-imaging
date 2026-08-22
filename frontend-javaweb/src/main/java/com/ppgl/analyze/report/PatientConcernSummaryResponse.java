package com.ppgl.analyze.report;

import java.util.List;

public record PatientConcernSummaryResponse(
        Long taskId,
        String patientName,
        String patientIdCard,
        String originalFilename,
        String riskLevel,
        String tumorVolumeMl,
        int questionCount,
        List<String> questions,
        String summary,
        String generatedAt
) {
}
