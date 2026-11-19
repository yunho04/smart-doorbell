package com.smartdoorbell.backend.event.controller;

import com.smartdoorbell.backend.event.dto.CreateEventRequest;
import com.smartdoorbell.backend.event.dto.EventResponse;
import com.smartdoorbell.backend.event.dto.EventResultRequest;
import com.smartdoorbell.backend.event.entity.Event;
import com.smartdoorbell.backend.event.service.EventService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/events")
public class EventController {

    private final EventService eventService;

    public EventController(EventService eventService) {
        this.eventService = eventService;
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

    // Event 조회
    @GetMapping("/{eventId}")
    public EventResponse getEvent(
            @PathVariable Long eventId
    ) {
        Event event = eventService.getEvent(eventId);

        return EventResponse.from(event);
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
