package com.smartdoorbell.backend.media.service;

import com.smartdoorbell.backend.event.EventNotFoundException;
import com.smartdoorbell.backend.event.entity.Event;
import com.smartdoorbell.backend.event.repository.EventRepository;
import com.smartdoorbell.backend.media.entity.MediaFile;
import com.smartdoorbell.backend.media.repository.MediaFileRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.MediaTypeFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

@Service
@Transactional
public class MediaService {

    private static final Logger log = LoggerFactory.getLogger(MediaService.class);
    // Keep representative rows distinct from existing IMAGE rows without changing the media schema.
    private static final String REPRESENTATIVE_PATH = "/uploads/representative-images/";
    private static final Map<String, String> IMAGE_EXTENSIONS = Map.of(
            "image/jpeg", "jpg", "image/png", "png", "image/gif", "gif",
            "image/webp", "webp", "image/bmp", "bmp"
    );

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
                .orElseThrow(() -> new EventNotFoundException(eventId));

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
            try (InputStream input = file.getInputStream()) {
                Files.copy(input, filePath, StandardCopyOption.REPLACE_EXISTING);
            }

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

    public MediaFile saveRepresentativeImage(Long eventId, MultipartFile file) {
        Event event = eventRepository.findLockedById(eventId)
                .orElseThrow(() -> new EventNotFoundException(eventId));
        if (file.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Image file is empty");
        }

        String extension = MediaTypeFactory.getMediaType(file.getOriginalFilename())
                .map(MediaType::toString)
                .map(IMAGE_EXTENSIONS::get)
                .orElseGet(() -> IMAGE_EXTENSIONS.getOrDefault(
                        Optional.ofNullable(file.getContentType()).orElse(""), ""));
        if (extension.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unsupported image type");
        }

        MediaFile previous = findRepresentativeImage(eventId).orElse(null);
        String storedPath = REPRESENTATIVE_PATH + eventId + "/" + UUID.randomUUID() + "." + extension;
        Path newPath = Path.of("." + storedPath);
        Path oldPath = previous == null ? null : Path.of("." + previous.getFilePath());
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                if (status == STATUS_ROLLED_BACK) {
                    deleteImage(newPath);
                } else if (status == STATUS_COMMITTED && oldPath != null) {
                    deleteImage(oldPath);
                }
            }
        });

        try (InputStream input = file.getInputStream()) {
            Files.createDirectories(newPath.getParent());
            Files.copy(input, newPath);
        } catch (IOException e) {
            log.error("Failed to store representative image for event {}", eventId, e);
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Failed to save representative image");
        }

        if (previous == null) {
            return mediaFileRepository.save(new MediaFile(event, "IMAGE", storedPath));
        }

        previous.replaceFile(storedPath);
        return previous;
    }

    public RepresentativeImage getRepresentativeImage(Long eventId) {
        // Hold the shared event lock while reading, so a replacement cannot remove the file mid-read.
        eventRepository.findSharedById(eventId).orElseThrow(() -> new EventNotFoundException(eventId));
        MediaFile image = findRepresentativeImage(eventId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        String filePath = image.getFilePath();

        try {
            return new RepresentativeImage(Files.readAllBytes(Path.of("." + filePath)),
                    MediaTypeFactory.getMediaType(filePath).orElse(MediaType.APPLICATION_OCTET_STREAM));
        } catch (NoSuchFileException e) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        } catch (IOException e) {
            log.error("Failed to read representative image for event {}", eventId, e);
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Failed to read representative image");
        }
    }

    @Transactional(readOnly = true)
    public boolean hasRepresentativeImage(Long eventId) {
        return findRepresentativeImage(eventId).isPresent();
    }

    @Transactional(readOnly = true)
    public Set<Long> findRepresentativeImageEventIds() {
        return mediaFileRepository.findRepresentativeImageEventIds(REPRESENTATIVE_PATH);
    }

    private Optional<MediaFile> findRepresentativeImage(Long eventId) {
        return mediaFileRepository.findFirstByEventIdAndMediaTypeAndFilePathStartingWith(eventId, "IMAGE", REPRESENTATIVE_PATH);
    }

    private void deleteImage(Path path) {
        try {
            Files.deleteIfExists(path);
        } catch (IOException e) {
            log.warn("Failed to delete representative image file {}", path, e);
        }
    }

    public record RepresentativeImage(byte[] data, MediaType contentType) {
    }
}
