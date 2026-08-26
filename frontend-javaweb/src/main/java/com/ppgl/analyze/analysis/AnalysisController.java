package com.ppgl.analyze.analysis;

import com.ppgl.analyze.auth.ApiResponse;
import com.ppgl.analyze.auth.AuthenticatedUser;
import com.ppgl.analyze.auth.UserRole;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/analysis")
public class AnalysisController {

    private final AnalysisService analysisService;
    private final PpglPipelineClient ppglPipelineClient;

    public AnalysisController(AnalysisService analysisService, PpglPipelineClient ppglPipelineClient) {
        this.analysisService = analysisService;
        this.ppglPipelineClient = ppglPipelineClient;
    }

    @GetMapping("/board")
    public ApiResponse<AnalysisBoardResponse> board(@AuthenticationPrincipal Jwt jwt) {
        Long doctorId = AuthenticatedUser.from(jwt).require(UserRole.DOCTOR).id();
        return ApiResponse.ok("查询成功", analysisService.board(doctorId));
    }

    @GetMapping("/node-status")
    public ApiResponse<ComputeNodeStatusResponse> nodeStatus(@AuthenticationPrincipal Jwt jwt) {
        AuthenticatedUser.from(jwt).require(UserRole.DOCTOR);
        return ApiResponse.ok("查询成功", ppglPipelineClient.status());
    }

    @PostMapping("/tasks")
    public ApiResponse<AnalysisBoardResponse> submit(
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody AnalysisSubmitRequest request
    ) {
        Long doctorId = AuthenticatedUser.from(jwt).require(UserRole.DOCTOR).id();
        return ApiResponse.ok("任务已加入队列", analysisService.submit(doctorId, request));
    }
}
