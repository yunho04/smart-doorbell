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
