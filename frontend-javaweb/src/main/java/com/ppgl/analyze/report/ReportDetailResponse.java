package com.ppgl.analyze.report;

public record ReportDetailResponse(
        Long taskId,
        Long ctImageId,
        String patientName,
        String patientIdCard,
        String originalFilename,
        String tumorVolumeMl,
        String riskLevel,
        boolean patientVisible,
        String doctorReviewStatus,
        String doctorReviewStatusLabel,
        String doctorReviewNote,
        String doctorReviewedAt,
        String summaryJson,
        String resultJson,
        String metricsJson,
        String riskJson,
        String labelMapJson,
        String reportMarkdown,
        boolean imageAvailable,
        String imageUrl,
        boolean overlayAvailable,
        String overlayUrl,
        boolean segmentationAvailable,
        String segmentationUrl,
        boolean meshAvailable,
        String meshUrl,
        String meshManifestUrl
) {
}
