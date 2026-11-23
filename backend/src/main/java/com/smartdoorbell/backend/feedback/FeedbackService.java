package com.smartdoorbell.backend.feedback;

import com.smartdoorbell.backend.event.EventNotFoundException;
import com.smartdoorbell.backend.event.entity.Event;
import com.smartdoorbell.backend.event.repository.EventRepository;
import com.smartdoorbell.backend.eventresponse.repository.EventResponseHistoryRepository;
import com.smartdoorbell.backend.llm.LlmClient;
import com.smartdoorbell.backend.llm.LlmFeedbackRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.client.RestClientException;

import java.util.List;

@Service
public class FeedbackService {

    private static final Logger log = LoggerFactory.getLogger(FeedbackService.class);

    private final EventRepository eventRepository;
    private final FeedbackRepository feedbackRepository;
    private final EventResponseHistoryRepository responseRepository;
    private final LlmClient llmClient;

    public FeedbackService(EventRepository eventRepository, FeedbackRepository feedbackRepository,
                           EventResponseHistoryRepository responseRepository, LlmClient llmClient) {
        this.eventRepository = eventRepository;
        this.feedbackRepository = feedbackRepository;
        this.responseRepository = responseRepository;
        this.llmClient = llmClient;
    }

    @Transactional
    public void saveFeedback(Long eventId, AccuracyLevel accuracyLevel) {
        Event event = eventRepository.findLockedById(eventId)
                .orElseThrow(() -> new EventNotFoundException(eventId));

        Feedback feedback = feedbackRepository.findByEventId(eventId).orElse(null);
        if (feedback == null) {
            feedbackRepository.save(new Feedback(event, accuracyLevel));
        } else {
            feedback.updateAccuracy(accuracyLevel);
        }

        List<LlmFeedbackRequest.Response> responses = responseRepository.findAllByEventIdOrderByCreatedAtAscIdAsc(eventId)
                .stream()
                .map(response -> new LlmFeedbackRequest.Response(response.getResponseCode(), response.getResponseText()))
                .toList();
        LlmFeedbackRequest request = new LlmFeedbackRequest(eventId, event.getRiskLevel(), event.getSummary(), accuracyLevel, responses);

        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                try {
                    llmClient.sendFeedback(request);
                } catch (RestClientException e) {
                    log.warn("LLM feedback failed for event {}", eventId, e);
                }
            }
        });
    }
}
