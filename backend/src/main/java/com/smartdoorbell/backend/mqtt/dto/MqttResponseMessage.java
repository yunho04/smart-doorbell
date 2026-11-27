package com.smartdoorbell.backend.mqtt.dto;

public record MqttResponseMessage(
        Long eventId,
        String responseCode,
        String responseText
) {
}