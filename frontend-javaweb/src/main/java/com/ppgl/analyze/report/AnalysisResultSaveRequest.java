package com.ppgl.analyze.report;

import java.math.BigDecimal;

public record AnalysisResultSaveRequest(
        Long taskId,
        Long ctImageId,
        Long doctorId,
        String resultJsonPath,
        String metricsJsonPath,
        String riskJsonPath,
        String labelMapJsonPath,
        String reportMdPath,
        String overlayPath,
        BigDecimal tumorVolumeMl,
        String riskLevel,
        String summaryJson
) {
}
