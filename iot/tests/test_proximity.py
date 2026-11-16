import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from proximity_camera.camera import Camera, worker
from proximity_camera.config import DEFAULTS, load_config
from proximity_camera.controller import Controller
from proximity_camera.sensor import HCSR04, Reading

class StubCamera:
    def __init__(self): self.calls = 0; self.fail = False
    def capture(self, request_id):
        self.calls += 1
        if self.fail: raise RuntimeError('failed')
        return 'ok'

class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.now = 0; self.camera = StubCamera()
        self.c = Controller(None, self.camera, DEFAULTS, lambda: self.now)
    def feed(self, *values):
        for value in values: self.c.step(Reading(value, self.now, 'error' if value is None else None))
    def test_held_and_rearm(self):
        self.feed(40, 40, 40, 40, 80, 80, 80)
        self.assertEqual(self.camera.calls, 1)
        self.assertEqual(self.c.state, 'LATCHED')
        self.now = 6; self.feed(80, 40, 40, 40)
        self.assertEqual(self.camera.calls, 2)
    def test_invalid_resets_and_never_rearms(self):
        self.feed(40, 40, None, 40, 40); self.assertEqual(self.camera.calls, 0)
        self.feed(40); self.now = 6; self.feed(80, 80, None, 80, 80, 500, 40, 40, 40)
        self.assertEqual(self.camera.calls, 1)
    def test_failure_does_not_retry_held(self):
        self.camera.fail = True; self.feed(40, 40, 40, 40, 40)
        self.assertEqual(self.camera.calls, 1)
    def test_cooldown_starts_after_capture(self):
        def capture(_): self.now = 10
        self.camera.capture = capture; self.feed(40, 40, 40, 80, 80, 80)
        self.assertEqual(self.c.state, 'LATCHED')
        self.now = 15; self.feed(80); self.assertEqual(self.c.state, 'ARMED')

class Pin:
    def __init__(self): self.state = False; self.when_changed = None
    def close(self): pass
class Factory:
    def __init__(self): self.pins = {23: Pin(), 24: Pin()}; self.closed = False; self.released = ()
    def reserve_pins(self, owner, *pins): pass
    def release_pins(self, owner, *pins): self.released = pins
    def pin(self, n): return self.pins[n]
    def ticks(self): return 100.0
    def ticks_diff(self, later, earlier): return later - earlier
    def close(self): self.closed = True
class SensorTests(unittest.TestCase):
    def run_edges(self, edges):
        f = Factory(); s = HCSR04(23, 24, .001, f)
        class Event:
            flag = False
            def clear(self): self.flag = False
            def set(self): self.flag = True
            def is_set(self): return self.flag
            def wait(self, timeout):
                for t, state in edges: s._changed(t, state)
        s.event = Event(); result = s.read(); s.close(); s.close()
        self.assertTrue(f.closed); self.assertEqual(f.released, (23,24)); self.assertIsNone(f.pins[24].when_changed)
        return result
    def test_stale_or_late_echo_is_invalid(self):
        self.assertIsNone(self.run_edges([(99, True), (99.0005, False), (100.002, True), (100.0025, False)]).distance_cm)
    def test_fresh_echo_first_pair_wins(self):
        result = self.run_edges([(100.0001, True), (100.0006, False), (100.0008, False)])
        self.assertAlmostEqual(result.distance_cm, 8.575)
    def test_falling_first_invalid(self):
        self.assertIsNone(self.run_edges([(100.0001, False)]).distance_cm)

class CameraTests(unittest.TestCase):
    def test_storage_and_mock(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = dict(DEFAULTS, output_dir=d, min_free_bytes=0, max_files=1)
            camera = Camera(cfg, 'mock'); path = camera.capture('one')
            self.assertTrue(path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
            with self.assertRaisesRegex(RuntimeError, 'storage'): camera.capture('two')
            self.assertEqual(len(list(Path(d).iterdir())), 1)
    def test_size_limit_cleans_partial(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError): Camera(dict(DEFAULTS, output_dir=d, min_free_bytes=0, max_file_bytes=1), 'mock').capture('one')
            self.assertEqual(list(Path(d).iterdir()), [])
    def test_timeout_terminate_kill_wait(self):
        class Process:
            def __init__(self, cmd): self.actions=[]; Path(cmd[-6]).write_bytes(b'partial')
            def wait(self, timeout=None):
                self.actions.append(('wait', timeout))
                if timeout is not None: raise subprocess.TimeoutExpired('worker', timeout)
                return -9
            def poll(self): return None
            def terminate(self): self.actions.append('terminate')
            def kill(self): self.actions.append('kill')
        with tempfile.TemporaryDirectory() as d:
            processes=[]
            def start(cmd): processes.append(Process(cmd)); return processes[-1]
            with self.assertRaisesRegex(RuntimeError, 'timed out'): Camera(dict(DEFAULTS,output_dir=d,min_free_bytes=0),'hardware',start).capture('one')
            self.assertIn('terminate',processes[0].actions); self.assertIn('kill',processes[0].actions)
            self.assertEqual(processes[0].actions[-1],('wait',None)); self.assertEqual(list(Path(d).iterdir()),[])
    def test_autofocus_failure_closes(self):
        class Picam:
            instance = None
            def __init__(self): Picam.instance=self; self.actions=[]
            def create_still_configuration(self, **kwargs): return kwargs
            def configure(self, config): pass
            def start(self, **kwargs): pass
            def autofocus_cycle(self, **kwargs): return 'job'
            def wait(self, job, timeout): return False
            def stop(self): self.actions.append('stop')
            def close(self): self.actions.append('close')
        with self.assertRaisesRegex(RuntimeError,'autofocus'): worker('unused.jpg',0,1,1,1280,720,Picam)
        self.assertEqual(Picam.instance.actions,['stop','close'])

class CLITests(unittest.TestCase):
    def test_mock_without_pi_libraries(self):
        with tempfile.TemporaryDirectory() as d:
            config=Path(d)/'config.json'; config.write_text(json.dumps({'output_dir':str(Path(d)/'photos'),'min_free_bytes':0}))
            result=subprocess.run([sys.executable,'-m','proximity_camera','run','--mode','mock','--config',str(config),'--max-captures','1'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr); self.assertIn('mode=MOCK',result.stderr)
            self.assertEqual(len(list((Path(d)/'photos').iterdir())),1)
    def test_capture_failure_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as d:
            config=Path(d)/'config.json'
            config.write_text(json.dumps({'output_dir':str(Path(d)/'photos'),'min_free_bytes':0,'max_file_bytes':1}))
            result=subprocess.run([sys.executable,'-m','proximity_camera','run','--mode','mock','--config',str(config),'--max-captures','1'],capture_output=True,text=True)
            self.assertEqual(result.returncode,1,result.stderr)
            self.assertIn('result=failed',result.stderr)
    def test_invalid_config(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'config.json'; path.write_text('{"near_cm":80,"far_cm":70}')
            with self.assertRaises(ValueError): load_config(path)

if __name__ == '__main__': unittest.main()
