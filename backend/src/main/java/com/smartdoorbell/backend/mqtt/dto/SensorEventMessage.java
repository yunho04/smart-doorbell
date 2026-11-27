package com.smartdoorbell.backend.mqtt.dto;

public record SensorEventMessage(
        Long deviceId,
        String sensorType,
        Double value,
        Boolean presenceDetected
) {
    public boolean isPresenceDetected() {
        return presenceDetected != null ? presenceDetected : value != null && value > 0;
    }
}
