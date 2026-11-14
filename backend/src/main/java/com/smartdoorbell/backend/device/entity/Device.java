package com.smartdoorbell.backend.device.entity;

import jakarta.persistence.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "devices")
public class Device {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "device_id")
    private Long id;

    @Column(name = "device_name", nullable = false, length = 100)
    private String deviceName;

    @Column(name = "status", nullable = false, length = 20)
    private String status = "OFFLINE";

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected Device() {
    }

    public Device(String deviceName, String status) {
        this.deviceName = deviceName;
        this.status = status;
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

    public String getDeviceName() {
        return deviceName;
    }

    public String getStatus() {
        return status;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setDeviceName(String deviceName) {
        this.deviceName = deviceName;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
