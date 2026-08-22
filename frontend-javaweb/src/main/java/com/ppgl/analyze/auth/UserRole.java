package com.ppgl.analyze.auth;

import java.util.Locale;

public enum UserRole {
    DOCTOR("医生"),
    PATIENT("病人"),
    ADMIN("管理员");

    private final String label;

    UserRole(String label) {
        this.label = label;
    }

    public String label() {
        return label;
    }

    public static UserRole from(String value) {
        if (value == null || value.isBlank()) {
            return PATIENT;
        }
        try {
            return UserRole.valueOf(value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException ex) {
            throw new AuthException("用户类型不正确");
        }
    }
}
