package com.smartdoorbell.backend.event.service;

import com.smartdoorbell.backend.device.entity.Device;
import com.smartdoorbell.backend.device.repository.DeviceRepository;
import com.smartdoorbell.backend.event.entity.Event;
import com.smartdoorbell.backend.event.repository.EventRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional
public class EventService {

    private final EventRepository eventRepository;
    private final DeviceRepository deviceRepository;

    public EventService(
            EventRepository eventRepository,
            DeviceRepository deviceRepository
    ) {
        this.eventRepository = eventRepository;
        this.deviceRepository = deviceRepository;
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

        Event event = eventRepository.findById(eventId)
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
}
