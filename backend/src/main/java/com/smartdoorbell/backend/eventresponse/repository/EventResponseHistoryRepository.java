package com.smartdoorbell.backend.eventresponse.repository;

import com.smartdoorbell.backend.eventresponse.entity.EventResponseHistory;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface EventResponseHistoryRepository
        extends JpaRepository<EventResponseHistory, Long> {

    List<EventResponseHistory> findAllByEventIdOrderByCreatedAtAscIdAsc(Long eventId);
}
