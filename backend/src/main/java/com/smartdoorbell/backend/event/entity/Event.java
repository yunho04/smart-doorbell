package com.smartdoorbell.backend.event.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;


@Entity
@Table(name = "events")

public class Event {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String status;

    private LocalDateTime startedAt;

    private LocalDateTime endedAt;

    protected Event() {
    }

}
