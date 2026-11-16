import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from proximity_camera.camera import Camera, worker
from proximity_camera.config import DEFAULTS, load_config
from proximity_camera.controller import Controller
from proximity_camera.sensor import HCSR04, RPiGPIOHCSR04, Reading
from unittest.mock import patch

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

class FakeClock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now
    def sleep(self, seconds): self.now += seconds

class FakeGPIO:
    BCM, OUT, IN, LOW, HIGH, PUD_OFF = 'BCM', 'OUT', 'IN', 0, 1, 'OFF'
    def __init__(self, clock, values):
        self.clock, self.values = clock, iter(values)
        self.last = 0; self.outputs = []; self.cleaned = []; self.setup_calls = []
    def setmode(self, mode): self.mode = mode
    def setup(self, pin, mode, **kwargs): self.setup_calls.append((pin, mode, kwargs))
    def output(self, pin, value): self.outputs.append((self.clock.now, pin, value))
    def input(self, pin):
        self.clock.now += .0001
        self.last = next(self.values, self.last)
        return self.last
    def cleanup(self, pins): self.cleaned.append(list(pins))

class PollingSensorTests(unittest.TestCase):
    def make(self, values, **kwargs):
        clock = FakeClock(); gpio = FakeGPIO(clock, values)
        sensor = RPiGPIOHCSR04(20, 16, timeout=.001, settle=0, pulse=.00001,
                              gpio=gpio, clock=clock, sleep=clock.sleep, **kwargs)
        return sensor, gpio, clock
    def test_fresh_pulse(self):
        s, gpio, _ = self.make([0, 0, 1, 1, 1, 1, 1, 0])
        result = s.read()
        self.assertAlmostEqual(result.distance_cm, 8.575)
        s.close(); s.close()
        self.assertEqual(gpio.cleaned, [[20, 16]])
        self.assertEqual(gpio.setup_calls[1][2]['pull_up_down'], gpio.PUD_OFF)
        with self.assertRaisesRegex(RuntimeError, 'closed'): s.read()
    def test_faults(self):
        for values, error in [([1], 'already high'), ([0], 'rise timeout'),
                              ([0, 1], 'fall timeout'), ([0, 1, 0], 'out of range')]:
            with self.subTest(error=error):
                s, gpio, _ = self.make(values)
                result = s.read(); self.assertIsNone(result.distance_cm); self.assertIn(error, result.error)
                s.close()
    def test_trigger_spacing(self):
        s, gpio, _ = self.make([0,1,1,1,1,1,0,0,1,1,1,1,1,0])
        s.read(); s.read(); s.close()
        highs = [t for t, _, v in gpio.outputs if v == gpio.HIGH]
        self.assertGreaterEqual(highs[1]-highs[0], .06)
    def test_interrupt_forces_low(self):
        s, gpio, _ = self.make([0])
        s.sleep = lambda _: (_ for _ in ()).throw(KeyboardInterrupt()) if gpio.outputs and gpio.outputs[-1][2] == gpio.HIGH else None
        with self.assertRaises(KeyboardInterrupt): s.read()
        self.assertEqual(gpio.outputs[-1][2], gpio.LOW)
        s.close()
    def test_setup_failure_cleans_only_successful_pin(self):
        clock = FakeClock(); gpio = FakeGPIO(clock, [])
        def setup(pin, mode, **kwargs):
            if pin == 16: raise RuntimeError('setup failure')
        gpio.setup = setup
        with self.assertRaisesRegex(RuntimeError, 'setup failure'):
            RPiGPIOHCSR04(20, 16, gpio=gpio, clock=clock, sleep=clock.sleep)
        self.assertEqual(gpio.cleaned, [[20]])

class SensorConfigTests(unittest.TestCase):
    def test_invalid_backend_and_timing(self):
        for update in ({'sensor_backend':'bad'}, {'trigger_pulse_s':0}, {'trigger_pulse_s':.011},
                       {'sensor_settle_s':-1}, {'sensor_settle_s':float('inf')}):
            with self.subTest(update=update), tempfile.TemporaryDirectory() as d:
                p=Path(d)/'config.json'; p.write_text(json.dumps(update))
                with self.assertRaises(ValueError): load_config(p)
    def test_existing_config_and_example_remain_usable(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'old.json'
            p.write_text(json.dumps({'trigger_bcm': 23, 'echo_bcm': 24, 'interval_s': .1}))
            old = load_config(p)
            self.assertEqual((old['trigger_bcm'], old['echo_bcm'], old['interval_s']), (23, 24, .1))
            self.assertEqual((old['sensor_backend'], old['sensor_settle_s'], old['trigger_pulse_s']), ('rpi_gpio', .2, .01))
        example = load_config(Path(__file__).resolve().parents[1] / 'config.example.json')
        self.assertEqual((example['trigger_bcm'], example['echo_bcm'], example['interval_s']), (20, 16, .5))
        self.assertEqual((example['sensor_backend'], example['sensor_settle_s'], example['trigger_pulse_s']), ('rpi_gpio', .2, .01))
    def test_backend_selection(self):
        from proximity_camera import __main__ as cli
        class FakeSensor:
            def __init__(self, *args, **kwargs): self.args=args; self.kwargs=kwargs
            def read(self): raise StopIteration
            def close(self): pass
        for backend, name in [('rpi_gpio','RPiGPIOHCSR04'), ('lgpio','HCSR04')]:
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as d:
                p=Path(d)/'config.json'; p.write_text(json.dumps({'sensor_backend':backend}))
                with patch.object(cli, name, wraps=FakeSensor) as selected:
                    self.assertEqual(cli.main(['sensor','--mode','hardware','--config',str(p)]),0)
                    selected.assert_called_once_with(20,16,.1,settle=.2,pulse=.01)

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
