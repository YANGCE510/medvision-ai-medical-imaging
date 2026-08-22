package com.ppgl.analyze.report;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ppgl.analyze.auth.ApiResponse;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
@RequestMapping("/api/reports")
public class ReportController {

    private final ReportService reportService;
    private final ObjectMapper objectMapper;

    public ReportController(ReportService reportService, ObjectMapper objectMapper) {
        this.reportService = reportService;
        this.objectMapper = objectMapper;
    }

    @GetMapping
    public ApiResponse<List<ReportListItemResponse>> list(@RequestParam Long doctorId) {
        return ApiResponse.ok("查询成功", reportService.list(doctorId));
    }

    @GetMapping("/{taskId}")
    public ApiResponse<ReportDetailResponse> detail(@PathVariable Long taskId, @RequestParam Long doctorId) {
        return ApiResponse.ok("查询成功", reportService.detail(taskId, doctorId));
    }

    @PostMapping("/{taskId}/review")
    public ApiResponse<ReportDetailResponse> review(
            @PathVariable Long taskId,
            @RequestParam Long doctorId,
            @RequestBody ReportReviewRequest request
    ) {
        return ApiResponse.ok("保存成功", reportService.reviewForPatient(taskId, doctorId, request));
    }

    @GetMapping("/{taskId}/overlay")
    public ResponseEntity<Resource> overlay(@PathVariable Long taskId, @RequestParam Long doctorId) {
        return ResponseEntity.ok()
                .contentType(MediaType.IMAGE_PNG)
                .body(reportService.overlay(taskId, doctorId));
    }

    @GetMapping("/{taskId}/image")
    public ResponseEntity<Resource> image(@PathVariable Long taskId, @RequestParam Long doctorId) {
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "inline; filename=\"image-task-" + taskId + ".nii.gz\"")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(reportService.image(taskId, doctorId));
    }

    @GetMapping("/{taskId}/segmentation")
    public ResponseEntity<Resource> segmentation(@PathVariable Long taskId, @RequestParam Long doctorId) {
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"segmentation-task-" + taskId + ".nii.gz\"")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(reportService.segmentation(taskId, doctorId));
    }

    @GetMapping("/{taskId}/mesh")
    public ResponseEntity<Resource> mesh(@PathVariable Long taskId, @RequestParam Long doctorId) {
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("model/gltf-binary"))
                .body(reportService.mesh(taskId, doctorId));
    }

    @GetMapping("/{taskId}/mesh-manifest")
    public ResponseEntity<Resource> meshManifest(@PathVariable Long taskId, @RequestParam Long doctorId) {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(reportService.meshManifest(taskId, doctorId));
    }

    @GetMapping("/{taskId}/chat")
    public ApiResponse<List<ReportChatResponse>> chatHistory(@PathVariable Long taskId, @RequestParam Long doctorId) {
        return ApiResponse.ok("查询成功", reportService.chatHistory(taskId, doctorId));
    }

    @GetMapping("/{taskId}/patient-concern-summary")
    public ApiResponse<PatientConcernSummaryResponse> patientConcernSummary(
            @PathVariable Long taskId,
            @RequestParam Long doctorId
    ) {
        return ApiResponse.ok("分析成功", reportService.patientConcernSummary(taskId, doctorId));
    }

    @PostMapping("/{taskId}/chat/stream")
    public ResponseEntity<StreamingResponseBody> chatStream(
            @PathVariable Long taskId,
            @RequestParam Long doctorId,
            @RequestBody ReportChatRequest request
    ) {
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("application/x-ndjson"))
                .body(output -> {
                    try {
                        reportService.streamChat(taskId, doctorId, request, output);
                    } catch (Exception ex) {
                        writeStreamError(output, ex);
                    }
                });
    }

    private void writeStreamError(OutputStream output, Exception ex) {
        String message = ex.getMessage() == null || ex.getMessage().isBlank()
                ? "生成中断，请重试"
                : ex.getMessage();
        try {
            String line = objectMapper.writeValueAsString(Map.of("type", "error", "detail", message));
            output.write((line + "\n").getBytes(StandardCharsets.UTF_8));
            output.flush();
        } catch (IOException ignored) {
            // The client may already have closed the streaming connection.
        }
    }
}
