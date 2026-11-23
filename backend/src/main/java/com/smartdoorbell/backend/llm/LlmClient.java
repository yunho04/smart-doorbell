package com.smartdoorbell.backend.llm;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.util.Map;

@Component
public class LlmClient {

    private final RestClient restClient;

    public LlmClient(@Value("${llm.base-url}") String baseUrl) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofSeconds(2));
        requestFactory.setReadTimeout(Duration.ofSeconds(3));
        this.restClient = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(requestFactory)
                .build();
    }

    public void finalizeEvent(Long eventId) {
        restClient.post()
                .uri("/api/v1/events/{eventId}/finalize", eventId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("eventId", eventId))
                .retrieve()
                .toBodilessEntity();
    }

    public void sendFeedback(LlmFeedbackRequest request) {
        restClient.post()
                .uri("/api/v1/events/{eventId}/feedback", request.eventId())
                .contentType(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .toBodilessEntity();
    }
}
