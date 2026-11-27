package com.smartdoorbell.backend.media.dto;

public record RepresentativeImageResponse(Long eventId, Long mediaId, String imageUrl, String status) {

    public static String imageUrl(Long eventId) {
        return "/api/v1/events/" + eventId + "/image";
    }
}
