package com.ppgl.analyze.auth;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;

public record AuthenticatedUser(Long id, String username, UserRole role) {

    public static AuthenticatedUser from(Jwt jwt) {
        Number rawId = jwt.getClaim("uid");
        String rawRole = jwt.getClaimAsString("role");
        if (rawId == null || rawRole == null) {
            throw new AccessDeniedException("登录凭证缺少用户信息");
        }
        return new AuthenticatedUser(rawId.longValue(), jwt.getSubject(), UserRole.from(rawRole));
    }

    public AuthenticatedUser require(UserRole expectedRole) {
        if (role != expectedRole) {
            throw new AccessDeniedException("当前账号无权执行此操作");
        }
        return this;
    }
}
