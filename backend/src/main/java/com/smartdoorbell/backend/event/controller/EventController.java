package com.smartdoorbell.backend.event.controller;

import com.smartdoorbell.backend.auth.SessionAuthentication;
import com.smartdoorbell.backend.event.dto.CreateEventRequest;
import com.smartdoorbell.backend.event.dto.EventDetailResponse;
import com.smartdoorbell.backend.event.dto.EventResponse;
import com.smartdoorbell.backend.event.dto.EventResultRequest;
import com.smartdoorbell.backend.event.dto.EventSummaryResponse;
import com.smartdoorbell.backend.event.entity.Event;
import com.smartdoorbell.backend.event.service.EventQueryService;
import com.smartdoorbell.backend.event.service.EventService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1/events")
public class EventController {

    private final EventService eventService;
    private final EventQueryService eventQueryService;

    public EventController(EventService eventService, EventQueryService eventQueryService) {
        this.eventService = eventService;
        this.eventQueryService = eventQueryService;
    }

    // Event 생성
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public EventResponse createEvent(
            @RequestBody CreateEventRequest request
    ) {
        Event event = eventService.createEvent(request.deviceId());

        return EventResponse.from(event);
    }

    @SessionAuthentication.Required
    @GetMapping
    public List<EventSummaryResponse> listEvents() {
        return eventQueryService.listEvents();
    }

    @SessionAuthentication.Required
    @GetMapping("/{eventId}")
    public EventDetailResponse getEvent(@PathVariable Long eventId) {
        return eventQueryService.getEvent(eventId);
    }

    // LLM 최종 결과 저장
    @PostMapping("/{eventId}/result")
    public EventResponse saveResult(
            @PathVariable Long eventId,
            @RequestBody EventResultRequest request
    ) {
        Event event = eventService.completeEvent(
                eventId,
                request.riskLevel(),
                request.summary(),
                request.responseCode(),
                request.responseText()
        );

        return EventResponse.from(event);
    }
}
