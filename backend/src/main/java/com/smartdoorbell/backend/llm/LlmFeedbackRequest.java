package com.smartdoorbell.backend.llm;

import com.smartdoorbell.backend.feedback.AccuracyLevel;

import java.util.List;

public record LlmFeedbackRequest(Long eventId, String riskLevel, String summary, AccuracyLevel accuracyLevel,
                                 List<Response> responses) {

    public record Response(String responseCode, String responseText) {
    }
}
