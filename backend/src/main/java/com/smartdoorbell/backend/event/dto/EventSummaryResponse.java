package com.smartdoorbell.backend.event.dto;

import com.smartdoorbell.backend.event.entity.Event;
import com.smartdoorbell.backend.feedback.AccuracyLevel;

import java.time.LocalDateTime;

public record EventSummaryResponse(Long eventId, String status, LocalDateTime startedAt, LocalDateTime endedAt,
                                   String riskLevel, String summary, String representativeImageUrl, AccuracyLevel feedback) {

    public static EventSummaryResponse from(Event event, String representativeImageUrl, AccuracyLevel feedback) {
        return new EventSummaryResponse(event.getId(), event.getStatus(), event.getStartedAt(), event.getEndedAt(),
                event.getRiskLevel(), event.getSummary(), representativeImageUrl, feedback);
    }
}
