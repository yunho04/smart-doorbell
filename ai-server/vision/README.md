---
title: Vision 서버 README
created: 2026-11-16
updated: 2026-11-16
tags: [course/클라우드AIoT, project/스마트도어벨, dev/python]
source: SAD v1.1 3.1 구성도·6.1·8장, ERD v1.1 VISION_RESULTS, 11-16 모델 비교 시험
status: growing
---

# Vision 서버 (장준용)

Pi가 방문 Event 동안 **1초에 1장** 사진을 보내면, 장마다 물체를 찾고 Event 단위로 모아 **1차 위험도**를 매긴 뒤 **LLM 서버로 보낸다**. LLM은 이 1차 판단과 다른 센서 값으로 2차 판단을 한다. 이미지는 밖으로 안 나가고 라벨만 넘긴다 (SAD 6.2).
회의 안건은 [[../회의록/Vision 모듈 회의 준비]].

## 실행

```bash
python -m venv .venv
.venv\Scripts\activate          # 맥·리눅스·Pi: source .venv/bin/activate
pip install -r requirements.txt
set LLM_URL=http://<허인혜 서버>/vision/result      # 맥·리눅스: export LLM_URL=...
uvicorn app:app --host 0.0.0.0 --port 8000
```

첫 실행 때 모델 `yoloe-26m-seg.pt`(70MB)와 글 인코더 `mobileclip2_b.ts`(254MB)를 자동으로 받는다. 서버 켜는 데 10초쯤 걸린다.
테스트: `python test_app.py` → `OK`

## 연결 시험 (Pi → Vision → LLM, 내 PC 하나로)

LLM 서버가 아직 없어서 받는 쪽을 임시로 정했다: **`POST /vision/result`** (JSON). 허인혜 서버가 같은 경로로 받으면 Vision 코드는 안 바뀐다.

```bash
# 터미널 1: 가짜 LLM 서버 (받은 것을 화면에 찍음)
uvicorn mock_llm:app --port 8001
# 터미널 2: Vision 서버
set LLM_URL=http://127.0.0.1:8001/vision/result
uvicorn app:app --port 8000
# 터미널 3: Pi 흉내 (사진 한 장을 1초에 1장씩 35초 동안)
python pi_sim.py 방문자.jpg 101 35
```

11-16 결과 (헬멧 쓴 방문자 사진, 노트북 CPU): 34장 보냄 → LLM에는 **3번만** 도착했다 (1장째 LOW → 2장째 MEDIUM "얼굴 가림: helmet" → 30초째 HIGH "30초 머묾"). 장당 0.4~0.5초. LLM 쪽 최신값은 `GET http://127.0.0.1:8001/vision/result/101`.

Windows에서는 `localhost` 대신 **`127.0.0.1`**을 쓴다. `localhost`로 쓰면 접속할 때마다 2초쯤 늦어져 1초 1장이 안 지켜졌다.

## 모델: YOLOE-26m (글로 찾을 물체를 정하는 YOLO)

수업 5장의 YOLOv8n은 COCO 80종만 알아서 헬멧·마스크·복면·택배 상자를 못 찾는다. YOLOE는 같은 `ultralytics` 라이브러리에서 `set_classes(["helmet", ...])`처럼 **글로 지정한 물체를 추가 학습 없이** 찾는다.

11-16 시험 (Wikimedia 사진 16장, 노트북 CPU):

| 모델 | 장당 시간 | 헬멧 3장 | 마스크 (제대로 쓴 1장) | 복면 2장 | 방망이 | 칼 1장 |
|---|---|---|---|---|---|---|
| YOLOv8n (수업, COCO) | 0.06초 | 못 함 | 못 함 | 못 함 | 못 찾음 | 못 찾음 |
| YOLO26n (최신, COCO) | 0.06초 | 못 함 | 못 함 | 못 함 | 0.26 | 못 찾음 |
| YOLOE-26s | 0.25초 | 3/3 | 0.55 | 0/2 | 0.77 | 못 찾음 |
| **YOLOE-26m (채택)** | **0.6초** | **3/3 (0.81~0.93)** | **0.82** | **1/2** | **0.78** | 못 찾음 |

- 턱에 걸친 마스크는 0.21~0.23으로 낮게 나와 기준값 0.5에서 걸러진다 (가린 게 아니니 맞는 동작)
- **칼은 세 모델 모두 못 찾았다.** 흉기 판단은 Vision만 믿지 말고 충격 센서·LLM 2차 판단으로 보완
- 1초에 1장이라 장당 0.6초면 충분. 서버가 느리면 `VISION_MODEL=yoloe-26s-seg.pt`

## 1차 위험도 규칙 (`judge()`)

라벨은 한 Event에서 **2장 이상** 나와야 인정한다 (한 장짜리 오탐 거르기).

| 위험도 | 조건 |
|---|---|
| HIGH | 흉기(knife·baseball bat) 보임, 또는 얼굴 가림 + 30초 넘게 머묾 |
| MEDIUM | 얼굴 가림(helmet·face mask·balaclava), 또는 30초 넘게 머묾 |
| LOW | 그 외. 택배 상자가 보이면 오래 있어도 배회로 안 봄 |

헬멧만으로 HIGH가 아닌 이유: 배달 기사가 헬멧 쓰고 오는 일이 흔하다. 오래 머물 때만 올린다.

## API

`POST /vision/analyze` — `multipart/form-data`

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `image` | 파일 (JPEG·PNG) | O | 10MB 이하. 1초에 1장 |
| `event_id` | 정수 | O | Spring이 발급한 Event ID |

헤더: 서버에 `VISION_API_TOKEN`을 설정했으면 `Authorization: Bearer <토큰>` 필수 (SAD 6.1 장치 키)

```bash
curl -F event_id=101 -F image=@visitor.jpg http://localhost:8000/vision/analyze
```

### 응답 (200) = LLM으로 보내는 JSON과 같다 (값은 예시)

```json
{
  "event_id": 55,
  "frame_no": 2,
  "captured_at": "2026-11-18T15:42:15.789+09:00",
  "person_detected": true,
  "person_count": 1,
  "objects": [{"label": "helmet", "confidence": 0.81, "bbox": [412, 180, 470, 240]}],
  "processing_ms": 547,
  "person_visible_sec": 1,
  "package_detected": false,
  "face_covered": true,
  "weapon_labels": [],
  "vision_risk_level": "MEDIUM",
  "vision_reasons": ["얼굴 가림: helmet"]
}
```

| 필드 | 범위 | 설명 |
|---|---|---|
| `frame_no` | Event | 이 Event에서 몇 번째 사진인지. LLM이 대표 사진 고를 때 이 번호를 쓴다 (11-17 톡방 frameId) |
| `captured_at` | 이번 사진 | Vision이 사진을 받은 시각 (STT와 시간 순서 맞추기용) |
| `person_detected`, `person_count`, `objects`, `processing_ms` | 이번 사진 | ERD `VISION_RESULTS` 컬럼 이름 그대로. `bbox`는 `[x1, y1, x2, y2]` 픽셀 |
| `person_visible_sec` | Event | 사람이 처음 보인 때부터 마지막으로 보인 때까지 초 |
| `package_detected`, `face_covered`, `weapon_labels` | Event | 2장 이상에서 확인된 것만 |
| `vision_risk_level`, `vision_reasons` | Event | 1차 위험도 `LOW`/`MEDIUM`/`HIGH`(ERD `final_risk_level`과 같은 값)와 한국어 근거 |

### LLM으로 보내는 때

`LLM_URL`로 위 JSON을 `POST`한다(타임아웃 3초). **사진마다 매번** 보낸다 (11-17 톡방에서 정함. 11-16엔 "바뀔 때만"이었음).
LLM 서버가 죽어 있어도 Vision은 계속 돌고, 실패는 로그에 남는다.

### 대표 사진 올리기 `POST /vision/events/{event_id}/representative`

**대표 사진은 LLM(허인혜)이 고른다** (11-17 톡방, 11-18 확인). LLM이 finalize 뒤 고른 사진 번호를 보내면, Vision이 그 사진 원본을 Spring `POST /api/v1/events/{id}/image`(multipart 키 `file`)로 올린다 (11-18 체크리스트 15단계).

```json
{"frame_no": 12}
```

| 코드 | 이유 |
|---|---|
| 200 | 업로드 성공. 본문 = Spring 응답 `{mediaId, eventId, mediaType, filePath}` + `frame_no` |
| 404 | 그 Event·번호의 사진이 없음 (Event당 최근 300장만 메모리에 둠, 사진이 10분 안 오면 Event 삭제) |
| 502 | Spring 연결 실패 또는 Spring 에러 |
| 503 | `SPRING_URL` 설정 안 됨 |

### 에러

| 코드 | 이유 |
|---|---|
| 400 | 이미지로 열 수 없는 파일 |
| 401 | 토큰 불일치 |
| 413 | 10MB 초과 |
| 422 | `image`나 `event_id` 빠짐 (FastAPI 기본) |

## 환경변수

| 이름 | 기본값 | 용도 |
|---|---|---|
| `LLM_URL` | 없음 | LLM 서버 주소. 비우면 안 보냄 |
| `SPRING_URL` | 없음 | Spring 주소 (예: `http://10.21.33.82:8080`). 대표 사진 업로드용 |
| `SAVE_DIR` | 없음 | 설정하면 사진을 `SAVE_DIR/event{id}_{첫 사진 시각}/frame0001.jpg`로 저장 (테스트용). 방문자 사진이라 기본은 저장 안 함 (SAD 6장). 레포에 올리지 말 것 |

확인용 페이지: 서버 PC 브라우저에서 `http://127.0.0.1:8000/vision/latest` — 마지막 사진·위험도·근거를 1초마다 새로고침 (localhost에서만 열림).
| `VISION_MODEL` | `yoloe-26m-seg.pt` | 느리면 `yoloe-26s-seg.pt` |
| `VISION_API_TOKEN` | 없음 | 설정하면 Bearer 토큰 검사. 비우면 검사 안 함 (로컬 연동 테스트용) |

라벨별 신뢰도 기준·배회 시간(30초)·인정 장수(2장)는 `app.py` 맨 위 상수. 현관 카메라 사진으로 조정한다.

## 로그 (SAD 8장 형식, JSON 한 줄)

```json
{"ts": "2026-11-16T21:52:42+09:00", "service": "vision", "event_id": 55, "stage": "vision_analyze", "elapsed_ms": 547, "result": "frame=2 person=7 risk=MEDIUM", "error": null}
{"ts": "2026-11-16T21:52:42+09:00", "service": "vision", "event_id": 55, "stage": "vision_to_llm", "elapsed_ms": 3, "result": "MEDIUM", "error": null}
```

## 한계

- Event 누적값은 메모리에만 있다. 서버를 재시작하면 진행 중이던 Event는 처음부터 다시 센다
- 10분 동안 사진이 안 오면 그 Event 상태를 지운다 (Vision은 Event 종료를 모른다)
- 요청을 한 줄로 처리한다. Pi 1대(1초 1장)엔 충분하고, 여러 대면 서버 워커를 늘려야 한다
