package com.smartdoorbell.backend.event.service;

import com.smartdoorbell.backend.event.dto.EventDetailResponse;
import com.smartdoorbell.backend.event.dto.EventSummaryResponse;
import com.smartdoorbell.backend.event.entity.Event;
import com.smartdoorbell.backend.event.repository.EventRepository;
import com.smartdoorbell.backend.eventresponse.repository.EventResponseHistoryRepository;
import com.smartdoorbell.backend.feedback.AccuracyLevel;
import com.smartdoorbell.backend.feedback.Feedback;
import com.smartdoorbell.backend.feedback.FeedbackRepository;
import com.smartdoorbell.backend.media.dto.RepresentativeImageResponse;
import com.smartdoorbell.backend.media.service.MediaService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

@Service
@Transactional(readOnly = true)
public class EventQueryService {

    private final EventService eventService;
    private final EventRepository eventRepository;
    private final EventResponseHistoryRepository responseRepository;
    private final FeedbackRepository feedbackRepository;
    private final MediaService mediaService;

    public EventQueryService(EventService eventService, EventRepository eventRepository,
                             EventResponseHistoryRepository responseRepository, FeedbackRepository feedbackRepository,
                             MediaService mediaService) {
        this.eventService = eventService;
        this.eventRepository = eventRepository;
        this.responseRepository = responseRepository;
        this.feedbackRepository = feedbackRepository;
        this.mediaService = mediaService;
    }

    public List<EventSummaryResponse> listEvents() {
        List<Event> events = eventRepository.findAllByOrderByStartedAtDescIdDesc();
        Set<Long> imageEventIds = mediaService.findRepresentativeImageEventIds();
        Map<Long, AccuracyLevel> feedbackByEvent = feedbackRepository.findAll().stream()
                .collect(Collectors.toMap(Feedback::getEventId, Feedback::getAccuracyLevel));

        return events.stream().map(event -> {
            Long eventId = event.getId();
            String imageUrl = imageEventIds.contains(eventId) ? RepresentativeImageResponse.imageUrl(eventId) : null;
            return EventSummaryResponse.from(event, imageUrl, feedbackByEvent.get(eventId));
        }).toList();
    }

    // Read result metadata and the replaceable response history from the same snapshot.
    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    public EventDetailResponse getEvent(Long eventId) {
        Event event = eventService.getEvent(eventId);
        String imageUrl = mediaService.hasRepresentativeImage(eventId) ? RepresentativeImageResponse.imageUrl(eventId) : null;
        AccuracyLevel feedback = feedbackRepository.findByEventId(eventId).map(Feedback::getAccuracyLevel).orElse(null);

        return EventDetailResponse.from(event, imageUrl, responseRepository.findAllByEventIdOrderByCreatedAtAscIdAsc(eventId), feedback);
    }
}
