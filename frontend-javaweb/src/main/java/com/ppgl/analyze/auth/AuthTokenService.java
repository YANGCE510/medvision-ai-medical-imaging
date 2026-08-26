package com.ppgl.analyze.auth;

import java.time.Duration;
import java.time.Instant;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.stereotype.Service;

@Service
public class AuthTokenService {

    private static final String ISSUER = "ppgl-analyze";

    private final JwtEncoder jwtEncoder;
    private final Duration tokenTtl;

    public AuthTokenService(
            JwtEncoder jwtEncoder,
            @Value("${ppgl.auth.jwt-ttl-minutes:120}") long tokenTtlMinutes
    ) {
        this.jwtEncoder = jwtEncoder;
        this.tokenTtl = Duration.ofMinutes(Math.max(5, tokenTtlMinutes));
    }

    public IssuedToken issue(UserResponse user) {
        Instant issuedAt = Instant.now();
        Instant expiresAt = issuedAt.plus(tokenTtl);
        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer(ISSUER)
                .subject(user.username())
                .issuedAt(issuedAt)
                .expiresAt(expiresAt)
                .claim("uid", user.id())
                .claim("role", user.role())
                .build();
        JwsHeader header = JwsHeader.with(MacAlgorithm.HS256).build();
        String value = jwtEncoder.encode(JwtEncoderParameters.from(header, claims)).getTokenValue();
        return new IssuedToken(value, expiresAt, tokenTtl);
    }

    public record IssuedToken(String value, Instant expiresAt, Duration ttl) {
    }
}
