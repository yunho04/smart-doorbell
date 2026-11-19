package com.smartdoorbell.backend.eventresponse.controller;

import com.smartdoorbell.backend.event.service.EventService;
import com.smartdoorbell.backend.eventresponse.dto.EventResponseHistoryResponse;
import com.smartdoorbell.backend.eventresponse.dto.EventResponseRequest;
import com.smartdoorbell.backend.eventresponse.entity.EventResponseHistory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/events")
public class EventResponseController {

    private final EventService eventService;

    public EventResponseController(EventService eventService) {
        this.eventService = eventService;
    }

    @PostMapping("/{eventId}/response")
    public ResponseEntity<EventResponseHistoryResponse> saveResponse(
            @PathVariable Long eventId,
            @RequestBody EventResponseRequest request
    ) {

        EventResponseHistory response =
                eventService.saveResponse(
                        eventId,
                        request.responseCode(),
                        request.responseText()
                );

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(EventResponseHistoryResponse.from(response));
    }
}
