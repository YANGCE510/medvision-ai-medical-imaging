package com.ppgl.analyze.care;

public record FollowUpPlanRequest(
        Long taskId,
        String followUpDate,
        String reason,
        String preparation
) {
}
