package com.smartdoorbell.backend.media.entity;

import com.smartdoorbell.backend.event.entity.Event;
import jakarta.persistence.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "media_files")
public class MediaFile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "media_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "event_id", nullable = false)
    private Event event;

    @Column(name = "media_type", nullable = false, length = 20)
    private String mediaType;

    @Column(name = "file_path", nullable = false, length = 500)
    private String filePath;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected MediaFile() {
    }

    public MediaFile(Event event, String mediaType, String filePath) {
        this.event = event;
        this.mediaType = mediaType;
        this.filePath = filePath;
    }

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now();
        }
    }

    public Long getId() {
        return id;
    }

    public Event getEvent() {
        return event;
    }

    public String getMediaType() {
        return mediaType;
    }

    public String getFilePath() {
        return filePath;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}