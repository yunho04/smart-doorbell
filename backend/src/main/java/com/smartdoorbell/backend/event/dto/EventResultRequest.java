package com.smartdoorbell.backend.event.dto;

import com.smartdoorbell.backend.eventresponse.dto.EventResponseRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

import java.util.List;

public record EventResultRequest(
        String riskLevel,
        String summary,
        String responseCode,
        String responseText,
        String purpose,
        String conversationSummary,
        @Valid List<@NotNull ConversationTurn> conversation,
        List<EventResponseRequest> responses
) {
    public record ConversationTurn(
            @NotNull Integer turnNo,
            String visitorText,
            String purpose,
            @NotNull String responseCode,
            @NotNull String responseText
    ) {
    }
}
