package com.smartdoorbell.backend.eventresponse.controller;

import com.smartdoorbell.backend.event.service.EventService;
import com.smartdoorbell.backend.eventresponse.dto.EventResponseHistoryResponse;
import com.smartdoorbell.backend.eventresponse.dto.EventResponseRequest;
import com.smartdoorbell.backend.eventresponse.entity.EventResponseHistory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import com.smartdoorbell.backend.mqtt.service.MqttPublisher;
import tools.jackson.databind.json.JsonMapper;
import com.smartdoorbell.backend.mqtt.dto.MqttResponseMessage;
import tools.jackson.core.JacksonException;

@RestController
@RequestMapping("/api/v1/events")
public class EventResponseController {

    private final EventService eventService;
    private final MqttPublisher mqttPublisher;
    private final JsonMapper jsonMapper;

    public EventResponseController(
            EventService eventService,
            MqttPublisher mqttPublisher,
            JsonMapper jsonMapper
    ) {
        this.eventService = eventService;
        this.mqttPublisher = mqttPublisher;
        this.jsonMapper = jsonMapper;
    }

    @PostMapping("/{eventId}/response")
    public ResponseEntity<EventResponseHistoryResponse> saveResponse(
            @PathVariable Long eventId,
            @RequestBody EventResponseRequest request
    ) throws JacksonException {

        EventResponseHistory response =
                eventService.saveResponse(
                        eventId,
                        request.responseCode(),
                        request.responseText()
                );

        Long deviceId = response.getEvent().getDevice().getId();

        MqttResponseMessage mqttMessage =
                new MqttResponseMessage(
                        eventId,
                        request.responseCode(),
                        request.responseText()
                );

        String payload = jsonMapper.writeValueAsString(mqttMessage);

        String topic = "doorbell/" + deviceId + "/response";

        mqttPublisher.publish(topic, payload);

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(EventResponseHistoryResponse.from(response));
    }
}