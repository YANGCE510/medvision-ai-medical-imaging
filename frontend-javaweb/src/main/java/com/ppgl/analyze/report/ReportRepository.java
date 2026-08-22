package com.ppgl.analyze.report;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class ReportRepository {

    private final JdbcTemplate jdbcTemplate;

    private final RowMapper<AnalysisResultRecord> rowMapper = (rs, rowNum) -> {
        Timestamp reviewedAt = rs.getTimestamp("doctor_reviewed_at");
        return new AnalysisResultRecord(
                rs.getLong("id"),
                rs.getLong("task_id"),
                rs.getLong("ct_image_id"),
                rs.getLong("doctor_id"),
                rs.getString("patient_name"),
                rs.getString("patient_id_card"),
                rs.getString("original_filename"),
                rs.getString("result_json_path"),
                rs.getString("metrics_json_path"),
                rs.getString("risk_json_path"),
                rs.getString("label_map_json_path"),
                rs.getString("report_md_path"),
                rs.getString("overlay_path"),
                rs.getBigDecimal("tumor_volume_ml"),
                rs.getString("risk_level"),
                rs.getString("summary_json"),
                rs.getBoolean("patient_visible"),
                rs.getString("doctor_review_status"),
                rs.getString("doctor_review_note"),
                reviewedAt == null ? null : reviewedAt.toLocalDateTime(),
                rs.getObject("reviewed_by", Long.class),
                rs.getTimestamp("created_at").toLocalDateTime()
        );
    };

    public ReportRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public AnalysisResultRecord save(AnalysisResultSaveRequest request) {
        Optional<AnalysisResultRecord> existing = findByTaskIdAndDoctorId(request.taskId(), request.doctorId());
        if (existing.isPresent()) {
            jdbcTemplate.update(
                    """
                    UPDATE analysis_results
                    SET result_json_path = ?, metrics_json_path = ?, risk_json_path = ?, label_map_json_path = ?,
                        report_md_path = ?, overlay_path = ?, tumor_volume_ml = ?, risk_level = ?, summary_json = ?,
                        patient_visible = FALSE, doctor_review_status = 'PENDING', doctor_review_note = NULL,
                        doctor_reviewed_at = NULL, reviewed_by = NULL
                    WHERE task_id = ? AND doctor_id = ?
                    """,
                    request.resultJsonPath(),
                    request.metricsJsonPath(),
                    request.riskJsonPath(),
                    request.labelMapJsonPath(),
                    request.reportMdPath(),
                    request.overlayPath(),
                    request.tumorVolumeMl(),
                    request.riskLevel(),
                    request.summaryJson(),
                    request.taskId(),
                    request.doctorId()
            );
            return findByTaskIdAndDoctorId(request.taskId(), request.doctorId())
                    .orElseThrow(() -> new ReportException("分析结果保存失败"));
        }

        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    """
                    INSERT INTO analysis_results
                        (task_id, ct_image_id, doctor_id, result_json_path, metrics_json_path, risk_json_path,
                         label_map_json_path, report_md_path, overlay_path, tumor_volume_ml, risk_level, summary_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    Statement.RETURN_GENERATED_KEYS
            );
            statement.setLong(1, request.taskId());
            statement.setLong(2, request.ctImageId());
            statement.setLong(3, request.doctorId());
            statement.setString(4, request.resultJsonPath());
            statement.setString(5, request.metricsJsonPath());
            statement.setString(6, request.riskJsonPath());
            statement.setString(7, request.labelMapJsonPath());
            statement.setString(8, request.reportMdPath());
            statement.setString(9, request.overlayPath());
            statement.setBigDecimal(10, request.tumorVolumeMl());
            statement.setString(11, request.riskLevel());
            statement.setString(12, request.summaryJson());
            return statement;
        }, keyHolder);
        Number id = keyHolder.getKey();
        if (id == null) {
            throw new ReportException("分析结果保存失败");
        }
        return findById(id.longValue()).orElseThrow(() -> new ReportException("分析结果保存失败"));
    }

    public List<AnalysisResultRecord> findByDoctorId(Long doctorId) {
        return jdbcTemplate.query(
                baseSelect()
                        + """
                        WHERE r.doctor_id = ?
                        ORDER BY r.created_at DESC, r.id DESC
                        """,
                rowMapper,
                doctorId
        );
    }

    public Optional<AnalysisResultRecord> findByTaskIdAndDoctorId(Long taskId, Long doctorId) {
        List<AnalysisResultRecord> rows = jdbcTemplate.query(
                baseSelect() + "WHERE r.task_id = ? AND r.doctor_id = ?",
                rowMapper,
                taskId,
                doctorId
        );
        return rows.stream().findFirst();
    }

    public List<AnalysisResultRecord> findByPatientIdCard(String patientIdCard) {
        return jdbcTemplate.query(
                baseSelect()
                        + """
                        WHERE c.patient_id_card = ?
                        ORDER BY r.created_at DESC, r.id DESC
                        """,
                rowMapper,
                patientIdCard
        );
    }

    public List<AnalysisResultRecord> findPublishedByPatientIdCard(String patientIdCard) {
        return jdbcTemplate.query(
                baseSelect()
                        + """
                        WHERE c.patient_id_card = ?
                          AND r.patient_visible = TRUE
                        ORDER BY r.created_at DESC, r.id DESC
                        """,
                rowMapper,
                patientIdCard
        );
    }

    public Optional<AnalysisResultRecord> findByTaskIdAndPatientIdCard(Long taskId, String patientIdCard) {
        List<AnalysisResultRecord> rows = jdbcTemplate.query(
                baseSelect() + "WHERE r.task_id = ? AND c.patient_id_card = ?",
                rowMapper,
                taskId,
                patientIdCard
        );
        return rows.stream().findFirst();
    }

    public Optional<AnalysisResultRecord> findPublishedByTaskIdAndPatientIdCard(Long taskId, String patientIdCard) {
        List<AnalysisResultRecord> rows = jdbcTemplate.query(
                baseSelect()
                        + """
                        WHERE r.task_id = ?
                          AND c.patient_id_card = ?
                          AND r.patient_visible = TRUE
                        """,
                rowMapper,
                taskId,
                patientIdCard
        );
        return rows.stream().findFirst();
    }

    public void updatePatientReview(Long taskId, Long doctorId, boolean patientVisible, String doctorReviewNote) {
        int rows = jdbcTemplate.update(
                """
                UPDATE analysis_results
                SET patient_visible = ?,
                    doctor_review_status = ?,
                    doctor_review_note = ?,
                    doctor_reviewed_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END,
                    reviewed_by = CASE WHEN ? THEN ? ELSE NULL END
                WHERE task_id = ? AND doctor_id = ?
                """,
                patientVisible,
                patientVisible ? "PUBLISHED" : "PENDING",
                doctorReviewNote,
                patientVisible,
                patientVisible,
                doctorId,
                taskId,
                doctorId
        );
        if (rows == 0) {
            throw new ReportException("报告不存在");
        }
    }

    private Optional<AnalysisResultRecord> findById(Long id) {
        List<AnalysisResultRecord> rows = jdbcTemplate.query(baseSelect() + "WHERE r.id = ?", rowMapper, id);
        return rows.stream().findFirst();
    }

    private String baseSelect() {
        return """
                SELECT r.id, r.task_id, r.ct_image_id, r.doctor_id,
                       c.patient_name, c.patient_id_card, c.original_filename,
                       r.result_json_path, r.metrics_json_path, r.risk_json_path,
                       r.label_map_json_path, r.report_md_path, r.overlay_path,
                       r.tumor_volume_ml, r.risk_level, r.summary_json,
                       r.patient_visible, r.doctor_review_status, r.doctor_review_note,
                       r.doctor_reviewed_at, r.reviewed_by, r.created_at
                FROM analysis_results r
                JOIN ct_images c ON c.id = r.ct_image_id
                """;
    }
}
