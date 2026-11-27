# HC-SR04 ECHO 폴링 진단

2026-11-17 사용자는 ECHO가 BCM16에 분압 없이 직결되어 있다고 확인했다. 측정을 중지하고 `sudo poweroff` 후 전원 케이블을 분리한다. 전원이 꺼진 상태에서 ECHO에 분압 또는 적절한 레벨 변환을 추가하고 배선·전압을 확인하기 전까지 아래 진단을 실행하지 않는다. 보호 회로의 추가·검증은 아직 완료되지 않았다. [README의 현재 배선 예시](../README.md)를 참고한다.

보호 회로 확인 후 이 진단은 TRIG BCM20(물리 38번)과 ECHO BCM16(물리 36번)를 사용한다. 기존 센서 프로그램을 종료하고 이전에 사용한 같은 가상환경에서 실행한다. 센서 앞 20~30cm에 책을 세운 뒤 코드 블록 전체를 붙여 넣는다. 다섯 번의 결과와 첫 줄을 함께 확인한다. 기존 BCM23/24 진단 설정은 현재 보고된 핀으로 바뀌었다. 매 측정 전 대기 0.2초, HIGH 0.01초, 측정 간 대기 0.5초는 앱 기본과 같지만 이 진단의 상승·하강 제한은 각각 0.03초로 앱 기본 0.1초와 다르다.

```sh
python3 - <<'PY'
import time
import RPi.GPIO as GPIO

TRIG, ECHO = 20, 16
configured = []

def wait_for(level, timeout_ns):
    deadline = time.monotonic_ns() + timeout_ns
    while time.monotonic_ns() < deadline:
        if GPIO.input(ECHO) == level:
            return time.monotonic_ns()
    return None

print(f"GPIO.VERSION={getattr(GPIO, 'VERSION', 'unknown')} file={getattr(GPIO, '__file__', 'unknown')}")
try:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(TRIG, GPIO.OUT, initial=GPIO.LOW)
    configured.append(TRIG)
    GPIO.setup(ECHO, GPIO.IN, pull_up_down=GPIO.PUD_OFF)
    configured.append(ECHO)
    for cycle in range(1, 6):
        if cycle > 1:
            time.sleep(0.5)
        time.sleep(0.2)
        if GPIO.input(ECHO) != GPIO.LOW:
            print(f"{cycle}: ECHO_STUCK_HIGH")
            continue
        try:
            GPIO.output(TRIG, GPIO.HIGH)
            time.sleep(0.01)
        finally:
            GPIO.output(TRIG, GPIO.LOW)
        rise = wait_for(GPIO.HIGH, 30_000_000)
        if rise is None:
            print(f"{cycle}: NO_RISE")
            continue
        fall = wait_for(GPIO.LOW, 30_000_000)
        if fall is None:
            print(f"{cycle}: NO_FALL")
            continue
        pulse_us = (fall - rise) / 1000
        distance_cm = pulse_us * 0.0343 / 2
        print(f"{cycle}: OK {distance_cm:.1f} cm pulse_us={pulse_us:.0f}")
except KeyboardInterrupt:
    print("중단됨")
finally:
    try:
        if TRIG in configured:
            GPIO.output(TRIG, GPIO.LOW)
    finally:
        if configured:
            GPIO.cleanup(configured)
PY
```

`OK`가 반복되면 입력 폴링에서는 펄스를 관찰한 것이므로 기존 lgpio 콜백 경로를 추가 조사할 근거가 된다. 거리는 대략적인 값이다. `NO_RISE`는 상승 신호를 관찰하지 못했다는 뜻이며 센서 고장을 증명하지 않는다. 배선·전원·입력·TRIG 신호·스케줄링 등도 원인일 수 있다. `NO_FALL`은 상승 후 하강을 제한 시간 내에 관찰하지 못한 경우이고, `ECHO_STUCK_HIGH`는 시작 시 HIGH여서 해당 측정의 TRIG를 건너뛴 경우다. 첫 줄의 버전과 파일 경로는 사용 중인 구현을 살펴보기 위한 정보이며 `RPi.GPIO`가 래퍼일 가능성도 있다.

폴링은 소프트웨어가 읽은 시각을 기준으로 하므로 펄스를 놓치거나 실제 길이와 다른 값을 기록할 수 있다. [RPi.GPIO 입력 공식 문서](https://sourceforge.net/p/raspberry-gpio-python/wiki/Inputs/)의 입력 폴링 방식과 같이 확인하며, 이 진단은 실제 장치에서 실행하기 전까지 검증되지 않았다.
