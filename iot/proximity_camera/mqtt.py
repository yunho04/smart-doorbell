"""One-in-flight MQTT event exchange; ambiguous state requires operator intervention."""
import json
import logging
import threading
import time

MAX_LONG = 2**63 - 1


def valid_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= MAX_LONG


class EventClient:
    def __init__(self, config, client=None):
        self.cfg = config
        self.sensor_topic = 'doorbell/%s/sensor' % config['device_id']
        self.event_topic = 'doorbell/%s/event' % config['device_id']
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.received = threading.Event()
        self.pending = False
        self.event_id = None
        self.seen = set()
        self.poisoned = False
        self.closing = False
        self.sub_mid = None
        if client is None:
            import paho.mqtt.client as mqtt
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=config.get("mqtt_client_id") or "doorbell-sensor-camera-%s" % config["device_id"], protocol=mqtt.MQTTv311,
                                 clean_session=True, reconnect_on_failure=False)
            client.connect_timeout = config['connection_timeout_s']
        self.client = client
        client.on_connect_fail = self._connect_fail
        client.on_connect = self._connect
        client.on_subscribe = self._subscribe
        client.on_message = self._message
        client.on_disconnect = self._disconnect

    def _fail(self):
        self.poisoned = True
        self.ready.set()
        self.received.set()

    def _connect_fail(self, client, userdata):
        with self.lock:
            self._fail()
        client.disconnect()

    def _connect(self, client, userdata, flags, reason_code, properties):
        with self.lock:
            if reason_code != 0:
                self._fail()
                return
            result, self.sub_mid = client.subscribe(self.event_topic, qos=1)
            if result != 0:
                self._fail()

    def _subscribe(self, client, userdata, mid, reason_codes, properties):
        with self.lock:
            if mid != self.sub_mid or len(reason_codes) != 1 or reason_codes[0] != 1:
                self._fail()
            else:
                self.ready.set()

    def _message(self, client, userdata, message):
        with self.lock:
            if self.poisoned or self.closing:
                return
        if message.topic != self.event_topic or message.retain or len(message.payload) > 4096:
            return
        try:
            data = json.loads(message.payload)
            if not isinstance(data, dict) or data.get('status') != 'CREATED' or not valid_id(data.get('eventId')):
                return
            event_id = data['eventId']
        except (UnicodeDecodeError, ValueError, TypeError):
            return
        with self.lock:
            if self.poisoned or self.closing:
                return
            if event_id in self.seen:
                return
            self.seen.add(event_id)
            if not self.pending or self.event_id is not None:
                self._fail()
            else:
                self.event_id = event_id
                self.received.set()

    def _disconnect(self, client, userdata, flags, reason_code, properties):
        with self.lock:
            if not self.closing:
                self._fail()

    def start(self):
        try:
            self.client.connect_async(self.cfg['mqtt_host'], self.cfg['mqtt_port'], keepalive=30)
            self.client.loop_start()
            if not self.ready.wait(self.cfg['connection_timeout_s']):
                with self.lock: self._fail()
            self.check()
            logging.info("mqtt ready host=%s port=%s client_id=%s subscribe=%s qos=1", self.cfg["mqtt_host"], self.cfg["mqtt_port"], self.cfg.get("mqtt_client_id") or "doorbell-sensor-camera-%s" % self.cfg["device_id"], self.event_topic)
        except BaseException:
            self.close()
            raise

    def check(self):
        with self.lock:
            if self.poisoned:
                raise RuntimeError('MQTT event state uncertain; intervention required')

    def create_event(self, request_id, distance_cm):
        with self.lock:
            if self.poisoned or self.closing or not self.ready.is_set() or self.pending:
                raise RuntimeError('MQTT event state unavailable')
            self.pending = True
            self.event_id = None
            self.received.clear()
        deadline = time.monotonic() + self.cfg['event_timeout_s']
        try:
            self.publish_presence(timeout=min(self.cfg['presence_ack_timeout_s'], self.cfg['event_timeout_s']))
            if not self.received.wait(max(0, deadline - time.monotonic())):
                raise RuntimeError('MQTT event response timed out')
            self.check()
            with self.lock: return self.event_id
        except BaseException:
            with self.lock: self._fail()
            raise

    def publish_presence(self, timeout=None):
        self.check()
        with self.lock:
            if self.closing or not self.pending:
                raise RuntimeError('MQTT session unavailable')
        payload = json.dumps({'deviceId': self.cfg['device_id'], 'sensorType': self.cfg['sensor_type'], 'value': 1, 'presenceDetected': True}, separators=(',', ':'))
        try:
            info = self.client.publish(self.sensor_topic, payload, qos=1, retain=False)
            if info.rc != 0:
                raise RuntimeError('MQTT publish failed')
            info.wait_for_publish(timeout=self.cfg['presence_ack_timeout_s'] if timeout is None else timeout)
            if not info.is_published():
                raise RuntimeError('MQTT publish acknowledgement timed out')
            self.check()
        except BaseException:
            with self.lock: self._fail()
            raise

    def abort(self):
        with self.lock: self._fail()

    def finish(self):
        with self.lock:
            if self.poisoned:
                raise RuntimeError('MQTT event state uncertain; intervention required')
            self.pending = False
            self.event_id = None

    def close(self):
        with self.lock:
            if self.closing:
                return
            self.closing = True
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()
