package com.ppgl.analyze.care;

import com.ppgl.analyze.auth.UserAccount;
import com.ppgl.analyze.auth.UserRepository;
import com.ppgl.analyze.auth.UserRole;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class CareService {

    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");
    private static final Set<String> PLAN_STATUSES = Set.of("PENDING", "SUBMITTED", "VIEWED", "COMPLETED");
    private static final Set<String> FEEDBACK_STATUSES = Set.of("PENDING", "REPLIED", "CLOSED");

    private final CareRepository careRepository;
    private final UserRepository userRepository;

    public CareService(CareRepository careRepository, UserRepository userRepository) {
        this.careRepository = careRepository;
        this.userRepository = userRepository;
    }

    public List<FollowUpPlanResponse> listFollowUps(Long doctorId) {
        ensureDoctor(doctorId);
        return careRepository.findPlansByDoctor(doctorId).stream()
                .map(this::toPlanResponse)
                .toList();
    }

    public FollowUpPlanResponse saveFollowUp(Long doctorId, FollowUpPlanRequest request) {
        ensureDoctor(doctorId);
        Long taskId = request == null ? null : request.taskId();
        LocalDate followUpDate = parseDate(request == null ? null : request.followUpDate());
        String reason = required(request == null ? null : request.reason(), "请填写回访原因", 500);
        String preparation = trimLimit(request == null ? null : request.preparation(), 500);
        CareRepository.ReportAccessRow report = careRepository.findPublishedReportForDoctor(taskId, doctorId)
                .orElseThrow(() -> badRequest("请先发布报告后再设置回访计划"));
        return toPlanResponse(careRepository.savePlan(report, followUpDate, reason, preparation));
    }

    public FollowUpPlanResponse updateFollowUpStatus(Long doctorId, Long planId, FollowUpStatusRequest request) {
        ensureDoctor(doctorId);
        String status = normalizeStatus(request == null ? null : request.status(), PLAN_STATUSES, "回访状态不正确");
        CareRepository.PlanRow plan = careRepository.findPlanForDoctor(planId, doctorId)
                .orElseThrow(() -> notFound("回访计划不存在"));
        careRepository.updatePlanStatus(plan.id(), doctorId, status);
        return careRepository.findPlanForDoctor(plan.id(), doctorId)
                .map(this::toPlanResponse)
                .orElseThrow(() -> notFound("回访计划不存在"));
    }

    public List<FollowUpPlanResponse> patientFollowUps(Long patientUserId, Long taskId) {
        UserAccount user = ensurePatient(patientUserId);
        careRepository.findPublishedReportForPatient(taskId, user.patientIdCard())
                .orElseThrow(() -> notFound("报告不存在或无权查看"));
        return careRepository.findPlansForPatientReport(taskId, user.patientIdCard()).stream()
                .map(this::toPlanResponse)
                .toList();
    }

    public List<FollowUpPlanResponse> patientFollowUps(Long patientUserId) {
        UserAccount user = ensurePatient(patientUserId);
        return careRepository.findPlansByPatientIdCard(user.patientIdCard()).stream()
                .map(this::toPlanResponse)
                .toList();
    }

    public FollowUpSubmissionResponse submitFollowUp(Long patientUserId, Long planId, FollowUpSubmissionRequest request) {
        UserAccount user = ensurePatient(patientUserId);
        CareRepository.PlanRow plan = careRepository.findPlanForPatient(planId, user.patientIdCard())
                .orElseThrow(() -> notFound("回访计划不存在或无权提交"));
        if (careRepository.existsSubmissionByPlanAndPatient(plan.id(), patientUserId)) {
            throw badRequest("该回访表已提交，不能重复填写");
        }
        String symptoms = normalizeSymptoms(request == null ? List.of() : request.symptoms());
        FollowUpSubmissionRequest normalized = new FollowUpSubmissionRequest(
                request == null ? List.of() : request.symptoms(),
                trimLimit(request == null ? null : request.bloodPressure(), 80),
                trimLimit(request == null ? null : request.heartRate(), 80),
                trimLimit(request == null ? null : request.treatmentStatus(), 120),
                trimLimit(request == null ? null : request.newExamResults(), 1000),
                trimLimit(request == null ? null : request.patientNote(), 1000)
        );
        return toSubmissionResponse(careRepository.createSubmission(plan, patientUserId, normalized, symptoms));
    }

    public List<PatientFeedbackResponse> listFeedbacks(Long doctorId) {
        ensureDoctor(doctorId);
        return careRepository.findFeedbacksByDoctor(doctorId).stream()
                .map(this::toFeedbackResponse)
                .toList();
    }

    public List<PatientFeedbackResponse> patientFeedbacks(Long patientUserId) {
        UserAccount user = ensurePatient(patientUserId);
        return careRepository.findFeedbacksByPatient(patientUserId, user.patientIdCard()).stream()
                .map(this::toFeedbackResponse)
                .toList();
    }

    public PatientFeedbackResponse createFeedback(Long patientUserId, Long taskId, PatientFeedbackRequest request) {
        UserAccount user = ensurePatient(patientUserId);
        String question = required(request == null ? null : request.question(), "请填写需要医生处理的问题", 1000);
        if (careRepository.countPendingFeedbacksByPatient(patientUserId, user.patientIdCard()) >= 3) {
            throw badRequest("最多同时提交 3 个未回复反馈，请等待医生回复后再提交");
        }
        CareRepository.ReportAccessRow report = careRepository.findPublishedReportForPatient(taskId, user.patientIdCard())
                .orElseThrow(() -> notFound("报告不存在或无权反馈"));
        return toFeedbackResponse(careRepository.createFeedback(report, patientUserId, question));
    }

    public PatientFeedbackResponse replyFeedback(Long doctorId, Long feedbackId, FeedbackReplyRequest request) {
        ensureDoctor(doctorId);
        CareRepository.FeedbackRow feedback = careRepository.findFeedback(feedbackId)
                .filter((item) -> item.doctorId().equals(doctorId))
                .orElseThrow(() -> notFound("反馈不存在"));
        String status = normalizeStatus(request == null ? null : request.status(), FEEDBACK_STATUSES, "反馈状态不正确");
        String reply = trimLimit(request == null ? null : request.doctorReply(), 1000);
        careRepository.updateFeedback(feedback.id(), doctorId, reply, status);
        return careRepository.findFeedback(feedback.id())
                .map(this::toFeedbackResponse)
                .orElseThrow(() -> notFound("反馈不存在"));
    }

    private FollowUpPlanResponse toPlanResponse(CareRepository.PlanRow row) {
        boolean overdue = "PENDING".equals(row.status()) && row.followUpDate().isBefore(LocalDate.now());
        return new FollowUpPlanResponse(
                row.id(),
                row.taskId(),
                row.patientName(),
                row.patientIdCard(),
                row.originalFilename(),
                blankToDash(row.riskLevel()),
                row.followUpDate().toString(),
                blankToEmpty(row.reason()),
                blankToEmpty(row.preparation()),
                row.status(),
                overdue ? "已逾期" : planStatusLabel(row.status()),
                overdue,
                row.createdAt().format(DATE_TIME_FORMATTER),
                row.latestSubmission() == null ? null : toSubmissionResponse(row.latestSubmission())
        );
    }

    private FollowUpSubmissionResponse toSubmissionResponse(CareRepository.SubmissionRow row) {
        return new FollowUpSubmissionResponse(
                row.id(),
                row.planId(),
                row.taskId(),
                row.patientUserId(),
                blankToEmpty(row.symptoms()),
                blankToEmpty(row.bloodPressure()),
                blankToEmpty(row.heartRate()),
                blankToEmpty(row.treatmentStatus()),
                blankToEmpty(row.newExamResults()),
                blankToEmpty(row.patientNote()),
                row.createdAt().format(DATE_TIME_FORMATTER)
        );
    }

    private PatientFeedbackResponse toFeedbackResponse(CareRepository.FeedbackRow row) {
        return new PatientFeedbackResponse(
                row.id(),
                row.taskId(),
                row.patientName(),
                row.patientIdCard(),
                row.originalFilename(),
                blankToEmpty(row.question()),
                row.status(),
                feedbackStatusLabel(row.status()),
                blankToEmpty(row.doctorReply()),
                row.createdAt().format(DATE_TIME_FORMATTER),
                row.updatedAt().format(DATE_TIME_FORMATTER)
        );
    }

    private UserAccount ensureDoctor(Long doctorId) {
        UserAccount user = userRepository.findById(doctorId)
                .orElseThrow(() -> badRequest("医生账号不存在"));
        if (UserRole.from(user.role()) != UserRole.DOCTOR) {
            throw badRequest("只有医生用户可以管理回访和反馈");
        }
        return user;
    }

    private UserAccount ensurePatient(Long patientUserId) {
        UserAccount user = userRepository.findById(patientUserId)
                .orElseThrow(() -> badRequest("病人账号不存在"));
        if (UserRole.from(user.role()) != UserRole.PATIENT) {
            throw badRequest("只有病人账号可以提交回访和反馈");
        }
        if (!user.enabled()) {
            throw badRequest("账号不可用");
        }
        if (user.patientIdCard() == null || user.patientIdCard().isBlank()) {
            throw badRequest("病人账号未绑定身份证号");
        }
        return user;
    }

    private LocalDate parseDate(String value) {
        String normalized = required(value, "请选择建议复查时间", 32);
        try {
            return LocalDate.parse(normalized);
        } catch (RuntimeException ex) {
            throw badRequest("建议复查时间格式不正确");
        }
    }

    private String normalizeSymptoms(List<String> symptoms) {
        if (symptoms == null || symptoms.isEmpty()) {
            return "";
        }
        return symptoms.stream()
                .map((item) -> trimLimit(item, 40))
                .filter((item) -> !item.isBlank())
                .distinct()
                .collect(Collectors.joining("、"));
    }

    private String normalizeStatus(String value, Set<String> allowed, String message) {
        String normalized = value == null ? "" : value.trim().toUpperCase();
        if (!allowed.contains(normalized)) {
            throw badRequest(message);
        }
        return normalized;
    }

    private String required(String value, String message, int maxLength) {
        String normalized = trimLimit(value, maxLength);
        if (normalized.isBlank()) {
            throw badRequest(message);
        }
        return normalized;
    }

    private String trimLimit(String value, int maxLength) {
        String normalized = value == null ? "" : value.trim();
        return normalized.length() > maxLength ? normalized.substring(0, maxLength) : normalized;
    }

    private String planStatusLabel(String status) {
        return switch (status) {
            case "SUBMITTED" -> "患者已提交";
            case "VIEWED" -> "医生已查看";
            case "COMPLETED" -> "已完成";
            default -> "待回访";
        };
    }

    private String feedbackStatusLabel(String status) {
        return switch (status) {
            case "REPLIED" -> "已回复";
            case "CLOSED" -> "已关闭";
            default -> "待处理";
        };
    }

    private String blankToDash(String value) {
        return value == null || value.isBlank() ? "-" : value;
    }

    private String blankToEmpty(String value) {
        return value == null ? "" : value;
    }

    private ResponseStatusException badRequest(String message) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
    }

    private ResponseStatusException notFound(String message) {
        return new ResponseStatusException(HttpStatus.NOT_FOUND, message);
    }
}
