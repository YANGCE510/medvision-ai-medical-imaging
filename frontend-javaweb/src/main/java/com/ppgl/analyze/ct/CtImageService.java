package com.ppgl.analyze.ct;

import com.ppgl.analyze.auth.AuthException;
import com.ppgl.analyze.auth.UserAccount;
import com.ppgl.analyze.auth.UserRepository;
import com.ppgl.analyze.auth.UserRole;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

@Service
public class CtImageService {

    private static final Logger log = LoggerFactory.getLogger(CtImageService.class);
    private static final Pattern ID_CARD_PATTERN = Pattern.compile("^[1-9]\\d{16}[0-9Xx]$");

    private final CtImageRepository ctImageRepository;
    private final UserRepository userRepository;
    private final Path uploadDir;
    private final Path resultDir;

    public CtImageService(
            CtImageRepository ctImageRepository,
            UserRepository userRepository,
            @Value("${ppgl.upload.ct-dir}") String uploadDir,
            @Value("${ppgl.analysis.result-dir}") String resultDir
    ) {
        this.ctImageRepository = ctImageRepository;
        this.userRepository = userRepository;
        this.uploadDir = Path.of(uploadDir).toAbsolutePath().normalize();
        this.resultDir = Path.of(resultDir).toAbsolutePath().normalize();
    }

    public List<CtImageResponse> listByDoctor(Long doctorId) {
        ensureDoctor(doctorId);
        return ctImageRepository.findByDoctorId(doctorId).stream()
                .map(CtImageResponse::from)
                .toList();
    }

    public CtImageResponse upload(Long doctorId, String patientName, String patientIdCard, String remark, MultipartFile file) {
        ensureDoctor(doctorId);
        String normalizedPatientName = required(patientName, "病人姓名不能为空");
        String normalizedIdCard = normalizePatientIdCard(patientIdCard);
        String normalizedRemark = normalizeRemark(remark);

        if (file == null || file.isEmpty()) {
            throw new CtImageException("请选择 CT 文件");
        }

        try {
            Files.createDirectories(uploadDir);
            String originalFilename = normalizeFilename(file.getOriginalFilename());
            String storedFilename = UUID.randomUUID() + "-" + originalFilename;
            Path target = uploadDir.resolve(storedFilename).normalize();
            if (!target.startsWith(uploadDir)) {
                throw new CtImageException("文件名不合法");
            }
            Files.copy(file.getInputStream(), target, StandardCopyOption.REPLACE_EXISTING);

            CtImage image = new CtImage(
                    null,
                    doctorId,
                    normalizedPatientName,
                    normalizedIdCard,
                    normalizedRemark,
                    originalFilename,
                    storedFilename,
                    target.toString(),
                    file.getSize(),
                    "未分析",
                    LocalDateTime.now()
            );
            return CtImageResponse.from(ctImageRepository.create(image));
        } catch (IOException ex) {
            throw new CtImageException("CT 文件保存失败");
        }
    }

    @Transactional
    public void delete(Long doctorId, Long id) {
        ensureDoctor(doctorId);
        CtImage image = ctImageRepository.findByDoctorIdAndId(doctorId, id)
                .orElseThrow(() -> new CtImageException("影像记录不存在"));
        List<Long> taskIds = ctImageRepository.findTaskIdsByDoctorAndCtImage(doctorId, id);
        List<Path> cleanupPaths = cleanupPaths(image, taskIds);
        ctImageRepository.deleteCascade(doctorId, id);
        cleanupFiles(cleanupPaths);
    }

    private List<Path> cleanupPaths(CtImage image, List<Long> taskIds) {
        Set<Path> paths = new LinkedHashSet<>();
        addIfSafe(paths, image.filePath(), uploadDir);
        for (Long taskId : taskIds) {
            if (taskId != null) {
                addIfSafe(paths, resultDir.resolve("task-" + taskId).toString(), resultDir);
            }
        }
        return new ArrayList<>(paths);
    }

    private void addIfSafe(Set<Path> paths, String rawPath, Path allowedRoot) {
        if (rawPath == null || rawPath.isBlank()) {
            return;
        }
        Path path = Path.of(rawPath).toAbsolutePath().normalize();
        if (path.startsWith(allowedRoot)) {
            paths.add(path);
        } else {
            log.warn("跳过不在允许目录内的删除路径：{}", path);
        }
    }

    private void cleanupFiles(List<Path> paths) {
        for (Path path : paths) {
            try {
                deletePath(path);
            } catch (IOException ex) {
                log.warn("文件清理失败：{}", path, ex);
            }
        }
    }

    private void deletePath(Path path) throws IOException {
        if (!Files.exists(path)) {
            return;
        }
        if (Files.isDirectory(path)) {
            try (var stream = Files.walk(path)) {
                for (Path item : stream.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(item);
                }
            }
        } else {
            Files.deleteIfExists(path);
        }
    }

    private void ensureDoctor(Long doctorId) {
        if (doctorId == null) {
            throw new CtImageException("医生账号不能为空");
        }
        UserAccount user = userRepository.findById(doctorId)
                .orElseThrow(() -> new CtImageException("医生账号不存在"));
        if (UserRole.from(user.role()) != UserRole.DOCTOR) {
            throw new AuthException("只有医生用户可以管理 CT 影像");
        }
    }

    private String required(String value, String message) {
        String normalized = value == null ? "" : value.trim();
        if (normalized.isBlank()) {
            throw new CtImageException(message);
        }
        return normalized;
    }

    private String normalizePatientIdCard(String value) {
        String normalized = required(value, "身份证不能为空").toUpperCase();
        if (!ID_CARD_PATTERN.matcher(normalized).matches()) {
            throw new CtImageException("身份证号需为 18 位合法格式");
        }
        return normalized;
    }

    private String normalizeRemark(String remark) {
        String normalized = remark == null ? "" : remark.trim();
        return normalized.length() > 500 ? normalized.substring(0, 500) : normalized;
    }

    private String normalizeFilename(String filename) {
        if (filename == null || filename.isBlank()) {
            return "ct-image.dat";
        }
        return Path.of(filename).getFileName().toString().replaceAll("[^A-Za-z0-9._-]", "_");
    }
}
