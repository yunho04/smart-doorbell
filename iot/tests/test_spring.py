import json
import socket
import tempfile
import threading
import time
import unittest
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from proximity_camera.camera import Camera
from proximity_camera.config import DEFAULTS, load_config, validate_spring_config
from proximity_camera.controller import Controller
from proximity_camera.mqtt import EventClient
from proximity_camera.sensor import Reading
from proximity_camera.spring import SpringIntegration, upload_image


class FakeClient:
    def __init__(self): self.published = []; self.ack = True; self.respond = 15; self.closed = False
    def connect_async(self, *args, **kwargs): self.connection = args
    def loop_start(self):
        self.on_connect(self, None, None, 0, None)
        self.on_subscribe(self, None, 7, [1], None)
    def subscribe(self, topic, qos): self.subscription = (topic, qos); return 0, 7
    def publish(self, topic, payload, qos, retain):
        self.published.append((topic, json.loads(payload), qos, retain))
        if self.respond is not None: self.message(self.respond)
        fake = self
        class Info:
            rc = 0
            def wait_for_publish(self, timeout): pass
            def is_published(self): return fake.ack
        return Info()
    def message(self, event_id, topic='doorbell/1/event', retain=False, status='CREATED'):
        msg = SimpleNamespace(topic=topic, retain=retain, payload=json.dumps({'eventId': event_id, 'status': status}).encode())
        self.on_message(self, None, msg)
    def disconnect(self): self.closed = True
    def loop_stop(self): pass


class MQTTTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeClient(); self.cfg = dict(DEFAULTS, mqtt_host='127.0.0.1', event_timeout_s=.01, connection_timeout_s=.01)
        self.events = EventClient(self.cfg, self.fake); self.events.start()
    def tearDown(self): self.events.close()
    def test_subscription_then_publish_and_early_response(self):
        self.assertEqual(self.fake.subscription, ('doorbell/1/event', 1))
        self.assertEqual(self.events.create_event('req', 32), 15)
        self.assertEqual(self.fake.published, [('doorbell/1/sensor', {'deviceId': 1, 'sensorType': 'MOTION', 'value': 1, 'presenceDetected': True}, 1, False)])
        self.fake.message(15); self.events.check(); self.events.finish()
    def test_invalid_messages_ignored_then_timeout(self):
        self.fake.respond = None
        for value, topic, retain in [(False,'doorbell/1/event',False),(5,'other',False),(7,'doorbell/1/event',True)]:
            self.fake.message(value, topic, retain)
        with self.assertRaises(RuntimeError): self.events.create_event('r', 40)
        with self.assertRaises(RuntimeError): self.events.create_event('r2', 40)
    def test_ambiguous_and_unsolicited_poison(self):
        self.events.create_event('r', 40); self.fake.message(16)
        with self.assertRaises(RuntimeError): self.events.finish()
        other = EventClient(self.cfg, FakeClient()); other.start(); other.client.message(20)
        with self.assertRaises(RuntimeError): other.create_event('r', 40)
        other.close()
    def test_uncertain_publish_and_disconnect(self):
        self.fake.ack = False
        with self.assertRaises(RuntimeError): self.events.create_event('r', 40)
        self.assertTrue(self.events.poisoned)
        other = EventClient(self.cfg, FakeClient()); other.start()
        other._disconnect(other.client, None, None, 1, None)
        with self.assertRaises(RuntimeError): other.create_event('r', 40)
        other.close()
    def test_lifecycle_guards_and_terminal_state(self):
        client = FakeClient(); events = EventClient(self.cfg, client)
        with self.assertRaises(RuntimeError): events.create_event('before-start', 40)
        self.assertEqual(client.published, [])
        events.start(); events.abort(); seen = set(events.seen)
        client.message(100)
        self.assertEqual(events.seen, seen)
        events.close(); events.close(); client.message(101)
        self.assertEqual(events.seen, seen)
        with self.assertRaises(RuntimeError): events.create_event('after-close', 40)
        self.assertEqual(client.published, [])

    def test_close_without_poison_prevents_publish(self):
        client = FakeClient(); events = EventClient(self.cfg, client); events.start(); events.close()
        client.message(100)
        self.assertEqual(events.seen, set())
        with self.assertRaises(RuntimeError): events.create_event('after-close', 40)
        self.assertEqual(client.published, [])

    def test_startup_failures_close_without_publish(self):
        for failure in ('missing_suback', 'bad_connack', 'connect_fail'):
            class Failing(FakeClient):
                stopped = False
                def loop_stop(self): self.stopped = True
                def loop_start(self):
                    if failure == 'connect_fail': self.on_connect_fail(self, None)
                    elif failure == 'bad_connack': self.on_connect(self, None, None, 1, None)
                    else: self.on_connect(self, None, None, 0, None)
            with self.subTest(failure=failure):
                client = Failing(); events = EventClient(self.cfg, client)
                with self.assertRaises(RuntimeError): events.start()
                self.assertTrue(client.closed); self.assertTrue(client.stopped)
                self.assertEqual(client.published, [])
                if failure == 'missing_suback':
                    events._subscribe(client, None, 7, [1], None)
                with self.assertRaises(RuntimeError): events.create_event('r', 40)
                self.assertEqual(client.published, [])

    def test_bad_suback_fails_and_cleans_up(self):
        class Bad(FakeClient):
            def loop_start(self):
                self.on_connect(self, None, None, 0, None); self.on_subscribe(self, None, 7, [0], None)
        client = Bad(); events = EventClient(self.cfg, client)
        with self.assertRaises(RuntimeError): events.start()
        self.assertTrue(client.closed)


class Handler(BaseHTTPRequestHandler):
    status = 201; result = {'mediaId': 3, 'eventId': 15, 'mediaType': 'IMAGE', 'filePath': '/image'}; calls = []; delay = 0
    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        self.calls.append((self.path, self.headers['Content-Type'], body))
        if self.delay: time.sleep(self.delay)
        try:
            self.send_response(self.status); self.end_headers()
            self.wfile.write(self.result if isinstance(self.result, bytes) else json.dumps(self.result).encode())
        except (BrokenPipeError, ConnectionResetError): pass
    def log_message(self, *args): pass


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
    def setUp(self):
        Handler.status = 201; Handler.result = {'mediaId':3,'eventId':15,'mediaType':'IMAGE','filePath':'/image'}; Handler.calls = []; Handler.delay = 0
        self.tmp = tempfile.TemporaryDirectory(); self.path = Path(self.tmp.name)/'test.png'; self.path.write_bytes(b'example-png')
        self.cfg = dict(DEFAULTS, spring_base_url='http://127.0.0.1:%s' % self.server.server_port, http_timeout_s=.2)
    def tearDown(self): self.tmp.cleanup()
    def test_multipart_contents(self):
        upload_image(self.cfg, 15, self.path)
        path, content_type, body = Handler.calls[0]
        self.assertEqual(path, '/api/v1/events/15/image')
        message = BytesParser(policy=default).parsebytes(('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
        parts = list(message.iter_parts()); self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].get_param('name', header='content-disposition'), 'file')
        self.assertEqual(parts[0].get_payload(decode=True), b'example-png')
    def test_errors_and_no_retry(self):
        for status, result in [(400, {}), (404, {}), (500, {}), (302, {}), (201, b'bad'), (201, {'mediaId':3,'eventId':16,'mediaType':'IMAGE','filePath':'x'}), (201, {'mediaId':3,'eventId':15,'mediaType':'VIDEO','filePath':'x'}), (201, b' '*65537)]:
            with self.subTest(status=status, result=str(result)[:20]):
                Handler.status, Handler.result, Handler.calls = status, result, []
                with self.assertRaises(RuntimeError): upload_image(self.cfg, 15, self.path)
                self.assertEqual(len(Handler.calls), 1)
    def test_limit_and_timeout(self):
        with self.assertRaises(ValueError): upload_image(dict(self.cfg, max_file_bytes=2),15,self.path)
        self.assertEqual(Handler.calls, [])
        Handler.delay = .2
        with self.assertRaises(socket.timeout): upload_image(dict(self.cfg, http_timeout_s=.03),15,self.path)
        self.assertEqual(len(Handler.calls), 1)
    def test_controller_order_and_mock_camera(self):
        order = []; fake = FakeClient(); events = EventClient(self.cfg, fake); events.start()
        original_publish = fake.publish
        def publish(*args, **kwargs): order.append('event'); return original_publish(*args, **kwargs)
        fake.publish = publish
        cfg = dict(self.cfg, output_dir=self.tmp.name, min_free_bytes=0, consecutive=1)
        camera = Camera(cfg, 'mock'); capture = camera.capture
        def capture_order(request_id): order.append('capture'); return capture(request_id)
        camera.capture = capture_order
        integration = SpringIntegration(cfg, events)
        with patch('proximity_camera.spring.upload_image', wraps=upload_image) as upload:
            controller = Controller(None, camera, cfg, integration=integration)
            controller.step(Reading(40, 0, None))
            self.assertEqual(controller.failures, 0); self.assertEqual(upload.call_count, 1)
        self.assertEqual(order, ['event', 'capture']); self.assertEqual(len(Handler.calls), 1)
        self.assertTrue(Handler.calls[0][2].find(b'\x89PNG') >= 0); integration.close()


class ConfigTests(unittest.TestCase):
    def test_invalid_spring_config(self):
        with tempfile.TemporaryDirectory() as d:
            file = Path(d)/'cfg.json'
            for cfg in [{'mqtt_host':True}, {'mqtt_host':123}, {'spring_base_url':[]}, {'spring_base_url':3}, {'mqtt_host':'broker.local'}, {'spring_base_url':'http://localhost:8080'}, {'spring_base_url':'http://user@127.0.0.1'}, {'device_id':True}, {'event_timeout_s':0}]:
                file.write_text(json.dumps(cfg))
                with self.assertRaises(ValueError): load_config(file)

class AsyncTests(unittest.TestCase):
    def setUp(self):
        from proximity_camera.async_controller import AsyncSpringController
        self.now = 0
        self.cfg = dict(DEFAULTS, consecutive=1, cooldown_s=0)
        self.fake = FakeClient()
        self.events = EventClient(self.cfg, self.fake)
        self.events.start()
        self.release = threading.Event()
        self.capturing = threading.Event()
        self.uploads = []
        outer = self
        class Camera:
            def session(self, stopping):
                from contextlib import nullcontext
                return nullcontext(self)
            def capture(self, request_id):
                outer.capturing.set()
                if not outer.release.wait(2): raise RuntimeError('test camera timeout')
                return 'photo.jpg'
        class Integration:
            events = self.events
            def create_event(self, req, dist): return self.events.create_event(req, dist)
            def upload(self, event_id, path, request_id, finish=True): outer.uploads.append(event_id)
            def abort(self): self.events.abort()
        self.lookups = []
        self.status = 'DETECTED'
        def lookup(cfg, event_id): self.lookups.append(event_id); return self.status
        self.controller = AsyncSpringController(None, Camera(), self.cfg, Integration(), lambda: self.now, lookup)
    def tearDown(self):
        self.release.set()
        if self.controller.job: self.controller.job.join(3)
        self.events.close()
    def step(self, now, value, error=None):
        self.now = now
        self.controller.step(Reading(value, 0, error))
    def begin(self):
        self.step(0, 40)
        self.assertTrue(self.capturing.wait(1))
    def test_heartbeats_during_camera_and_stop_on_far_invalid(self):
        self.begin()
        for t in (2, 4, 6, 8, 10, 12): self.step(t, 40)
        self.assertEqual(len(self.fake.published), 7)
        self.step(14, 80); self.step(16, None, 'no echo')
        self.assertEqual(len(self.fake.published), 7)
        self.release.set(); self.controller.job.join(1)
        self.assertEqual(self.uploads, [15])
    def test_short_return_and_long_gap_status(self):
        self.begin(); self.step(2, 80); self.step(4, 40)
        self.assertEqual(len(self.fake.published), 2)
        self.release.set(); self.controller.job.join(1)
        self.step(15, 40); self.step(15.5, 40)
        self.assertEqual(self.lookups, [15]); self.assertEqual(len(self.fake.published), 3)
        self.step(26, 80); self.assertEqual(self.lookups, [15, 15])
        self.assertEqual(self.controller.state, 'LATCHED')
        self.status = 'ANALYZING'; self.step(27, 80)
        self.assertEqual(self.controller.state, 'ARMED')
        self.assertEqual(self.uploads, [15])
    def test_long_gap_while_busy_never_publishes(self):
        self.begin(); self.step(11, 40)
        self.assertEqual(len(self.fake.published), 1); self.assertEqual(self.lookups, [])
        self.release.set(); self.controller.job.join(1)
        self.step(12, 40); self.step(12.5, 40)
        self.assertEqual(self.lookups, [15]); self.assertEqual(len(self.fake.published), 2)
    def test_failed_ack_stops_and_no_retry(self):
        self.begin(); self.fake.ack = False
        with self.assertRaises(RuntimeError): self.step(2, 40)
        with self.assertRaises(RuntimeError): self.step(4, 40)
        self.assertEqual(len(self.fake.published), 2)
    def test_close_waits_for_job(self):
        self.begin(); self.release.set(); self.controller.close()
        self.assertEqual(self.uploads, [15]); self.assertFalse(self.controller.job.is_alive())

class StatusHTTPTests(HTTPTests):
    def test_get_status_validation(self):
        from proximity_camera.spring import get_event_status
        def do_get(handler):
            handler.send_response(Handler.status); handler.end_headers()
            handler.wfile.write(json.dumps(Handler.result).encode())
        with patch.object(Handler, 'do_GET', do_get, create=True):
            Handler.status = 200
            Handler.result = {'eventId': 15, 'deviceId': 1, 'status': 'DETECTED'}
            self.assertEqual(get_event_status(self.cfg, 15), 'DETECTED')
            for result in ({'eventId': 16, 'deviceId': 1, 'status': 'DETECTED'}, {'eventId': 15, 'deviceId': True, 'status': 'DETECTED'}, {'eventId': 15, 'deviceId': 1, 'status': 'CREATED'}):
                Handler.result = result
                with self.assertRaises(RuntimeError): get_event_status(self.cfg, 15)
            Handler.status = 302
            with self.assertRaises(RuntimeError): get_event_status(self.cfg, 15)

class SchoolConfigTests(unittest.TestCase):
    def test_school_profile_and_validation(self):
        cfg = load_config(Path(__file__).resolve().parents[1] / 'config.school.json')
        validate_spring_config(cfg)
        self.assertEqual((cfg['mqtt_host'], cfg['spring_base_url'], cfg['mqtt_client_id']),
                         ('10.21.33.82', 'http://10.21.33.82:8080', 'doorbell-sensor-camera-1'))
        with tempfile.TemporaryDirectory() as d:
            file = Path(d) / 'config.json'
            for value in ('', 'bad\nclient', 42, 'x' * 129):
                file.write_text(json.dumps({'mqtt_client_id': value}))
                with self.assertRaises(ValueError): load_config(file)
            file.write_text(json.dumps({'presence_interval_s': 9, 'mqtt_host': '127.0.0.1', 'spring_base_url': 'http://127.0.0.1'}))
            with self.assertRaises(ValueError): validate_spring_config(load_config(file))
            file.write_text(json.dumps({'interval_s': 10, 'mqtt_host': '127.0.0.1', 'spring_base_url': 'http://127.0.0.1'}))
            local_cfg = load_config(file)
            self.assertEqual(local_cfg['interval_s'], 10)
            with self.assertRaises(ValueError): validate_spring_config(local_cfg)

class InitialPublishTests(unittest.TestCase):
    def test_event_deadline_is_shared_between_puback_and_reply(self):
        client = FakeClient(); client.respond = None
        cfg = dict(DEFAULTS, mqtt_host='127.0.0.1', event_timeout_s=5)
        events = EventClient(cfg, client); events.start()
        recorded = []
        def publish(timeout=None): recorded.append(timeout)
        events.publish_presence = publish
        class Received:
            def clear(self): pass
            def wait(self, timeout): recorded.append(timeout); return False
            def set(self): pass
        events.received = Received()
        with patch('proximity_camera.mqtt.time.monotonic', side_effect=[100, 104]):
            with self.assertRaises(RuntimeError): events.create_event('r', 40)
        self.assertEqual(recorded, [2, 1]); events.close()

class ShutdownTests(AsyncTests):
    def test_cancel_prevents_upload_after_camera(self):
        self.begin()
        self.controller.cancel()
        self.release.set()
        self.controller.close()
        self.assertEqual(self.uploads, [])

    def test_worker_error_is_not_hidden_by_poison(self):
        self.begin()
        self.controller.job_error = RuntimeError('camera failed detail')
        self.events.abort()
        with self.assertRaisesRegex(RuntimeError, 'camera failed detail'):
            self.controller.check()

    def test_timeout_is_reported(self):
        class Stuck:
            def join(self, timeout): pass
            def is_alive(self): return True
        self.controller.job = Stuck()
        with self.assertRaisesRegex(RuntimeError, 'did not stop'):
            self.controller.close()
        self.controller.job = None

class MaxCapturesCLITests(unittest.TestCase):
    def test_one_capture_keeps_reading_until_worker_done(self):
        from proximity_camera.__main__ import main
        from unittest.mock import MagicMock
        reads = []
        class Sensor:
            def __init__(self, *args): pass
            def read(self): reads.append(1); return Reading(40, 0, None)
            def close(self): pass
        class Controller:
            def __init__(self, *args, **kwargs): self.attempts = 0; self.failures = 0
            def step(self, reading): self.attempts = 1
            def initial_done(self): return len(reads) >= 3
            def close(self): pass
            def cancel(self): pass
        cfg = dict(DEFAULTS, mqtt_host='127.0.0.1', spring_base_url='http://127.0.0.1:8080')
        with patch('proximity_camera.__main__.load_config', return_value=cfg), \
             patch('proximity_camera.__main__.MockSensor', Sensor), \
             patch('proximity_camera.__main__.time.sleep'), \
             patch('proximity_camera.mqtt.EventClient', return_value=MagicMock()), \
             patch('proximity_camera.spring.SpringIntegration', return_value=MagicMock()), \
             patch('proximity_camera.async_controller.AsyncSpringController', Controller):
            self.assertEqual(main(['run', '--mode', 'mock', '--spring', '--max-captures', '1']), 0)
        self.assertEqual(len(reads), 3)
