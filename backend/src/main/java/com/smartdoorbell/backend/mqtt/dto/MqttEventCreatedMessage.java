package com.smartdoorbell.backend.mqtt.dto;

public record MqttEventCreatedMessage(Long eventId, String status) {
}
