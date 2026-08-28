package com.ppgl.analyze.auth;

public record SetupRequest(String username, String password, String displayName, String phone) {
}
