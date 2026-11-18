import sys
from gpiozero import DigitalInputDevice
from signal import pause
from time import time
import paho.mqtt.client as mqtt
import requests

BROKER = sys.argv[1]
SERVER = f"http://{BROKER}:8000/upload"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER, 1883)
client.loop_start()

sensor = DigitalInputDevice(17)
last_sent = 0

def on_sound():
    global last_sent
    now = time()
    if now - last_sent < 3:
        return
    last_sent = now
    client.publish("sensor/sound", "detected")
    print("소리 감지 -> MQTT 발행")
    try:
        with open("sample.wav", "rb") as f:
            r = requests.post(SERVER, files={"file": ("sample.wav", f, "audio/wav")}, timeout=10)
        print("업로드 결과:", r.json())
    except Exception as e:
        print("업로드 실패:", e)

sensor.when_deactivated = on_sound
print("대기 중... (Ctrl+C로 종료)")
pause()
