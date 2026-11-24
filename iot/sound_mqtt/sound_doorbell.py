"""소리 감지 -> Spring 명세(MVP v1)에 맞춘 센서 이벤트 발행 + 대표 사진 업로드.

사용: python sound_doorbell.py <MQTT_BROKER> <SPRING_HOST> [이미지경로]
"""
import sys
import json
import threading
import mimetypes
from time import time
from signal import pause

from gpiozero import DigitalInputDevice
import paho.mqtt.client as mqtt
import requests

BROKER = sys.argv[1]
SPRING = sys.argv[2]
IMAGE_PATH = sys.argv[3] if len(sys.argv) > 3 else "visitor.jpg"

DEVICE_ID = 1
SENSOR_TYPE = "SOUND"   # 백엔드와 확정 필요 (명세 예시: MOTION, SHOCK, DOORBELL)
SENSOR_TOPIC = f"doorbell/{DEVICE_ID}/sensor"
EVENT_TOPIC = f"doorbell/{DEVICE_ID}/event"
COOLDOWN_S = 5
EVENT_WAIT_S = 5

event_ready = threading.Event()
event_id = None


def on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe(EVENT_TOPIC, qos=1)
    print("브로커 연결, 구독:", EVENT_TOPIC)


def on_message(client, userdata, msg):
    global event_id
    try:
        data = json.loads(msg.payload.decode())
        event_id = data["eventId"]
    except (ValueError, KeyError) as e:
        print("event 메시지 형식 오류:", e)
        return
    print("eventId 수신:", data)
    event_ready.set()


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, 1883)
client.loop_start()

sensor = DigitalInputDevice(17)
last = 0


def on_sound():
    global last
    now = time()
    if now - last < COOLDOWN_S:
        return
    last = now
    try:
        event_ready.clear()
        payload = {"deviceId": DEVICE_ID, "sensorType": SENSOR_TYPE, "value": 1}
        client.publish(SENSOR_TOPIC, json.dumps(payload), qos=1)
        print("센서 이벤트 발행:", payload)

        if not event_ready.wait(timeout=EVENT_WAIT_S):
            print(f"eventId 응답 없음 ({EVENT_WAIT_S}초)")
            return

        url = f"http://{SPRING}:8080/api/v1/events/{event_id}/image"
        mime = mimetypes.guess_type(IMAGE_PATH)[0] or "image/jpeg"
        with open(IMAGE_PATH, "rb") as f:
            r = requests.post(url, files={"file": (IMAGE_PATH, f, mime)}, timeout=10)
        print("이미지 업로드:", r.status_code, r.text)
    except Exception as e:
        print("실패:", e)


sensor.when_deactivated = on_sound
print("대기 중... (Ctrl+C로 종료)")
pause()
