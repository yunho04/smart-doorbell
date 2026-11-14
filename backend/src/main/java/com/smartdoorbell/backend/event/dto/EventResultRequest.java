package com.smartdoorbell.backend.event.dto;

public record EventResultRequest(
        String riskLevel,
        String summary,
        String responseCode,
        String responseText
) {
}
