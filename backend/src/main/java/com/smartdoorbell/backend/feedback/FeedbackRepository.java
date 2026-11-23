package com.smartdoorbell.backend.feedback;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Optional;

public interface FeedbackRepository extends JpaRepository<Feedback, Long> {

    @Query("select f from Feedback f where f.event.id = :eventId")
    Optional<Feedback> findByEventId(Long eventId);
}
