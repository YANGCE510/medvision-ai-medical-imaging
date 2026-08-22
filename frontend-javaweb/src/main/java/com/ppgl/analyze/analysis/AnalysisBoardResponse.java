package com.ppgl.analyze.analysis;

import java.util.List;

public record AnalysisBoardResponse(
        List<AnalysisCandidateResponse> candidates,
        List<AnalysisTaskResponse> tasks
) {
}
