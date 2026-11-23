package com.smartdoorbell.backend.event.dto;

import com.smartdoorbell.backend.event.entity.Event;
import com.smartdoorbell.backend.eventresponse.entity.EventResponseHistory;
import com.smartdoorbell.backend.feedback.AccuracyLevel;

import java.time.LocalDateTime;
import java.util.List;

public record EventDetailResponse(Long eventId, Long deviceId, String status, LocalDateTime startedAt, LocalDateTime endedAt,
                                  String riskLevel, String summary, String responseCode, String responseText,
                                  String representativeImageUrl, List<Response> responses, AccuracyLevel feedback) {

    public static EventDetailResponse from(Event event, String representativeImageUrl,
                                           List<EventResponseHistory> responses, AccuracyLevel feedback) {
        return new EventDetailResponse(event.getId(), event.getDevice().getId(), event.getStatus(), event.getStartedAt(),
                event.getEndedAt(), event.getRiskLevel(), event.getSummary(), event.getResponseCode(), event.getResponseText(),
                representativeImageUrl, responses.stream().map(Response::from).toList(), feedback);
    }

    public record Response(Long responseId, String responseCode, String responseText, LocalDateTime createdAt) {

        private static Response from(EventResponseHistory response) {
            return new Response(response.getId(), response.getResponseCode(), response.getResponseText(), response.getCreatedAt());
        }
    }
}
