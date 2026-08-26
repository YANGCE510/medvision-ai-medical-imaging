package com.ppgl.analyze.ct;

import com.ppgl.analyze.auth.ApiResponse;
import com.ppgl.analyze.auth.AuthenticatedUser;
import com.ppgl.analyze.auth.UserRole;
import java.util.List;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/ct-images")
public class CtImageController {

    private final CtImageService ctImageService;

    public CtImageController(CtImageService ctImageService) {
        this.ctImageService = ctImageService;
    }

    @GetMapping
    public ApiResponse<List<CtImageResponse>> list(@AuthenticationPrincipal Jwt jwt) {
        Long doctorId = doctorId(jwt);
        return ApiResponse.ok("查询成功", ctImageService.listByDoctor(doctorId));
    }

    @PostMapping
    public ApiResponse<CtImageResponse> upload(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam String patientName,
            @RequestParam String patientIdCard,
            @RequestParam(required = false) String remark,
            @RequestParam MultipartFile file
    ) {
        Long doctorId = doctorId(jwt);
        return ApiResponse.ok("CT 上传成功", ctImageService.upload(doctorId, patientName, patientIdCard, remark, file));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable Long id, @AuthenticationPrincipal Jwt jwt) {
        Long doctorId = doctorId(jwt);
        ctImageService.delete(doctorId, id);
        return ApiResponse.ok("删除成功", null);
    }

    private Long doctorId(Jwt jwt) {
        return AuthenticatedUser.from(jwt).require(UserRole.DOCTOR).id();
    }
}
