# 소리 감지 → MQTT 발행 · HTTP 업로드 (라즈베리파이 통신 검증)

이번 구현은 사운드 센서 소리 감지 → MQTT 이벤트 발행 → 가짜 음성 파일(`sample.wav`) HTTP 업로드까지다. 파이와 맥북(브로커·서버 역할) 사이의 통신 경로를 검증하는 것이 목적이다. 마이크, 스피커, 카메라 연결과 실제 음성 녹음·재생, STT, Event ID, DB 저장은 구현 범위가 아니다. 소리 감지 센서는 "기준 이상의 소리가 났다"만 알려주며 사람과 다른 소리를 구분하지 않는다. 아래 값은 2026-11-16 기준 사용자 실행 결과이며, 자동화 테스트는 작성하지 않았고 모든 검증은 수동으로 했다.

## 실행 요구사항

| 구분 | 요구사항과 확인 상태 |
|---|---|
| 파이 | Raspberry Pi 4B (4GB), Raspberry Pi OS(Debian 기반), Python 3.13 (실행 출력의 경로 `python3.13` 기준). 가상환경은 `--system-site-packages`로 생성 |
| 파이 패키지 | `gpiozero`(OS 기본 제공 패키지 사용), `paho-mqtt` 2.x(`CallbackAPIVersion` 사용), `requests`. `paho-mqtt`와 `requests`는 가상환경에 pip로 설치 |
| 맥북(임시 서버) | Docker Desktop, `eclipse-mosquitto` 이미지, FastAPI + uvicorn + python-multipart |
| 센서 | AO / G / + / DO 4핀 사운드 센서 모듈 (디지털 출력 DO만 사용, AO 미연결) |
| 네트워크 | 파이와 맥북이 같은 와이파이 또는 같은 아이폰 핫스팟. 맥북 IP는 네트워크가 바뀔 때마다 변하므로 실행 시 인자로 넘김 |

## 구성

| 파일 | 설명 | 상태 |
|---|---|---|
| `sound_upload.py` | 소리 감지 시 MQTT 발행 + `sample.wav` HTTP 업로드. 맥북 IP를 실행 인자로 받음 | 검증됨 |
| `tools/sound_event.py` | 센서 연결 확인용. 소리 감지 시각만 출력 | 검증됨 |
| `tools/mock_server.py` | 업로드 받는 임시 FastAPI 서버. 받은 파일을 `uploads/`에 저장. 백엔드 서버가 나오면 대체 | 검증됨 |

## 배선

파이 전원을 끈 상태에서 연결한다. BCM 번호와 물리 핀 번호를 구분한다.

| 센서 핀 | 파이 |
|---|---|
| `+` | 3.3V (물리 1) |
| `G` | GND (물리 6) |
| `DO` | GPIO17 (BCM17, 물리 11) |
| `AO` | 연결 안 함 |

센서 `+`는 5V가 아니라 3.3V에 연결한다. 점퍼선은 센서와 파이 핀이 모두 바늘형이라 암-암 케이블을 사용했다. 가변저항(파란 나사)으로 감도를 조절한다.

## 통신 구성

| 방향 | 프로토콜 | 주소 | 내용 |
|---|---|---|---|
| 파이 → 브로커 | MQTT | 토픽 `sensor/sound` | 페이로드 `detected` |
| 브로커 → 파이 | MQTT | 토픽 `control` | 제어 명령 문자열 (수신 코드는 미검증) |
| 파이 → 서버 | HTTP POST | `http://<맥북IP>:8000/upload` | multipart `file` 필드, 응답 `{"filename", "size"}` |

## 검증 결과

| 항목 | 확인 방법 | 결과 |
|---|---|---|
| 파이 SSH 접속 (집 와이파이, 학교 아이폰 핫스팟) | `ssh <사용자>@<호스트>.local` | 확인 |
| MQTT 파이 → 맥북 | `mosquitto_pub` / `mosquitto_sub` | 확인 |
| MQTT 맥북 → 파이 | `mosquitto_sub`(파이) / `mosquitto_pub`(맥북) | 확인 |
| HTTP 업로드 | `curl -F`로 텍스트 파일, 1MB 파일 | 확인 |
| 사운드 센서 DO 감지 | `tools/sound_event.py` 출력 | 확인 |
| 소리 감지 → MQTT 발행 | 맥북 구독 쪽에 `detected` 출력 | 확인 |
| 소리 감지 → MQTT + 파일 업로드 | `sound_upload.py`, 맥북 `uploads/`에 파일 생성 | 확인 |
| Tailscale 원격 접속 | - | 미설치 |
| 마이크, 스피커, 카메라 | - | 미연결 |

## 실행 방법

### 맥북 (브로커와 임시 서버)

```bash
# 브로커: 설정 파일을 만들고 컨테이너 실행 (최초 1회)
mkdir -p ~/mosq
printf "listener 1883\nallow_anonymous true\n" > ~/mosq/mosquitto.conf
docker run -d --name mosquitto -p 1883:1883 \
  -v ~/mosq/mosquitto.conf:/mosquitto/config/mosquitto.conf \
  eclipse-mosquitto

# 이후에는
docker start mosquitto

# 맥북 IP 확인
ipconfig getifaddr en0

# 임시 업로드 서버 (tools 폴더에서)
cd iot/sound_mqtt/tools
pip install fastapi uvicorn python-multipart
uvicorn mock_server:app --host 0.0.0.0 --port 8000

# 구독으로 수신 확인 (다른 터미널)
docker exec -it mosquitto mosquitto_sub -h localhost -p 1883 -d -t "sensor/sound"
```

`allow_anonymous true`는 인증 없는 테스트용 설정이다. 개발 중 같은 로컬 망에서만 사용한다.

### 파이

```bash
python3 -m venv --system-site-packages ~/venv
source ~/venv/bin/activate
pip install paho-mqtt requests

# 가짜 음성 파일 생성 (440Hz 사인파 2초, 실제 녹음이 아님)
python - << 'EOF'
import wave, math, struct
with wave.open("sample.wav", "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    for i in range(32000):
        w.writeframes(struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / 16000))))
EOF

python tools/sound_event.py                 # 센서 감지 확인
python sound_upload.py <맥북IP>             # 감지 → MQTT + 업로드
```

정상이면 파이에 `소리 감지 -> MQTT 발행`과 `업로드 결과: {...}`가 출력되고, 맥북 구독 터미널에 `detected`가 나타나며, 맥북 `uploads/`에 `<타임스탬프>_sample.wav`가 저장된다.

## 동작 상세

- 이 모듈은 소리가 감지되면 DO가 `1`에서 `0`으로 내려간다. 코드는 내려가는 순간(`when_deactivated`)을 소리 감지로 본다.
- 일정 간격으로 값을 읽는 폴링 방식(0.01초 주기)은 박수처럼 몇 ms짜리 짧은 신호를 놓쳤다. 이벤트 방식은 짧은 신호도 잡았다.
- `bounce_time`을 주면 짧은 신호가 걸러진다. 그래서 `bounce_time`은 쓰지 않고, 코드에서 마지막 발행 후 일정 시간(3초) 안의 감지는 무시한다.
- 가변저항을 감도가 너무 높은 쪽에 두면 한 번의 소리에 여러 번 감지된다. 이 경우 조용할 때 감지가 없는 위치로 반 바퀴 되돌린다.
- 맥북 IP는 코드에 쓰지 않고 실행 인자로 받는다.

## 한계와 다음 작업

- 센서는 소리 유무만 알려주며, 음성 내용이나 크기 수치는 알 수 없다. 크기 수치가 필요하면 AO를 ADC 칩에 연결해야 한다.
- 업로드 파일은 프로그램이 만든 `sample.wav`다. 마이크가 연결되면 이 파일을 녹음 결과로 교체한다.
- MQTT 토픽 이름과 페이로드, 업로드 엔드포인트는 임시 규약이다. 백엔드(Spring Boot, FastAPI) 구현과 맞춰 확정해야 한다.
- 브로커 인증, 이벤트 ID, 이벤트 저장은 구현하지 않았다.
- 집 밖 접속(Tailscale)은 아직 설정하지 않았다.
