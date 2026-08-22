package com.ppgl.analyze.care;

import java.util.List;

public record FollowUpSubmissionRequest(
        List<String> symptoms,
        String bloodPressure,
        String heartRate,
        String treatmentStatus,
        String newExamResults,
        String patientNote
) {
}
