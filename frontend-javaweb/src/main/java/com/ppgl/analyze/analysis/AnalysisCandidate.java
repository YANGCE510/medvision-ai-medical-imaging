package com.ppgl.analyze.analysis;

import java.time.LocalDateTime;

record AnalysisCandidate(
        Long ctImageId,
        Long doctorId,
        String doctorName,
        String patientName,
        String patientIdCard,
        String originalFilename,
        String filePath,
        long fileSize,
        String status,
        LocalDateTime createdAt
) {
}
