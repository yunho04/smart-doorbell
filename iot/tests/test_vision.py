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
        self.assertEqual(job.timeout, base + self.cfg['vision_timeout_s'])
        self.controller.job = None
