package com.smartdoorbell.backend.feedback;

import com.smartdoorbell.backend.event.entity.Event;
import jakarta.persistence.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "feedbacks")
public class Feedback {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "feedback_id")
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "event_id", nullable = false, unique = true)
    private Event event;

    @Enumerated(EnumType.STRING)
    @Column(name = "accuracy_level", nullable = false, length = 20)
    private AccuracyLevel accuracyLevel;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    protected Feedback() {
    }

    Feedback(Event event, AccuracyLevel accuracyLevel) {
        this.event = event;
        this.accuracyLevel = accuracyLevel;
        this.createdAt = LocalDateTime.now();
        this.updatedAt = createdAt;
    }

    void updateAccuracy(AccuracyLevel accuracyLevel) {
        this.accuracyLevel = accuracyLevel;
        this.updatedAt = LocalDateTime.now();
    }

    public Long getEventId() {
        return event.getId();
    }

    public AccuracyLevel getAccuracyLevel() {
        return accuracyLevel;
    }
}
