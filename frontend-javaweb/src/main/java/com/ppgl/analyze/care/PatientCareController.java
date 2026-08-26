package com.ppgl.analyze.care;

import com.ppgl.analyze.auth.ApiResponse;
import com.ppgl.analyze.auth.AuthenticatedUser;
import com.ppgl.analyze.auth.UserRole;
import java.util.List;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/patient/care")
public class PatientCareController {

    private final CareService careService;

    public PatientCareController(CareService careService) {
        this.careService = careService;
    }

    @GetMapping("/follow-ups")
    public ApiResponse<List<FollowUpPlanResponse>> allFollowUps(@AuthenticationPrincipal Jwt jwt) {
        Long patientUserId = patientId(jwt);
        return ApiResponse.ok("查询成功", careService.patientFollowUps(patientUserId));
    }

    @GetMapping("/reports/{taskId}/follow-ups")
    public ApiResponse<List<FollowUpPlanResponse>> followUps(
            @PathVariable Long taskId,
            @AuthenticationPrincipal Jwt jwt
    ) {
        Long patientUserId = patientId(jwt);
        return ApiResponse.ok("查询成功", careService.patientFollowUps(patientUserId, taskId));
    }

    @PostMapping("/follow-ups/{planId}/submit")
    public ApiResponse<FollowUpSubmissionResponse> submitFollowUp(
            @PathVariable Long planId,
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody FollowUpSubmissionRequest request
    ) {
        Long patientUserId = patientId(jwt);
        return ApiResponse.ok("提交成功", careService.submitFollowUp(patientUserId, planId, request));
    }

    @PostMapping("/reports/{taskId}/feedbacks")
    public ApiResponse<PatientFeedbackResponse> createFeedback(
            @PathVariable Long taskId,
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody PatientFeedbackRequest request
    ) {
        Long patientUserId = patientId(jwt);
        return ApiResponse.ok("提交成功", careService.createFeedback(patientUserId, taskId, request));
    }

    @GetMapping("/feedbacks")
    public ApiResponse<List<PatientFeedbackResponse>> feedbacks(@AuthenticationPrincipal Jwt jwt) {
        Long patientUserId = patientId(jwt);
        return ApiResponse.ok("查询成功", careService.patientFeedbacks(patientUserId));
    }

    private Long patientId(Jwt jwt) {
        return AuthenticatedUser.from(jwt).require(UserRole.PATIENT).id();
    }
}
