package com.ppgl.analyze.analysis;

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
public class AnalysisRepository {

    private static final List<String> ACTIVE_STATUSES = List.of(
            AnalysisStatuses.TASK_QUEUED,
            AnalysisStatuses.TASK_PREPROCESSING,
            AnalysisStatuses.TASK_UPLOADING,
            AnalysisStatuses.TASK_WAITING_JETSON,
            AnalysisStatuses.TASK_POSTPROCESSING,
            AnalysisStatuses.TASK_RUNNING
    );

    private final JdbcTemplate jdbcTemplate;

    private final RowMapper<AnalysisCandidate> candidateMapper = (rs, rowNum) -> new AnalysisCandidate(
            rs.getLong("ct_image_id"),
            rs.getLong("doctor_id"),
            rs.getString("doctor_name"),
            rs.getString("patient_name"),
            rs.getString("patient_id_card"),
            rs.getString("original_filename"),
            rs.getString("file_path"),
            rs.getLong("file_size"),
            rs.getString("status"),
            rs.getTimestamp("created_at").toLocalDateTime()
    );

    private final RowMapper<AnalysisTask> taskMapper = (rs, rowNum) -> new AnalysisTask(
            rs.getLong("id"),
            rs.getLong("ct_image_id"),
            rs.getLong("doctor_id"),
            nullableLong(rs.getObject("requester_id")),
            rs.getString("doctor_name"),
            rs.getString("patient_name"),
            rs.getString("patient_id_card"),
            rs.getString("original_filename"),
            rs.getString("file_path"),
            rs.getString("jetson_case_id"),
            rs.getString("mode"),
            rs.getString("device"),
            rs.getString("status"),
            rs.getInt("progress"),
            rs.getString("stage"),
            rs.getString("message"),
            rs.getString("failed_reason"),
            nullableDateTime(rs.getTimestamp("created_at")),
            nullableDateTime(rs.getTimestamp("started_at")),
            nullableDateTime(rs.getTimestamp("completed_at"))
    );

    public AnalysisRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<AnalysisCandidate> findCandidates(Long doctorId) {
        return jdbcTemplate.query(
                """
                SELECT c.id AS ct_image_id, c.doctor_id, u.display_name AS doctor_name,
                       c.patient_name, c.patient_id_card, c.original_filename, c.file_path,
                       c.file_size, c.status, c.created_at
                FROM ct_images c
                JOIN users u ON u.id = c.doctor_id
                WHERE c.doctor_id = ?
                  AND c.status IN (?, ?)
                  AND NOT EXISTS (
                      SELECT 1 FROM analysis_tasks t
                      WHERE t.ct_image_id = c.id
                        AND t.status IN (?, ?, ?, ?, ?, ?)
                  )
                ORDER BY c.created_at DESC, c.id DESC
                """,
                candidateMapper,
                doctorId,
                AnalysisStatuses.CT_PENDING,
                AnalysisStatuses.CT_FAILED,
                ACTIVE_STATUSES.get(0),
                ACTIVE_STATUSES.get(1),
                ACTIVE_STATUSES.get(2),
                ACTIVE_STATUSES.get(3),
                ACTIVE_STATUSES.get(4),
                ACTIVE_STATUSES.get(5)
        );
    }

    public Optional<AnalysisCandidate> findCandidateById(Long ctImageId, Long doctorId) {
        List<AnalysisCandidate> candidates = jdbcTemplate.query(
                """
                SELECT c.id AS ct_image_id, c.doctor_id, u.display_name AS doctor_name,
                       c.patient_name, c.patient_id_card, c.original_filename, c.file_path,
                       c.file_size, c.status, c.created_at
                FROM ct_images c
                JOIN users u ON u.id = c.doctor_id
                WHERE c.id = ? AND c.doctor_id = ?
                """,
                candidateMapper,
                ctImageId,
                doctorId
        );
        return candidates.stream().findFirst();
    }

    public boolean hasActiveTaskForCt(Long ctImageId) {
        Integer count = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*) FROM analysis_tasks
                WHERE ct_image_id = ? AND status IN (?, ?, ?, ?, ?, ?)
                """,
                Integer.class,
                ctImageId,
                ACTIVE_STATUSES.get(0),
                ACTIVE_STATUSES.get(1),
                ACTIVE_STATUSES.get(2),
                ACTIVE_STATUSES.get(3),
                ACTIVE_STATUSES.get(4),
                ACTIVE_STATUSES.get(5)
        );
        return count != null && count > 0;
    }

    public AnalysisTask createTask(AnalysisCandidate candidate, Long requesterId, String mode, String device) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    """
                    INSERT INTO analysis_tasks
                        (ct_image_id, doctor_id, requester_id, mode, device, status, progress, stage, message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    Statement.RETURN_GENERATED_KEYS
            );
            statement.setLong(1, candidate.ctImageId());
            statement.setLong(2, candidate.doctorId());
            if (requesterId == null) {
                statement.setObject(3, null);
            } else {
                statement.setLong(3, requesterId);
            }
            statement.setString(4, mode);
            statement.setString(5, device);
            statement.setString(6, AnalysisStatuses.TASK_QUEUED);
            statement.setInt(7, 0);
            statement.setString(8, "queued");
            statement.setString(9, "等待调度");
            return statement;
        }, keyHolder);
        Number id = keyHolder.getKey();
        if (id == null) {
            throw new AnalysisException("分析任务创建失败");
        }
        return findTaskById(id.longValue()).orElseThrow(() -> new AnalysisException("分析任务创建失败"));
    }

    public List<AnalysisTask> findTasks(Long doctorId) {
        return jdbcTemplate.query(
                baseTaskSelect()
                        + """
                        WHERE t.doctor_id = ?
                        ORDER BY
                          CASE t.status
                            WHEN '预处理中' THEN 1
                            WHEN '上传中' THEN 2
                            WHEN '等待 Jetson' THEN 3
                            WHEN '分析中' THEN 4
                            WHEN '后处理中' THEN 5
                            WHEN '排队中' THEN 6
                            WHEN '分析失败' THEN 7
                            WHEN '已完成' THEN 8
                            ELSE 9
                          END,
                          t.created_at ASC,
                          t.id ASC
                        """,
                taskMapper,
                doctorId
        );
    }

    public Optional<AnalysisTask> findTaskById(Long id) {
        List<AnalysisTask> tasks = jdbcTemplate.query(
                baseTaskSelect() + "WHERE t.id = ?",
                taskMapper,
                id
        );
        return tasks.stream().findFirst();
    }

    public Optional<AnalysisTask> findNextQueuedTask() {
        List<AnalysisTask> tasks = jdbcTemplate.query(
                baseTaskSelect()
                        + """
                        WHERE t.status = ?
                        ORDER BY t.created_at ASC, t.id ASC
                        LIMIT 1
                        """,
                taskMapper,
                AnalysisStatuses.TASK_QUEUED
        );
        return tasks.stream().findFirst();
    }

    public void updateCtStatus(Long ctImageId, String status) {
        jdbcTemplate.update("UPDATE ct_images SET status = ? WHERE id = ?", status, ctImageId);
    }

    public void updateTaskProgress(Long taskId, String status, int progress, String stage, String message) {
        jdbcTemplate.update(
                """
                UPDATE analysis_tasks
                SET status = ?, progress = ?, stage = ?, message = ?, failed_reason = NULL
                WHERE id = ?
                """,
                status,
                progress,
                stage,
                message,
                taskId
        );
    }

    public void markTaskStarted(Long taskId, String status, int progress, String stage, String message) {
        jdbcTemplate.update(
                """
                UPDATE analysis_tasks
                SET status = ?, progress = ?, stage = ?, message = ?, started_at = COALESCE(started_at, ?), failed_reason = NULL
                WHERE id = ?
                """,
                status,
                progress,
                stage,
                message,
                Timestamp.valueOf(LocalDateTime.now()),
                taskId
        );
    }

    public void setJetsonCaseId(Long taskId, String jetsonCaseId) {
        jdbcTemplate.update("UPDATE analysis_tasks SET jetson_case_id = ? WHERE id = ?", jetsonCaseId, taskId);
    }

    public void markTaskDone(Long taskId, String message) {
        jdbcTemplate.update(
                """
                UPDATE analysis_tasks
                SET status = ?, progress = 100, stage = ?, message = ?, completed_at = ?, failed_reason = NULL
                WHERE id = ?
                """,
                AnalysisStatuses.TASK_DONE,
                "completed",
                message,
                Timestamp.valueOf(LocalDateTime.now()),
                taskId
        );
    }

    public void markTaskFailed(Long taskId, String reason) {
        jdbcTemplate.update(
                """
                UPDATE analysis_tasks
                SET status = ?, progress = 100, stage = ?, message = ?, failed_reason = ?, completed_at = ?
                WHERE id = ?
                """,
                AnalysisStatuses.TASK_FAILED,
                "failed",
                "分析失败",
                reason,
                Timestamp.valueOf(LocalDateTime.now()),
                taskId
        );
    }

    private String baseTaskSelect() {
        return """
                SELECT t.id, t.ct_image_id, t.doctor_id, t.requester_id,
                       u.display_name AS doctor_name,
                       c.patient_name, c.patient_id_card, c.original_filename, c.file_path,
                       t.jetson_case_id, t.mode, t.device, t.status, t.progress,
                       t.stage, t.message, t.failed_reason, t.created_at, t.started_at, t.completed_at
                FROM analysis_tasks t
                JOIN ct_images c ON c.id = t.ct_image_id
                JOIN users u ON u.id = t.doctor_id
                """;
    }

    private static LocalDateTime nullableDateTime(Timestamp timestamp) {
        return timestamp == null ? null : timestamp.toLocalDateTime();
    }

    private static Long nullableLong(Object value) {
        if (value == null) {
            return null;
        }
        return ((Number) value).longValue();
    }
}
