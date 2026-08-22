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
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PpglPipelineClient {

    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final long POLL_INTERVAL_MS = 3000L;
    private static final int TRANSIENT_ERROR_ATTEMPTS = 5;
    private static final int HOST_TIMEOUT_MS = 1200;
    private static final int PORT_TIMEOUT_MS = 1500;
    private static final int INTERFACE_TIMEOUT_MS = 3000;

    private final ObjectMapper objectMapper;
    private final String baseUrl;
    private final Duration timeout;

    public PpglPipelineClient(
            ObjectMapper objectMapper,
            @Value("${ppgl.pipeline.base-url}") String baseUrl,
            @Value("${ppgl.pipeline.timeout-minutes:30}") long timeoutMinutes
    ) {
        this.objectMapper = objectMapper;
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.timeout = Duration.ofMinutes(Math.max(1, timeoutMinutes));
    }

    public ComputeNodeStatusResponse status() {
        long started = System.nanoTime();
        URI uri = URI.create(baseUrl);
        String host = uri.getHost();
        int port = resolvePort(uri);
        boolean hostReachable = false;
        boolean serviceReachable = false;
        boolean interfaceReachable = false;
        String hostAddress = "";
        String errorMessage = "";
        String interfaceStatus = "";

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
            InterfaceProbeResult probe = probeInterface();
            interfaceReachable = probe.reachable();
            interfaceStatus = probe.status();
            if (!probe.message().isBlank()) {
                errorMessage = probe.message();
            }
        }

        long latencyMs = Math.max(1L, (System.nanoTime() - started) / 1_000_000L);
        boolean available = interfaceReachable;
        String status = available ? "online" : serviceReachable ? "port-only" : hostReachable ? "host-only" : "offline";
        String message = available
                ? "分析服务接口可用"
                : serviceReachable
                        ? "端口可连接，但分析接口未通过"
                        : hostReachable
                                ? "主机可达，但分析服务端口不可连接"
                                : "分析节点不可达" + (errorMessage == null || errorMessage.isBlank() ? "" : "：" + errorMessage);

        return new ComputeNodeStatusResponse(
                status,
                available,
                hostReachable,
                serviceReachable,
                interfaceReachable,
                baseUrl,
                host == null ? "" : host,
                hostAddress,
                port,
                latencyMs,
                interfaceStatus,
                message,
                LocalDateTime.now().format(DATE_TIME_FORMATTER)
        );
    }

    public void run(Path ctNifti, Path outputDir, String mode, String device) {
        try {
            Files.createDirectories(outputDir);
            String caseId = upload(ctNifti);
            Files.writeString(outputDir.resolve("case_id.txt"), caseId);
            postWithTransientRetry("/api/cases/" + caseId + "/segment?mode=" + mode + "&device=" + device
                    + "&force=true&totalseg_fast=false&totalseg_fastest=false");
            waitUntilDone(caseId);
            downloadJson("/api/cases/" + caseId + "/result", outputDir.resolve("result.json"));
            downloadOptionalJson("/api/cases/" + caseId + "/metrics", outputDir.resolve("clinical_metrics.json"));
            downloadOptionalJson("/api/cases/" + caseId + "/risk", outputDir.resolve("risk.json"));
            downloadOptionalJson("/api/cases/" + caseId + "/label-map", outputDir.resolve("label_map.json"));
            downloadOptionalText("/api/cases/" + caseId + "/report", outputDir.resolve("report.md"));
            downloadOptionalFile("/api/cases/" + caseId + "/overlay", outputDir.resolve("overlay.png"));
            downloadOptionalFile("/api/cases/" + caseId + "/mask", outputDir.resolve("mask.nii.gz"));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new AnalysisException("PPGL 完整分析服务调用被中断：" + ex.getMessage(), ex);
        } catch (IOException ex) {
            throw new AnalysisException("PPGL 完整分析服务调用失败：" + ex.getMessage(), ex);
        }
    }

    public void runWithExistingTotalseg(String caseId, Path ctNifti, Path totalsegZip, Path outputDir, String mode, String device) {
        try {
            Files.createDirectories(outputDir);
            String safeCaseId = caseId.replaceAll("[^A-Za-z0-9_-]", "_");
            Files.writeString(outputDir.resolve("case_id.txt"), safeCaseId);
            uploadExistingTotalseg(safeCaseId, ctNifti, totalsegZip, mode, device);
            waitUntilDone(safeCaseId);
            downloadJson("/api/cases/" + safeCaseId + "/result", outputDir.resolve("result.json"));
            downloadOptionalJson("/api/cases/" + safeCaseId + "/metrics", outputDir.resolve("clinical_metrics.json"));
            downloadOptionalJson("/api/cases/" + safeCaseId + "/risk", outputDir.resolve("risk.json"));
            downloadOptionalJson("/api/cases/" + safeCaseId + "/label-map", outputDir.resolve("label_map.json"));
            downloadOptionalText("/api/cases/" + safeCaseId + "/report", outputDir.resolve("report.md"));
            downloadOptionalFile("/api/cases/" + safeCaseId + "/overlay", outputDir.resolve("overlay.png"));
            downloadOptionalFile("/api/cases/" + safeCaseId + "/mask", outputDir.resolve("mask.nii.gz"));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new AnalysisException("PPGL 完整分析服务调用被中断：" + ex.getMessage(), ex);
        } catch (IOException ex) {
            throw new AnalysisException("PPGL 完整分析服务调用失败：" + ex.getMessage(), ex);
        }
    }

    private String upload(Path ctNifti) throws IOException {
        String boundary = "----PPGLAnalyze" + UUID.randomUUID();
        HttpURLConnection connection = open("/api/cases/upload");
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);

        try (OutputStream output = connection.getOutputStream()) {
            output.write(("\r\n--" + boundary + "\r\n"
                    + "Content-Disposition: form-data; name=\"file\"; filename=\"" + ctNifti.getFileName() + "\"\r\n"
                    + "Content-Type: application/gzip\r\n\r\n").getBytes(StandardCharsets.UTF_8));
            Files.copy(ctNifti, output);
            output.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        }

        JsonNode node = readJsonResponse(connection);
        String caseId = node.path("case_id").asText("");
        if (caseId.isBlank()) {
            throw new IOException("上传响应缺少 case_id：" + node);
        }
        return caseId;
    }

    private void uploadExistingTotalseg(String caseId, Path ctNifti, Path totalsegZip, String mode, String device) throws IOException {
        if (!Files.isRegularFile(ctNifti)) {
            throw new IOException("原始 CT 不存在：" + ctNifti);
        }
        if (!Files.isRegularFile(totalsegZip)) {
            throw new IOException("TotalSegmentator mask zip 不存在：" + totalsegZip);
        }
        String boundary = "----PPGLAnalyze" + UUID.randomUUID();
        HttpURLConnection connection = open("/api/cases/" + caseId + "/run-with-existing-totalseg");
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);

        try (OutputStream output = connection.getOutputStream()) {
            writeFilePart(output, boundary, "file", "ct.nii.gz", "application/gzip", ctNifti);
            writeFilePart(output, boundary, "totalseg_zip", "totalseg_existing.zip", "application/zip", totalsegZip);
            writeTextPart(output, boundary, "mode", mode == null || mode.isBlank() ? "abdomen" : mode);
            writeTextPart(output, boundary, "device", device == null || device.isBlank() ? "cuda" : device);
            output.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        }

        readJsonResponse(connection);
    }

    private void writeFilePart(OutputStream output, String boundary, String name, String filename, String contentType, Path file)
            throws IOException {
        output.write(("\r\n--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + name + "\"; filename=\"" + filename + "\"\r\n"
                + "Content-Type: " + contentType + "\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        Files.copy(file, output);
    }

    private void writeTextPart(OutputStream output, String boundary, String name, String value) throws IOException {
        output.write(("\r\n--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n"
                + value).getBytes(StandardCharsets.UTF_8));
    }

    private void waitUntilDone(String caseId) throws IOException, InterruptedException {
        Instant deadline = Instant.now().plus(timeout);
        int consecutiveErrors = 0;
        while (!Thread.currentThread().isInterrupted()) {
            if (Instant.now().isAfter(deadline)) {
                throw new IOException("PPGL pipeline 超过 " + timeout.toMinutes() + " 分钟未完成");
            }
            JsonNode status;
            try {
                status = getJson("/api/cases/" + caseId + "/status");
                consecutiveErrors = 0;
            } catch (IOException ex) {
                if (!isTransientFailure(ex)) {
                    throw ex;
                }
                consecutiveErrors++;
                if (consecutiveErrors >= TRANSIENT_ERROR_ATTEMPTS) {
                    throw new IOException("PPGL pipeline 状态查询连续失败：" + ex.getMessage(), ex);
                }
                Thread.sleep(POLL_INTERVAL_MS);
                continue;
            }
            String value = status.path("status").asText("");
            if ("completed".equals(value)) {
                return;
            }
            if ("failed".equals(value)) {
                throw new IOException(status.path("message").asText("PPGL pipeline 失败"));
            }
            Thread.sleep(POLL_INTERVAL_MS);
        }
    }

    private void postWithTransientRetry(String path) throws IOException, InterruptedException {
        for (int attempt = 1; attempt <= TRANSIENT_ERROR_ATTEMPTS; attempt++) {
            try {
                post(path);
                return;
            } catch (IOException ex) {
                if (!isTransientFailure(ex) || attempt >= TRANSIENT_ERROR_ATTEMPTS) {
                    throw new IOException("PPGL pipeline 启动请求失败：" + ex.getMessage(), ex);
                }
                Thread.sleep(POLL_INTERVAL_MS);
            }
        }
    }

    private void post(String path) throws IOException {
        HttpURLConnection connection = open(path);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.getOutputStream().close();
        readJsonResponse(connection);
    }

    private JsonNode getJson(String path) throws IOException {
        HttpURLConnection connection = open(path);
        connection.setRequestMethod("GET");
        return readJsonResponse(connection);
    }

    private void downloadJson(String path, Path target) throws IOException {
        JsonNode node = getJson(path);
        Files.writeString(target, objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(node));
    }

    private void downloadOptionalJson(String path, Path target) throws IOException {
        try {
            downloadJson(path, target);
        } catch (IOException ignored) {
            // Optional pipeline artifact.
        }
    }

    private void downloadOptionalText(String path, Path target) throws IOException {
        try {
            HttpURLConnection connection = open(path);
            connection.setRequestMethod("GET");
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) {
                return;
            }
            try (InputStream input = connection.getInputStream()) {
                Files.writeString(target, new String(input.readAllBytes(), StandardCharsets.UTF_8));
            }
        } catch (IOException ignored) {
            // Optional pipeline artifact.
        }
    }

    private void downloadOptionalFile(String path, Path target) throws IOException {
        try {
            HttpURLConnection connection = open(path);
            connection.setRequestMethod("GET");
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) {
                return;
            }
            try (InputStream input = connection.getInputStream()) {
                Files.copy(input, target, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException ignored) {
            // Optional pipeline artifact.
        }
    }

    private JsonNode readJsonResponse(HttpURLConnection connection) throws IOException {
        int status = connection.getResponseCode();
        String body = readResponseBody(connection, status);
        if (status < 200 || status >= 300) {
            throw new HttpResponseException(status, connection.getResponseMessage(), body);
        }
        return objectMapper.readTree(body);
    }

    private boolean isTransientFailure(IOException ex) {
        if (ex instanceof HttpResponseException response) {
            return response.statusCode() == 429 || response.statusCode() >= 500;
        }
        return true;
    }

    private HttpURLConnection open(String path) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) URI.create(baseUrl + path).toURL().openConnection();
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(0);
        return connection;
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

    private int resolvePort(URI uri) {
        if (uri.getPort() > 0) {
            return uri.getPort();
        }
        return "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
    }

    private InterfaceProbeResult probeInterface() {
        try {
            HttpURLConnection connection = (HttpURLConnection) URI.create(baseUrl + "/openapi.json").toURL().openConnection();
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(PORT_TIMEOUT_MS);
            connection.setReadTimeout(INTERFACE_TIMEOUT_MS);

            int statusCode = connection.getResponseCode();
            String body = readResponseBody(connection, statusCode);
            if (statusCode < 200 || statusCode >= 300) {
                return new InterfaceProbeResult(false, "", statusCode + " " + connection.getResponseMessage());
            }

            JsonNode node = objectMapper.readTree(body);
            JsonNode paths = node.path("paths");
            boolean hasUpload = paths.has("/api/cases/upload");
            boolean hasExistingTotalseg = paths.has("/api/cases/{case_id}/run-with-existing-totalseg");
            boolean healthy = hasUpload && hasExistingTotalseg;
            String title = node.path("info").path("title").asText("");
            String message = healthy ? "" : "端口有响应，但未发现完整分析接口";
            return new InterfaceProbeResult(healthy, title.isBlank() ? "OK" : title, message);
        } catch (IOException | IllegalArgumentException ex) {
            return new InterfaceProbeResult(false, "", ex.getMessage());
        }
    }

    private record InterfaceProbeResult(boolean reachable, String status, String message) {
    }

    private static class HttpResponseException extends IOException {

        private final int statusCode;

        private HttpResponseException(int statusCode, String responseMessage, String body) {
            super(statusCode + " " + responseMessage + ": " + body);
            this.statusCode = statusCode;
        }

        private int statusCode() {
            return statusCode;
        }
    }
}
