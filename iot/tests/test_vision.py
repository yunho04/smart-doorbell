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
from unittest.mock import patch

from proximity_camera.config import DEFAULTS, load_config
from proximity_camera.vision import analyze_image
import test_spring


class Handler(BaseHTTPRequestHandler):
    status = 200
    body = b'{"event_id":15}'
    calls = []
    delay = 0
    def do_POST(self):
        data = self.rfile.read(int(self.headers['Content-Length']))
        Handler.calls.append((self.path, self.headers['Content-Type'], data))
        if Handler.delay: time.sleep(Handler.delay)
        self.send_response(Handler.status)
        self.end_headers()
        try: self.wfile.write(Handler.body)
        except (BrokenPipeError, ConnectionResetError): pass
    def log_message(self, *args): pass


class VisionHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
    def setUp(self):
        Handler.calls = []; Handler.status = 200; Handler.body = b'{"event_id":15}'; Handler.delay = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'sample.jpg'; self.path.write_bytes(b'jpeg bytes\x00')
        self.cfg = dict(DEFAULTS, vision_base_url='http://127.0.0.1:%s' % self.server.server_port)
    def tearDown(self): self.tmp.cleanup()
    def test_multipart_and_same_id(self):
        self.assertEqual(analyze_image(self.cfg, 15, self.path), {'event_id': 15})
        path, content_type, body = Handler.calls[0]
        self.assertEqual(path, '/vision/analyze')
        msg = BytesParser(policy=default).parsebytes(('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
        parts = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True) for part in msg.iter_parts()}
        self.assertEqual(parts, {'image': b'jpeg bytes\x00', 'event_id': b'15'})
        self.assertEqual(self.path.read_bytes(), b'jpeg bytes\x00')
    def test_invalid_responses_no_retry(self):
        for status, body in [(500,b'{}'),(302,b'{}'),(200,b'no'),(200,b'[]'),(200,b'{"event_id":16}'),(200,b'{"event_id":true}'),(200,b'x'*65537)]:
            Handler.status, Handler.body = status, body
            before = len(Handler.calls)
            with self.assertRaises(RuntimeError): analyze_image(self.cfg, 15, self.path)
            self.assertEqual(len(Handler.calls), before+1)
        self.assertTrue(self.path.exists())
    def test_input_limits_and_id(self):
        for event_id in (True, 0, 2**63):
            with self.assertRaises(ValueError): analyze_image(self.cfg, event_id, self.path)
        self.path.write_bytes(b'')
        with self.assertRaises(ValueError): analyze_image(self.cfg, 15, self.path)
        self.path.write_bytes(b'1234'); self.cfg['max_file_bytes'] = 3
        with self.assertRaises(ValueError): analyze_image(self.cfg, 15, self.path)
        self.assertEqual(len(Handler.calls), 0); self.assertTrue(self.path.exists())
    def test_timeout_no_retry(self):
        Handler.delay = .2; self.cfg['vision_timeout_s'] = .03
        with self.assertRaises(socket.timeout): analyze_image(self.cfg, 15, self.path)
        self.assertEqual(len(Handler.calls), 1); self.assertTrue(self.path.exists())


class VisionConfigTests(unittest.TestCase):
    def test_validation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'config.json'
            for value in ('http://example.com', 'http://127.0.0.1/path', 'http://user@127.0.0.1', 3):
                p.write_text(json.dumps({'vision_base_url': value}))
                with self.assertRaises(ValueError): load_config(p)
            for value in (True, 0, 121, '30'):
                p.write_text(json.dumps({'vision_timeout_s': value}))
                with self.assertRaises(ValueError): load_config(p)


class VisionAsyncTests(test_spring.AsyncTests):
    def test_enabled_uses_same_photo_and_id(self):
        self.cfg['vision_base_url'] = 'http://127.0.0.1'
        with patch('proximity_camera.async_controller.analyze_image') as analyze:
            self.begin(); self.release.set(); self.controller.close()
            analyze.assert_called_once_with(self.cfg, 15, 'photo.jpg')
            self.assertEqual(self.uploads, [15])
    def test_disabled(self):
        with patch('proximity_camera.async_controller.analyze_image') as analyze:
            self.begin(); self.release.set(); self.controller.close(); analyze.assert_not_called()
    def test_spring_failure(self):
        self.cfg['vision_base_url'] = 'http://127.0.0.1'
        self.controller.integration.upload = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('upload'))
        with patch('proximity_camera.async_controller.analyze_image') as analyze:
            self.begin(); self.release.set(); self.controller.job.join(1)
            analyze.assert_not_called(); self.assertIsNotNone(self.controller.job_error)
    def test_vision_failure_does_not_reupload(self):
        self.cfg['vision_base_url'] = 'http://127.0.0.1'
        with patch('proximity_camera.async_controller.analyze_image', side_effect=RuntimeError('vision')) as analyze:
            self.begin(); self.release.set(); self.controller.job.join(1)
            with self.assertRaises(RuntimeError): self.controller.check()
            self.assertEqual(self.uploads, [15]); self.assertEqual(analyze.call_count, 1)
    def test_cancel_after_upload(self):
        self.cfg['vision_base_url'] = 'http://127.0.0.1'
        def upload(*args, **kwargs): self.controller.cancel()
        self.controller.integration.upload = upload
        with patch('proximity_camera.async_controller.analyze_image') as analyze:
            self.begin(); self.release.set(); self.controller.close(); analyze.assert_not_called()
    def test_presence_during_vision(self):
        self.cfg['vision_base_url'] = 'http://127.0.0.1'
        entered = threading.Event(); release = threading.Event()
        def analyze(*args): entered.set(); release.wait(2)
        with patch('proximity_camera.async_controller.analyze_image', side_effect=analyze):
            self.begin(); self.release.set(); self.assertTrue(entered.wait(1))
            self.step(2, 40); self.assertEqual(len(self.fake.published), 2)
            self.assertTrue(self.controller.busy()); release.set(); self.controller.close()
    def test_close_budget(self):
        class Job:
            def join(self, timeout): self.timeout = timeout
            def is_alive(self): return False
        job = Job(); self.controller.job = job
        self.controller.close(); base = job.timeout
        self.cfg['vision_base_url'] = 'http://127.0.0.1'; self.controller.close()
        self.assertEqual(job.timeout, base + self.cfg['vision_timeout_s'] + self.cfg['camera_capture_timeout_s'] + 1)
        self.controller.job = None

class PeriodicVisionTests(unittest.TestCase):
    def setUp(self):
        from proximity_camera.async_controller import AsyncSpringController
        from proximity_camera.camera import Camera
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = dict(DEFAULTS, output_dir=self.tmp.name, min_free_bytes=0,
                        vision_base_url='http://127.0.0.1', vision_interval_s=.04,
                        consecutive=1, cooldown_s=0)
        self.now = 0
        self.sent = []
        self.status = 'DETECTED'
        self.lookups = []
        class Events:
            def check(self): pass
            def publish_presence(inner): self.sent.append('presence')
            def finish(inner): self.sent.append('finish')
        class Integration:
            events = Events()
            def create_event(inner, request_id, distance): return 15
            def upload(inner, event_id, path, request_id, finish=False): self.sent.append(('upload', event_id, path))
            def abort(inner): pass
        def lookup(cfg, event_id): self.lookups.append(event_id); return self.status
        self.controller = AsyncSpringController(None, Camera(self.cfg, 'mock'), self.cfg, Integration(), lambda: self.now, lookup)
        self.frames = []
        self.received = threading.Event()
        def analyze(cfg, event_id, path):
            self.frames.append((event_id, path, path.read_bytes()))
            if len(self.frames) >= 3: self.received.set()
        self.patch = patch('proximity_camera.async_controller.analyze_image', side_effect=analyze)
        self.patch.start()
    def tearDown(self):
        self.controller.cancel()
        self.controller.close()
        self.patch.stop()
        self.tmp.cleanup()
    def step(self, now, distance):
        self.now = now
        self.controller.step(test_spring.Reading(distance, 0, None))
    def test_fresh_frames_and_owned_cleanup(self):
        user = Path(self.tmp.name) / 'user.txt'; user.write_text('keep')
        self.step(0, 40)
        self.assertTrue(self.received.wait(2))
        self.controller.close()
        self.assertEqual([x[0] for x in self.frames], [15] * len(self.frames))
        self.assertEqual(len({x[2] for x in self.frames}), len(self.frames))
        self.assertEqual(len([x for x in self.sent if isinstance(x, tuple)]), 1)
        self.assertTrue(self.frames[0][1].exists())
        self.assertTrue(all(not x[1].exists() for x in self.frames[1:]))
        self.assertTrue(user.exists())
    def test_gap_checks_while_busy_then_resume_and_end(self):
        self.step(0, 40)
        self.assertTrue(self.received.wait(2))
        self.step(11, 80)
        self.assertEqual(self.lookups, [15])
        self.assertFalse(self.controller.vision_allowed.is_set())
        self.step(11.5, 40)
        self.assertTrue(self.controller.vision_allowed.is_set())
        self.status = 'COMPLETED'
        self.step(22, 80)
        self.assertTrue(self.controller.session_ended.is_set())
        self.controller.job.join(2)
        self.step(23, 80)
        self.assertEqual(self.controller.state, 'ARMED')
        self.assertIn('finish', self.sent)

    def test_failed_additional_frame_is_preserved(self):
        calls = []
        def analyze(cfg, event_id, path):
            calls.append(path)
            if len(calls) == 2: raise RuntimeError('vision unavailable')
        self.patch.stop()
        self.patch = patch('proximity_camera.async_controller.analyze_image', side_effect=analyze)
        self.patch.start()
        self.step(0, 40)
        self.controller.job.join(2)
        self.assertIsNotNone(self.controller.job_error)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(path.exists() for path in calls))
        self.controller.job_error = None

    def test_mqtt_failure_after_vision_success_is_not_vision_failure(self):
        for failing_frame in (1, 2):
            with self.subTest(failing_frame=failing_frame):
                self.frames.clear()
                def check():
                    if len(self.frames) >= failing_frame:
                        raise RuntimeError('MQTT event state uncertain; intervention required')
                self.controller.integration.events.check = check
                with self.assertLogs(level='INFO') as logs:
                    self.controller._work('request%s' % failing_frame, 40)
                self.assertEqual(len(self.frames), failing_frame)
                self.assertEqual(len([x for x in self.sent if isinstance(x, tuple)]), 1)
                self.assertTrue(any('vision request_id=' in line and 'result=success' in line for line in logs.output))
                self.assertTrue(any('mqtt request_id=' in line and 'result=failed' in line for line in logs.output))
                self.assertFalse(any('vision request_id=' in line and 'result=failed' in line for line in logs.output))
                self.assertTrue(self.frames[-1][1].exists())
                self.sent.clear()
                self.controller.job_error = None

    def test_slow_vision_never_overlaps_or_catches_up(self):
        starts = []
        def analyze(cfg, event_id, path):
            starts.append(time.monotonic())
            time.sleep(.09)
            if len(starts) >= 3: self.received.set()
        self.patch.stop()
        self.patch = patch('proximity_camera.async_controller.analyze_image', side_effect=analyze)
        self.patch.start()
        self.step(0, 40)
        self.assertTrue(self.received.wait(2))
        self.controller.close()
        self.assertTrue(all(b - a >= .09 for a, b in zip(starts, starts[1:])))

    def test_paused_close_stops_promptly(self):
        self.step(0, 40)
        self.assertTrue(self.received.wait(2))
        self.step(11, 80)
        start = time.monotonic()
        self.controller.close()
        self.assertLess(time.monotonic() - start, 1)

class PersistentCameraTests(unittest.TestCase):
    def test_child_prepares_once_and_captures_twice(self):
        import sys
        import types
        from proximity_camera.camera import _session_worker
        class Pipe:
            def __init__(self): self.incoming = iter(['first.jpg', 'second.jpg', None]); self.outgoing = []
            def recv(self): return next(self.incoming)
            def send(self, value): self.outgoing.append(value)
            def close(self): pass
        pipe = Pipe(); prepared = []; captures = []
        class Camera:
            def stop(self): pass
            def close(self): pass
        modules = {'picamera2': types.SimpleNamespace(Picamera2=Camera), 'libcamera': types.SimpleNamespace(controls=object())}
        with patch.dict(sys.modules, modules), patch('proximity_camera.camera._prepare', side_effect=lambda *args: prepared.append(1)), patch('proximity_camera.camera._capture', side_effect=lambda camera, path, timeout: captures.append(path)):
            _session_worker(pipe, DEFAULTS)
        self.assertEqual(prepared, [1])
        self.assertEqual(captures, ['first.jpg', 'second.jpg'])
        self.assertEqual([x[0] for x in pipe.outgoing], ['ready', 'captured', 'captured'])

    def test_capture_error_stops_child_before_partial_removal(self):
        from proximity_camera.camera import Camera, CameraSession
        with tempfile.TemporaryDirectory() as directory:
            cfg = dict(DEFAULTS, output_dir=directory, min_free_bytes=0)
            camera = Camera(cfg, 'hardware')
            session = CameraSession(camera)
            observed = []
            class Pipe:
                def send(self, path): Path(path).write_bytes(b'partial')
            session.pipe = Pipe()
            def fail(*args): raise RuntimeError('timeout')
            def close(): observed.extend(Path(directory).glob('*.part.jpg'))
            session._receive = fail; session.close = close
            with self.assertRaisesRegex(RuntimeError, 'timeout'):
                camera.capture('request', session)
            self.assertEqual(len(observed), 1)
            self.assertFalse(observed[0].exists())


class CadenceTests(unittest.TestCase):
    def test_slot_boundaries_and_missed_slots(self):
        from proximity_camera.async_controller import _next_slot
        for now, expected in ((.1, 1), (1, 2), (1.4, 2), (3.4, 4)):
            self.assertEqual(_next_slot(0, now, 1), expected)

    def test_interval_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            for value in (True, 0, -1, 121, float('nan'), float('inf'), '1'):
                config.write_text(json.dumps({'vision_interval_s': value}))
                with self.assertRaises(ValueError): load_config(config)
            config.write_text(json.dumps({'vision_interval_s': 1}))
            self.assertEqual(load_config(config)['vision_interval_s'], 1)

# A real spawn target that implements the camera protocol without Pi dependencies.
def spawned_fake_camera(pipe, cfg):
    pipe.send(('ready', None))
    while True:
        path = pipe.recv()
        if path is None:
            break
        Path(path).write_bytes(('frame:' + path).encode())
        pipe.send(('captured', None))
    pipe.close()


class CameraIPCTests(unittest.TestCase):
    def session(self):
        from proximity_camera.camera import Camera, CameraSession
        return CameraSession(Camera(dict(DEFAULTS, camera_timeout_s=.02), 'hardware'))

    def test_actual_spawn_two_captures(self):
        from proximity_camera.camera import Camera
        with tempfile.TemporaryDirectory() as directory:
            cfg = dict(DEFAULTS, output_dir=directory, min_free_bytes=0, camera_timeout_s=5)
            with patch('proximity_camera.camera._session_worker', spawned_fake_camera):
                with Camera(cfg, 'hardware').session() as session:
                    first = session.capture('one')
                    second = session.capture('two')
                    self.assertNotEqual(first.read_bytes(), second.read_bytes())
                self.assertIsNone(session.pipe)
                self.assertIsNone(session.process)
                session.close()

    def test_receive_timeout_cancel_eof_and_dead_worker(self):
        from proximity_camera.camera import CameraSessionCancelled
        class Pipe:
            ready = False
            def poll(self, delay): return self.ready
            def recv(self): raise EOFError()
        class Process:
            alive = True
            def is_alive(self): return self.alive
        session = self.session(); session.pipe = Pipe(); session.process = Process()
        with self.assertRaisesRegex(RuntimeError, 'timed out'): session._receive('ready', .001)
        with self.assertRaisesRegex(RuntimeError, 'timed out'): session._receive('captured', .001)
        session.stopping.set()
        with self.assertRaises(CameraSessionCancelled): session._receive('captured', 1)
        session.stopping.clear(); session.pipe.ready = True
        with self.assertRaisesRegex(RuntimeError, 'exited'): session._receive('ready', 1)
        session.pipe.ready = False; session.process.alive = False
        with self.assertRaisesRegex(RuntimeError, 'exited'): session._receive('ready', 1)

    def test_forced_shutdown_and_cleanup_failure(self):
        class Pipe:
            def __init__(self): self.closed = False
            def send(self, value): pass
            def close(self): self.closed = True
        class Process:
            def __init__(self, stuck=False): self.actions = []; self.alive = True; self.exitcode = None; self.stuck = stuck
            def is_alive(self): return self.alive
            def join(self, timeout): self.actions.append(('join', timeout))
            def terminate(self): self.actions.append('terminate')
            def kill(self):
                self.actions.append('kill')
                if not self.stuck: self.alive = False; self.exitcode = -9
            def close(self): self.actions.append('close')
        session = self.session(); process = Process(); pipe = Pipe()
        session.process, session.pipe, session.started = process, pipe, True
        session.close(); session.close()
        self.assertEqual(process.actions, [('join', 2), 'terminate', ('join', 2), 'kill', ('join', 2), 'close'])
        self.assertTrue(pipe.closed)
        session = self.session(); process = Process(stuck=True); pipe = Pipe()
        session.process, session.pipe, session.started = process, pipe, True
        with self.assertRaisesRegex(RuntimeError, 'did not stop'): session.close()
        self.assertTrue(pipe.closed)
        session.close()

    def test_cancelled_capture_does_not_fail_visit(self):
        from proximity_camera.camera import CameraSessionCancelled
        from proximity_camera.async_controller import AsyncSpringController
        entered = threading.Event()
        class Camera:
            def session(self, stopping):
                class Session:
                    def __enter__(inner): entered.set(); stopping.wait(2); raise CameraSessionCancelled()
                    def __exit__(inner, *args): pass
                return Session()
        class Events:
            def check(self): pass
        class Integration:
            events = Events()
            def create_event(self, *args): return 15
            def abort(self): raise AssertionError('cancel must not abort')
            def upload(self, *args, **kwargs): raise AssertionError('cancel must not upload')
        cfg = dict(DEFAULTS, vision_base_url='http://127.0.0.1', consecutive=1)
        controller = AsyncSpringController(None, Camera(), cfg, Integration())
        controller.step(test_spring.Reading(40, 0, None))
        self.assertTrue(entered.wait(1)); controller.cancel(); controller.close()
        self.assertIsNone(controller.job_error)

    def test_first_vision_waits_again_if_gate_closes_during_check(self):
        from proximity_camera.async_controller import AsyncSpringController
        paused = threading.Event(); first_sent = threading.Event()
        class Camera:
            def session(self, stopping):
                from contextlib import nullcontext
                return nullcontext(self)
            def capture(self, request_id): return 'photo.jpg'
        class Events:
            checks = 0
            def check(inner):
                inner.checks += 1
                # step() checks once before the worker; worker's pre-POST check is second.
                if inner.checks == 2:
                    controller.vision_allowed.clear(); paused.set()
        class Integration:
            events = Events()
            def create_event(self, *args): return 15
            def abort(self): pass
            def upload(self, *args, **kwargs): pass
        cfg = dict(DEFAULTS, vision_base_url='http://127.0.0.1', consecutive=1)
        controller = AsyncSpringController(None, Camera(), cfg, Integration())
        with patch('proximity_camera.async_controller.analyze_image', side_effect=lambda *args: first_sent.set()):
            controller.step(test_spring.Reading(40, 0, None))
            self.assertTrue(paused.wait(1))
            self.assertFalse(first_sent.wait(.05))
            self.assertTrue(controller.busy())
            controller.vision_allowed.set()
            self.assertTrue(first_sent.wait(1))
            controller.close()

    def test_cli_interrupt_during_camera_start_returns_130(self):
        from proximity_camera.__main__ import main
        from proximity_camera.camera import CameraSessionCancelled
        started = threading.Event()
        class Camera:
            def __init__(self, *args): pass
            def session(self, stopping):
                class Session:
                    def __enter__(inner):
                        started.set(); stopping.wait(2); raise CameraSessionCancelled()
                    def __exit__(inner, *args): pass
                return Session()
        class Sensor:
            def __init__(self, *args): self.reads = 0
            def read(self):
                self.reads += 1
                if self.reads == 1: return test_spring.Reading(40, 0, None)
                if not started.wait(1): raise RuntimeError('camera did not start')
                raise KeyboardInterrupt()
            def close(self): pass
        class Events:
            def __init__(self, cfg): pass
            def start(self): pass
            def check(self): pass
            def close(self): pass
        class Integration:
            def __init__(self, cfg, events): self.events = events
            def create_event(self, *args): return 15
            def close(self): pass
            def abort(self): raise AssertionError('cancel must not abort')
            def upload(self, *args, **kwargs): raise AssertionError('cancel must not upload')
        cfg = dict(DEFAULTS, mqtt_host='127.0.0.1', spring_base_url='http://127.0.0.1',
                   vision_base_url='http://127.0.0.1', consecutive=1)
        with patch('proximity_camera.__main__.load_config', return_value=cfg), \
             patch('proximity_camera.__main__.Camera', Camera), \
             patch('proximity_camera.__main__.MockSensor', Sensor), \
             patch('proximity_camera.__main__.time.sleep'), \
             patch('proximity_camera.mqtt.EventClient', Events), \
             patch('proximity_camera.spring.SpringIntegration', Integration):
            self.assertEqual(main(['run', '--mode', 'mock', '--spring']), 130)


class LimitedVisitTests(unittest.TestCase):
    def test_limit_stops_after_first_vision_without_waiting_for_main_loop(self):
        from proximity_camera.async_controller import AsyncSpringController
        first = threading.Event(); calls = []
        class Camera:
            def session(self, stopping):
                from contextlib import nullcontext
                return nullcontext(self)
            def capture(self, request_id): return 'representative.jpg'
        class Events:
            def check(self): pass
        class Integration:
            events = Events()
            def create_event(self, *args): return 15
            def upload(self, *args, **kwargs): pass
            def abort(self): pass
        cfg = dict(DEFAULTS, consecutive=1, vision_base_url='http://127.0.0.1', vision_interval_s=.02)
        controller = AsyncSpringController(None, Camera(), cfg, Integration(), max_attempts=1)
        def analyze(*args): calls.append(args); first.set()
        with patch('proximity_camera.async_controller.analyze_image', side_effect=analyze):
            controller.step(test_spring.Reading(40, 0, None))
            self.assertTrue(first.wait(1))
            # Simulate the main loop being held in a sensor or presence operation.
            controller.job.join(.2)
            self.assertFalse(controller.busy())
            self.assertEqual(len(calls), 1)
            controller.close()
