package com.smartdoorbell.backend.media.controller;

import com.smartdoorbell.backend.media.dto.MediaFileResponse;
import com.smartdoorbell.backend.media.entity.MediaFile;
import com.smartdoorbell.backend.media.service.MediaService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/v1/events")
public class MediaController {

    private final MediaService mediaService;

    public MediaController(MediaService mediaService) {
        this.mediaService = mediaService;
    }

    @PostMapping("/{eventId}/image")
    @ResponseStatus(HttpStatus.CREATED)
    public MediaFileResponse uploadImage(
            @PathVariable Long eventId,
            @RequestParam("file") MultipartFile file
    ) {

        MediaFile mediaFile = mediaService.saveImage(eventId, file);

        return MediaFileResponse.from(mediaFile);
    }
}
