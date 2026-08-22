package com.ppgl.analyze.analysis;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class AnalysisService {

    private final AnalysisRepository analysisRepository;
    private final PpglPipelineClient ppglPipelineClient;
    private final AnalysisResultArchiveService resultArchiveService;
    private final Duration taskTimeout;
    private final Path jobRoot;
    private final String pythonBin;
    private final Path pythonWorker;
    private final String pipelineMode;
    private final ExecutorService queueExecutor = Executors.newSingleThreadExecutor();
    private final AtomicBoolean workerActive = new AtomicBoolean(false);

    public AnalysisService(
            AnalysisRepository analysisRepository,
            PpglPipelineClient ppglPipelineClient,
            AnalysisResultArchiveService resultArchiveService,
            @Value("${ppgl.analysis.task-timeout-minutes:5}") long taskTimeoutMinutes,
            @Value("${ppgl.analysis.job-dir:jobs}") String jobRoot,
            @Value("${ppgl.analysis.python-bin:python3}") String pythonBin,
            @Value("${ppgl.analysis.python-worker:python-worker/worker.py}") String pythonWorker,
            @Value("${ppgl.pipeline.mode:abdomen}") String pipelineMode
    ) {
        this.analysisRepository = analysisRepository;
        this.ppglPipelineClient = ppglPipelineClient;
        this.resultArchiveService = resultArchiveService;
        this.taskTimeout = Duration.ofMinutes(Math.max(1, taskTimeoutMinutes));
        this.jobRoot = Path.of(jobRoot).toAbsolutePath().normalize();
        this.pythonBin = pythonBin;
        this.pythonWorker = Path.of(pythonWorker).toAbsolutePath().normalize();
        this.pipelineMode = pipelineMode;
    }

    @PostConstruct
    public void resumeQueue() {
        triggerWorker();
    }

    @PreDestroy
    public void shutdown() {
        queueExecutor.shutdownNow();
    }

    public AnalysisBoardResponse board(Long doctorId) {
        requireDoctorId(doctorId);
        return new AnalysisBoardResponse(
                analysisRepository.findCandidates(doctorId).stream()
                        .map(AnalysisCandidateResponse::from)
                        .toList(),
                taskResponses(doctorId)
        );
    }

    public AnalysisBoardResponse submit(AnalysisSubmitRequest request) {
        if (request == null || request.ctImageIds() == null || request.ctImageIds().isEmpty()) {
            throw new AnalysisException("请选择要分析的 CT");
        }
        requireDoctorId(request.requesterId());

        String mode = normalizeOption(request.mode(), "total");
        String device = normalizeOption(request.device(), "cuda");
        List<AnalysisTask> createdTasks = new ArrayList<>();

        for (Long ctImageId : request.ctImageIds()) {
            if (ctImageId == null || analysisRepository.hasActiveTaskForCt(ctImageId)) {
                continue;
            }
            AnalysisCandidate candidate = analysisRepository.findCandidateById(ctImageId, request.requesterId())
                    .orElse(null);
            if (candidate == null || !isEligible(candidate.status())) {
                continue;
            }
            AnalysisTask task = analysisRepository.createTask(candidate, request.requesterId(), mode, device);
            analysisRepository.updateCtStatus(candidate.ctImageId(), AnalysisStatuses.CT_QUEUED);
            createdTasks.add(task);
        }

        if (createdTasks.isEmpty()) {
            throw new AnalysisException("没有可提交的 CT，可能已经在队列中");
        }

        triggerWorker();
        return board(request.requesterId());
    }

    private List<AnalysisTaskResponse> taskResponses(Long doctorId) {
        List<AnalysisTask> tasks = analysisRepository.findTasks(doctorId);
        Map<Long, Integer> queuePositions = new HashMap<>();
        int position = 1;
        for (AnalysisTask task : tasks) {
            if (AnalysisStatuses.TASK_QUEUED.equals(task.status())) {
                queuePositions.put(task.id(), position);
                position += 1;
            }
        }
        return tasks.stream()
                .map(task -> AnalysisTaskResponse.from(task, queuePositions))
                .toList();
    }

    private void triggerWorker() {
        if (workerActive.compareAndSet(false, true)) {
            queueExecutor.submit(this::drainQueue);
        }
    }

    private void drainQueue() {
        try {
            while (!Thread.currentThread().isInterrupted()) {
                AnalysisTask task = analysisRepository.findNextQueuedTask().orElse(null);
                if (task == null) {
                    break;
                }
                processTask(task);
            }
        } finally {
            workerActive.set(false);
            if (analysisRepository.findNextQueuedTask().isPresent()) {
                triggerWorker();
            }
        }
    }

    private void processTask(AnalysisTask task) {
        try {
            Path ctPath = Path.of(task.filePath());
            if (!Files.exists(ctPath)) {
                failTask(task, "本地 CT 文件不存在：" + ctPath);
                return;
            }
            if (!isSupportedInput(task.originalFilename())) {
                failTask(task, "当前仅支持 DICOM 目录、.nii、.nii.gz 文件");
                return;
            }

            analysisRepository.updateCtStatus(task.ctImageId(), AnalysisStatuses.CT_RUNNING);
            String jobId = "task-" + task.id();
            Path jobDir = jobRoot.resolve(jobId).normalize();
            if (!jobDir.startsWith(jobRoot)) {
                failTask(task, "任务目录不合法");
                return;
            }
            Files.createDirectories(jobDir.resolve("input"));
            Files.createDirectories(jobDir.resolve("preprocessed"));
            Files.createDirectories(jobDir.resolve("jetson_result"));
            Files.createDirectories(jobDir.resolve("final"));

            Path inputCopy = jobDir.resolve("input").resolve(ctPath.getFileName()).normalize();
            Files.copy(ctPath, inputCopy, StandardCopyOption.REPLACE_EXISTING);

            analysisRepository.setJetsonCaseId(task.id(), jobId);
            analysisRepository.markTaskStarted(task.id(), AnalysisStatuses.TASK_PREPROCESSING, 10, "preprocessing", "正在进行本机预处理");
            runPythonWorker("prepare", task, jobId, jobDir, inputCopy);

            analysisRepository.updateTaskProgress(task.id(), AnalysisStatuses.TASK_UPLOADING, 35, "uploading", "正在上传 CT 到 PPGL 主后端");
            ppglPipelineClient.run(
                    jobDir.resolve("input").resolve("original.nii.gz"),
                    jobDir.resolve("ppgl_pipeline"),
                    pipelineMode,
                    task.device()
            );

            analysisRepository.updateTaskProgress(task.id(), AnalysisStatuses.TASK_POSTPROCESSING, 92, "ppgl_pipeline", "正在整理 PPGL 主后端分析结果");
            applyPpglPipelineResult(jobDir);

            analysisRepository.updateTaskProgress(task.id(), AnalysisStatuses.TASK_POSTPROCESSING, 95, "archiving", "正在保存分析结果");
            runPythonWorker("mesh", task, jobId, jobDir, inputCopy);
            resultArchiveService.archive(task, jobDir);
            analysisRepository.markTaskDone(task.id(), "AI 分析完成");
            analysisRepository.updateCtStatus(task.ctImageId(), AnalysisStatuses.CT_DONE);
        } catch (Exception ex) {
            failTask(task, ex.getMessage() == null ? "分析任务异常" : ex.getMessage());
        }
    }

    private void failTask(AnalysisTask task, String reason) {
        analysisRepository.markTaskFailed(task.id(), reason);
        analysisRepository.updateCtStatus(task.ctImageId(), AnalysisStatuses.CT_FAILED);
    }

    private boolean isEligible(String status) {
        return AnalysisStatuses.CT_PENDING.equals(status) || AnalysisStatuses.CT_FAILED.equals(status);
    }

    private String normalizeOption(String value, String fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        return value.trim();
    }

    private boolean isSupportedInput(String filename) {
        String lower = filename == null ? "" : filename.toLowerCase(Locale.ROOT);
        return lower.endsWith(".nii") || lower.endsWith(".nii.gz") || !lower.contains(".");
    }

    private void runPythonWorker(String action, AnalysisTask task, String jobId, Path jobDir, Path inputPath)
            throws IOException, InterruptedException {
        if (!Files.isRegularFile(pythonWorker)) {
            throw new AnalysisException("Python worker 不存在：" + pythonWorker);
        }
        List<String> command = new ArrayList<>();
        command.add(pythonBin);
        command.add(pythonWorker.toString());
        command.add(action);
        command.add("--job-id");
        command.add(jobId);
        command.add("--job-dir");
        command.add(jobDir.toString());
        command.add("--task");
        command.add(task.mode());
        if ("prepare".equals(action)) {
            command.add("--input");
            command.add(inputPath.toString());
        }

        Process process = new ProcessBuilder(command)
                .directory(Path.of(".").toAbsolutePath().normalize().toFile())
                .redirectErrorStream(true)
                .start();
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        process.getInputStream().transferTo(output);
        boolean finished = process.waitFor(taskTimeout.toMinutes(), TimeUnit.MINUTES);
        if (!finished) {
            process.destroyForcibly();
            throw new AnalysisException(action + " 超过 " + taskTimeout.toMinutes() + " 分钟未完成");
        }
        if (process.exitValue() != 0) {
            throw new AnalysisException(action + " 执行失败：" + output.toString());
        }
    }

    private void applyPpglPipelineResult(Path jobDir) throws IOException {
        Path pipelineDir = jobDir.resolve("ppgl_pipeline");
        Path fusedMask = pipelineDir.resolve("mask.nii.gz");
        if (!Files.isRegularFile(fusedMask)) {
            throw new AnalysisException("PPGL 主后端结果缺少融合总标签 mask.nii.gz");
        }
        Path finalDir = jobDir.resolve("final");
        Path segmentation = finalDir.resolve("segmentation.nii.gz");
        Path originalTotalseg = finalDir.resolve("totalseg_segmentation.nii.gz");
        if (Files.isRegularFile(segmentation) && !Files.isRegularFile(originalTotalseg)) {
            Files.copy(segmentation, originalTotalseg, StandardCopyOption.REPLACE_EXISTING);
        }
        Files.copy(fusedMask, segmentation, StandardCopyOption.REPLACE_EXISTING);
        Path labelMap = pipelineDir.resolve("label_map.json");
        if (Files.isRegularFile(labelMap)) {
            Files.copy(labelMap, finalDir.resolve("label_map.json"), StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private void requireDoctorId(Long doctorId) {
        if (doctorId == null) {
            throw new AnalysisException("医生账号不能为空");
        }
    }
}
