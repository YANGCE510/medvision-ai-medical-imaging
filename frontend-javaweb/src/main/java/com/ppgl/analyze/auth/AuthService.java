package com.ppgl.analyze.auth;

import java.util.Locale;
import java.util.regex.Pattern;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AuthService {

    private static final Pattern USERNAME_PATTERN = Pattern.compile("^[A-Za-z0-9_]{3,32}$");
    private static final Pattern EMAIL_PATTERN = Pattern.compile("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$");
    private static final Pattern PHONE_PATTERN = Pattern.compile("^1[3-9]\\d{9}$");
    private static final Pattern ID_CARD_PATTERN = Pattern.compile("^[1-9]\\d{16}[0-9Xx]$");

    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder(12);
    private final UserRepository userRepository;

    public AuthService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public UserResponse register(RegisterRequest request) {
        String username = normalize(request.username());
        String password = request.password() == null ? "" : request.password();
        String displayName = blankToDefault(request.displayName(), username);
        String email = normalizeNullable(request.email());
        String phone = normalize(request.phone());
        UserRole role = UserRole.PATIENT;
        if (request.role() != null && !request.role().isBlank() && UserRole.from(request.role()) != UserRole.PATIENT) {
            throw new AuthException("公开注册仅支持患者账号，医生和管理员由系统管理员创建");
        }
        String patientIdCard = normalizePatientIdCard(request.patientIdCard(), role);

        validateUsername(username);
        validatePassword(password);
        validateEmail(email);
        validatePhone(phone);

        if (userRepository.existsByUsername(username)) {
            throw new AuthException("账号已存在");
        }
        if (email != null && userRepository.existsByEmail(email)) {
            throw new AuthException("邮箱已被使用");
        }
        if (userRepository.existsByPhone(phone)) {
            throw new AuthException("手机号已被使用");
        }
        if (patientIdCard != null && userRepository.existsByPatientIdCard(patientIdCard)) {
            throw new AuthException("身份证号已被使用");
        }

        String passwordHash = passwordEncoder.encode(password);
        UserAccount user = userRepository.create(username, passwordHash, displayName, email, phone, patientIdCard, role);
        return UserResponse.from(user);
    }

    public UserResponse login(LoginRequest request) {
        String login = normalize(request.username());
        String password = request.password() == null ? "" : request.password();

        validateLogin(login);
        UserAccount user = userRepository.findByUsernameOrPhone(login)
                .orElseThrow(() -> new AuthException("账号或密码错误"));

        if (!user.enabled() || !passwordEncoder.matches(password, user.passwordHash())) {
            throw new AuthException("账号或密码错误");
        }
        return UserResponse.from(user);
    }

    public UserResponse findEnabledUser(Long userId) {
        UserAccount user = userRepository.findById(userId)
                .orElseThrow(() -> new AuthException("用户不存在"));
        if (!user.enabled()) {
            throw new AuthException("账号已禁用");
        }
        return UserResponse.from(user);
    }

    private void validateUsername(String username) {
        if (!USERNAME_PATTERN.matcher(username).matches()) {
            throw new AuthException("账号需为 3-32 位字母、数字或下划线");
        }
    }

    private void validateLogin(String login) {
        if (!USERNAME_PATTERN.matcher(login).matches() && !PHONE_PATTERN.matcher(login).matches()) {
            throw new AuthException("账号或手机号格式不正确");
        }
    }

    private void validatePassword(String password) {
        if (password.length() < 6 || password.length() > 64) {
            throw new AuthException("密码长度需为 6-64 位");
        }
    }

    private void validateEmail(String email) {
        if (email != null && !EMAIL_PATTERN.matcher(email).matches()) {
            throw new AuthException("邮箱格式不正确");
        }
    }

    private void validatePhone(String phone) {
        if (!PHONE_PATTERN.matcher(phone).matches()) {
            throw new AuthException("手机号格式不正确");
        }
    }

    private String normalizePatientIdCard(String value, UserRole role) {
        String normalized = value == null ? "" : value.trim().toUpperCase(Locale.ROOT);
        if (role == UserRole.PATIENT && normalized.isBlank()) {
            throw new AuthException("病人账号需要填写身份证号");
        }
        if (!normalized.isBlank() && !ID_CARD_PATTERN.matcher(normalized).matches()) {
            throw new AuthException("身份证号格式不正确");
        }
        return normalized.isBlank() ? null : normalized;
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
    }

    private String normalizeNullable(String value) {
        String normalized = normalize(value);
        return normalized.isBlank() ? null : normalized;
    }

    private String blankToDefault(String value, String fallback) {
        String normalized = value == null ? "" : value.trim();
        return normalized.isBlank() ? fallback : normalized;
    }
}
