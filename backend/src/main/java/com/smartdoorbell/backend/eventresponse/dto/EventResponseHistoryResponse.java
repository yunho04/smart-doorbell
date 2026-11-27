package com.smartdoorbell.backend.eventresponse.dto;

import com.smartdoorbell.backend.eventresponse.entity.EventResponseHistory;

import java.time.LocalDateTime;

public record EventResponseHistoryResponse(
        Long responseId,
        Long eventId,
        String responseCode,
        String responseText,
        LocalDateTime createdAt
) {

    public static EventResponseHistoryResponse from(
            EventResponseHistory response
    ) {
        return new EventResponseHistoryResponse(
                response.getId(),
                response.getEvent().getId(),
                response.getResponseCode(),
                response.getResponseText(),
                response.getCreatedAt()
        );
    }
}
