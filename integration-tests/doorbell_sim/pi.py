"""가상 Pi1: 실제 Pi 와 같은 토픽/페이로드로 센서 메시지를 발행하고 Spring 의 MQTT 메시지를 수신한다."""
import json
import os
import threading
import time

import paho.mqtt.client as mqtt


class Message:
    def __init__(self, topic, data):
        self.topic, self.data, self.at = topic, data, time.monotonic()


class VirtualPi:
    def __init__(self, host, port, device_id):
        self.host, self.port, self.device_id = host, port, device_id
        self.sensor_topic = "doorbell/%s/sensor" % device_id
        self.event_topic = "doorbell/%s/event" % device_id
        self.response_topic = "doorbell/%s/response" % device_id
        self.messages = []
        self.cond = threading.Condition()
        self.subscribed = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311,
                                  client_id="integration-sim-pi1-%d" % os.getpid())
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = lambda *a: self.subscribed.set()
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe([(self.event_topic, 1), (self.response_topic, 1)])

    def _on_message(self, client, userdata, message):
        try:
            data = json.loads(message.payload)
        except ValueError:
            data = {"_raw": message.payload.decode("utf-8", "replace")}
        with self.cond:
            self.messages.append(Message(message.topic, data))
            self.cond.notify_all()

    def start(self, timeout=5):
        self.client.connect(self.host, self.port, keepalive=30)
        self.client.loop_start()
        return self.subscribed.wait(timeout)

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()

    def publish_presence(self):
        """iot/proximity_camera/mqtt.py 의 publish_presence 와 동일한 페이로드."""
        payload = json.dumps({"deviceId": self.device_id, "sensorType": "MOTION", "value": 1,
                              "presenceDetected": True}, separators=(",", ":"))
        self.client.publish(self.sensor_topic, payload, qos=1, retain=False).wait_for_publish(timeout=5)

    def mark(self):
        with self.cond:
            return len(self.messages)

    def since(self, mark):
        with self.cond:
            return self.messages[mark:]

    def wait_for(self, predicate, timeout, since=0):
        deadline = time.monotonic() + timeout
        with self.cond:
            while True:
                for message in self.messages[since:]:
                    if predicate(message):
                        return message
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.cond.wait(remaining)

    def wait_event(self, status, timeout, since=0, event_id=None):
        return self.wait_for(lambda m: m.topic == self.event_topic and m.data.get("status") == status
                             and (event_id is None or m.data.get("eventId") == event_id), timeout, since)
