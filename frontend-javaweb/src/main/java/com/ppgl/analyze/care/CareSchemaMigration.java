package com.ppgl.analyze.care;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
class CareSchemaMigration implements ApplicationRunner {

    private final JdbcTemplate jdbcTemplate;

    CareSchemaMigration(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void run(ApplicationArguments args) {
        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS follow_up_plans (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    task_id BIGINT NOT NULL,
                    doctor_id BIGINT NOT NULL,
                    follow_up_date DATE NOT NULL,
                    reason VARCHAR(500) NOT NULL,
                    preparation VARCHAR(500),
                    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_follow_up_plans_task_id (task_id),
                    INDEX idx_follow_up_plans_doctor_id (doctor_id),
                    INDEX idx_follow_up_plans_status (status),
                    INDEX idx_follow_up_plans_date (follow_up_date)
                )
                """);
        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS follow_up_submissions (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    plan_id BIGINT NOT NULL,
                    task_id BIGINT NOT NULL,
                    patient_user_id BIGINT NOT NULL,
                    symptoms TEXT,
                    blood_pressure VARCHAR(80),
                    heart_rate VARCHAR(80),
                    treatment_status VARCHAR(120),
                    new_exam_results TEXT,
                    patient_note TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_follow_up_submissions_plan_id (plan_id),
                    INDEX idx_follow_up_submissions_task_id (task_id),
                    INDEX idx_follow_up_submissions_patient (patient_user_id)
                )
                """);
        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS patient_feedbacks (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    task_id BIGINT NOT NULL,
                    doctor_id BIGINT NOT NULL,
                    patient_user_id BIGINT NOT NULL,
                    question TEXT NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
                    doctor_reply TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_patient_feedbacks_doctor_id (doctor_id),
                    INDEX idx_patient_feedbacks_task_id (task_id),
                    INDEX idx_patient_feedbacks_status (status)
                )
                """);
    }
}
