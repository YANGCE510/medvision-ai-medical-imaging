package com.ppgl.analyze.auth;

import java.time.Instant;

public record AuthSessionResponse(UserResponse user, String accessToken, String tokenType, Instant expiresAt) {
}
