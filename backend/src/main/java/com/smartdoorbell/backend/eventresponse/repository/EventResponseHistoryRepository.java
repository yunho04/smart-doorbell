package com.smartdoorbell.backend.eventresponse.repository;

import com.smartdoorbell.backend.eventresponse.entity.EventResponseHistory;
import org.springframework.data.jpa.repository.JpaRepository;

public interface EventResponseHistoryRepository
        extends JpaRepository<EventResponseHistory, Long> {
}
