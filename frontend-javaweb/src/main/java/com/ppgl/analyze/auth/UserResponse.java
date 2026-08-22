package com.ppgl.analyze.auth;

public record UserResponse(Long id, String username, String displayName, String email, String phone, String patientIdCard, String role, String roleLabel) {

    public static UserResponse from(UserAccount user) {
        UserRole role = UserRole.from(user.role());
        return new UserResponse(
                user.id(),
                user.username(),
                user.displayName(),
                user.email(),
                user.phone(),
                user.patientIdCard(),
                role.name(),
                role.label()
        );
    }
}
