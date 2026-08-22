package com.ppgl.analyze.report;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ReportChatClient {

    private final ObjectMapper objectMapper;
    private final String chatUrl;

    public ReportChatClient(
            ObjectMapper objectMapper,
            @Value("${ppgl.llm.chat-url:http://127.0.0.1:8000/api/llm/chat/stream}") String chatUrl
    ) {
        this.objectMapper = objectMapper;
        this.chatUrl = chatUrl;
    }

    public String stream(JsonNode requestBody, OutputStream output) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) URI.create(chatUrl).toURL().openConnection();
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(0);
        connection.setRequestProperty("Content-Type", "application/json");
        connection.setRequestProperty("Accept", "application/x-ndjson");

        try (OutputStream request = connection.getOutputStream()) {
            request.write(objectMapper.writeValueAsBytes(requestBody));
        }

        int status = connection.getResponseCode();
        InputStream stream = status >= 200 && status < 300 ? connection.getInputStream() : connection.getErrorStream();
        if (stream == null) {
            throw new IOException("Jetson 聊天接口无响应");
        }
        try (InputStream input = stream) {
            if (status < 200 || status >= 300) {
                String body = new String(input.readAllBytes(), StandardCharsets.UTF_8);
                throw new IOException(status + " " + connection.getResponseMessage() + ": " + body);
            }
            return streamLines(input, output);
        }
    }

    private String streamLines(InputStream input, OutputStream output) throws IOException {
        StringBuilder answer = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                output.write((line + "\n").getBytes(StandardCharsets.UTF_8));
                output.flush();
                JsonNode node = objectMapper.readTree(line);
                String type = node.path("type").asText("");
                if ("delta".equals(type)) {
                    answer.append(node.path("text").asText(""));
                } else if ("done".equals(type)) {
                    String finalAnswer = node.path("answer").asText("");
                    return finalAnswer.isBlank() ? answer.toString() : finalAnswer;
                } else if ("error".equals(type)) {
                    throw new IOException(node.path("detail").asText("AI 对话失败"));
                }
            }
        }
        return answer.toString();
    }
}
