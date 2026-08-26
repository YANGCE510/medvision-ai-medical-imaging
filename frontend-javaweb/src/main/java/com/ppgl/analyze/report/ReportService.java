package com.ppgl.analyze.report;

import com.ppgl.analyze.ct.CtImage;
import com.ppgl.analyze.ct.CtImageRepository;
import com.ppgl.analyze.auth.UserAccount;
import com.ppgl.analyze.auth.UserRepository;
import com.ppgl.analyze.auth.UserRole;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.io.OutputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private static final Logger log = LoggerFactory.getLogger(ReportService.class);
    private static final DateTimeFormatter REVIEW_TIME_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");

    private final ReportRepository reportRepository;
    private final CtImageRepository ctImageRepository;
    private final ReportChatRepository reportChatRepository;
    private final ReportChatClient reportChatClient;
    private final UserRepository userRepository;
    private final ObjectMapper objectMapper;
    private final int maxChatContentChars;
    private final String pythonBin;
    private final Path pythonWorker;

    public ReportService(
            ReportRepository reportRepository,
            CtImageRepository ctImageRepository,
            ReportChatRepository reportChatRepository,
            ReportChatClient reportChatClient,
            UserRepository userRepository,
            ObjectMapper objectMapper,
            @Value("${ppgl.report.chat.max-content-chars:4000}") int maxChatContentChars,
            @Value("${ppgl.analysis.python-bin:python3}") String pythonBin,
            @Value("${ppgl.analysis.python-worker:python-worker/worker.py}") String pythonWorker
    ) {
        this.reportRepository = reportRepository;
        this.ctImageRepository = ctImageRepository;
        this.reportChatRepository = reportChatRepository;
        this.reportChatClient = reportChatClient;
        this.userRepository = userRepository;
        this.objectMapper = objectMapper;
        this.maxChatContentChars = Math.max(500, maxChatContentChars);
        this.pythonBin = pythonBin;
        this.pythonWorker = Path.of(pythonWorker).toAbsolutePath().normalize();
    }

    public List<ReportListItemResponse> list(Long doctorId) {
        requireDoctorId(doctorId);
        return reportRepository.findByDoctorId(doctorId).stream()
                .map(this::listItem)
                .toList();
    }

    private ReportListItemResponse listItem(AnalysisResultRecord record) {
        return ReportListItemResponse.from(
                record,
                reportListTumorVolume(record),
                reportListRiskLevel(record)
        );
    }

    public ReportDetailResponse detail(Long taskId, Long doctorId) {
        requireDoctorId(doctorId);
        AnalysisResultRecord record = reportRepository.findByTaskIdAndDoctorId(taskId, doctorId)
                .orElseThrow(() -> new ReportException("报告不存在"));
        return detailResponse(record, doctorId);
    }

    private ReportDetailResponse detailResponse(AnalysisResultRecord record, Long doctorId) {
        Long taskId = record.taskId();
        String segmentationUrl = "/api/reports/" + taskId + "/segmentation";
        String meshUrl = "/api/reports/" + taskId + "/mesh";
        String meshManifestUrl = "/api/reports/" + taskId + "/mesh-manifest";
        Path segmentationPath = segmentationPath(record);
        Path meshPath = meshPath(record);
        return new ReportDetailResponse(
                record.taskId(),
                record.ctImageId(),
                record.patientName(),
                record.patientIdCard(),
                record.originalFilename(),
                record.tumorVolumeMl() == null ? "-" : record.tumorVolumeMl().toPlainString(),
                blankToDash(record.riskLevel()),
                record.patientVisible(),
                reviewStatus(record),
                reviewStatusLabel(record),
                blankToEmpty(record.doctorReviewNote()),
                formatReviewTime(record),
                blankToDash(record.summaryJson()),
                readText(record.resultJsonPath()),
                readText(record.metricsJsonPath()),
                readText(record.riskJsonPath()),
                readText(record.labelMapJsonPath()),
                readText(record.reportMdPath()),
                Files.isRegularFile(imagePath(record)),
                "/api/reports/" + taskId + "/image",
                false,
                "",
                Files.isRegularFile(segmentationPath),
                segmentationUrl,
                Files.isRegularFile(segmentationPath) || Files.isRegularFile(meshPath),
                meshUrl,
                meshManifestUrl
        );
    }

    public ReportDetailResponse reviewForPatient(Long taskId, Long doctorId, ReportReviewRequest request) {
        requireDoctorId(doctorId);
        boolean patientVisible = request != null && Boolean.TRUE.equals(request.patientVisible());
        String note = normalizeDoctorReviewNote(request == null ? null : request.doctorReviewNote());
        reportRepository.updatePatientReview(taskId, doctorId, patientVisible, note);
        AnalysisResultRecord record = reportRepository.findByTaskIdAndDoctorId(taskId, doctorId)
                .orElseThrow(() -> new ReportException("报告不存在"));
        return detailResponse(record, doctorId);
    }

    public List<ReportListItemResponse> patientList(Long patientUserId) {
        UserAccount user = patientUser(patientUserId);
        return reportRepository.findPublishedByPatientIdCard(user.patientIdCard()).stream()
                .map(this::listItem)
                .toList();
    }

    public ReportDetailResponse patientDetail(Long taskId, Long patientUserId) {
        AnalysisResultRecord record = patientRecord(taskId, patientUserId);
        return patientDetailResponse(record);
    }

    private ReportDetailResponse patientDetailResponse(AnalysisResultRecord record) {
        return new ReportDetailResponse(
                record.taskId(),
                record.ctImageId(),
                record.patientName(),
                record.patientIdCard(),
                record.originalFilename(),
                reportListTumorVolume(record),
                reportListRiskLevel(record),
                record.patientVisible(),
                reviewStatus(record),
                reviewStatusLabel(record),
                blankToEmpty(record.doctorReviewNote()),
                formatReviewTime(record),
                blankToDash(record.summaryJson()),
                "",
                readText(record.metricsJsonPath()),
                readText(record.riskJsonPath()),
                "",
                readText(record.reportMdPath()),
                false,
                "",
                false,
                "",
                false,
                "",
                false,
                "",
                ""
        );
    }

    public Resource overlay(Long taskId, Long doctorId) {
        requireDoctorId(doctorId);
        AnalysisResultRecord record = reportRepository.findByTaskIdAndDoctorId(taskId, doctorId)
                .orElseThrow(() -> new ReportException("报告不存在"));
        if (!isFile(record.overlayPath())) {
            throw new ReportException("预览图不存在");
        }
        return new FileSystemResource(Path.of(record.overlayPath()));
    }

    public Resource image(Long taskId, Long doctorId) {
        AnalysisResultRecord record = record(taskId, doctorId);
        Path path = imagePath(record);
        if (!Files.isRegularFile(path)) {
            throw new ReportException("原始 CT 图像不存在");
        }
        return new FileSystemResource(path);
    }

    public Resource segmentation(Long taskId, Long doctorId) {
        requireDoctorId(doctorId);
        AnalysisResultRecord record = reportRepository.findByTaskIdAndDoctorId(taskId, doctorId)
                .orElseThrow(() -> new ReportException("报告不存在"));
        Path path = segmentationPath(record);
        if (!Files.isRegularFile(path)) {
            throw new ReportException("分割结果不存在");
        }
        return new FileSystemResource(path);
    }

    public Resource mesh(Long taskId, Long doctorId) {
        AnalysisResultRecord record = record(taskId, doctorId);
        Path path = ensureMesh(record);
        return new FileSystemResource(path);
    }

    public Resource meshManifest(Long taskId, Long doctorId) {
        AnalysisResultRecord record = record(taskId, doctorId);
        ensureMesh(record);
        Path path = meshManifestPath(record);
        if (!Files.isRegularFile(path)) {
            throw new ReportException("三维模型清单不存在");
        }
        return new FileSystemResource(path);
    }

    public List<ReportChatResponse> chatHistory(Long taskId, Long doctorId) {
        record(taskId, doctorId);
        return reportChatRepository.findByTaskAndDoctor(taskId, doctorId).stream()
                .map(ReportChatResponse::from)
                .toList();
    }

    public List<ReportChatResponse> patientChatHistory(Long taskId, Long patientUserId) {
        patientRecord(taskId, patientUserId);
        return reportChatRepository.findByTaskAndDoctor(taskId, patientUserId).stream()
                .map(ReportChatResponse::from)
                .toList();
    }

    public PatientConcernSummaryResponse patientConcernSummary(Long taskId, Long doctorId) {
        AnalysisResultRecord record = record(taskId, doctorId);
        if (!record.patientVisible()) {
            throw new ReportException("报告尚未发布给患者端，暂无可分析的患者担忧");
        }
        List<String> allQuestions = reportChatRepository
                .findPatientQuestionsByTaskAndPatientIdCard(taskId, record.patientIdCard())
                .stream()
                .map(ReportChatRecord::content)
                .map((content) -> content == null ? "" : content.trim())
                .filter((content) -> !content.isBlank())
                .toList();
        List<String> questions = latestItems(allQuestions, 30);
        String summary;
        if (questions.isEmpty()) {
            summary = "暂无患者向 AI 提问的记录。可以在患者产生问答后，再分析其关注点。";
        } else {
            try {
                summary = reportChatClient.stream(buildPatientConcernSummaryRequest(record, questions), OutputStream.nullOutputStream()).trim();
            } catch (IOException ex) {
                throw new ReportException("患者担忧总结失败：" + ex.getMessage(), ex);
            }
            if (summary.isBlank()) {
                summary = "未能生成有效摘要，请稍后重试。";
            }
        }
        return new PatientConcernSummaryResponse(
                record.taskId(),
                record.patientName(),
                record.patientIdCard(),
                record.originalFilename(),
                reportListRiskLevel(record),
                reportListTumorVolume(record),
                allQuestions.size(),
                latestItems(allQuestions, 8),
                summary,
                LocalDateTime.now().format(REVIEW_TIME_FORMATTER)
        );
    }

    public void streamChat(Long taskId, Long doctorId, ReportChatRequest request, OutputStream output) {
        AnalysisResultRecord record = record(taskId, doctorId);
        String question = request == null || request.question() == null ? "" : request.question().trim();
        if (question.isBlank()) {
            throw new ReportException("请输入要咨询的问题");
        }
        try {
            String directAnswer = directDoctorChatAnswer(question);
            if (directAnswer != null) {
                writeDirectStreamAnswer(directAnswer, output);
                reportChatRepository.append(taskId, doctorId, "user", limitContent(question));
                reportChatRepository.append(taskId, doctorId, "assistant", limitContent(directAnswer));
                return;
            }
            JsonNode chatRequest = buildChatRequest(record, question, request);
            log.info(
                    "Report chat request taskId={}, doctorId={}, questionLength={}, questionPreview={}, historyCount={}, payloadChars={}",
                    taskId,
                    doctorId,
                    question.length(),
                    question.substring(0, Math.min(question.length(), 40)),
                    request == null || request.history() == null ? 0 : request.history().size(),
                    chatRequest.toString().length()
            );
            String answer = reportChatClient.stream(chatRequest, output);
            if (!answer.isBlank()) {
                reportChatRepository.append(taskId, doctorId, "user", limitContent(question));
                reportChatRepository.append(taskId, doctorId, "assistant", limitContent(answer));
            }
        } catch (IOException ex) {
            throw new ReportException("AI 对话请求失败：" + ex.getMessage(), ex);
        }
    }

    private String directDoctorChatAnswer(String question) {
        String clean = question == null ? "" : question.trim();
        String compact = clean.replaceAll("\\s+", "").toLowerCase();
        if (compact.isBlank()) {
            return null;
        }
        if (compact.matches("^(你好|您好|hi|hello|hey|测试|测试回复|ping|在吗|在不在)[。.!！?？]*$")) {
            return "你好，我在。你可以问我当前报告里的影像结论、临床指标、风险因素，也可以问 PPGL 相关基础概念。";
        }
        if (compact.contains("ppgl") && (compact.contains("定义") || compact.contains("是什么") || compact.contains("什么意思"))) {
            return "PPGL 通常指嗜铬细胞瘤和副神经节瘤。嗜铬细胞瘤多起源于肾上腺髓质，副神经节瘤多起源于肾上腺外的副神经节组织。它们都可能分泌儿茶酚胺，临床上常结合影像、实验室检查、病理和遗传评估综合判断。";
        }
        return null;
    }

    private void writeDirectStreamAnswer(String answer, OutputStream output) throws IOException {
        ObjectNode delta = objectMapper.createObjectNode();
        delta.put("type", "delta");
        delta.put("text", answer);
        writeStreamLine(delta, output);

        ObjectNode done = objectMapper.createObjectNode();
        done.put("type", "done");
        done.put("answer", answer);
        writeStreamLine(done, output);
    }

    private void writeStreamLine(JsonNode node, OutputStream output) throws IOException {
        output.write((objectMapper.writeValueAsString(node) + "\n").getBytes(StandardCharsets.UTF_8));
        output.flush();
    }

    public String patientChat(Long taskId, Long patientUserId, ReportChatRequest request) {
        AnalysisResultRecord record = patientRecord(taskId, patientUserId);
        String question = request == null || request.question() == null ? "" : request.question().trim();
        if (question.isBlank()) {
            throw new ReportException("请输入要咨询的问题");
        }
        try {
            JsonNode chatRequest = buildPatientChatRequest(record, question, request);
            String answer = reportChatClient.stream(chatRequest, OutputStream.nullOutputStream());
            if (!answer.isBlank()) {
                reportChatRepository.append(taskId, patientUserId, "user", limitContent(question));
                reportChatRepository.append(taskId, patientUserId, "assistant", limitContent(answer));
            }
            return answer;
        } catch (IOException ex) {
            throw new ReportException("AI 对话请求失败：" + ex.getMessage(), ex);
        }
    }

    private JsonNode buildPatientChatRequest(AnalysisResultRecord record, String question, ReportChatRequest request) {
        ObjectNode root = objectMapper.createObjectNode();
        ObjectNode context = objectMapper.createObjectNode();
        context.put("audience", "patient");
        context.put("answer_style", "用普通病人能理解的中文回答，像解释体检报告里的一个指标。直接回答问题，不要复述整份报告，不要输出表格，不要堆专业字段名，不要替代医生诊断。");
        context.put("doctor_review_note", blankToEmpty(record.doctorReviewNote()));

        ArrayNode rules = objectMapper.createArrayNode();
        rules.add("根据问题给出中等长度回答，通常 200 到 500 字；复杂指标解释可适当更完整，但不要超过请求的 max_tokens。");
        rules.add("优先用 3 到 6 个清楚要点回答，每个要点先给结论，再用一两句话解释原因。");
        rules.add("优先解释患者问到的概念或指标含义。");
        rules.add("患者问注意事项时，只给通用复诊准备和生活观察建议。");
        rules.add("不要制造恐慌；必要时提醒以医生面诊意见为准。");
        context.set("rules", rules);

        context.set("patient_summary", patientSummaryContext(record));
        root.put("question", question);
        root.set("context", context);
        root.set("history", patientHistoryContext(request));
        root.put("max_tokens", normalizePatientMaxTokens(request == null ? null : request.maxTokens()));
        return root;
    }

    private JsonNode buildPatientConcernSummaryRequest(AnalysisResultRecord record, List<String> questions) {
        ObjectNode root = objectMapper.createObjectNode();
        ObjectNode context = objectMapper.createObjectNode();
        context.put("audience", "doctor");
        context.put("task", "patient_concern_summary");
        context.put("patient_name", record.patientName());
        context.put("original_filename", record.originalFilename());
        context.put("risk_level", reportListRiskLevel(record));
        context.put("tumor_volume_ml", reportListTumorVolume(record));
        ArrayNode questionArray = objectMapper.createArrayNode();
        for (String question : questions) {
            questionArray.add(question);
        }
        context.set("patient_questions", questionArray);
        root.set("context", context);
        root.put("question", """
                请根据 context.patient_questions 中患者向 AI 提出的问题，为医生生成一份很简短的“患者担忧摘要”。
                硬性要求：
                1. 总字数控制在 500 到 1200 个中文字符左右。
                2. 只写纯文本，不要 Markdown，不要 #、-、*、**、表格或长列表。
                3. 最多三句话或三行，每行都直接说重点。
                4. 只总结患者表达出的关注点和困惑，不做心理诊断，不给治疗决策。
                5. 内容结构：主要担忧；医生沟通重点；仍需澄清的问题。
                """);
        root.put("max_tokens", 800);
        return root;
    }

    private ObjectNode patientSummaryContext(AnalysisResultRecord record) {
        ObjectNode metrics = parseJsonObject(readText(record.metricsJsonPath()));
        ObjectNode risk = parseJsonObject(readText(record.riskJsonPath()));
        ObjectNode tumorBurden = metrics.path("tumor_burden").isObject()
                ? (ObjectNode) metrics.path("tumor_burden")
                : objectMapper.createObjectNode();

        ObjectNode summary = objectMapper.createObjectNode();
        summary.put("risk_level", reportListRiskLevel(record));
        summary.put("tumor_volume_ml", reportListTumorVolume(record));
        putText(summary, "suspected_location", metrics.path("origin_assessment").path("suspected_origin"));
        putText(summary, "tumor_side", metrics.path("tumor_side_by_nearest_kidney"));
        putText(summary, "max_diameter_mm", tumorBurden.path("max_diameter_mm"));
        putText(summary, "risk_note", risk.path("overall_level"));
        return summary;
    }

    private void putText(ObjectNode target, String fieldName, JsonNode value) {
        if (value == null || value.isMissingNode() || value.isNull()) {
            return;
        }
        String text = value.isValueNode() ? value.asText("").trim() : value.toString();
        if (!text.isBlank()) {
            target.put(fieldName, text);
        }
    }

    private JsonNode buildChatRequest(AnalysisResultRecord record, String question, ReportChatRequest request) {
        return buildChatRequest(record, question, request, false);
    }

    private JsonNode buildChatRequest(AnalysisResultRecord record, String question, ReportChatRequest request, boolean patientAudience) {
        ObjectNode root = objectMapper.createObjectNode();
        ObjectNode context = objectMapper.createObjectNode();
        boolean includeReportContext = patientAudience || Boolean.TRUE.equals(request == null ? null : request.includeReportContext());
        if (patientAudience) {
            context.put("audience", "patient");
            context.put("answer_style", "用通俗、克制、安抚但不淡化风险的中文回答；可以解释报告，也可以回答复诊准备、常见注意事项和患者担忧；不要替代医生给出诊断或治疗决策。");
        }
        context.put("report_linked", includeReportContext);
        if (includeReportContext) {
            context.put("report", readText(record.reportMdPath()));
            ObjectNode metrics = parseJsonObject(readText(record.metricsJsonPath()));
            ObjectNode result = parseJsonObject(readText(record.resultJsonPath()));
            context.set("metrics", metricsContext(metrics));
            context.set("risk", riskContext(record));
            context.set("result", resultContext(record, metrics, result));
        } else {
            context.put("answer_style", "直接回答医生的问题。不要引用当前病例、影像指标、风险等级或报告内容；如果问题需要当前报告数据，请提醒医生先打开“关联报告”。");
            root.put("system_text", "你是一个通用中文助手。直接回答用户当前问题；不要主动引用病例、影像报告、临床指标或风险等级。");
        }
        root.put("question", question);
        root.set("context", context);
        root.set("history", historyContext(request));
        root.put("max_tokens", normalizeMaxTokens(request == null ? null : request.maxTokens()));
        return root;
    }

    private ObjectNode metricsContext(ObjectNode metrics) {
        ObjectNode summary = objectMapper.createObjectNode();
        copy(summary, "tumor_volume_ml", metrics, "apr_tumor_volume_ml");
        copy(summary, "tumor_component_count", metrics, "tumor_component_count");
        copy(summary, "tumor_side_by_nearest_kidney", metrics, "tumor_side_by_nearest_kidney");
        copy(summary, "origin_assessment", metrics, "origin_assessment");
        copy(summary, "anchor_distances_mm", metrics, "anchor_distances_mm");
        copy(summary, "nearest_anatomic_structures", metrics, "nearest_anatomic_structures");
        JsonNode tumorBurden = metrics.path("tumor_burden");
        if (tumorBurden.isObject()) {
            copy(summary, "max_diameter_mm", tumorBurden, "max_diameter_mm");
            copy(summary, "equivalent_sphere_diameter_mm", tumorBurden, "equivalent_sphere_diameter_mm");
            copy(summary, "multifocal_after_apr", tumorBurden, "multifocal_after_apr");
        }
        return summary;
    }

    private ObjectNode riskContext(AnalysisResultRecord record) {
        ObjectNode risk = parseJsonObject(readText(record.riskJsonPath()));
        ObjectNode summary = objectMapper.createObjectNode();
        if (risk.hasNonNull("overall_level")) {
            summary.set("level", risk.get("overall_level"));
        } else {
            summary.put("level", blankToDash(record.riskLevel()));
        }
        copy(summary, "imaging_followup_risk_level", risk, "imaging_followup_risk_level");
        copy(summary, "surgical_complexity_level", risk, "surgical_complexity_level");
        copy(summary, "segmentation_confidence", risk, "segmentation_confidence");
        copy(summary, "reasons", risk, "reasons");
        copy(summary, "risk_factors", risk, "risk_factors");
        copy(summary, "protective_factors", risk, "protective_factors");
        copy(summary, "nearest_structures", risk, "nearest_structures");
        copy(summary, "missing_required_clinical_data", risk, "missing_required_clinical_data");
        copy(summary, "limitations", risk, "limitations");
        return summary;
    }

    private ObjectNode resultContext(AnalysisResultRecord record, ObjectNode metrics, ObjectNode result) {
        ObjectNode summary = objectMapper.createObjectNode();
        if (result.hasNonNull("case_id")) {
            summary.set("case_id", result.get("case_id"));
        } else {
            summary.put("case_id", "task-" + record.taskId());
        }
        summary.put("task_id", record.taskId());
        summary.put("patient_name", record.patientName());
        summary.put("patient_id_card", record.patientIdCard());
        summary.put("original_filename", record.originalFilename());
        summary.put("tumor_volume_ml", record.tumorVolumeMl() == null ? "" : record.tumorVolumeMl().toPlainString());
        copy(summary, "summary", result, "summary");
        copy(summary, "tumor_burden", result, "tumor_burden");
        copy(summary, "origin_assessment", result, "origin_assessment");
        copy(summary, "nearest_anatomic_structures", result, "nearest_anatomic_structures");
        if (!summary.has("tumor_burden")) {
            copy(summary, "tumor_burden", metrics, "tumor_burden");
        }
        if (!summary.has("origin_assessment")) {
            copy(summary, "origin_assessment", metrics, "origin_assessment");
        }
        if (!summary.has("nearest_anatomic_structures")) {
            copy(summary, "nearest_anatomic_structures", metrics, "nearest_anatomic_structures");
        }
        return summary;
    }

    private void copy(ObjectNode target, String targetName, JsonNode source, String sourceName) {
        JsonNode value = source == null ? null : source.get(sourceName);
        if (value != null && !value.isNull()) {
            target.set(targetName, value);
        }
    }

    private ArrayNode historyContext(ReportChatRequest request) {
        ArrayNode history = objectMapper.createArrayNode();
        List<ReportChatMessage> messages = request == null || request.history() == null
                ? Collections.emptyList()
                : request.history();
        int start = Math.max(0, messages.size() - 10);
        for (ReportChatMessage message : messages.subList(start, messages.size())) {
            if (message == null || message.role() == null || message.content() == null || message.content().isBlank()) {
                continue;
            }
            String role = "assistant".equals(message.role()) ? "assistant" : "user";
            ObjectNode item = objectMapper.createObjectNode();
            item.put("role", role);
            item.put("content", message.content());
            history.add(item);
        }
        return history;
    }

    private ArrayNode patientHistoryContext(ReportChatRequest request) {
        ArrayNode history = objectMapper.createArrayNode();
        List<ReportChatMessage> messages = request == null || request.history() == null
                ? Collections.emptyList()
                : request.history();
        int start = Math.max(0, messages.size() - 2);
        for (ReportChatMessage message : messages.subList(start, messages.size())) {
            if (message == null || message.role() == null || message.content() == null || message.content().isBlank()) {
                continue;
            }
            String role = "assistant".equals(message.role()) ? "assistant" : "user";
            ObjectNode item = objectMapper.createObjectNode();
            item.put("role", role);
            item.put("content", limitPatientHistory(message.content()));
            history.add(item);
        }
        return history;
    }

    private String limitPatientHistory(String content) {
        String value = content == null ? "" : content.trim();
        return value.length() > 160 ? value.substring(0, 160) : value;
    }

    private List<String> latestItems(List<String> items, int maxItems) {
        if (items == null || items.isEmpty()) {
            return List.of();
        }
        int start = Math.max(0, items.size() - maxItems);
        return new ArrayList<>(items.subList(start, items.size()));
    }

    private ObjectNode parseJsonObject(String value) {
        if (value == null || value.isBlank()) {
            return objectMapper.createObjectNode();
        }
        try {
            JsonNode node = objectMapper.readTree(value);
            return node != null && node.isObject() ? (ObjectNode) node : objectMapper.createObjectNode();
        } catch (IOException ex) {
            return objectMapper.createObjectNode();
        }
    }

    private String reportListTumorVolume(AnalysisResultRecord record) {
        if (record.tumorVolumeMl() != null) {
            return record.tumorVolumeMl().stripTrailingZeros().toPlainString();
        }
        ObjectNode metrics = parseJsonObject(readText(record.metricsJsonPath()));
        ObjectNode summary = parseJsonObject(record.summaryJson());
        ObjectNode result = parseJsonObject(readText(record.resultJsonPath()));
        JsonNode value = firstJsonValue(
                metrics.path("apr_tumor_volume_ml"),
                metrics.path("tumor_burden").path("apr_tumor_volume_ml"),
                metrics.path("tumor_burden").path("raw_tumor_volume_ml"),
                summary.path("clinical_metrics").path("apr_tumor_volume_ml"),
                summary.path("clinical_metrics").path("tumor_burden").path("apr_tumor_volume_ml"),
                summary.path("tumor_burden").path("apr_tumor_volume_ml"),
                summary.path("tumorVolumeMl"),
                summary.path("tumor_volume_ml"),
                result.path("clinical_metrics").path("apr_tumor_volume_ml"),
                result.path("clinical_metrics").path("tumor_burden").path("apr_tumor_volume_ml"),
                result.path("tumor_burden").path("apr_tumor_volume_ml"),
                result.path("tumorVolumeMl"),
                result.path("tumor_volume_ml")
        );
        return formatDecimalValue(value);
    }

    private String reportListRiskLevel(AnalysisResultRecord record) {
        if (record.riskLevel() != null && !record.riskLevel().isBlank()) {
            return formatRiskLevel(record.riskLevel());
        }
        ObjectNode risk = parseJsonObject(readText(record.riskJsonPath()));
        ObjectNode summary = parseJsonObject(record.summaryJson());
        ObjectNode result = parseJsonObject(readText(record.resultJsonPath()));
        JsonNode value = firstJsonValue(
                risk.path("overall_level"),
                risk.path("imaging_followup_risk_level"),
                summary.path("risk_assessment").path("overall_level"),
                summary.path("risk_assessment").path("imaging_followup_risk_level"),
                result.path("risk_assessment").path("overall_level"),
                result.path("risk_assessment").path("imaging_followup_risk_level")
        );
        return formatRiskLevel(jsonText(value));
    }

    private JsonNode firstJsonValue(JsonNode... values) {
        for (JsonNode value : values) {
            if (value != null && !value.isMissingNode() && !value.isNull() && !value.asText("").isBlank()) {
                return value;
            }
        }
        return null;
    }

    private String jsonText(JsonNode value) {
        return value == null ? "" : value.asText("").trim();
    }

    private String formatDecimalValue(JsonNode value) {
        String text = jsonText(value);
        if (text.isBlank()) {
            return "-";
        }
        try {
            return new BigDecimal(text).stripTrailingZeros().toPlainString();
        } catch (NumberFormatException ex) {
            return text;
        }
    }

    private String formatRiskLevel(String value) {
        if (value == null || value.isBlank()) {
            return "-";
        }
        return switch (value.trim().toLowerCase()) {
            case "low" -> "低风险";
            case "intermediate", "moderate", "medium" -> "中风险";
            case "high" -> "高风险";
            default -> value.trim();
        };
    }

    private int normalizeMaxTokens(Integer maxTokens) {
        if (maxTokens == null) {
            return 800;
        }
        return Math.max(128, Math.min(maxTokens, 1200));
    }

    private int normalizePatientMaxTokens(Integer maxTokens) {
        if (maxTokens == null) {
            return 800;
        }
        return Math.max(80, Math.min(maxTokens, 800));
    }

    private String limitContent(String content) {
        if (content == null) {
            return "";
        }
        return content.length() > maxChatContentChars ? content.substring(0, maxChatContentChars) : content;
    }

    private void requireDoctorId(Long doctorId) {
        if (doctorId == null) {
            throw new ReportException("医生账号不能为空");
        }
    }

    private String readText(String path) {
        if (path == null || path.isBlank()) {
            return "";
        }
        Path file = Path.of(path);
        if (!Files.isRegularFile(file)) {
            return "";
        }
        try {
            return Files.readString(file);
        } catch (IOException ex) {
            throw new ReportException("读取报告文件失败", ex);
        }
    }

    private boolean isFile(String path) {
        return path != null && !path.isBlank() && Files.isRegularFile(Path.of(path));
    }

    private AnalysisResultRecord record(Long taskId, Long doctorId) {
        requireDoctorId(doctorId);
        return reportRepository.findByTaskIdAndDoctorId(taskId, doctorId)
                .orElseThrow(() -> new ReportException("报告不存在"));
    }

    private AnalysisResultRecord patientRecord(Long taskId, Long patientUserId) {
        UserAccount user = patientUser(patientUserId);
        return reportRepository.findPublishedByTaskIdAndPatientIdCard(taskId, user.patientIdCard())
                .orElseThrow(() -> new ReportException("报告不存在或无权查看"));
    }

    private String normalizeDoctorReviewNote(String value) {
        String normalized = value == null ? "" : value.trim();
        if (normalized.length() > 1000) {
            throw new ReportException("医生备注不能超过 1000 字");
        }
        return normalized;
    }

    private String reviewStatus(AnalysisResultRecord record) {
        return record.patientVisible() ? "PUBLISHED" : "PENDING";
    }

    private String reviewStatusLabel(AnalysisResultRecord record) {
        return record.patientVisible() ? "已发布给患者" : "待医生审核";
    }

    private String formatReviewTime(AnalysisResultRecord record) {
        return record.doctorReviewedAt() == null ? "" : record.doctorReviewedAt().format(REVIEW_TIME_FORMATTER);
    }

    private String blankToEmpty(String value) {
        return value == null ? "" : value;
    }

    private UserAccount patientUser(Long patientUserId) {
        if (patientUserId == null) {
            throw new ReportException("病人账号不能为空");
        }
        UserAccount user = userRepository.findById(patientUserId)
                .orElseThrow(() -> new ReportException("病人账号不存在"));
        if (!UserRole.PATIENT.name().equals(user.role())) {
            throw new ReportException("只有病人账号可以查看病人端报告");
        }
        if (!user.enabled()) {
            throw new ReportException("账号不可用");
        }
        if (user.patientIdCard() == null || user.patientIdCard().isBlank()) {
            throw new ReportException("病人账号未绑定身份证号");
        }
        return user;
    }

    private Path segmentationPath(AnalysisResultRecord record) {
        return taskDir(record).resolve("final").resolve("segmentation.nii.gz");
    }

    private Path imagePath(AnalysisResultRecord record) {
        return ctImageRepository.findByDoctorIdAndId(record.doctorId(), record.ctImageId())
                .map(CtImage::filePath)
                .filter(path -> !path.isBlank())
                .map(Path::of)
                .orElse(Path.of("__missing__"));
    }

    private Path meshPath(AnalysisResultRecord record) {
        return taskDir(record).resolve("final").resolve("meshes").resolve("scene.glb");
    }

    private Path meshManifestPath(AnalysisResultRecord record) {
        return taskDir(record).resolve("final").resolve("meshes").resolve("mesh_manifest.json");
    }

    private Path taskDir(AnalysisResultRecord record) {
        Path resultPath = Path.of(record.resultJsonPath());
        Path taskDir = resultPath.getParent();
        if (taskDir == null) {
            return Path.of("__missing__");
        }
        if ("ppgl_pipeline".equals(taskDir.getFileName().toString()) && taskDir.getParent() != null) {
            return taskDir.getParent();
        }
        return taskDir;
    }

    private Path ensureMesh(AnalysisResultRecord record) {
        Path path = meshPath(record);
        if (Files.isRegularFile(path)) {
            return path;
        }
        Path segmentation = segmentationPath(record);
        if (!Files.isRegularFile(segmentation)) {
            throw new ReportException("分割结果不存在，无法生成三维模型");
        }
        runMeshWorker(taskDir(record));
        if (!Files.isRegularFile(path)) {
            throw new ReportException("三维模型生成失败");
        }
        return path;
    }

    private void runMeshWorker(Path taskDir) {
        List<String> command = new ArrayList<>();
        command.add(pythonBin);
        command.add(pythonWorker.toString());
        command.add("mesh");
        command.add("--job-id");
        command.add(taskDir.getFileName().toString());
        command.add("--job-dir");
        command.add(taskDir.toString());
        try {
            Process process = new ProcessBuilder(command)
                    .directory(Path.of(".").toAbsolutePath().normalize().toFile())
                    .redirectErrorStream(true)
                    .start();
            String output = new String(process.getInputStream().readAllBytes());
            boolean finished = process.waitFor(Duration.ofMinutes(5).toMillis(), java.util.concurrent.TimeUnit.MILLISECONDS);
            if (!finished) {
                process.destroyForcibly();
                throw new ReportException("三维模型生成超时");
            }
            if (process.exitValue() != 0) {
                throw new ReportException("三维模型生成失败：" + output);
            }
        } catch (IOException ex) {
            throw new ReportException("三维模型生成失败", ex);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new ReportException("三维模型生成被中断", ex);
        }
    }

    private String blankToDash(String value) {
        return value == null || value.isBlank() ? "-" : value;
    }
}
