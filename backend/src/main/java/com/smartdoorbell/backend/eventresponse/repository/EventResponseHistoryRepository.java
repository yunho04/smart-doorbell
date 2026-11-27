package com.smartdoorbell.backend.eventresponse.repository;

import com.smartdoorbell.backend.eventresponse.entity.EventResponseHistory;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface EventResponseHistoryRepository
        extends JpaRepository<EventResponseHistory, Long> {

    List<EventResponseHistory> findAllByEventIdOrderByCreatedAtAscIdAsc(Long eventId);

    @Modifying
    @Query("delete from EventResponseHistory history where history.event.id = :eventId")
    void deleteAllByEventId(@Param("eventId") Long eventId);
}
