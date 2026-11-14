-- =========================================================
-- AIoT Smart Doorbell - MVP v1 Database Schema
-- PostgreSQL 16
-- =========================================================


-- =========================================================
-- 0. 기존 개발용 테이블 삭제
-- 아직 실제 데이터가 없으므로 초기화 후 다시 생성
-- =========================================================

DROP TABLE IF EXISTS media_files CASCADE;
DROP TABLE IF EXISTS events CASCADE;
DROP TABLE IF EXISTS devices CASCADE;


-- =========================================================
-- 1. DEVICES
-- Raspberry Pi 스마트 도어벨 장치
-- =========================================================

CREATE TABLE devices (
    device_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    device_name VARCHAR(100) NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'OFFLINE',

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_device_status
        CHECK (status IN ('ONLINE', 'OFFLINE'))
);


-- =========================================================
-- 2. EVENTS
-- 한 번의 방문 상황 전체를 관리하는 핵심 테이블
-- =========================================================

CREATE TABLE events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    device_id BIGINT NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'DETECTED',

    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    ended_at TIMESTAMP,

    risk_level VARCHAR(20),

    summary TEXT,

    response_code VARCHAR(50),

    response_text TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_events_device
        FOREIGN KEY (device_id)
        REFERENCES devices(device_id),

    CONSTRAINT chk_event_status
        CHECK (
            status IN (
                'DETECTED',
                'ANALYZING',
                'RESPONDING',
                'COMPLETED',
                'FAILED'
            )
        ),

    CONSTRAINT chk_risk_level
        CHECK (
            risk_level IS NULL
            OR risk_level IN ('LOW', 'MEDIUM', 'HIGH')
        )
);


-- =========================================================
-- 3. MEDIA_FILES
-- Event와 관련된 사진/음성/영상 파일 경로 저장
-- 실제 파일 자체는 DB에 저장하지 않음
-- =========================================================

CREATE TABLE media_files (
    media_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    event_id BIGINT NOT NULL,

    media_type VARCHAR(20) NOT NULL,

    file_path VARCHAR(500) NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_media_event
        FOREIGN KEY (event_id)
        REFERENCES events(event_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_media_type
        CHECK (
            media_type IN ('IMAGE', 'AUDIO', 'VIDEO')
        )
);


-- =========================================================
-- 4. 조회 성능을 위한 인덱스
-- =========================================================

CREATE INDEX idx_events_device_id
    ON events(device_id);

CREATE INDEX idx_events_started_at
    ON events(started_at);

CREATE INDEX idx_media_files_event_id
    ON media_files(event_id);


-- =========================================================
-- 5. MVP 테스트용 Raspberry Pi 장치 1개 생성
-- =========================================================

INSERT INTO devices (
    device_name,
    status
)
VALUES (
    '현관 스마트 도어벨',
    'ONLINE'
);