package com.ppgl.analyze.ct;

import java.time.LocalDateTime;

public record CtImage(
        Long id,
        Long doctorId,
        String patientName,
        String patientIdCard,
        String remark,
        String originalFilename,
        String storedFilename,
        String filePath,
        long fileSize,
        String status,
        LocalDateTime createdAt
) {
}
