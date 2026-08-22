package com.ppgl.analyze.viewer;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/cases")
public class CaseViewerController {

    private static final Pattern CASE_ID_PATTERN = Pattern.compile("[A-Za-z0-9_-]{1,80}");
    private static final Set<String> ALLOWED_FILES = Set.of("image.nii.gz", "seg.nii.gz");

    private final Path caseRootDir;

    public CaseViewerController(@Value("${medical.case-root-dir}") String caseRootDir) {
        this.caseRootDir = Path.of(caseRootDir).toAbsolutePath().normalize();
    }

    @GetMapping("/{caseId}/viewer-files")
    public CaseViewerFilesResponse viewerFiles(@PathVariable String caseId) {
        Path caseDir = caseDir(caseId);
        if (!Files.isRegularFile(caseDir.resolve("image.nii.gz"))) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "缺少原始 CT 图像，无法进行 overlay 显示。");
        }
        if (!Files.isRegularFile(caseDir.resolve("seg.nii.gz"))) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "分割结果文件不存在。");
        }
        return new CaseViewerFilesResponse(
                caseId,
                "/api/cases/" + caseId + "/files/image.nii.gz",
                "/api/cases/" + caseId + "/files/seg.nii.gz"
        );
    }

    @GetMapping("/{caseId}/files/{fileName}")
    public ResponseEntity<Resource> file(@PathVariable String caseId, @PathVariable String fileName) throws IOException {
        // Only expose the two viewer files and reject path traversal attempts.
        if (!ALLOWED_FILES.contains(fileName) || fileName.contains("..") || fileName.contains("/") || fileName.contains("\\")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "文件名不合法。");
        }

        Path file = caseDir(caseId).resolve(fileName).normalize();
        if (!file.startsWith(caseRootDir) || !Files.isRegularFile(file)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "文件不存在。");
        }

        // FileSystemResource lets Spring stream the file instead of loading it into memory.
        Resource resource = new FileSystemResource(file);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(Files.size(file))
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.inline().filename(fileName).build().toString())
                .body(resource);
    }

    private Path caseDir(String caseId) {
        if (!CASE_ID_PATTERN.matcher(caseId).matches()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "caseId 不合法。");
        }
        Path caseDir = caseRootDir.resolve(caseId).normalize();
        if (!caseDir.startsWith(caseRootDir)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "caseId 不合法。");
        }
        return caseDir;
    }
}
