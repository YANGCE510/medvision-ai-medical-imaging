package com.ppgl.analyze.ct;

import java.time.format.DateTimeFormatter;

public record CtImageResponse(
        Long id,
        Long doctorId,
        String patientName,
        String patientIdCard,
        String remark,
        String originalFilename,
        long fileSize,
        String readableFileSize,
        String status,
        String createdAt
) {
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");

    public static CtImageResponse from(CtImage image) {
        return new CtImageResponse(
                image.id(),
                image.doctorId(),
                image.patientName(),
                image.patientIdCard(),
                image.remark(),
                image.originalFilename(),
                image.fileSize(),
                readableSize(image.fileSize()),
                image.status(),
                image.createdAt().format(FORMATTER)
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
