package com.smartdoorbell.backend.event.dto;

import com.smartdoorbell.backend.event.entity.Event;
import com.smartdoorbell.backend.eventresponse.entity.EventResponseHistory;
import com.smartdoorbell.backend.feedback.AccuracyLevel;

import java.time.LocalDateTime;
import java.util.Comparator;
import java.util.List;

public record EventDetailResponse(Long eventId, Long deviceId, String status, LocalDateTime startedAt, LocalDateTime endedAt,
                                  String riskLevel, String summary, String responseCode, String responseText,
                                  String representativeImageUrl, List<Response> responses, AccuracyLevel feedback,
                                  String purpose, String conversationSummary, List<ConversationTurn> conversation) {

    public static EventDetailResponse from(Event event, String representativeImageUrl,
                                           List<EventResponseHistory> responses, AccuracyLevel feedback) {
        List<ConversationTurn> conversation = responses.stream()
                .filter(response -> response.getTurnNo() != null)
                .sorted(Comparator.comparing(EventResponseHistory::getTurnNo))
                .map(ConversationTurn::from)
                .toList();
        return new EventDetailResponse(event.getId(), event.getDevice().getId(), event.getStatus(), event.getStartedAt(),
                event.getEndedAt(), event.getRiskLevel(), event.getSummary(), event.getResponseCode(), event.getResponseText(),
                representativeImageUrl, responses.stream().map(Response::from).toList(), feedback,
                event.getPurpose(), event.getConversationSummary(), conversation);
    }

    public record Response(Long responseId, String responseCode, String responseText, LocalDateTime createdAt) {

        private static Response from(EventResponseHistory response) {
            return new Response(response.getId(), response.getResponseCode(), response.getResponseText(), response.getCreatedAt());
        }
    }

    public record ConversationTurn(Integer turnNo, String visitorText, String purpose, String responseCode, String responseText) {

        private static ConversationTurn from(EventResponseHistory response) {
            return new ConversationTurn(response.getTurnNo(), response.getVisitorText(), response.getPurpose(),
                    response.getResponseCode(), response.getResponseText());
        }
    }
}
