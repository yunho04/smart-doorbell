# Smart Doorbell

AIoT 기반 스마트 도어벨 시스템입니다.

방문자의 접근을 감지하고 카메라 및 음성 데이터를 수집하여 AI 분석을 수행합니다.
분석 결과와 위험도를 저장하고, 사전에 정의된 안내 문구를 Raspberry Pi 스피커를 통해 출력하는 것을 목표로 합니다.

MVP v2에서는 사용자가 웹 Dashboard에서 방문 Event의 대표사진, 위험도, 상황 요약, AI 응대 기록을 확인하고, AI의 위험도 판단이 정확했는지 피드백을 남길 수 있습니다.

## 시스템 구성

```text
Raspberry Pi 1
- 초음파 센서
- 카메라

Raspberry Pi 2
- 마이크
- 스피커

Backend
- Spring Boot
- PostgreSQL
- MQTT

AI
- Vision
- STT
- LLM / RAG

Frontend
- React (TypeScript, Vite)
```

Frontend는 MQTT나 AI 서버와 직접 통신하지 않고 Spring REST API만 사용합니다.

## 전체 흐름

```text
사용자 비밀번호 인증
→ Dashboard

사람 감지
→ Event 생성
→ 카메라/Vision + 마이크/STT
→ LLM 판단 및 응답
→ Event 종료
→ 위험도/요약/대표사진 저장
→ Dashboard에서 조회
→ 사용자 정확도 Feedback
→ RAG 반영
```

## Project Structure

```text
smart-doorbell/
├── iot/          Raspberry Pi, Sensor, Camera, Microphone, Speaker
├── backend/      Spring Boot, PostgreSQL, MQTT
├── ai-server/    FastAPI, Vision, STT, LLM
├── frontend/     React Web Dashboard
│   ├── public/
│   ├── src/
│   │   ├── api/          REST 호출
│   │   ├── auth/         로그인 상태 관리
│   │   ├── components/   공통 화면 요소
│   │   ├── hooks/        자동 새로고침
│   │   ├── pages/        LoginPage, EventListPage, EventDetailPage
│   │   ├── types/        API 응답 타입
│   │   └── utils/        시간·문구 변환
│   ├── .env.example
│   └── package.json
├── docs/         Architecture, API 명세 등 프로젝트 문서
└── README.md
```

## Frontend 실행

Node.js와 npm이 필요합니다. (Node.js 22에서 확인)

```bash
cd frontend
cp .env.example .env    # 필요하면 Backend 주소 수정
npm install
npm run dev             # http://localhost:5173
```

그 밖의 명령:

```bash
npm run build     # 타입 검사 후 dist/ 에 빌드
npm run lint      # oxlint
npm run preview   # 빌드 결과 미리 보기
```

### 환경변수

`frontend/.env` 에 설정합니다. 실제 값은 저장소에 올리지 않습니다.

```text
VITE_API_BASE_URL=http://localhost:8080
```

| 변수 | 설명 |
| --- | --- |
| `VITE_API_BASE_URL` | Spring Backend 주소. 비워 두면 Frontend와 같은 출처의 `/api` 를 호출합니다. |
| `VITE_DEV_PROXY_TARGET` | (선택) 설정하면 개발 서버가 `/api` 요청을 이 주소로 전달합니다. |

Backend가 다른 IP에서 실행되면 브라우저가 세션 Cookie를 보내지 않을 수 있습니다.
이때는 `VITE_API_BASE_URL` 을 비우고 `VITE_DEV_PROXY_TARGET` 에 Backend 주소를 넣어, 브라우저가 Frontend와 같은 출처로 API를 호출하게 합니다.

### 사용자 인증

회원가입과 ID 없이 공용 비밀번호 하나로 접속합니다.

- 비밀번호 검증은 Backend가 하며, Frontend 코드에는 비밀번호가 없습니다.
- 인증은 Session Cookie 방식이고, Frontend는 모든 요청에 `credentials: 'include'` 를 붙입니다.
- 인증되지 않은 상태로 `/events`, `/events/:eventId` 에 접근하면 `/login` 으로 이동합니다.
- 사용 중 세션이 만료되어 `401` 이 오면 `/login` 으로 이동합니다.

`VITE_API_BASE_URL` 로 Backend를 직접 호출하는 경우, Backend는 Frontend 출처(예: `http://localhost:5173`)에 대해 Credentials를 허용하는 CORS 설정이 필요합니다.

### Frontend 연동 API

```text
POST /api/v1/auth/login
GET  /api/v1/auth/check
POST /api/v1/auth/logout

GET  /api/v1/events
GET  /api/v1/events/{eventId}
GET  /api/v1/events/{eventId}/image
POST /api/v1/events/{eventId}/feedback
```

### 화면

| 주소 | 내용 |
| --- | --- |
| `/login` | 공용 비밀번호 입력 |
| `/events` | 방문 Event 목록. 3초마다 자동으로 갱신됩니다. |
| `/events/:eventId` | 대표사진, 시작·종료시간, 상태, 위험도, 상황 요약, AI 응대 기록, 정확도 피드백(상/중/하). 진행 중인 Event는 3초마다 갱신됩니다. |

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

### MVP v2 Frontend Progress

- 사용자용 Web Dashboard 구현 완료 (로그인, Event 목록, Event 상세, 정확도 피드백, 로그아웃)
- 위 연동 API 중 인증, Event 목록, 대표사진 조회, 피드백 API는 Backend 구현이 필요합니다.
