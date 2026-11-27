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

    @Column(name = "turn_no")
    private Integer turnNo;

    @Column(name = "visitor_text", columnDefinition = "text")
    private String visitorText;

    @Column(name = "purpose", columnDefinition = "text")
    private String purpose;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected EventResponseHistory() {
    }

    public EventResponseHistory(
            Event event,
            String responseCode,
            String responseText
    ) {
        this(event, responseCode, responseText, null, null, null);
    }

    public EventResponseHistory(
            Event event,
            String responseCode,
            String responseText,
            Integer turnNo,
            String visitorText,
            String purpose
    ) {
        this.event = event;
        this.responseCode = responseCode;
        this.responseText = responseText;
        this.turnNo = turnNo;
        this.visitorText = visitorText;
        this.purpose = purpose;
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

    public Integer getTurnNo() {
        return turnNo;
    }

    public String getVisitorText() {
        return visitorText;
    }

    public String getPurpose() {
        return purpose;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
