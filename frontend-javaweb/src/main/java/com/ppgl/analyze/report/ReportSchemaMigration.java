package com.ppgl.analyze.report;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
class ReportSchemaMigration implements ApplicationRunner {

    private final JdbcTemplate jdbcTemplate;

    ReportSchemaMigration(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void run(ApplicationArguments args) {
        ensureColumn("patient_visible", "ALTER TABLE analysis_results ADD COLUMN patient_visible BOOLEAN NOT NULL DEFAULT FALSE");
        ensureColumn("doctor_review_status", "ALTER TABLE analysis_results ADD COLUMN doctor_review_status VARCHAR(32) NOT NULL DEFAULT 'PENDING'");
        ensureColumn("doctor_review_note", "ALTER TABLE analysis_results ADD COLUMN doctor_review_note TEXT");
        ensureColumn("doctor_reviewed_at", "ALTER TABLE analysis_results ADD COLUMN doctor_reviewed_at TIMESTAMP NULL");
        ensureColumn("reviewed_by", "ALTER TABLE analysis_results ADD COLUMN reviewed_by BIGINT");
        ensureIndex("idx_analysis_results_patient_visible", "ALTER TABLE analysis_results ADD INDEX idx_analysis_results_patient_visible (patient_visible)");
    }

    private void ensureColumn(String columnName, String ddl) {
        Integer count = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = SCHEMA()
                  AND table_name = 'analysis_results'
                  AND column_name = ?
                """,
                Integer.class,
                columnName
        );
        if (count == null || count == 0) {
            jdbcTemplate.execute(ddl);
        }
    }

    private void ensureIndex(String indexName, String ddl) {
        Integer count = indexCount(indexName);
        if (count == null || count == 0) {
            jdbcTemplate.execute(ddl);
        }
    }

    private Integer indexCount(String indexName) {
        try {
            return jdbcTemplate.queryForObject(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.statistics
                    WHERE table_schema = SCHEMA()
                      AND table_name = 'analysis_results'
                      AND index_name = ?
                    """,
                    Integer.class,
                    indexName
            );
        } catch (BadSqlGrammarException ignored) {
            return jdbcTemplate.queryForObject(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.indexes
                    WHERE table_schema = SCHEMA()
                      AND table_name = 'analysis_results'
                      AND index_name = ?
                    """,
                    Integer.class,
                    indexName
            );
        }
    }
}
