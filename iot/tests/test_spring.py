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
from proximity_camera.config import DEFAULTS, load_config
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
        self.assertEqual(self.fake.published, [('doorbell/1/sensor', {'deviceId': 1, 'sensorType': 'MOTION', 'value': 1}, 1, False)])
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
