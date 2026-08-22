package com.ppgl.analyze.care;

import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
class CareRepository {

    private final JdbcTemplate jdbcTemplate;

    CareRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    Optional<ReportAccessRow> findPublishedReportForDoctor(Long taskId, Long doctorId) {
        List<ReportAccessRow> rows = jdbcTemplate.query(
                reportAccessSelect() + """
                WHERE r.task_id = ?
                  AND r.doctor_id = ?
                  AND r.patient_visible = TRUE
                """,
                (rs, rowNum) -> new ReportAccessRow(
                        rs.getLong("task_id"),
                        rs.getLong("doctor_id"),
                        rs.getLong("ct_image_id"),
                        rs.getString("patient_name"),
                        rs.getString("patient_id_card"),
                        rs.getString("original_filename"),
                        rs.getString("risk_level")
                ),
                taskId,
                doctorId
        );
        return rows.stream().findFirst();
    }

    Optional<ReportAccessRow> findPublishedReportForPatient(Long taskId, String patientIdCard) {
        List<ReportAccessRow> rows = jdbcTemplate.query(
                reportAccessSelect() + """
                WHERE r.task_id = ?
                  AND c.patient_id_card = ?
                  AND r.patient_visible = TRUE
                """,
                (rs, rowNum) -> new ReportAccessRow(
                        rs.getLong("task_id"),
                        rs.getLong("doctor_id"),
                        rs.getLong("ct_image_id"),
                        rs.getString("patient_name"),
                        rs.getString("patient_id_card"),
                        rs.getString("original_filename"),
                        rs.getString("risk_level")
                ),
                taskId,
                patientIdCard
        );
        return rows.stream().findFirst();
    }

    List<PlanRow> findPlansByDoctor(Long doctorId) {
        return jdbcTemplate.query(planSelect() + """
                WHERE p.doctor_id = ?
                ORDER BY p.follow_up_date ASC, p.id DESC
                """, this::mapPlanRow, doctorId);
    }

    List<PlanRow> findPlansForPatientReport(Long taskId, String patientIdCard) {
        return jdbcTemplate.query(planSelect() + """
                WHERE p.task_id = ?
                  AND c.patient_id_card = ?
                  AND r.patient_visible = TRUE
                ORDER BY p.follow_up_date ASC, p.id DESC
                """, this::mapPlanRow, taskId, patientIdCard);
    }

    List<PlanRow> findPlansByPatientIdCard(String patientIdCard) {
        return jdbcTemplate.query(planSelect() + """
                WHERE c.patient_id_card = ?
                  AND r.patient_visible = TRUE
                ORDER BY p.follow_up_date ASC, p.id DESC
                """, this::mapPlanRow, patientIdCard);
    }

    Optional<PlanRow> findPlanForDoctor(Long planId, Long doctorId) {
        List<PlanRow> rows = jdbcTemplate.query(planSelect() + """
                WHERE p.id = ?
                  AND p.doctor_id = ?
                """, this::mapPlanRow, planId, doctorId);
        return rows.stream().findFirst();
    }

    Optional<PlanRow> findPlanForPatient(Long planId, String patientIdCard) {
        List<PlanRow> rows = jdbcTemplate.query(planSelect() + """
                WHERE p.id = ?
                  AND c.patient_id_card = ?
                  AND r.patient_visible = TRUE
                """, this::mapPlanRow, planId, patientIdCard);
        return rows.stream().findFirst();
    }

    PlanRow savePlan(ReportAccessRow report, LocalDate followUpDate, String reason, String preparation) {
        jdbcTemplate.update(
                """
                INSERT INTO follow_up_plans (task_id, doctor_id, follow_up_date, reason, preparation, status)
                VALUES (?, ?, ?, ?, ?, 'PENDING')
                ON DUPLICATE KEY UPDATE
                    follow_up_date = VALUES(follow_up_date),
                    reason = VALUES(reason),
                    preparation = VALUES(preparation),
                    status = IF(status = 'COMPLETED', 'COMPLETED', status)
                """,
                report.taskId(),
                report.doctorId(),
                Date.valueOf(followUpDate),
                reason,
                preparation
        );
        return findPlanForDoctorByTask(report.taskId(), report.doctorId())
                .orElseThrow(() -> new IllegalStateException("回访计划保存失败"));
    }

    Optional<PlanRow> findPlanForDoctorByTask(Long taskId, Long doctorId) {
        List<PlanRow> rows = jdbcTemplate.query(planSelect() + """
                WHERE p.task_id = ?
                  AND p.doctor_id = ?
                """, this::mapPlanRow, taskId, doctorId);
        return rows.stream().findFirst();
    }

    void updatePlanStatus(Long planId, Long doctorId, String status) {
        jdbcTemplate.update(
                "UPDATE follow_up_plans SET status = ? WHERE id = ? AND doctor_id = ?",
                status,
                planId,
                doctorId
        );
    }

    SubmissionRow createSubmission(PlanRow plan, Long patientUserId, FollowUpSubmissionRequest request, String symptoms) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    """
                    INSERT INTO follow_up_submissions
                        (plan_id, task_id, patient_user_id, symptoms, blood_pressure, heart_rate,
                         treatment_status, new_exam_results, patient_note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    Statement.RETURN_GENERATED_KEYS
            );
            statement.setLong(1, plan.id());
            statement.setLong(2, plan.taskId());
            statement.setLong(3, patientUserId);
            statement.setString(4, symptoms);
            statement.setString(5, request.bloodPressure());
            statement.setString(6, request.heartRate());
            statement.setString(7, request.treatmentStatus());
            statement.setString(8, request.newExamResults());
            statement.setString(9, request.patientNote());
            return statement;
        }, keyHolder);
        jdbcTemplate.update(
                "UPDATE follow_up_plans SET status = 'SUBMITTED' WHERE id = ? AND status <> 'COMPLETED'",
                plan.id()
        );
        Number id = keyHolder.getKey();
        return findSubmission(id == null ? null : id.longValue())
                .orElseThrow(() -> new IllegalStateException("回访提交失败"));
    }

    boolean existsSubmissionByPlanAndPatient(Long planId, Long patientUserId) {
        Integer count = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM follow_up_submissions
                WHERE plan_id = ?
                  AND patient_user_id = ?
                """,
                Integer.class,
                planId,
                patientUserId
        );
        return count != null && count > 0;
    }

    Optional<SubmissionRow> findSubmission(Long id) {
        if (id == null) {
            return Optional.empty();
        }
        List<SubmissionRow> rows = jdbcTemplate.query(
                submissionSelect() + "WHERE s.id = ?",
                this::mapSubmissionRow,
                id
        );
        return rows.stream().findFirst();
    }

    List<FeedbackRow> findFeedbacksByDoctor(Long doctorId) {
        return jdbcTemplate.query(feedbackSelect() + """
                WHERE f.doctor_id = ?
                ORDER BY f.created_at DESC, f.id DESC
                """, this::mapFeedbackRow, doctorId);
    }

    List<FeedbackRow> findFeedbacksByPatient(Long patientUserId, String patientIdCard) {
        return jdbcTemplate.query(feedbackSelect() + """
                WHERE f.patient_user_id = ?
                  AND c.patient_id_card = ?
                  AND r.patient_visible = TRUE
                ORDER BY f.created_at DESC, f.id DESC
                """, this::mapFeedbackRow, patientUserId, patientIdCard);
    }

    int countPendingFeedbacksByPatient(Long patientUserId, String patientIdCard) {
        Integer count = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM patient_feedbacks f
                JOIN analysis_results r ON r.task_id = f.task_id
                JOIN ct_images c ON c.id = r.ct_image_id
                WHERE f.patient_user_id = ?
                  AND c.patient_id_card = ?
                  AND r.patient_visible = TRUE
                  AND f.status = 'PENDING'
                """,
                Integer.class,
                patientUserId,
                patientIdCard
        );
        return count == null ? 0 : count;
    }

    FeedbackRow createFeedback(ReportAccessRow report, Long patientUserId, String question) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    """
                    INSERT INTO patient_feedbacks (task_id, doctor_id, patient_user_id, question, status)
                    VALUES (?, ?, ?, ?, 'PENDING')
                    """,
                    Statement.RETURN_GENERATED_KEYS
            );
            statement.setLong(1, report.taskId());
            statement.setLong(2, report.doctorId());
            statement.setLong(3, patientUserId);
            statement.setString(4, question);
            return statement;
        }, keyHolder);
        Number id = keyHolder.getKey();
        return findFeedback(id == null ? null : id.longValue())
                .orElseThrow(() -> new IllegalStateException("反馈提交失败"));
    }

    Optional<FeedbackRow> findFeedback(Long id) {
        if (id == null) {
            return Optional.empty();
        }
        List<FeedbackRow> rows = jdbcTemplate.query(
                feedbackSelect() + "WHERE f.id = ?",
                this::mapFeedbackRow,
                id
        );
        return rows.stream().findFirst();
    }

    void updateFeedback(Long feedbackId, Long doctorId, String reply, String status) {
        jdbcTemplate.update(
                """
                UPDATE patient_feedbacks
                SET doctor_reply = ?, status = ?
                WHERE id = ? AND doctor_id = ?
                """,
                reply,
                status,
                feedbackId,
                doctorId
        );
    }

    private String reportAccessSelect() {
        return """
                SELECT r.task_id, r.doctor_id, r.ct_image_id,
                       c.patient_name, c.patient_id_card, c.original_filename,
                       r.risk_level
                FROM analysis_results r
                JOIN ct_images c ON c.id = r.ct_image_id
                """;
    }

    private String planSelect() {
        return """
                SELECT p.id, p.task_id, p.doctor_id, p.follow_up_date,
                       p.reason, p.preparation, p.status, p.created_at,
                       c.patient_name, c.patient_id_card, c.original_filename,
                       r.risk_level,
                       s.id AS submission_id, s.patient_user_id,
                       s.symptoms, s.blood_pressure, s.heart_rate,
                       s.treatment_status, s.new_exam_results, s.patient_note,
                       s.created_at AS submission_created_at
                FROM follow_up_plans p
                JOIN analysis_results r ON r.task_id = p.task_id
                JOIN ct_images c ON c.id = r.ct_image_id
                LEFT JOIN follow_up_submissions s
                  ON s.id = (
                      SELECT MAX(s2.id)
                      FROM follow_up_submissions s2
                      WHERE s2.plan_id = p.id
                  )
                """;
    }

    private String submissionSelect() {
        return """
                SELECT s.id, s.plan_id, s.task_id, s.patient_user_id,
                       s.symptoms, s.blood_pressure, s.heart_rate,
                       s.treatment_status, s.new_exam_results, s.patient_note,
                       s.created_at
                FROM follow_up_submissions s
                """;
    }

    private String feedbackSelect() {
        return """
                SELECT f.id, f.task_id, f.doctor_id, f.patient_user_id,
                       f.question, f.status, f.doctor_reply, f.created_at, f.updated_at,
                       c.patient_name, c.patient_id_card, c.original_filename
                FROM patient_feedbacks f
                JOIN analysis_results r ON r.task_id = f.task_id
                JOIN ct_images c ON c.id = r.ct_image_id
                """;
    }

    private PlanRow mapPlanRow(java.sql.ResultSet rs, int rowNum) throws java.sql.SQLException {
        Long submissionId = rs.getObject("submission_id", Long.class);
        SubmissionRow submission = submissionId == null ? null : new SubmissionRow(
                submissionId,
                rs.getLong("id"),
                rs.getLong("task_id"),
                rs.getObject("patient_user_id", Long.class),
                rs.getString("symptoms"),
                rs.getString("blood_pressure"),
                rs.getString("heart_rate"),
                rs.getString("treatment_status"),
                rs.getString("new_exam_results"),
                rs.getString("patient_note"),
                rs.getTimestamp("submission_created_at").toLocalDateTime()
        );
        return new PlanRow(
                rs.getLong("id"),
                rs.getLong("task_id"),
                rs.getLong("doctor_id"),
                rs.getDate("follow_up_date").toLocalDate(),
                rs.getString("reason"),
                rs.getString("preparation"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toLocalDateTime(),
                rs.getString("patient_name"),
                rs.getString("patient_id_card"),
                rs.getString("original_filename"),
                rs.getString("risk_level"),
                submission
        );
    }

    private SubmissionRow mapSubmissionRow(java.sql.ResultSet rs, int rowNum) throws java.sql.SQLException {
        return new SubmissionRow(
                rs.getLong("id"),
                rs.getLong("plan_id"),
                rs.getLong("task_id"),
                rs.getLong("patient_user_id"),
                rs.getString("symptoms"),
                rs.getString("blood_pressure"),
                rs.getString("heart_rate"),
                rs.getString("treatment_status"),
                rs.getString("new_exam_results"),
                rs.getString("patient_note"),
                rs.getTimestamp("created_at").toLocalDateTime()
        );
    }

    private FeedbackRow mapFeedbackRow(java.sql.ResultSet rs, int rowNum) throws java.sql.SQLException {
        return new FeedbackRow(
                rs.getLong("id"),
                rs.getLong("task_id"),
                rs.getLong("doctor_id"),
                rs.getLong("patient_user_id"),
                rs.getString("patient_name"),
                rs.getString("patient_id_card"),
                rs.getString("original_filename"),
                rs.getString("question"),
                rs.getString("status"),
                rs.getString("doctor_reply"),
                rs.getTimestamp("created_at").toLocalDateTime(),
                rs.getTimestamp("updated_at").toLocalDateTime()
        );
    }

    record ReportAccessRow(
            Long taskId,
            Long doctorId,
            Long ctImageId,
            String patientName,
            String patientIdCard,
            String originalFilename,
            String riskLevel
    ) {
    }

    record PlanRow(
            Long id,
            Long taskId,
            Long doctorId,
            LocalDate followUpDate,
            String reason,
            String preparation,
            String status,
            LocalDateTime createdAt,
            String patientName,
            String patientIdCard,
            String originalFilename,
            String riskLevel,
            SubmissionRow latestSubmission
    ) {
    }

    record SubmissionRow(
            Long id,
            Long planId,
            Long taskId,
            Long patientUserId,
            String symptoms,
            String bloodPressure,
            String heartRate,
            String treatmentStatus,
            String newExamResults,
            String patientNote,
            LocalDateTime createdAt
    ) {
    }

    record FeedbackRow(
            Long id,
            Long taskId,
            Long doctorId,
            Long patientUserId,
            String patientName,
            String patientIdCard,
            String originalFilename,
            String question,
            String status,
            String doctorReply,
            LocalDateTime createdAt,
            LocalDateTime updatedAt
    ) {
    }
}
