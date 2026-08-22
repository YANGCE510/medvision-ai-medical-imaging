package com.ppgl.analyze.auth;

import java.time.LocalDateTime;

public record UserAccount(
        Long id,
        String username,
        String passwordHash,
        String displayName,
        String email,
        String phone,
        String patientIdCard,
        String role,
        boolean enabled,
        LocalDateTime createdAt
) {
}
