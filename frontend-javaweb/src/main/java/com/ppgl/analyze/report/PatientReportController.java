package com.ppgl.analyze.report;

import com.ppgl.analyze.auth.ApiResponse;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/patient/reports")
public class PatientReportController {

    private final ReportService reportService;

    public PatientReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping
    public ApiResponse<List<ReportListItemResponse>> list(@RequestParam Long patientUserId) {
        return ApiResponse.ok("查询成功", reportService.patientList(patientUserId));
    }

    @GetMapping("/{taskId}")
    public ApiResponse<ReportDetailResponse> detail(@PathVariable Long taskId, @RequestParam Long patientUserId) {
        return ApiResponse.ok("查询成功", reportService.patientDetail(taskId, patientUserId));
    }

    @GetMapping("/{taskId}/chat")
    public ApiResponse<List<ReportChatResponse>> chatHistory(@PathVariable Long taskId, @RequestParam Long patientUserId) {
        return ApiResponse.ok("查询成功", reportService.patientChatHistory(taskId, patientUserId));
    }

    @PostMapping("/{taskId}/chat")
    public ApiResponse<Map<String, String>> chat(
            @PathVariable Long taskId,
            @RequestParam Long patientUserId,
            @RequestBody ReportChatRequest request
    ) {
        String reply = reportService.patientChat(taskId, patientUserId, request);
        return ApiResponse.ok("回复成功", Map.of("reply", reply));
    }
}
