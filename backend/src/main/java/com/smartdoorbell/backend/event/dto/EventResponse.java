package com.smartdoorbell.backend.event.dto;

import com.smartdoorbell.backend.event.entity.Event;

import java.time.LocalDateTime;

public record EventResponse(
        Long eventId,
        Long deviceId,
        String status,
        LocalDateTime startedAt,
        LocalDateTime endedAt,
        String riskLevel,
        String summary,
        String responseCode,
        String responseText
) {

    public static EventResponse from(Event event) {
        return new EventResponse(
                event.getId(),
                event.getDevice().getId(),
                event.getStatus(),
                event.getStartedAt(),
                event.getEndedAt(),
                event.getRiskLevel(),
                event.getSummary(),
                event.getResponseCode(),
                event.getResponseText()
        );
    }
}
