package com.smartdoorbell.backend.device.repository;

import com.smartdoorbell.backend.device.entity.Device;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;

import java.util.Optional;

public interface DeviceRepository extends JpaRepository<Device, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<Device> findLockedById(Long id);
}
