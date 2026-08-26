package com.ppgl.analyze.analysis;

import java.util.List;

public record AnalysisSubmitRequest(
        List<Long> ctImageIds,
        String mode,
        String device
) {
}
