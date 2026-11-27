package com.smartdoorbell.backend.media.repository;

import com.smartdoorbell.backend.media.entity.MediaFile;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Optional;
import java.util.Set;

public interface MediaFileRepository extends JpaRepository<MediaFile, Long> {
    Optional<MediaFile> findFirstByEventIdAndMediaTypeAndFilePathStartingWith(Long eventId, String mediaType, String pathPrefix);

    @Query("""
            select distinct m.event.id from MediaFile m
            where m.mediaType = 'IMAGE' and m.filePath like concat(:pathPrefix, '%')
            """)
    Set<Long> findRepresentativeImageEventIds(String pathPrefix);
}
