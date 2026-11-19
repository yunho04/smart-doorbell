package com.smartdoorbell.backend.event.service;

import com.smartdoorbell.backend.device.entity.Device;
import com.smartdoorbell.backend.device.repository.DeviceRepository;
import com.smartdoorbell.backend.event.entity.Event;
import com.smartdoorbell.backend.event.repository.EventRepository;
import com.smartdoorbell.backend.eventresponse.entity.EventResponseHistory;
import com.smartdoorbell.backend.eventresponse.repository.EventResponseHistoryRepository;
import com.smartdoorbell.backend.mqtt.dto.MqttEventCreatedMessage;
import com.smartdoorbell.backend.mqtt.dto.MqttResponseMessage;
import com.smartdoorbell.backend.mqtt.service.MqttPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

@Service
@Transactional
public class EventService {

    private static final String DETECTED = "DETECTED";
    private static final long INACTIVITY_SECONDS = 10;

    private final MqttPublisher mqttPublisher;
    private final EventRepository eventRepository;
    private final DeviceRepository deviceRepository;
    private final EventResponseHistoryRepository eventResponseHistoryRepository;

    public EventService(
            EventRepository eventRepository,
            DeviceRepository deviceRepository,
            EventResponseHistoryRepository eventResponseHistoryRepository,
            MqttPublisher mqttPublisher
    ) {
        this.mqttPublisher = mqttPublisher;
        this.eventRepository = eventRepository;
        this.deviceRepository = deviceRepository;
        this.eventResponseHistoryRepository = eventResponseHistoryRepository;
    }

    // 1. 새로운 Event 생성
    public Event createEvent(Long deviceId) {

        Device device = deviceRepository.findById(deviceId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Device not found: " + deviceId)
                );

        Event event = new Event(device);

        return eventRepository.save(event);
    }

    public void detectPresence(Long deviceId) {
        // Serialize sensor-driven creation even when no active event exists yet.
        Device device = deviceRepository.findLockedById(deviceId)
                .orElseThrow(() -> new IllegalArgumentException("Device not found: " + deviceId));

        Event activeEvent = eventRepository
                .findFirstByDeviceIdAndStatusOrderByStartedAtDescIdDesc(deviceId, DETECTED)
                .orElse(null);
        if (activeEvent != null) {
            activeEvent.updateLastDetectedAt();
            return;
        }

        Event event = eventRepository.save(new Event(device));
        mqttPublisher.publishAfterCommit(
                "doorbell/" + deviceId + "/event",
                new MqttEventCreatedMessage(event.getId(), "CREATED")
        );
    }

    @Transactional(readOnly = true)
    public List<Long> findInactiveEventIds() {
        return eventRepository.findInactiveIds(DETECTED, LocalDateTime.now().minusSeconds(INACTIVITY_SECONDS));
    }

    public boolean startAnalysisIfInactive(Long eventId) {
        Event event = eventRepository.findLockedById(eventId).orElse(null);
        if (event == null || !DETECTED.equals(event.getStatus())) {
            return false;
        }

        LocalDateTime lastDetection = event.getLastDetectedAt();
        if (lastDetection == null) {
            lastDetection = event.getStartedAt();
        }

        LocalDateTime now = LocalDateTime.now();
        if (lastDetection.isAfter(now.minusSeconds(INACTIVITY_SECONDS))) {
            return false;
        }

        event.startAnalysis(now);
        return true;
    }

    // 2. Event 조회
    @Transactional(readOnly = true)
    public Event getEvent(Long eventId) {

        return eventRepository.findById(eventId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Event not found: " + eventId)
                );
    }

    // 3. LLM 최종 결과 저장
    public Event completeEvent(
            Long eventId,
            String riskLevel,
            String summary,
            String responseCode,
            String responseText
    ) {

        Event event = eventRepository.findLockedById(eventId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Event not found: " + eventId)
                );

        event.complete(
                riskLevel,
                summary,
                responseCode,
                responseText
        );

        return event;
    }

    public EventResponseHistory saveResponse(
            Long eventId,
            String responseCode,
            String responseText
    ) {
        Event event = eventRepository.findById(eventId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Event not found: " + eventId)
                );

        EventResponseHistory response =
                new EventResponseHistory(
                        event,
                        responseCode,
                        responseText
                );

        EventResponseHistory savedResponse = eventResponseHistoryRepository.save(response);
        mqttPublisher.publishAfterCommit(
                "doorbell/" + event.getDevice().getId() + "/response",
                new MqttResponseMessage(eventId, responseCode, responseText)
        );
        return savedResponse;
    }
}
