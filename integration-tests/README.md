# 통합 테스트 시뮬레이터

실제 라즈베리파이 · Vision AI · STT · LLM 서버 없이, Mac 로컬에서 Smart Doorbell 의 전체 데이터 흐름을 검증한다.
Spring 백엔드, MQTT 브로커, PostgreSQL 은 **실제 것**을 쓰고 나머지 세 역할만 가상으로 대신한다.

```
가상 Pi1 ──MQTT doorbell/{id}/sensor──▶ Spring ──MQTT doorbell/{id}/event (CREATED/ENDED)──▶ 가상 Pi1
                                          │  무감지 10초 → POST /api/v1/events/{id}/finalize
                                          ▼
                                       가상 LLM ──(가상 Vision) POST /representative-image──▶ Spring
                                          └────────────────── POST /result ─────────────────▶ Spring
대시보드 역할(세션 로그인): GET /events, GET /events/{id}, GET /events/{id}/image, POST /events/{id}/feedback ──▶ 가상 LLM /feedback
```

## 준비물

| 항목 | 확인 / 실행 |
| --- | --- |
| Python 3.10+ | `python3 --version` |
| MQTT 브로커 (1883) | `brew services start mosquitto` |
| PostgreSQL `smart_doorbell` DB | 평소 개발 DB 그대로 (MVP v2 스키마 + `docs/database/alter-llm-conversation.sql` 적용, device 1 존재) |
| JDK 21 | 백엔드 `build.gradle` toolchain |

Python 의존성(`paho-mqtt`, `requests`)은 `run.sh` 가 `integration-tests/.venv` 에 자동 설치한다.
직접 설치하려면:

```bash
cd integration-tests
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 실행

저장소 루트에서 명령어 한 번:

```bash
./integration-tests/run.sh
```

- 백엔드(8080)가 꺼져 있으면 **테스트 설정으로 직접 띄우고**, 끝나면 종료한다. (첫 기동은 Gradle 빌드 때문에 오래 걸릴 수 있다. 로그: `integration-tests/logs/backend.log`)
- 전체 5개 시나리오에 약 2분 걸린다. (이벤트 종료가 "무감지 10초" 규칙이라 방문 1건당 약 17초)
- 실패가 하나라도 있으면 종료 코드 1.

자주 쓰는 옵션 (`./integration-tests/run.sh --help`):

```bash
./integration-tests/run.sh --scenario delivery            # 한 시나리오만 (여러 번 지정 가능)
./integration-tests/run.sh --keep-backend                 # 끝난 뒤 백엔드를 켜 둠 (대시보드 확인용)
./integration-tests/run.sh --visit-seconds 8              # 방문 중 감지 전송 시간
DOORBELL_PASSWORD=**** ./integration-tests/run.sh         # 대시보드 비밀번호 지정
```

비밀번호를 지정하지 않으면 `backend/src/main/resources/application.properties` 의 `app.auth.password` 를 읽는다.

## 시나리오

| 이름 | 내용 | 주요 검증 |
| --- | --- | --- |
| `delivery` | 정상적인 택배 기사 방문 (LOW) | 전체 흐름, 피드백 HIGH |
| `unclear` | 방문 목적이 불분명한 방문자 (MEDIUM) | 방문 중 LLM 실시간 응답 → Pi1 MQTT 수신, `visitorText` 가 빈 문자열(발화 인식 안 됨)·`purpose` 가 null 인 턴 |
| `high-risk` | 위험도가 높은 방문자 (HIGH) | 전체 흐름, 피드백 LOW |
| `consecutive` | 연속 방문 | 방문1 이 ANALYZING 인 동안 방문2 감지 → 새 eventId, 두 결과가 섞이지 않음 |
| `duplicate` | 동일 이벤트 결과 중복 전송 | 같은 결과 2회 재전송 후 대화 기록/응답 이력 행 수 불변, 피드백 수정 시 행 1개 유지 |

방문 1건의 단계:

1. 가상 Pi1 이 `doorbell/{id}/sensor` 로 감지 메시지 발행 (실제 Pi 와 같은 페이로드) → Spring 의 `CREATED` 수신, 실제 `eventId` 확보
2. 방문 중 1초 간격으로 감지 메시지 전송 → 이벤트가 유지되는지(추가 `CREATED`/`ENDED` 없음) 확인
3. 감지 중단 → Spring 스케줄러가 10초 뒤 `ENDED` 발행, 상태 `ANALYZING`
4. 가상 LLM 이 `POST /api/v1/events/{id}/finalize` 수신 (본문 `{"eventId": n}`)
5. 가상 Vision 이 대표 이미지(PNG) 업로드 → 가상 LLM 이 최종 결과 전송
6. 상세 조회로 분석 결과 · 대화 기록 · 대표 이미지(다운로드 바이트 일치) 검증, 목록 API 노출 확인
7. 피드백 전송 → DB 저장, 가상 LLM `/feedback` 수신 본문 확인

최종 결과 JSON (`backend` 의 `EventResultRequest` 규격):

```json
{
  "riskLevel": "LOW",
  "summary": "[통합테스트] 택배 기사가 물품을 문 앞에 두고 떠났습니다.",
  "responseCode": "DELIVERY_01",
  "responseText": "문 앞에 두고 가시면 됩니다. 감사합니다.",
  "purpose": "택배 배송",
  "conversationSummary": "방문자가 택배 배송을 알렸고 문 앞에 두도록 안내했습니다.",
  "conversation": [
    {"turnNo": 1, "visitorText": "택배 왔습니다.", "purpose": "택배 배송",
     "responseCode": "DELIVERY_01", "responseText": "안녕하세요. 어떤 택배인가요?"}
  ]
}
```

`responseCode` 값은 저장소에 확정 목록이 없어 테스트용으로 정한 값이다. 실제 코드표가 정해지면 `doorbell_sim/scenarios.py` 만 고치면 된다.

## 실제 LLM 으로 요청이 나가지 않게 하는 방법

- 테스트 전용 설정 `config/application-integration.properties` 가 `llm.base-url` 을 로컬 가상 LLM(`http://127.0.0.1:18001`)으로 덮어쓴다. `application.properties` 는 수정하지 않는다.
- `run.sh` 는 백엔드를 `--spring.config.additional-location=file:.../application-integration.properties` 로 띄운다.
- 8080 에 백엔드가 이미 떠 있으면 프로세스 인자에 위 설정 파일이 있는지 확인하고, **없으면 센서 메시지를 보내기 전에 중단**한다. (평소 방식으로 띄운 백엔드는 종료 후 다시 실행)

백엔드를 직접 띄워 두고 반복 실행하려면:

```bash
cd backend
./gradlew bootRun --args="--spring.config.additional-location=file:$(pwd)/../integration-tests/config/application-integration.properties"
```

## 대시보드에서 확인

테스트 이벤트는 실제 DB 에 저장되므로 React 대시보드에 그대로 보인다. 요약이 `[통합테스트]` 로 시작하고, 대표 이미지는 위험도 색(초록/주황/빨강) 배경의 실루엣이다.

```bash
./integration-tests/run.sh --keep-backend     # 또는 평소대로 백엔드 실행
cd frontend && npm run dev                    # http://localhost:5173 로그인
```

`--keep-backend` 로 남긴 백엔드는 가상 LLM 주소를 보고 있으므로 확인이 끝나면 종료한다 (실행 끝에 출력되는 `kill <pid>`).

## 주의

- **DB 를 지우거나 초기화하지 않는다.** 실행할 때마다 이벤트가 6건씩 추가되고, 직접 DB 조회는 `psql` 로 `SELECT count(*)` 만 한다 (`psql` 이 없으면 해당 검증은 SKIP).
- 기본 `deviceId` 는 1 이다. 실제 Pi 가 같은 브로커에 같은 deviceId 로 연결돼 있으면 이벤트가 섞이므로 Pi 를 끄고 실행한다.
- 해당 device 에 `DETECTED` 상태 이벤트가 남아 있으면 첫 단계(`CREATED` 수신)가 실패한다. 10초쯤 뒤 다시 실행한다.

## 구성

```
integration-tests/
├── run.sh                                  실행기 (venv 준비 + 실행)
├── requirements.txt
├── config/application-integration.properties   테스트 전용 Spring 설정
└── doorbell_sim/
    ├── __main__.py     사전 점검, 옵션, 요약
    ├── runner.py       방문 단계와 시나리오별 검증
    ├── scenarios.py    시나리오 데이터 (결과 JSON)
    ├── pi.py           가상 Pi1 (MQTT)
    ├── llm.py          가상 LLM HTTP 서버
    ├── vision.py       가상 Vision (테스트 이미지 생성 · 업로드)
    ├── api.py          Spring REST 클라이언트
    ├── backend.py      백엔드 기동 · LLM 격리 확인
    ├── db.py           psql 읽기 전용 행 수 확인
    ├── report.py       단계별 PASS/FAIL 출력
    └── settings.py     경로 · properties 읽기
```
