package com.smartdoorbell.backend.event.service;

import com.smartdoorbell.backend.llm.LlmClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;

@Component
public class EventInactivityScheduler {

    private static final Logger log = LoggerFactory.getLogger(EventInactivityScheduler.class);

    private final EventService eventService;
    private final LlmClient llmClient;

    public EventInactivityScheduler(EventService eventService, LlmClient llmClient) {
        this.eventService = eventService;
        this.llmClient = llmClient;
    }

    @Scheduled(fixedDelay = 1000)
    public void finalizeInactiveEvents() {
        for (Long eventId : eventService.findInactiveEventIds()) {
            if (eventService.startAnalysisIfInactive(eventId)) {
                try {
                    llmClient.finalizeEvent(eventId);
                } catch (RestClientException e) {
                    log.error("LLM finalize failed for event {}", eventId, e);
                }
            }
        }
    }
}
