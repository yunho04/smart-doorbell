package com.smartdoorbell.backend.event.repository;

import com.smartdoorbell.backend.event.entity.Event;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface EventRepository extends JpaRepository<Event, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<Event> findFirstByDeviceIdAndStatusOrderByStartedAtDescIdDesc(Long deviceId, String status);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<Event> findLockedById(Long id);

    @Query("""
            select e.id from Event e
            where e.status = :status
              and coalesce(e.lastDetectedAt, e.startedAt) <= :cutoff
            """)
    List<Long> findInactiveIds(@Param("status") String status, @Param("cutoff") LocalDateTime cutoff);
}
