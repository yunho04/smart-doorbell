package com.smartdoorbell.backend.llm;

import com.smartdoorbell.backend.feedback.AccuracyLevel;

import java.util.List;

public record LlmFeedbackRequest(
        Long eventId,
        String summary,
        String accuracyLevel
) {


    public record Response(String responseCode, String responseText) {
    }
}
