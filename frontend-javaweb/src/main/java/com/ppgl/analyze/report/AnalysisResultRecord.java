package com.ppgl.analyze.report;

import java.math.BigDecimal;
import java.time.LocalDateTime;

record AnalysisResultRecord(
        Long id,
        Long taskId,
        Long ctImageId,
        Long doctorId,
        String patientName,
        String patientIdCard,
        String originalFilename,
        String resultJsonPath,
        String metricsJsonPath,
        String riskJsonPath,
        String labelMapJsonPath,
        String reportMdPath,
        String overlayPath,
        BigDecimal tumorVolumeMl,
        String riskLevel,
        String summaryJson,
        boolean patientVisible,
        String doctorReviewStatus,
        String doctorReviewNote,
        LocalDateTime doctorReviewedAt,
        Long reviewedBy,
        LocalDateTime createdAt
) {
}
