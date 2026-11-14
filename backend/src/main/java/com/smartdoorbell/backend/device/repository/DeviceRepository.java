package com.smartdoorbell.backend.device.repository;

import com.smartdoorbell.backend.device.entity.Device;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DeviceRepository extends JpaRepository<Device, Long> {
}
