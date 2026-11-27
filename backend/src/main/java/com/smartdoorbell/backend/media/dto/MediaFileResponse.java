package com.smartdoorbell.backend.media.dto;

import com.smartdoorbell.backend.media.entity.MediaFile;

public record MediaFileResponse(
        Long mediaId,
        Long eventId,
        String mediaType,
        String filePath
) {

    public static MediaFileResponse from(MediaFile mediaFile) {
        return new MediaFileResponse(
                mediaFile.getId(),
                mediaFile.getEvent().getId(),
                mediaFile.getMediaType(),
                mediaFile.getFilePath()
        );
    }
}