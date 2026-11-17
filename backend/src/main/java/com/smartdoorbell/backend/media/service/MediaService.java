package com.smartdoorbell.backend.media.service;

import com.smartdoorbell.backend.event.entity.Event;
import com.smartdoorbell.backend.event.repository.EventRepository;
import com.smartdoorbell.backend.media.entity.MediaFile;
import com.smartdoorbell.backend.media.repository.MediaFileRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;

@Service
@Transactional
public class MediaService {

    private final MediaFileRepository mediaFileRepository;
    private final EventRepository eventRepository;

    public MediaService(
            MediaFileRepository mediaFileRepository,
            EventRepository eventRepository
    ) {
        this.mediaFileRepository = mediaFileRepository;
        this.eventRepository = eventRepository;
    }

    public MediaFile saveImage(Long eventId, MultipartFile file) {

        // 1. Event가 실제로 존재하는지 확인
        Event event = eventRepository.findById(eventId)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Event not found: " + eventId
                        )
                );

        try {
            // 2. 저장 폴더 생성
            Path eventDirectory = Paths.get(
                    "uploads",
                    "events",
                    eventId.toString()
            );

            Files.createDirectories(eventDirectory);

            // 3. 대표 사진 파일 경로
            Path filePath = eventDirectory.resolve("visitor.jpg");

            // 4. 실제 사진 저장
            Files.copy(
                    file.getInputStream(),
                    filePath,
                    StandardCopyOption.REPLACE_EXISTING
            );

            // 5. DB에 저장할 상대 경로
            String storedPath =
                    "/uploads/events/" + eventId + "/visitor.jpg";

            // 6. MediaFile Entity 생성
            MediaFile mediaFile = new MediaFile(
                    event,
                    "IMAGE",
                    storedPath
            );

            // 7. PostgreSQL에 저장
            return mediaFileRepository.save(mediaFile);

        } catch (IOException e) {
            throw new RuntimeException(
                    "Failed to save image file",
                    e
            );
        }
    }
}
