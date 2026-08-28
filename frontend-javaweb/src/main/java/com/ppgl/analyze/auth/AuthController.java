package com.ppgl.analyze.auth;

import java.time.Duration;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;
    private final AuthTokenService authTokenService;

    public AuthController(AuthService authService, AuthTokenService authTokenService) {
        this.authService = authService;
        this.authTokenService = authTokenService;
    }

    @GetMapping("/setup-status")
    public ApiResponse<SetupStatusResponse> setupStatus() {
        return ApiResponse.ok("查询成功", new SetupStatusResponse(authService.setupRequired()));
    }

    @PostMapping("/setup")
    public ResponseEntity<ApiResponse<AuthSessionResponse>> setup(@RequestBody SetupRequest request) {
        UserResponse user = authService.setupFirstDoctor(request);
        return authenticatedResponse(HttpStatus.CREATED, "初始化成功", user);
    }

    @PostMapping("/register")
    public ResponseEntity<ApiResponse<AuthSessionResponse>> register(@RequestBody RegisterRequest request) {
        UserResponse user = authService.register(request);
        return authenticatedResponse(HttpStatus.CREATED, "注册成功", user);
    }

    @PostMapping("/login")
    public ResponseEntity<ApiResponse<AuthSessionResponse>> login(@RequestBody LoginRequest request) {
        UserResponse user = authService.login(request);
        return authenticatedResponse(HttpStatus.OK, "登录成功", user);
    }

    @PostMapping("/logout")
    public ResponseEntity<ApiResponse<Void>> logout() {
        ResponseCookie cookie = ResponseCookie.from(SecurityConfig.AUTH_COOKIE, "")
                .httpOnly(true)
                .sameSite("Strict")
                .path("/")
                .maxAge(Duration.ZERO)
                .build();
        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body(ApiResponse.ok("已退出登录", null));
    }

    @GetMapping("/me")
    public ApiResponse<UserResponse> me(@AuthenticationPrincipal Jwt jwt) {
        AuthenticatedUser current = AuthenticatedUser.from(jwt);
        return ApiResponse.ok("查询成功", authService.findEnabledUser(current.id()));
    }

    private ResponseEntity<ApiResponse<AuthSessionResponse>> authenticatedResponse(
            HttpStatus status,
            String message,
            UserResponse user
    ) {
        AuthTokenService.IssuedToken token = authTokenService.issue(user);
        ResponseCookie cookie = ResponseCookie.from(SecurityConfig.AUTH_COOKIE, token.value())
                .httpOnly(true)
                .sameSite("Strict")
                .path("/")
                .maxAge(token.ttl())
                .build();
        AuthSessionResponse session = new AuthSessionResponse(user, token.value(), "Bearer", token.expiresAt());
        return ResponseEntity.status(status)
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body(ApiResponse.ok(message, session));
    }
}
