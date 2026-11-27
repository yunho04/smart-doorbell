package com.smartdoorbell.backend.mqtt.dto;

public record MqttEventMessage(Long eventId, String status) {
}
