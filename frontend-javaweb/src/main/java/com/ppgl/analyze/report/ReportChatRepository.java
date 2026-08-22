package com.ppgl.analyze.report;

import jakarta.annotation.PostConstruct;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class ReportChatRepository {

    private final JdbcTemplate jdbcTemplate;
    private final int maxMessages;

    private final RowMapper<ReportChatRecord> rowMapper = (rs, rowNum) -> new ReportChatRecord(
            rs.getLong("id"),
            rs.getLong("task_id"),
            rs.getLong("doctor_id"),
            rs.getString("role"),
            rs.getString("content"),
            rs.getTimestamp("created_at").toLocalDateTime()
    );

    public ReportChatRepository(
            JdbcTemplate jdbcTemplate,
            @Value("${ppgl.report.chat.max-messages:100}") int maxMessages
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.maxMessages = Math.max(20, maxMessages);
    }

    @PostConstruct
    public void ensureTable() {
        jdbcTemplate.execute(
                """
                CREATE TABLE IF NOT EXISTS report_chat_messages (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    task_id BIGINT NOT NULL,
                    doctor_id BIGINT NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_report_chat_task_doctor (task_id, doctor_id, created_at),
                    CONSTRAINT chk_report_chat_role CHECK (role IN ('user', 'assistant'))
                )
                """
        );
    }

    public List<ReportChatRecord> findByTaskAndDoctor(Long taskId, Long doctorId) {
        return jdbcTemplate.query(
                """
                SELECT id, task_id, doctor_id, role, content, created_at
                FROM report_chat_messages
                WHERE task_id = ? AND doctor_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                rowMapper,
                taskId,
                doctorId
        );
    }

    public List<ReportChatRecord> findPatientQuestionsByTaskAndPatientIdCard(Long taskId, String patientIdCard) {
        return jdbcTemplate.query(
                """
                SELECT m.id, m.task_id, m.doctor_id, m.role, m.content, m.created_at
                FROM report_chat_messages m
                JOIN users u ON u.id = m.doctor_id
                WHERE m.task_id = ?
                  AND u.role = 'PATIENT'
                  AND u.patient_id_card = ?
                  AND m.role = 'user'
                ORDER BY m.created_at ASC, m.id ASC
                """,
                rowMapper,
                taskId,
                patientIdCard
        );
    }

    public void append(Long taskId, Long doctorId, String role, String content) {
        jdbcTemplate.update(
                """
                INSERT INTO report_chat_messages (task_id, doctor_id, role, content)
                VALUES (?, ?, ?, ?)
                """,
                taskId,
                doctorId,
                role,
                content
        );
        trim(taskId, doctorId);
    }

    private void trim(Long taskId, Long doctorId) {
        jdbcTemplate.update(
                """
                DELETE FROM report_chat_messages
                WHERE task_id = ? AND doctor_id = ?
                  AND id NOT IN (
                      SELECT id FROM (
                          SELECT id
                          FROM report_chat_messages
                          WHERE task_id = ? AND doctor_id = ?
                          ORDER BY created_at DESC, id DESC
                          LIMIT ?
                      ) keep_rows
                  )
                """,
                taskId,
                doctorId,
                taskId,
                doctorId,
                maxMessages
        );
    }
}
