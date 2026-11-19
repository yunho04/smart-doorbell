package com.smartdoorbell.backend.media.repository;

import com.smartdoorbell.backend.media.entity.MediaFile;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MediaFileRepository extends JpaRepository<MediaFile, Long> {
}