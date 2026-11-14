package com.smartdoorbell.backend.event.entity;

import com.smartdoorbell.backend.device.entity.Device;
import jakarta.persistence.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "events")
public class Event {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "event_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "device_id", nullable = false)
    private Device device;

    @Column(name = "status", nullable = false, length = 20)
    private String status = "DETECTED";

    @Column(name = "started_at", nullable = false)
    private LocalDateTime startedAt;

    @Column(name = "ended_at")
    private LocalDateTime endedAt;

    @Column(name = "risk_level", length = 20)
    private String riskLevel;

    @Column(name = "summary")
    private String summary;

    @Column(name = "response_code", length = 50)
    private String responseCode;

    @Column(name = "response_text")
    private String responseText;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    protected Event() {
    }

    public Event(Device device) {
        this.device = device;
        this.status = "DETECTED";
    }

    @PrePersist
    protected void onCreate() {
        LocalDateTime now = LocalDateTime.now();

        if (startedAt == null) {
            startedAt = now;
        }

        if (createdAt == null) {
            createdAt = now;
        }

        if (updatedAt == null) {
            updatedAt = now;
        }
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public Long getId() {
        return id;
    }

    public Device getDevice() {
        return device;
    }

    public String getStatus() {
        return status;
    }

    public LocalDateTime getStartedAt() {
        return startedAt;
    }

    public LocalDateTime getEndedAt() {
        return endedAt;
    }

    public String getRiskLevel() {
        return riskLevel;
    }

    public String getSummary() {
        return summary;
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

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public void complete(
            String riskLevel,
            String summary,
            String responseCode,
            String responseText
    ) {
        this.riskLevel = riskLevel;
        this.summary = summary;
        this.responseCode = responseCode;
        this.responseText = responseText;

        this.status = "COMPLETED";
        this.endedAt = LocalDateTime.now();
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
