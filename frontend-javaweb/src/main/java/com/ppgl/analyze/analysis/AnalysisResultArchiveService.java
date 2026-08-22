package com.ppgl.analyze.analysis;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.ppgl.analyze.report.AnalysisResultSaveRequest;
import com.ppgl.analyze.report.ReportRepository;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class AnalysisResultArchiveService {

    private final ReportRepository reportRepository;
    private final ObjectMapper objectMapper;
    private final Path resultDir;

    public AnalysisResultArchiveService(
            ReportRepository reportRepository,
            ObjectMapper objectMapper,
            @Value("${ppgl.analysis.result-dir}") String resultDir
    ) {
        this.reportRepository = reportRepository;
        this.objectMapper = objectMapper;
        this.resultDir = Path.of(resultDir).toAbsolutePath().normalize();
    }

    public void archive(AnalysisTask task, Path jobDir) {
        try {
            Path taskDir = resultDir.resolve("task-" + task.id()).normalize();
            if (!taskDir.startsWith(resultDir)) {
                throw new AnalysisException("结果目录不合法");
            }
            Files.createDirectories(taskDir);

            Path finalDir = jobDir.resolve("final");
            Path segmentation = finalDir.resolve("segmentation.nii.gz");
            if (!Files.isRegularFile(segmentation)) {
                throw new AnalysisException("后处理结果缺少 final/segmentation.nii.gz");
            }

            copyIfExists(jobDir.resolve("metadata.json"), taskDir.resolve("metadata.json"));
            copyIfExists(jobDir.resolve("status.json"), taskDir.resolve("status.json"));
            copyDirectory(finalDir, taskDir.resolve("final"));
            copyDirectory(jobDir.resolve("ppgl_pipeline"), taskDir.resolve("ppgl_pipeline"));

            Path pipelineDir = taskDir.resolve("ppgl_pipeline");
            Path summaryPath = firstExisting(pipelineDir.resolve("result.json"), taskDir.resolve("result.json"));
            if (!Files.isRegularFile(summaryPath)) {
                summaryPath = writeSummary(task, taskDir, taskDir.resolve("final").resolve("segmentation.nii.gz"));
            }
            Path metricsPath = firstExisting(pipelineDir.resolve("clinical_metrics.json"), taskDir.resolve("final").resolve("statistics.json"));
            Path riskPath = pipelineDir.resolve("risk.json");
            Path labelMapPath = pipelineDir.resolve("label_map.json");
            Path reportPath = firstExisting(pipelineDir.resolve("report.md"), taskDir.resolve("final").resolve("report.md"));
            Path overlayPath = firstExisting(pipelineDir.resolve("overlay.png"), taskDir.resolve("final").resolve("preview.png"));

            reportRepository.save(new AnalysisResultSaveRequest(
                    task.id(),
                    task.ctImageId(),
                    task.doctorId(),
                    summaryPath.toString(),
                    pathStringIfExists(metricsPath),
                    pathStringIfExists(riskPath),
                    pathStringIfExists(labelMapPath),
                    pathStringIfExists(reportPath),
                    pathStringIfExists(overlayPath),
                    null,
                    null,
                    Files.readString(summaryPath)
            ));
        } catch (IOException ex) {
            throw new AnalysisException("分析结果归档失败：" + ex.getMessage(), ex);
        }
    }

    private Path writeSummary(AnalysisTask task, Path taskDir, Path segmentation) throws IOException {
        ObjectNode summary = objectMapper.createObjectNode();
        summary.put("taskId", task.id());
        summary.put("ctImageId", task.ctImageId());
        summary.put("patientName", task.patientName());
        summary.put("originalFilename", task.originalFilename());
        summary.put("segmentationPath", segmentation.toString());
        summary.put("message", "TotalSegmentator split inference finished");
        Path summaryPath = taskDir.resolve("result.json");
        Files.writeString(summaryPath, objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(summary));
        return summaryPath;
    }

    private void copyIfExists(Path source, Path target) throws IOException {
        if (!Files.isRegularFile(source)) {
            return;
        }
        Files.createDirectories(target.getParent());
        Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
    }

    private void copyDirectory(Path sourceDir, Path targetDir) throws IOException {
        if (!Files.isDirectory(sourceDir)) {
            return;
        }
        try (var paths = Files.walk(sourceDir)) {
            for (Path source : paths.toList()) {
                Path target = targetDir.resolve(sourceDir.relativize(source)).normalize();
                if (!target.startsWith(targetDir)) {
                    throw new AnalysisException("结果目录包含非法路径");
                }
                if (Files.isDirectory(source)) {
                    Files.createDirectories(target);
                } else {
                    Files.createDirectories(target.getParent());
                    Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
                }
            }
        }
    }

    private String pathStringIfExists(Path path) {
        return Files.isRegularFile(path) ? path.toString() : "";
    }

    private Path firstExisting(Path first, Path fallback) {
        return Files.isRegularFile(first) ? first : fallback;
    }
}
