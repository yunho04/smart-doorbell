package com.smartdoorbell.backend.media.controller;

import com.smartdoorbell.backend.auth.SessionAuthentication;
import com.smartdoorbell.backend.media.dto.MediaFileResponse;
import com.smartdoorbell.backend.media.dto.RepresentativeImageResponse;
import com.smartdoorbell.backend.media.entity.MediaFile;
import com.smartdoorbell.backend.media.service.MediaService;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
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

    @PostMapping(path = "/{eventId}/representative-image", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public RepresentativeImageResponse uploadRepresentativeImage(@PathVariable Long eventId,
                                                                @RequestParam("file") MultipartFile file) {
        MediaFile image = mediaService.saveRepresentativeImage(eventId, file);
        return new RepresentativeImageResponse(eventId, image.getId(), RepresentativeImageResponse.imageUrl(eventId), "SAVED");
    }

    @SessionAuthentication.Required
    @GetMapping("/{eventId}/image")
    public ResponseEntity<byte[]> getImage(@PathVariable Long eventId) {
        MediaService.RepresentativeImage image = mediaService.getRepresentativeImage(eventId);
        return ResponseEntity.ok()
                .header("X-Content-Type-Options", "nosniff")
                .contentType(image.contentType())
                .body(image.data());
    }
}
