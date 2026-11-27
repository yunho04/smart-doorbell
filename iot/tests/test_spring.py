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
    def test_ended_requires_matching_active_nonretained_id(self):
        self.events.create_event('r', 40)
        for event_id, topic, retain in [(16, 'doorbell/1/event', False), (15, 'other', False), (15, 'doorbell/1/event', True), (False, 'doorbell/1/event', False)]:
            self.fake.message(event_id, topic, retain, 'ENDED')
        self.assertEqual(self.events.event_id, 15)
        self.fake.message(15, status='ENDED')
        self.fake.message(15, status='ENDED')
        self.assertTrue(self.events.ended(15))
        self.assertIsNone(self.events.event_id)
        self.assertFalse(self.events.pending)
        self.assertFalse(self.events.publish_presence())
        self.events.check()

    def test_created_then_ended_before_publish_returns(self):
        original = self.fake.publish
        def publish(*args, **kwargs):
            info = original(*args, **kwargs)
            self.fake.message(15, status='ENDED')
            return info
        self.fake.publish = publish
        self.assertEqual(self.events.create_event('r', 40), 15)
        self.assertTrue(self.events.ended(15))
        self.events.check()

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
    def test_failure_callbacks_log_first_cause_and_context(self):
        self.events.create_event('r', 40)
        with self.assertLogs(level='ERROR') as logs:
            self.fake.on_disconnect(self.fake, None, None, 7, None)
            self.events.abort()
            with self.assertRaisesRegex(RuntimeError, 'MQTT event state uncertain'):
                self.events.check()
        self.assertEqual(self.events.failure_reason, 'disconnected')
        self.assertEqual(len(logs.output), 1)
        self.assertIn('mqtt result=failed reason=disconnected reason_code=7', logs.output[0])
        other = EventClient(self.cfg, FakeClient()); other.start()
        other.create_event('r', 40)
        with self.assertLogs(level='ERROR') as logs:
            other.client.message(16)
            other.abort()
        self.assertEqual(other.failure_reason, 'unexpected_created')
        self.assertEqual(len(logs.output), 1)
        self.assertIn('active_event_id=15 received_event_id=16 pending=True', logs.output[0])
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
    def test_early_end_before_creation_returns_stops_without_capture(self):
        original = self.fake.publish
        def publish(*args, **kwargs):
            info = original(*args, **kwargs)
            self.fake.message(15, status='ENDED')
            return info
        self.fake.publish = publish
        self.controller.max_attempts = 1
        self.step(0, 40)
        self.controller.job.join(1)
        self.step(1, None, 'no echo')
        self.assertTrue(self.controller.initial_done())
        self.assertEqual(self.controller.failures, 1)
        self.assertFalse(self.capturing.is_set())
        self.assertEqual(self.uploads, [])

    def test_ended_then_disconnect_reconnects_only_after_worker(self):
        self.begin()
        self.fake.message(15, status='ENDED')
        self.fake.on_disconnect(self.fake, None, None, 1, None)
        replacements = []
        def reconnect():
            self.assertFalse(self.controller.busy())
            fresh = EventClient(self.cfg, FakeClient()); fresh.start()
            self.controller.integration.events = fresh
            replacements.append(fresh)
        self.controller.integration.reconnect = reconnect
        self.step(2, 80)
        self.assertEqual(replacements, [])
        self.release.set(); self.controller.job.join(1)
        self.step(3, 80)
        self.assertEqual(len(replacements), 1)
        self.assertEqual(self.controller.state, 'ARMED')
        replacements[0].close()

    def test_closing_does_not_discard_worker_failure(self):
        self.begin()
        self.fake.message(15, status='ENDED')
        self.step(1, None, 'no echo')
        self.controller.job_error = RuntimeError('camera cleanup failed')
        self.release.set(); self.controller.job.join(1)
        with self.assertRaisesRegex(RuntimeError, 'camera cleanup failed'):
            self.step(2, 80)
        self.assertEqual(self.controller.attempts, 1)

    def test_far_release_is_remembered_while_worker_closes(self):
        self.cfg['consecutive'] = 3
        for t in (0, 1, 2): self.step(t, 40)
        self.assertTrue(self.capturing.wait(1))
        self.fake.message(15, status='ENDED')
        for t in (3, 4, 5): self.step(t, 80)
        self.step(6, 60)
        self.release.set(); self.controller.job.join(1)
        self.step(7, 60)
        self.assertEqual(self.controller.state, 'ARMED')

    def test_ended_during_capture_preserves_file_and_rearms_after_quiet(self):
        self.cfg['consecutive'] = 3
        for t in (0, 1, 2): self.step(t, 40)
        self.assertTrue(self.capturing.wait(1))
        self.fake.message(15, status='ENDED')
        self.step(3, None, 'no echo')
        self.assertIsNone(self.controller.event_id)
        self.assertEqual(self.controller.state, 'CLOSING')
        self.release.set(); self.controller.job.join(1)
        self.assertEqual(self.uploads, [])
        self.fake.respond = 16
        self.step(13, 60)
        for t in (14, 15, 16): self.step(t, 40)
        self.controller.job.join(1)
        self.assertEqual(self.controller.attempts, 2)
        self.assertEqual(self.uploads, [16])

    def test_early_end_while_present_requires_release(self):
        self.cfg['consecutive'] = 3
        for t in (0, 1, 2): self.step(t, 40)
        self.assertTrue(self.capturing.wait(1))
        self.fake.message(15, status='ENDED')
        self.step(3, 40)
        self.release.set(); self.controller.job.join(1)
        for t in range(4, 20): self.step(t, 40)
        self.assertEqual(self.controller.attempts, 1)
        for t in (20, 21, 22): self.step(t, 80)
        self.assertEqual(self.controller.state, 'ARMED')

    def test_unauthorized_status_waits_for_ended(self):
        from proximity_camera.spring import EventStatusAuthorizationError
        self.begin(); self.release.set(); self.controller.job.join(1)
        calls = []
        def denied(cfg, event_id):
            calls.append(event_id)
            raise EventStatusAuthorizationError('HTTP 401')
        self.controller.status_lookup = denied
        self.step(11, None, 'no echo'); self.step(13, None, 'no echo')
        self.assertEqual(calls, [15])
        self.fake.message(15, status='ENDED')
        self.step(14, 80)
        self.assertEqual(self.controller.state, 'ARMED')

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
        self.step(2, 40); self.step(4, 40)
        self.assertEqual(self.controller.state, 'RECOVERING')
        self.assertEqual(len(self.fake.published), 2)
    def test_recovery_waits_for_worker_terminal_and_new_connection(self):
        self.begin()
        replacements = []
        def reconnect():
            self.assertFalse(self.controller.busy())
            self.events.close()
            fresh = EventClient(self.cfg, FakeClient()); fresh.start()
            self.controller.integration.events = fresh
            replacements.append(fresh)
        self.controller.integration.reconnect = reconnect
        self.fake.on_disconnect(self.fake, None, None, 1, None)
        self.step(2, 80); self.step(11, 80)
        self.assertEqual(replacements, [])
        self.release.set(); self.controller.job.join(1)
        self.assertEqual(self.uploads, [])
        self.step(12, 80); self.assertEqual(replacements, [])
        self.status = 'ANALYZING'; self.step(14, 80)
        self.assertEqual(self.controller.state, 'ARMED')
        self.assertEqual(replacements[0].client.published, [])
        replacements[0].close()

    def test_unknown_event_holds(self):
        from proximity_camera.mqtt import MQTTStateError
        self.controller.state = 'LATCHED'
        self.controller.job_error = MQTTStateError('event_response_timeout')
        self.step(0, 40); self.step(12, 40)
        self.assertEqual(self.controller.state, 'SAFE_HOLD')
        self.assertEqual(self.fake.published, [])

    def test_transient_lookup_pauses_until_confirmed(self):
        self.begin(); self.release.set(); self.controller.job.join(1)
        calls = []
        def lookup(cfg, event_id):
            calls.append(event_id)
            if len(calls) == 1: raise TimeoutError('temporary')
            return 'ANALYZING'
        self.controller.status_lookup = lookup
        self.step(11, 80); self.assertEqual(self.controller.state, 'LATCHED')
        self.assertFalse(self.controller.vision_allowed.is_set())
        self.step(11.5, 80); self.assertEqual(len(calls), 1)
        self.step(12, 80); self.assertEqual(self.controller.state, 'ARMED')

    def test_failed_lookup_does_not_reuse_previous_detected(self):
        self.begin(); self.release.set(); self.controller.job.join(1)
        results = iter(['DETECTED', TimeoutError('temporary'), 'DETECTED'])
        def lookup(cfg, event_id):
            result = next(results)
            if isinstance(result, Exception): raise result
            return result
        self.controller.status_lookup = lookup
        self.step(11, 80)
        self.step(12, 80)
        self.step(12.5, 40)
        self.assertEqual(len(self.fake.published), 1)
        self.step(13, 40)
        self.assertEqual(len(self.fake.published), 1)
        self.step(13.5, 40)
        self.assertEqual(len(self.fake.published), 2)

    def test_autofocus_skips_visit_then_rearms_and_succeeds(self):
        from proximity_camera.camera import AutofocusFailed
        from contextlib import contextmanager
        attempts = []
        failed = threading.Event()
        @contextmanager
        def session(stopping):
            attempts.append(1)
            if self.controller.event_id == 15:
                if len(attempts) >= 3: failed.set()
                raise AutofocusFailed('autofocus failed')
            yield self.controller.camera
        self.controller.config['vision_base_url'] = 'http://127.0.0.1:8000'
        self.controller.camera.session = session
        with patch('proximity_camera.async_controller.AUTOFOCUS_RETRY_DELAY_S', .001), \
             patch.object(self.controller.integration, 'abort') as abort, \
             patch('proximity_camera.async_controller.analyze_image') as vision:
            self.step(0, 40)
            self.assertTrue(failed.wait(1))
            self.status = 'ANALYZING'; self.step(11, 80)
            self.controller.job.join(1)
            self.assertTrue(self.controller.initial_done())
            self.assertEqual(self.controller.failures, 1)
            self.assertEqual(self.uploads, [])
            self.step(12, 80)
            self.assertEqual(self.controller.state, 'ARMED')
            self.fake.respond = 16
            self.controller.max_attempts = 2
            self.release.set(); self.step(13, 40)
            self.controller.job.join(1)
            self.assertEqual(self.uploads, [16])
            self.assertEqual(vision.call_count, 1)
            abort.assert_not_called()
            self.controller.close()

    def test_autofocus_retry_succeeds_in_same_visit(self):
        from proximity_camera.camera import AutofocusFailed
        from contextlib import contextmanager
        attempts = []
        @contextmanager
        def session(stopping):
            attempts.append(1)
            if len(attempts) <= 3:
                raise AutofocusFailed('autofocus failed')
            yield self.controller.camera
        self.controller.config['vision_base_url'] = 'http://127.0.0.1:8000'
        self.controller.max_attempts = 1
        self.controller.camera.session = session
        self.release.set()
        with patch('proximity_camera.async_controller.AUTOFOCUS_RETRY_DELAY_S', 0), \
             patch('proximity_camera.async_controller.analyze_image') as vision:
            self.step(0, 40); self.controller.job.join(2)
            self.assertEqual(len(attempts), 4)
            self.assertEqual(self.uploads, [15])
            self.assertEqual(len(self.fake.published), 1)
            vision.assert_called_once_with(self.controller.config, 15, 'photo.jpg')
            self.assertEqual(self.controller.failures, 0)
            self.controller.close()

    def test_autofocus_retry_stops_for_visit_end_or_cancellation(self):
        from proximity_camera.camera import AutofocusFailed
        from contextlib import contextmanager
        self.controller.config['vision_base_url'] = 'http://127.0.0.1:8000'
        for flag in ('stopping', 'session_ended', 'periodic_stop', 'terminal'):
            with self.subTest(flag=flag):
                attempts = []
                @contextmanager
                def session(stopping):
                    attempts.append(1)
                    if flag == 'terminal': self.controller.terminal = True
                    else: getattr(self.controller, flag).set()
                    raise AutofocusFailed('autofocus failed')
                    yield
                self.controller.camera.session = session
                with patch.object(self.controller.integration, 'create_event', return_value=15):
                    self.controller._work('request', 40)
                self.assertEqual(len(attempts), 1)
                self.assertEqual(self.uploads, [])
                self.assertEqual(self.controller.failures, 1)
                if flag == 'terminal': self.controller.terminal = False
                else: getattr(self.controller, flag).clear()
                self.controller.initial_complete.clear()

    def test_autofocus_retry_waits_for_gate_and_can_be_stopped(self):
        from proximity_camera.camera import AutofocusFailed
        from contextlib import contextmanager
        attempts = []
        failed = threading.Event()
        @contextmanager
        def session(stopping):
            attempts.append(1)
            self.controller.vision_allowed.clear()
            failed.set()
            raise AutofocusFailed('autofocus failed')
            yield
        self.controller.config['vision_base_url'] = 'http://127.0.0.1:8000'
        self.controller.camera.session = session
        self.step(0, 40)
        self.assertTrue(failed.wait(1))
        self.assertFalse(self.controller.initial_complete.wait(.15))
        self.assertEqual(len(attempts), 1)
        self.controller.periodic_stop.set()
        self.controller.job.join(1)
        self.assertFalse(self.controller.job.is_alive())
        self.assertEqual(len(attempts), 1)
        self.assertEqual(self.uploads, [])

    def test_gate_or_end_during_successful_retry(self):
        from proximity_camera.camera import AutofocusFailed
        from contextlib import contextmanager
        for ending in (True, False):
            with self.subTest(ending=ending):
                started, resume = threading.Event(), threading.Event()
                attempts = []
                @contextmanager
                def session(stopping):
                    attempts.append(1)
                    if len(attempts) == 1:
                        raise AutofocusFailed('autofocus failed')
                    started.set()
                    self.assertTrue(resume.wait(1))
                    yield self.controller.camera
                self.controller.config['vision_base_url'] = 'http://127.0.0.1:8000'
                self.controller.max_attempts = 1
                self.controller.attempts = 1
                self.controller.camera.session = session
                self.release.set()
                with patch('proximity_camera.async_controller.AUTOFOCUS_RETRY_DELAY_S', 0), \
                     patch('proximity_camera.async_controller.analyze_image') as vision, \
                     patch.object(self.controller.integration, 'create_event', return_value=15):
                    job = threading.Thread(target=self.controller._work, args=('request', 40))
                    job.start()
                    self.assertTrue(started.wait(1))
                    self.controller.vision_allowed.clear()
                    if ending: self.controller.session_ended.set()
                    resume.set()
                    if not ending:
                        self.assertFalse(self.capturing.wait(.1))
                        self.controller.vision_allowed.set()
                    job.join(1)
                    self.assertFalse(job.is_alive())
                    self.assertEqual(len(attempts), 2)
                    if ending:
                        self.assertEqual(self.uploads, [])
                        self.assertEqual(self.controller.failures, 1)
                        self.assertTrue(self.controller.initial_done())
                        vision.assert_not_called()
                    else:
                        self.assertEqual(self.uploads, [15])
                        vision.assert_called_once()
                self.controller.session_ended.clear()
                self.controller.initial_complete.clear()
                self.controller.failures = 0
                self.controller.vision_allowed.set()

    def test_other_camera_startup_errors_are_not_retried(self):
        from contextlib import contextmanager
        attempts = []
        @contextmanager
        def session(stopping):
            attempts.append(1)
            raise TimeoutError('camera startup timeout')
            yield
        self.controller.config['vision_base_url'] = 'http://127.0.0.1:8000'
        self.controller.camera.session = session
        self.step(0, 40); self.controller.job.join(2)
        self.assertEqual(len(attempts), 1)
        self.assertIsInstance(self.controller.job_error, TimeoutError)
        self.assertEqual(self.uploads, [])

    def test_final_autofocus_failure_remains_visible_after_rearm_check(self):
        from proximity_camera.camera import AutofocusFailed
        from contextlib import contextmanager
        @contextmanager
        def session(stopping):
            raise AutofocusFailed('autofocus failed')
            yield
        self.controller.config['vision_base_url'] = 'http://127.0.0.1:8000'
        self.controller.max_attempts = 1
        self.controller.camera.session = session
        self.step(0, 40)
        self.status = 'ANALYZING'; self.step(11, 80)
        self.controller.job.join(2)
        self.step(12, 80)
        self.assertTrue(self.controller.initial_done())
        self.assertEqual(self.controller.failures, 1)
        self.assertEqual(self.controller.attempts, 1)
        self.controller.close()

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
                         ('10.21.36.38', 'http://10.21.36.38:8080', 'doorbell-sensor-camera-1'))
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
    def test_autofocus_failure_exits_nonzero(self):
        from proximity_camera.__main__ import main
        from proximity_camera.camera import AutofocusFailed
        from contextlib import contextmanager
        from unittest.mock import MagicMock
        failed = threading.Event()
        class Sensor:
            def __init__(self, *args): self.reads = 0
            def read(self):
                self.reads += 1
                if self.reads == 1: return Reading(40, 0, None)
                failed.wait(1)
                return Reading(80, 0, None)
            def close(self): pass
        class Camera:
            def __init__(self, *args): pass
            @contextmanager
            def session(self, stopping):
                failed.set()
                raise AutofocusFailed('autofocus failed')
                yield
        from proximity_camera.async_controller import AsyncSpringController
        ticks = iter(range(0, 1000000, 11))
        def make_controller(*args, **kwargs):
            return AsyncSpringController(*args, clock=lambda: next(ticks),
                                         status_lookup=lambda cfg, event_id: 'ANALYZING', **kwargs)
        cfg = dict(DEFAULTS, consecutive=1, interval_s=.001, mqtt_host='127.0.0.1',
                   spring_base_url='http://127.0.0.1:8080', vision_base_url='http://127.0.0.1:8000')
        integration = MagicMock()
        integration.create_event.return_value = 15
        with patch('proximity_camera.__main__.load_config', return_value=cfg), \
             patch('proximity_camera.__main__.MockSensor', Sensor), \
             patch('proximity_camera.__main__.Camera', Camera), \
             patch('proximity_camera.async_controller.AsyncSpringController', make_controller), \
             patch('proximity_camera.mqtt.EventClient', return_value=MagicMock()), \
             patch('proximity_camera.spring.SpringIntegration', return_value=integration):
            self.assertEqual(main(['run', '--mode', 'mock', '--spring', '--max-captures', '1']), 1)
        integration.upload.assert_not_called()
        integration.abort.assert_not_called()

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
