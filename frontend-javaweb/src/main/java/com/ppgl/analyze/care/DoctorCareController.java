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
@RequestMapping("/api/care")
public class DoctorCareController {

    private final CareService careService;

    public DoctorCareController(CareService careService) {
        this.careService = careService;
    }

    @GetMapping("/follow-ups")
    public ApiResponse<List<FollowUpPlanResponse>> followUps(@AuthenticationPrincipal Jwt jwt) {
        Long doctorId = doctorId(jwt);
        return ApiResponse.ok("查询成功", careService.listFollowUps(doctorId));
    }

    @PostMapping("/follow-ups")
    public ApiResponse<FollowUpPlanResponse> saveFollowUp(
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody FollowUpPlanRequest request
    ) {
        Long doctorId = doctorId(jwt);
        return ApiResponse.ok("保存成功", careService.saveFollowUp(doctorId, request));
    }

    @PostMapping("/follow-ups/{planId}/status")
    public ApiResponse<FollowUpPlanResponse> updateFollowUpStatus(
            @PathVariable Long planId,
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody FollowUpStatusRequest request
    ) {
        Long doctorId = doctorId(jwt);
        return ApiResponse.ok("保存成功", careService.updateFollowUpStatus(doctorId, planId, request));
    }

    @GetMapping("/feedbacks")
    public ApiResponse<List<PatientFeedbackResponse>> feedbacks(@AuthenticationPrincipal Jwt jwt) {
        Long doctorId = doctorId(jwt);
        return ApiResponse.ok("查询成功", careService.listFeedbacks(doctorId));
    }

    @PostMapping("/feedbacks/{feedbackId}/reply")
    public ApiResponse<PatientFeedbackResponse> replyFeedback(
            @PathVariable Long feedbackId,
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody FeedbackReplyRequest request
    ) {
        Long doctorId = doctorId(jwt);
        return ApiResponse.ok("保存成功", careService.replyFeedback(doctorId, feedbackId, request));
    }

    private Long doctorId(Jwt jwt) {
        return AuthenticatedUser.from(jwt).require(UserRole.DOCTOR).id();
    }
}
