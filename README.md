# Smart Doorbell

AIoT 기반 스마트 도어벨 시스템입니다.

방문자의 접근을 감지하고 카메라 및 음성 데이터를 수집하여 AI 분석을 수행합니다.
분석 결과와 위험도를 저장하고, 사전에 정의된 안내 문구를 Raspberry Pi 스피커를 통해 출력하는 것을 목표로 합니다.

## Project Structure

- `iot/` : Raspberry Pi, Sensor, Camera, Microphone, Speaker
- `backend/` : Spring Boot, PostgreSQL
- `ai-server/` : FastAPI, Vision, STT, LLM
- `frontend/` : 최소 Web Dashboard
- `docs/` : Architecture, API 명세 등 프로젝트 문서

## Team Roles

- IoT / Raspberry Pi: 2명
- Backend / DB: 1명
- Vision AI: 1명
- STT / LLM: 1명


## Current Status

**MVP v1 — Integration in Progress**

현재 Raspberry Pi, Spring Boot, AI Server, PostgreSQL 간 End-to-End 연결을 구현하고 있습니다.

MVP v1에서는 방문 Event 생성, 대표 이미지 관리, AI 기반 위험도 및 상황 요약, LLM 응답 결과 저장을 우선 구현합니다.

### Current Backend / Database Progress

- PostgreSQL 연결 완료
- MVP v1 Database Schema 구성 완료
- DEVICES / EVENTS / MEDIA_FILES 테이블 구성
- Event 중심 데이터 모델 확정
- Spring Boot Event API 구현 진행 중
- MQTT 및 AI Server 연동 예정

자세한 진행사항은 `docs/progress/2026-11-15-mvp-v1.md`에서 확인할 수 있습니다.