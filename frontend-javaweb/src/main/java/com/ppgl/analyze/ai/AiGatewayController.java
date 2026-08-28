package com.ppgl.analyze.ai;

import com.ppgl.analyze.auth.AuthenticatedUser;
import com.ppgl.analyze.auth.UserRole;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
@RequestMapping("/api/ai")
public class AiGatewayController {

    private final AiGatewayClient aiGatewayClient;

    public AiGatewayController(AiGatewayClient aiGatewayClient) {
        this.aiGatewayClient = aiGatewayClient;
    }

    @PostMapping(value = "/cases/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<StreamingResponseBody> upload(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam MultipartFile file
    ) throws IOException, InterruptedException {
        return aiGatewayClient.upload(file, requireAiUser(jwt));
    }

    @PutMapping(
            value = "/brain/cases/{caseId}/images/{modality}",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public ResponseEntity<StreamingResponseBody> uploadBrainModality(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable String caseId,
            @PathVariable String modality,
            @RequestParam MultipartFile file
    ) throws IOException, InterruptedException {
        return aiGatewayClient.uploadBrainModality(
                caseId,
                modality,
                file,
                requireAiUser(jwt)
        );
    }

    @RequestMapping({"/cases", "/cases/**", "/brain/**", "/rag/**", "/llm/**"})
    public ResponseEntity<StreamingResponseBody> proxy(
            @AuthenticationPrincipal Jwt jwt,
            HttpServletRequest request
    ) throws IOException, InterruptedException {
        return aiGatewayClient.proxy(request, requireAiUser(jwt));
    }

    private AuthenticatedUser requireAiUser(Jwt jwt) {
        AuthenticatedUser user = AuthenticatedUser.from(jwt);
        if (user.role() != UserRole.DOCTOR && user.role() != UserRole.ADMIN) {
            throw new AccessDeniedException("只有医生或管理员可以使用 AI 分析服务");
        }
        return user;
    }
}
