package com.ppgl.analyze.report;

import java.time.format.DateTimeFormatter;

public record ReportListItemResponse(
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
        String createdAt
) {
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");

    static ReportListItemResponse from(AnalysisResultRecord record) {
        return from(
                record,
                record.tumorVolumeMl() == null ? "-" : record.tumorVolumeMl().toPlainString(),
                blankToDash(record.riskLevel())
        );
    }

    static ReportListItemResponse from(AnalysisResultRecord record, String tumorVolumeMl, String riskLevel) {
        return new ReportListItemResponse(
                record.taskId(),
                record.ctImageId(),
                record.patientName(),
                record.patientIdCard(),
                record.originalFilename(),
                blankToDash(tumorVolumeMl),
                blankToDash(riskLevel),
                record.patientVisible(),
                reviewStatus(record),
                reviewStatusLabel(record),
                blankToEmpty(record.doctorReviewNote()),
                record.doctorReviewedAt() == null ? "" : record.doctorReviewedAt().format(FORMATTER),
                record.createdAt().format(FORMATTER)
        );
    }

    private static String blankToDash(String value) {
        return value == null || value.isBlank() ? "-" : value;
    }

    private static String blankToEmpty(String value) {
        return value == null ? "" : value;
    }

    private static String reviewStatus(AnalysisResultRecord record) {
        return record.patientVisible() ? "PUBLISHED" : "PENDING";
    }

    private static String reviewStatusLabel(AnalysisResultRecord record) {
        return record.patientVisible() ? "已发布给患者" : "待医生审核";
    }
}
