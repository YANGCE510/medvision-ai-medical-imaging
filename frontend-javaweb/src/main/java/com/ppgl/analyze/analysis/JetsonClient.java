package com.ppgl.analyze.analysis;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class JetsonClient {

    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final int HOST_TIMEOUT_MS = 1200;
    private static final int PORT_TIMEOUT_MS = 1500;
    private static final int HEALTH_TIMEOUT_MS = 2000;

    private final String baseUrl;
    private final ObjectMapper objectMapper;
    private final String internalApiKey;

    public JetsonClient(
            @Value("${ppgl.jetson.base-url}") String baseUrl,
            ObjectMapper objectMapper,
            @Value("${ppgl.internal.api-key}") String internalApiKey
    ) {
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.objectMapper = objectMapper;
        this.internalApiKey = internalApiKey;
    }

    public ComputeNodeStatusResponse status() {
        long started = System.nanoTime();
        URI uri = URI.create(baseUrl);
        String host = uri.getHost();
        int port = resolvePort(uri);
        boolean hostReachable = false;
        boolean serviceReachable = false;
        boolean healthReachable = false;
        String hostAddress = "";
        String errorMessage = "";
        String healthStatus = "";

        try {
            InetAddress address = InetAddress.getByName(host);
            hostAddress = address.getHostAddress();
            hostReachable = address.isReachable(HOST_TIMEOUT_MS);
            try (Socket socket = new Socket()) {
                socket.connect(new InetSocketAddress(address, port), PORT_TIMEOUT_MS);
                serviceReachable = true;
            } catch (IOException ex) {
                errorMessage = ex.getMessage();
            }
        } catch (IOException | IllegalArgumentException ex) {
            errorMessage = ex.getMessage();
        }

        if (serviceReachable) {
            HealthProbeResult health = probeHealth();
            healthReachable = health.reachable();
            healthStatus = health.status();
            if (!health.message().isBlank()) {
                errorMessage = health.message();
            }
        }

        long latencyMs = Math.max(1L, (System.nanoTime() - started) / 1_000_000L);
        boolean available = healthReachable;
        String status = available ? "online" : serviceReachable ? "port-only" : hostReachable ? "host-only" : "offline";
        String message = available
                ? "Jetson 健康检查通过，推理接口可用"
                : serviceReachable
                        ? "端口可连接，但检查接口未通过，未确认是 Jetson 推理服务"
                        : hostReachable
                                ? "Jetson 主机可达，但推理服务端口不可连接"
                                : "Jetson 主机不可达" + (errorMessage == null || errorMessage.isBlank() ? "" : "：" + errorMessage);

        return new ComputeNodeStatusResponse(
                status,
                available,
                hostReachable,
                serviceReachable,
                healthReachable,
                baseUrl,
                host == null ? "" : host,
                hostAddress,
                port,
                latencyMs,
                healthStatus,
                message,
                LocalDateTime.now().format(DATE_TIME_FORMATTER)
        );
    }

    public void predict(
            String jobId,
            Path requestZip,
            Path outputZip,
            String taskIds,
            String model,
            String trainer,
            String folds,
            boolean tta
    ) {
        try {
            Files.createDirectories(outputZip.getParent());
            uploadPredictRequest(jobId, requestZip, outputZip, taskIds, model, trainer, folds, tta);
        } catch (IOException ex) {
            throw new AnalysisException("Jetson 推理请求失败：" + ex.getMessage(), ex);
        }
    }

    private int resolvePort(URI uri) {
        if (uri.getPort() > 0) {
            return uri.getPort();
        }
        return "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
    }

    private HealthProbeResult probeHealth() {
        try {
            HttpURLConnection connection = (HttpURLConnection) URI.create(baseUrl + "/health").toURL().openConnection();
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(PORT_TIMEOUT_MS);
            connection.setReadTimeout(HEALTH_TIMEOUT_MS);
            connection.setRequestProperty("X-PPGL-Internal-Key", internalApiKey);

            int statusCode = connection.getResponseCode();
            String body = readResponseBody(connection, statusCode);
            if (statusCode < 200 || statusCode >= 300) {
                return new HealthProbeResult(false, "", statusCode + " " + connection.getResponseMessage());
            }

            JsonNode node = objectMapper.readTree(body);
            String status = node.path("status").asText("");
            boolean hasJetsonHealthShape = node.has("status") && node.has("cuda_available");
            boolean cudaAvailable = node.path("cuda_available").asBoolean(false);
            boolean healthy = hasJetsonHealthShape && cudaAvailable && "ok".equalsIgnoreCase(status);
            String message = "";
            if (!hasJetsonHealthShape) {
                message = "端口有响应，但不是预期的 Jetson 健康检查接口";
            } else if (!cudaAvailable) {
                message = "Jetson 健康检查接口可访问，但 CUDA 不可用";
            } else if (!"ok".equalsIgnoreCase(status)) {
                message = "Jetson 健康检查接口可访问，但状态不是 ok：" + status;
            }
            boolean reachable = healthy;
            return new HealthProbeResult(reachable, status, message);
        } catch (IOException | IllegalArgumentException ex) {
            return new HealthProbeResult(false, "", ex.getMessage());
        }
    }

    private record HealthProbeResult(boolean reachable, String status, String message) {
    }

    private void uploadPredictRequest(
            String jobId,
            Path requestZip,
            Path outputZip,
            String taskIds,
            String model,
            String trainer,
            String folds,
            boolean tta
    ) throws IOException {
        String boundary = "----PPGLAnalyze" + UUID.randomUUID();
        HttpURLConnection connection = (HttpURLConnection) URI.create(baseUrl + "/predict").toURL().openConnection();
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(0);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        connection.setRequestProperty("X-PPGL-Internal-Key", internalApiKey);

        try (OutputStream output = connection.getOutputStream()) {
            writeField(output, boundary, "job_id", jobId);
            writeField(output, boundary, "task_ids", taskIds);
            writeField(output, boundary, "model", model);
            writeField(output, boundary, "trainer", trainer);
            writeField(output, boundary, "folds", folds);
            writeField(output, boundary, "tta", Boolean.toString(tta));
            writeFile(output, boundary, "file", requestZip);
            output.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        }

        int status = connection.getResponseCode();
        if (status < 200 || status >= 300) {
            String body = readResponseBody(connection, status);
            throw new IOException(status + " " + connection.getResponseMessage() + ": " + body);
        }

        try (InputStream input = connection.getInputStream()) {
            Files.copy(input, outputZip, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private void writeField(OutputStream output, String boundary, String name, String value) throws IOException {
        output.write(("\r\n--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n"
                + value).getBytes(StandardCharsets.UTF_8));
    }

    private void writeFile(OutputStream output, String boundary, String name, Path file) throws IOException {
        output.write(("\r\n--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + name + "\"; filename=\"" + file.getFileName() + "\"\r\n"
                + "Content-Type: application/zip\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        Files.copy(file, output);
    }

    private String readResponseBody(HttpURLConnection connection, int status) throws IOException {
        InputStream stream = status >= 200 && status < 300 ? connection.getInputStream() : connection.getErrorStream();
        if (stream == null) {
            return "";
        }
        try (InputStream input = stream) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
