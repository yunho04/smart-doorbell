# STT·LLM 서버 (ai-server/llm) — MVP v1

담당: 허인혜

스마트 도어벨 AI 서버 중 STT·LLM 파트. 「LLM 연동 API 명세서 MVP v1」 기준.
지금은 **데이터 전송과 흐름이 동작하는 기본 틀**이며, STT와 LLM은 Mock(가짜 응답)이다.

## 실행

```bash
python3.13 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # SPRING_BASE_URL을 Mac의 실제 LAN IP로 수정

./run.sh                           # = uvicorn app.main:app --host 0.0.0.0 --port 8001
```

- API 문서: http://localhost:8001/docs
- **포트 8001:** Vision 서버가 8000을 쓰므로 LLM 서버는 8001을 쓴다 (같은 PC에서 둘 다 실행 가능)
- 자동 테스트: `pytest -q`
- 통합 당일:
  - Spring 담당에게 → `llm.base-url=http://<AI_IP>:8001`
  - Vision 담당에게 → `LLM_URL=http://<AI_IP>:8001/vision/result` (Windows 같은 PC면 `127.0.0.1`)
  - Pi B 담당에게 → 음성 업로드 주소 `http://<AI_IP>:8001/api/v1/events/{eventId}/audio` (응답의 `responseCode`로 바로 재생)
  - 내 `.env`에 → `SPRING_BASE_URL=http://<Spring IP>:8080`, `VISION_BASE_URL=http://<Vision IP>:8000`

## Groq 연결 (STT·LLM)

STT와 LLM 모두 Groq API를 쓴다 (OpenAI 호환, `openai` 라이브러리로 접속).

| 용도 | 모델 (`.env`) | 호출 시점 |
|---|---|---|
| STT | `STT_MODEL=whisper-large-v3-turbo` (`language=ko`) | 음성마다 |
| 방문 목적 분류 | `LLM_FAST_MODEL=openai/gpt-oss-20b` | 음성마다 (빨라야 함) |
| 최종 위험도 + 요약 | `LLM_MODEL=openai/gpt-oss-120b` | finalize 때 1회 (한 번의 호출로 둘 다) |

1. `.env`의 `GROQ_API_KEY=`에 키를 넣는다 (GitHub·채팅에 올리지 않기)
2. `pip install -r requirements.txt` (openai 추가됨)
3. `python scripts/check_groq.py` → 방문 목적·위험도·요약이 실제 모델로 나오는지 확인 (`python scripts/check_groq.py 녹음.m4a`로 STT도 확인)
4. 서버 재시작 후 `/health`에서 `"llm": "groq/openai/gpt-oss-120b"`, `"stt": "groq/whisper-large-v3-turbo"` 확인

**안전장치**
- 키가 비어 있으면 자동으로 Mock으로 동작한다 (서버는 항상 켜짐).
- Groq 호출 실패·시간 초과·형식 오류 → 규칙 기반 판단으로 대체 (로그에 `model=fallback-rule`), Event가 멈추지 않는다.
- 방문자 발화는 `<visitor_transcript>` 안의 데이터로만 전달하고, 태그를 닫는 꺾쇠는 바꿔서 지시를 끼워 넣지 못하게 한다.
- 출력은 JSON으로 받아 정해진 값(목적·위험도)만 인정하고, 최종 위험도는 코드에서 max(Vision 1차, LLM)로 한 번 더 막는다.
- Whisper가 무음에서 지어내는 문장("시청해 주셔서 감사합니다" 등)은 버리고 '알아듣지 못함'으로 처리한다.
- 테스트(`pytest`)는 항상 Mock으로 돌아 실제 API를 호출하지 않는다.

## 전체 흐름 (11-18 팀 결정 반영)

```
1) Pi 센서 감지 → Spring이 Event 생성, eventId 발급 → MQTT로 Pi A·Pi B에 전달
2) Pi A ─사진(1초 1장)─▶ Vision ─결과(사진마다)─▶ LLM  POST /vision/result
3) Pi B ─음성──▶ LLM                       POST /api/v1/events/{id}/audio
     STT → 방문 목적 분류 → 사전 정의 대사 선택
     → HTTP 응답의 responseCode로 Pi B가 바로 재생 (Spring을 거치지 않음)
4) Spring: 마지막 감지 후 10초 미감지 → LLM POST /api/v1/events/{id}/finalize {eventId}  (Event당 1회)
5) LLM: 보관한 Vision + STT 기록 종합 → RAG 위험도 판단 + 요약
     LLM ─▶ Spring POST /api/v1/events/{id}/result {riskLevel, summary, responseCode, responseText} → COMPLETED
6) LLM: 대표 사진 frame_no 선택 → Vision POST /vision/events/{id}/representative {"frame_no": N}
     → Vision이 그 사진 원본을 Spring POST /api/v1/events/{id}/image 로 업로드
```

Vision·STT 결과는 Spring을 거치지 않고 LLM 서버가 eventId별로 보관한다 (명세서 1장).
마지막 대사는 /result의 `responseCode`, `responseText`로 Spring DB에 남는다.

## API

### AI 서버가 받는 요청

| API | 호출하는 쪽 | 입력 | 출력 | 근거 |
|---|---|---|---|---|
| `POST /api/v1/events/{id}/finalize` | Spring | `{"eventId": 15}` | 202 `{"eventId":15,"status":"ACCEPTED"}` (중복 시 200 `ALREADY_FINALIZED`) | 명세서 4장 |
| `POST /vision/result` | Vision 서버 | Vision 담당 코드의 JSON 그대로 (`event_id`, `frame_no`, `person_visible_sec`, `package_detected`, `face_covered`, `weapon_labels`, `vision_risk_level`, `vision_reasons` 등) | `{"ok": true}` | Vision README |
| `GET /vision/result/{id}` | 확인용 | - | 해당 Event의 최신 Vision 결과 | Vision mock_llm과 동일 |
| `POST /api/v1/events/{id}/audio` | Pi B | multipart: `file` (wav 권장) | 텍스트, 방문 목적, `responseCode`, `sentToSpring` 등 | AI 내부 규약 |
| `GET /api/v1/events/{id}/state` | 디버깅용 | - | 보관 중인 프레임 수, 발화, 대표 프레임, 피처 | - |
| `GET /health` | 누구나 | - | 상태, Spring 주소 | - |
| `POST /api/v1/feedback` | Spring | `eventId`, `userLabel`(NORMAL/CAUTION/DANGER), `memo`(선택) | `caseId`, `totalCases`, `updated` | features는 finalize 때 서버가 저장해 둔 값 사용. 없으면 404 |

### AI 서버가 Spring으로 보내는 요청

| API | 시점 | 본문 |
|---|---|---|
| `POST {SPRING}/api/v1/events/{id}/response` | **기본 사용 안 함** (`SEND_RESPONSE_TO_SPRING=true`일 때만) | `{"responseCode":"DELIVERY_01","responseText":"..."}` |
| `POST {SPRING}/api/v1/events/{id}/result` | finalize 후 분석 완료 시 | `{"riskLevel":"LOW","summary":"...","responseCode":"DELIVERY_01","responseText":"..."}` (뒤 두 개는 마지막 재생 대사, 없으면 null. Spring `EventResultRequest`와 동일) |

### AI 서버가 Vision으로 보내는 요청

| API | 시점 | 본문 |
|---|---|---|
| `POST {VISION}/vision/events/{id}/representative` | /result 전송 직후 | `{"frame_no": 12}` (사람 인식 신뢰도가 가장 높은 사진, Vision이 보관 중인 최근 300장 안에서 선택) |

Spring 전송은 실패하면 1회만 재시도하고, AI 서버 처리는 계속 진행한다 (무한 재시도 없음).

### 대사 코드 (`data/reply_templates.json`)

| 방문 목적 | responseCode | 응대 종료 |
|---|---|---|
| 택배 / 일반 방문 / 점검 / 기타 | `DELIVERY_01` / `VISIT_01` / `REPAIR_01` / `OTHER_01` | 종료 |
| 알아듣지 못함 (1~2회차) | `ASK_AGAIN_01` | 계속 |
| 알아듣지 못함 (3회차) | `HANDOVER_01` | 종료 |

응대 횟수(turn)는 AI 서버가 eventId별로 자동으로 센다.

## 직접 흐름 테스트 (터미널 3개)

```bash
# 터미널 1: 가짜 Spring (AI가 보내는 /response, /result를 화면에 출력)
uvicorn scripts.fake_spring:app --port 8080

# 터미널 2: AI 서버
./run.sh

# 터미널 3: 이벤트 1건 흐름
./scripts/try_flow.sh 15 delivery      # Vision → 음성 → 상태 확인 → finalize (LLM 서버 8001)
./scripts/try_flow.sh 16 noise         # 못 알아들은 경우 → ASK_AGAIN_01
```

Mock STT는 음성 파일 이름으로 문장을 정한다: `delivery`, `visit`, `repair`, `suspicious`, 그 외는 알아듣지 못한 것으로 처리.

## MVP v1에서의 제약

- **Vision 1차 위험도 유지:** 최종 위험도 = max(Vision 1차, LLM 2차). 흉기·얼굴 가림으로 Vision이 높게 본 상황을 LLM이 낮추지 못한다 (NFR-01).
- **센서 값이 없음:** Spring이 finalize 때 eventId만 보내므로 충격 횟수·반복 접근은 위험도 판단에 쓰지 않는다. 방문 시각과 체류 시간은 AI 서버가 Vision·음성을 **받은 시각** 기준으로 계산한다 (기기 시계가 틀려도 안전).
- **규칙 하한선 없음:** Spring이 riskLevel을 그대로 저장한다 (SAD ADR-02의 하한선은 후속 단계).
- **대표 사진:** LLM이 `frame_no`만 고르고, 사진 원본 업로드는 Vision이 한다. `VISION_BASE_URL`이 비어 있으면 전달하지 않는다.
- **메모리 보관:** 진행 중인 이벤트 데이터는 메모리에 있으므로 시연 중 서버를 재시작하지 않는다.
- **인증 없음:** MVP v1 명세에 맞춰 꺼 둠. `.env`의 `DEVICE_KEYS`, `INTERNAL_TOKEN`을 채우면 켜진다.

## 폴더 구조

```
app/
├─ main.py              서버 진입점, 에러 형식 통일, 요청 로그
├─ config.py            .env 설정
├─ schemas.py           요청/응답 형식 (JSON은 camelCase)
├─ security.py          장치 키 / 내부 토큰 (MVP에서는 꺼짐)
├─ routers/
│  ├─ vision.py         POST /vision/result (Vision 담당 형식)
│  ├─ events.py         finalize, audio, state
│  └─ feedback.py       사용자 평가 -> RAG 사례 추가
└─ services/
   ├─ stt.py            음성 → 텍스트 (MockSTT → WhisperSTT)
   ├─ llm.py            목적 분류·위험도·요약 (MockLLM → RealLLM)
   ├─ templates.py      방문 목적 → 대사 코드
   ├─ event_cache.py    eventId별 Vision·STT 결과 보관
   ├─ analyzer.py       finalize 시 종합 분석, 대표 프레임 선정
   ├─ rag_store.py      RAG 사례 저장소 (JSON 파일)
   └─ spring_client.py  Spring /response, /result 호출
data/  reply_templates.json, cases.json
scripts/  fake_spring.py, try_flow.sh
tests/test_flow.py
```

## 다음 단계 (TODO)

1. `services/stt.py`: faster-whisper 연결 후 `.env`에서 `STT_BACKEND=whisper`
2. `routers/events.py`: ffmpeg로 wav 16kHz mono 변환
3. `services/llm.py`: RealLLM에 LLM SDK 연결 (방문자 발화는 `<visitor_transcript>` 태그로 분리)
4. `services/rag_store.py`: 문장 임베딩 + 코사인 유사도로 교체
5. `data/cases.json`: 기본 시나리오 20~30개로 확장
