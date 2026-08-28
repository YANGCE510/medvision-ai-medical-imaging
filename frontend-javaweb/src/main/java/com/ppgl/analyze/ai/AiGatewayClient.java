package com.ppgl.analyze.ai;

import com.ppgl.analyze.auth.AuthenticatedUser;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@Component
public class AiGatewayClient {

    private static final String PUBLIC_PREFIX = "/api/ai";
    private static final List<String> RESPONSE_HEADERS = List.of(
            "content-type",
            "content-disposition",
            "cache-control",
            "x-accel-buffering",
            "content-length"
    );
    private static final Set<String> BRAIN_MODALITIES = Set.of("flair", "t1", "t1ce", "t2");

    private final HttpClient httpClient;
    private final String baseUrl;
    private final String internalApiKey;
    private final Duration requestTimeout;

    public AiGatewayClient(
            @Value("${ppgl.pipeline.base-url}") String baseUrl,
            @Value("${ppgl.internal.api-key}") String internalApiKey,
            @Value("${ppgl.pipeline.timeout-minutes:30}") long timeoutMinutes
    ) {
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.internalApiKey = internalApiKey;
        this.requestTimeout = Duration.ofMinutes(Math.max(1, timeoutMinutes));
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(15))
                .build();
    }

    public ResponseEntity<StreamingResponseBody> proxy(
            HttpServletRequest servletRequest,
            AuthenticatedUser user
    ) throws IOException, InterruptedException {
        String requestUri = servletRequest.getRequestURI();
        if (!requestUri.startsWith(PUBLIC_PREFIX)) {
            throw new IllegalArgumentException("AI gateway path is invalid");
        }
        String upstreamPath = "/api" + requestUri.substring(PUBLIC_PREFIX.length());
        String query = servletRequest.getQueryString();
        URI uri = URI.create(baseUrl + upstreamPath + (query == null || query.isBlank() ? "" : "?" + query));

        byte[] body = servletRequest.getInputStream().readAllBytes();
        HttpRequest.BodyPublisher publisher = body.length == 0
                ? HttpRequest.BodyPublishers.noBody()
                : HttpRequest.BodyPublishers.ofByteArray(body);
        HttpRequest.Builder builder = delegatedRequest(uri, user)
                .method(servletRequest.getMethod(), publisher);
        copyRequestHeader(servletRequest, builder, "Content-Type");
        copyRequestHeader(servletRequest, builder, "Accept");
        return send(builder.build());
    }

    public ResponseEntity<StreamingResponseBody> upload(
            MultipartFile file,
            AuthenticatedUser user
    ) throws IOException, InterruptedException {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("请选择 CT 文件");
        }
        String boundary = "----PPGLGateway" + UUID.randomUUID();
        String filename = sanitizeFilename(file.getOriginalFilename());
        byte[] header = ("--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"file\"; filename=\"" + filename + "\"\r\n"
                + "Content-Type: application/gzip\r\n\r\n").getBytes(StandardCharsets.UTF_8);
        byte[] footer = ("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8);
        HttpRequest.BodyPublisher body = HttpRequest.BodyPublishers.concat(
                HttpRequest.BodyPublishers.ofByteArray(header),
                HttpRequest.BodyPublishers.ofInputStream(() -> inputStream(file)),
                HttpRequest.BodyPublishers.ofByteArray(footer)
        );
        HttpRequest request = delegatedRequest(URI.create(baseUrl + "/api/cases/upload"), user)
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .POST(body)
                .build();
        return send(request);
    }

    public ResponseEntity<StreamingResponseBody> uploadBrainModality(
            String caseId,
            String modality,
            MultipartFile file,
            AuthenticatedUser user
    ) throws IOException, InterruptedException {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("请选择 MRI 文件");
        }
        String safeCaseId = requirePathSegment(caseId, "病例编号无效");
        String safeModality = modality == null ? "" : modality.trim().toLowerCase();
        if (!BRAIN_MODALITIES.contains(safeModality)) {
            throw new IllegalArgumentException("MRI 序列名称无效");
        }

        String boundary = "----PPGLBrainGateway" + UUID.randomUUID();
        String filename = sanitizeFilename(file.getOriginalFilename(), safeModality + ".nii.gz");
        byte[] header = ("--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"file\"; filename=\"" + filename + "\"\r\n"
                + "Content-Type: application/gzip\r\n\r\n").getBytes(StandardCharsets.UTF_8);
        byte[] footer = ("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8);
        HttpRequest.BodyPublisher body = HttpRequest.BodyPublishers.concat(
                HttpRequest.BodyPublishers.ofByteArray(header),
                HttpRequest.BodyPublishers.ofInputStream(() -> inputStream(file)),
                HttpRequest.BodyPublishers.ofByteArray(footer)
        );
        URI uri = URI.create(baseUrl + "/api/brain/cases/" + safeCaseId + "/images/" + safeModality);
        HttpRequest request = delegatedRequest(uri, user)
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .PUT(body)
                .build();
        return send(request);
    }

    private HttpRequest.Builder delegatedRequest(URI uri, AuthenticatedUser user) {
        return HttpRequest.newBuilder(uri)
                .timeout(requestTimeout)
                .header("X-PPGL-Internal-Key", internalApiKey)
                .header("X-PPGL-User-Id", String.valueOf(user.id()))
                .header("X-PPGL-User-Role", user.role().name())
                .header("X-PPGL-Username", user.username() == null ? "" : user.username());
    }

    private ResponseEntity<StreamingResponseBody> send(HttpRequest request)
            throws IOException, InterruptedException {
        HttpResponse<InputStream> upstream = httpClient.send(
                request,
                HttpResponse.BodyHandlers.ofInputStream()
        );
        HttpHeaders headers = new HttpHeaders();
        for (String name : RESPONSE_HEADERS) {
            upstream.headers().firstValue(name).ifPresent(value -> headers.add(name, value));
        }
        StreamingResponseBody body = output -> {
            try (InputStream input = upstream.body()) {
                input.transferTo(output);
            }
        };
        return new ResponseEntity<>(body, headers, upstream.statusCode());
    }

    private void copyRequestHeader(
            HttpServletRequest servletRequest,
            HttpRequest.Builder builder,
            String name
    ) {
        String value = servletRequest.getHeader(name);
        if (value != null && !value.isBlank()) {
            builder.header(name, value);
        }
    }

    private InputStream inputStream(MultipartFile file) {
        try {
            return file.getInputStream();
        } catch (IOException ex) {
            throw new IllegalStateException("CT 文件读取失败", ex);
        }
    }

    private String sanitizeFilename(String value) {
        return sanitizeFilename(value, "ct.nii.gz");
    }

    private String sanitizeFilename(String value, String fallback) {
        String filename = value == null || value.isBlank() ? fallback : value;
        return filename.replaceAll("[^A-Za-z0-9._-]", "_");
    }

    private String requirePathSegment(String value, String message) {
        String segment = value == null ? "" : value.trim();
        if (!segment.matches("[A-Za-z0-9_-]{1,120}")) {
            throw new IllegalArgumentException(message);
        }
        return segment;
    }
}
