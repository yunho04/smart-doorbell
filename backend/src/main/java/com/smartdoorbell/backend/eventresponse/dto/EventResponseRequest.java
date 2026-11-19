package com.smartdoorbell.backend.eventresponse.dto;

public record EventResponseRequest(
        String responseCode,
        String responseText
) {
}
