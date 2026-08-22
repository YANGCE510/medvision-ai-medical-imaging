package com.ppgl.analyze.analysis;

record ComputeNodeStatusResponse(
        String status,
        boolean available,
        boolean hostReachable,
        boolean serviceReachable,
        boolean healthReachable,
        String baseUrl,
        String host,
        String hostAddress,
        int port,
        long latencyMs,
        String healthStatus,
        String message,
        String checkedAt
) {
}
