package com.ppgl.analyze.auth;

public record RegisterRequest(String username, String password, String displayName, String email, String phone, String patientIdCard, String role) {
}
