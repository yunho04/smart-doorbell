package com.smartdoorbell.backend.eventresponse.entity;

import com.smartdoorbell.backend.event.entity.Event;
import jakarta.persistence.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "event_responses")
public class EventResponseHistory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "response_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "event_id", nullable = false)
    private Event event;

    @Column(name = "response_code", nullable = false, length = 50)
    private String responseCode;

    @Column(name = "response_text", nullable = false)
    private String responseText;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected EventResponseHistory() {
    }

    public EventResponseHistory(
            Event event,
            String responseCode,
            String responseText
    ) {
        this.event = event;
        this.responseCode = responseCode;
        this.responseText = responseText;
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

    public String getResponseCode() {
        return responseCode;
    }

    public String getResponseText() {
        return responseText;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}