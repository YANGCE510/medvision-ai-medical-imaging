package com.ppgl.analyze.care;

import com.ppgl.analyze.auth.ApiResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/patient/care")
public class PatientCareController {

    private final CareService careService;

    public PatientCareController(CareService careService) {
        this.careService = careService;
    }

    @GetMapping("/follow-ups")
    public ApiResponse<List<FollowUpPlanResponse>> allFollowUps(@RequestParam Long patientUserId) {
        return ApiResponse.ok("查询成功", careService.patientFollowUps(patientUserId));
    }

    @GetMapping("/reports/{taskId}/follow-ups")
    public ApiResponse<List<FollowUpPlanResponse>> followUps(
            @PathVariable Long taskId,
            @RequestParam Long patientUserId
    ) {
        return ApiResponse.ok("查询成功", careService.patientFollowUps(patientUserId, taskId));
    }

    @PostMapping("/follow-ups/{planId}/submit")
    public ApiResponse<FollowUpSubmissionResponse> submitFollowUp(
            @PathVariable Long planId,
            @RequestParam Long patientUserId,
            @RequestBody FollowUpSubmissionRequest request
    ) {
        return ApiResponse.ok("提交成功", careService.submitFollowUp(patientUserId, planId, request));
    }

    @PostMapping("/reports/{taskId}/feedbacks")
    public ApiResponse<PatientFeedbackResponse> createFeedback(
            @PathVariable Long taskId,
            @RequestParam Long patientUserId,
            @RequestBody PatientFeedbackRequest request
    ) {
        return ApiResponse.ok("提交成功", careService.createFeedback(patientUserId, taskId, request));
    }

    @GetMapping("/feedbacks")
    public ApiResponse<List<PatientFeedbackResponse>> feedbacks(@RequestParam Long patientUserId) {
        return ApiResponse.ok("查询成功", careService.patientFeedbacks(patientUserId));
    }
}
