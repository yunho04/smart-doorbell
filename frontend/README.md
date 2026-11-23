# Frontend — Web Dashboard (장준용)

`index.html` 한 파일이다. 설치·빌드 없음.

## 보기

- **그냥 열기**: `index.html` 더블클릭 → 목업 데이터 (11-18 통합 테스트에서 Spring에 저장된 5~8번 결과)
- **Spring에 붙이기**: `backend/src/main/resources/static/index.html`로 복사 → 브라우저에서 `http://<Mac IP>:8080/`
  - 같은 주소에서 열리므로 **CORS 설정이 필요 없다**
  - `GET /api/v1/events`가 `EventResponse` 배열을 주면 3초마다 실제 데이터로 바뀐다 (오른쪽 위 "실시간 · Spring 연결됨")
  - API가 없거나 실패하면 목업 그대로 보인다

## Spring에 필요한 것 (MVP v2 명세 기준, 11-23)

| # | API | 없으면 |
|---|---|---|
| 1 | `GET /api/v1/events?limit=50` — `EventResponse` 배열, 최신순 (**명세에 아직 없음, 요청**) | 목업만 보임 (**이것만 있으면 목록·상세·요약·위험도가 실제로 뜬다**) |
| 2 | `GET /api/v1/events/{id}/image` — 대표 사진 (명세 4번 응답의 `imageUrl`) | "대표 사진 없음" |
| 3 | UI → Spring 정확도 평가: `POST /api/v1/events/{id}/feedback` `{eventId, accuracyLevel}` (명세 3번은 Spring → LLM만 있어 **이 주소는 가정**, 맞춰야 함) | 평가가 브라우저(localStorage)에만 저장됨 |
| 4 | (제안, 명세 없음) `GET` / `POST {text}` / `DELETE /{id}` `/api/v1/user-rules` | "내 규칙"이 브라우저에만 저장됨 |

## 쓰는 필드

- 필수: `eventId`, `status`(DETECTED·ANALYZING·COMPLETED·FAILED), `startedAt`, `endedAt`, `riskLevel`, `summary`
- 있으면 씀: `responses[]`(event_responses) 또는 `responseText`, `imageUrl`, `labels[]`(Vision 라벨)

## 화면

왼쪽 방문 목록(진행 중 / 오늘, 위험도 필터) · 가운데 방문 상세(대표 사진·요약·스피커 응답) · 오른쪽 **AI 판단 평가**("이 판단, 맞았나요?" 상=정확 · 중=부분적으로 정확 · 하=부정확, 명세 3번 `accuracyLevel`) + 내 규칙(제안).
HIGH 방문은 위쪽 빨간 띠. 디자인 레퍼런스: gumloop.com (godly.design).

처음 계획한 표시 항목: Event 시작·종료 시간, 방문자 사진, STT 결과, Speaker 응답, 위험도 — STT 결과는 Spring에 저장 칸이 없어 아직 못 띄움.
