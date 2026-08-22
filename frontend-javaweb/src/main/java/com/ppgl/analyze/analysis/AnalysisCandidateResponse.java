package com.ppgl.analyze.analysis;

import java.time.format.DateTimeFormatter;

public record AnalysisCandidateResponse(
        Long ctImageId,
        Long doctorId,
        String doctorName,
        String patientName,
        String patientIdCard,
        String originalFilename,
        String readableFileSize,
        String status,
        String createdAt
) {
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");

    static AnalysisCandidateResponse from(AnalysisCandidate candidate) {
        return new AnalysisCandidateResponse(
                candidate.ctImageId(),
                candidate.doctorId(),
                candidate.doctorName(),
                candidate.patientName(),
                candidate.patientIdCard(),
                candidate.originalFilename(),
                readableSize(candidate.fileSize()),
                candidate.status(),
                candidate.createdAt().format(FORMATTER)
        );
    }

    private static String readableSize(long bytes) {
        if (bytes < 1024) {
            return bytes + " B";
        }
        double kb = bytes / 1024.0;
        if (kb < 1024) {
            return String.format("%.1f KB", kb);
        }
        return String.format("%.1f MB", kb / 1024.0);
    }
}
