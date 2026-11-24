import sys
import paho.mqtt.client as mqtt

BROKER = sys.argv[1]

def on_connect(client, userdata, flags, reason_code, properties):
    print("브로커 연결됨")
    client.subscribe("control")

def on_message(client, userdata, msg):
    text = msg.payload.decode()
    print(f"[제어 명령] {text}")
    print(f"안내 음성 재생(가짜): {text}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, 1883)
print("control 대기 중... (Ctrl+C로 종료)")
client.loop_forever()
