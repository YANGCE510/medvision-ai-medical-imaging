package com.ppgl.analyze.ct;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class CtImageRepository {

    private final JdbcTemplate jdbcTemplate;

    private final RowMapper<CtImage> rowMapper = (rs, rowNum) -> new CtImage(
            rs.getLong("id"),
            rs.getLong("doctor_id"),
            rs.getString("patient_name"),
            rs.getString("patient_id_card"),
            rs.getString("remark"),
            rs.getString("original_filename"),
            rs.getString("stored_filename"),
            rs.getString("file_path"),
            rs.getLong("file_size"),
            rs.getString("status"),
            rs.getTimestamp("created_at").toLocalDateTime()
    );

    public CtImageRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<CtImage> findByDoctorId(Long doctorId) {
        return jdbcTemplate.query(
                """
                SELECT id, doctor_id, patient_name, patient_id_card, remark, original_filename,
                       stored_filename, file_path, file_size, status, created_at
                FROM ct_images
                WHERE doctor_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                rowMapper,
                doctorId
        );
    }

    public Optional<CtImage> findByDoctorIdAndId(Long doctorId, Long id) {
        List<CtImage> images = jdbcTemplate.query(
                """
                SELECT id, doctor_id, patient_name, patient_id_card, remark, original_filename,
                       stored_filename, file_path, file_size, status, created_at
                FROM ct_images
                WHERE doctor_id = ? AND id = ?
                """,
                rowMapper,
                doctorId,
                id
        );
        return images.stream().findFirst();
    }

    public CtImage create(CtImage image) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    """
                    INSERT INTO ct_images
                        (doctor_id, patient_name, patient_id_card, remark, original_filename,
                         stored_filename, file_path, file_size, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    Statement.RETURN_GENERATED_KEYS
            );
            statement.setLong(1, image.doctorId());
            statement.setString(2, image.patientName());
            statement.setString(3, image.patientIdCard());
            statement.setString(4, image.remark());
            statement.setString(5, image.originalFilename());
            statement.setString(6, image.storedFilename());
            statement.setString(7, image.filePath());
            statement.setLong(8, image.fileSize());
            statement.setString(9, image.status());
            return statement;
        }, keyHolder);

        Number id = keyHolder.getKey();
        if (id == null) {
            throw new CtImageException("影像记录保存失败");
        }
        return findByDoctorIdAndId(image.doctorId(), id.longValue())
                .orElseThrow(() -> new CtImageException("影像记录保存失败"));
    }

    public void delete(Long doctorId, Long id) {
        jdbcTemplate.update("DELETE FROM ct_images WHERE doctor_id = ? AND id = ?", doctorId, id);
    }

    public List<Long> findTaskIdsByDoctorAndCtImage(Long doctorId, Long ctImageId) {
        return jdbcTemplate.queryForList(
                """
                SELECT id
                FROM analysis_tasks
                WHERE doctor_id = ? AND ct_image_id = ?
                """,
                Long.class,
                doctorId,
                ctImageId
        );
    }

    public void deleteCascade(Long doctorId, Long ctImageId) {
        jdbcTemplate.update(
                """
                DELETE FROM report_chat_messages
                WHERE doctor_id = ?
                  AND task_id IN (
                      SELECT id
                      FROM analysis_tasks
                      WHERE doctor_id = ? AND ct_image_id = ?
                  )
                """,
                doctorId,
                doctorId,
                ctImageId
        );
        jdbcTemplate.update(
                """
                DELETE FROM analysis_results
                WHERE doctor_id = ? AND ct_image_id = ?
                """,
                doctorId,
                ctImageId
        );
        jdbcTemplate.update(
                """
                DELETE FROM analysis_tasks
                WHERE doctor_id = ? AND ct_image_id = ?
                """,
                doctorId,
                ctImageId
        );
        delete(doctorId, ctImageId);
    }
}
