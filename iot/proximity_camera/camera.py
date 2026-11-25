import os
import logging
import multiprocessing
import threading
import shutil
import struct
import subprocess
import sys
import time
import zlib
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path


def _png(identity=None):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 128, 72, 8, 2, 0, 0, 0)) +
            chunk(b"tEXt", b"Description\x00MOCK image - not a camera capture" + (str(identity).encode() if identity else b"")) +
            chunk(b"IDAT", zlib.compress((b"\x00" + b"\x66\x99\xcc" * 128) * 72)) + chunk(b"IEND", b""))


class AutofocusFailed(RuntimeError):
    """The camera explicitly reported autofocus failure."""


def _prepare(camera, settle, af_timeout, width, height, controls, clock, started):
    camera.configure(camera.create_still_configuration(
        main={"size": (width, height)}, buffer_count=3, queue=False,
        controls={"AfMode": controls.AfModeEnum.Manual,
                  "FrameDurationLimits": (33333, 100000)}))
    camera.start(show_preview=False)
    started[0] = True
    time.sleep(settle)
    camera.set_controls({"AfMode": controls.AfModeEnum.Auto,
                         "AfTrigger": controls.AfTriggerEnum.Start})
    start = clock()
    deadline = start + af_timeout
    last_state = None
    logging.info("camera autofocus started timeout_s=%s", af_timeout)
    try:
        while True:
            remaining = deadline - clock()
            if remaining <= 0:
                raise TimeoutError("autofocus deadline elapsed")
            metadata = camera.wait(camera.capture_metadata(wait=False), timeout=remaining)
            state = metadata.get("AfState")
            elapsed = clock() - start
            if state != last_state:
                logging.info("camera autofocus state=%s lens_position=%s elapsed_s=%.2f",
                             state, metadata.get("LensPosition"), elapsed)
                last_state = state
            if elapsed >= af_timeout:
                raise TimeoutError("autofocus deadline elapsed")
            if state == controls.AfStateEnum.Focused:
                break
            if state == controls.AfStateEnum.Failed:
                raise AutofocusFailed("autofocus failed")
            if state not in (controls.AfStateEnum.Idle, controls.AfStateEnum.Scanning):
                raise RuntimeError("unsupported autofocus metadata: AfState=%r" % (state,))
    except (TimeoutError, FutureTimeoutError) as exc:
        _flush_timed_out_job(camera)
        raise RuntimeError("autofocus timed out after %s seconds (last AfState=%s)" % (af_timeout, last_state)) from exc


def _capture(camera, path, capture_timeout):
    try:
        camera.wait(camera.capture_file(str(path), wait=False), timeout=capture_timeout)
    except (TimeoutError, FutureTimeoutError) as exc:
        _flush_timed_out_job(camera)
        raise RuntimeError("capture timed out after %s seconds" % capture_timeout) from exc

def worker(path, settle, af_timeout, capture_timeout, width, height, camera_class=None, controls=None, clock=None):
    if camera_class is None:
        from picamera2 import Picamera2
        camera_class = Picamera2
    if controls is None:
        from libcamera import controls
    camera = camera_class()
    started = [False]
    try:
        _prepare(camera, settle, af_timeout, width, height, controls, clock or time.monotonic, started)
        _capture(camera, path, capture_timeout)
    finally:
        try:
            if started[0]:
                camera.stop()
        finally:
            camera.close()

def _session_worker(pipe, cfg):
    camera = None
    started = [False]
    try:
        from picamera2 import Picamera2
        from libcamera import controls
        camera = Picamera2()
        _prepare(camera, cfg['settle_s'], cfg['camera_af_timeout_s'], cfg['camera_width'], cfg['camera_height'], controls, time.monotonic, started)
        pipe.send(('ready', None))
        while True:
            path = pipe.recv()
            if path is None:
                break
            _capture(camera, path, cfg['camera_capture_timeout_s'])
            pipe.send(('captured', None))
    except BaseException as exc:
        try:
            pipe.send(('autofocus_failed' if isinstance(exc, AutofocusFailed) else 'error', str(exc)))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        if camera is not None:
            try:
                if started[0]:
                    camera.stop()
            finally:
                camera.close()
        pipe.close()

def _flush_timed_out_job(camera):
    # After a timeout the job state is uncertain; flush only for cleanup.
    try:
        camera.cancel_all_and_flush()
    except Exception:
        logging.exception("camera job flush failed during timeout cleanup")


def _stop_process(process):
    if process.poll() is not None:
        process.wait()
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


class Camera:
    def __init__(self, config, mode, popen=subprocess.Popen):
        self.config, self.mode, self.popen = config, mode, popen

    def session(self, stopping=None):
        return CameraSession(self, stopping)

    def capture(self, request_id, session=None):
        cfg = self.config
        directory = Path(cfg["output_dir"])
        directory.mkdir(parents=True, exist_ok=True)
        # Count all files, including other user files; never delete existing pictures.
        files = [p for p in directory.iterdir() if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        if len(files) >= cfg["max_files"] or total >= cfg["max_total_bytes"] or shutil.disk_usage(directory).free < cfg["min_free_bytes"]:
            raise RuntimeError("storage limit reached")
        suffix = ".png" if self.mode == "mock" else ".jpg"
        prefix = "MOCK_" if self.mode == "mock" else "capture_"
        target = directory / (prefix + request_id + suffix)
        temporary = directory / ("." + prefix + request_id + ".part" + suffix)
        if target.exists() or temporary.exists():
            raise RuntimeError("capture path already exists")
        proc = None
        try:
            if self.mode == "mock":
                temporary.write_bytes(_png(request_id if session else None))
            elif session is not None:
                session._capture(temporary)
            else:
                command = [sys.executable, "-m", "proximity_camera", "_worker", str(temporary), str(cfg["settle_s"]), str(cfg["camera_af_timeout_s"]), str(cfg["camera_capture_timeout_s"]), str(cfg["camera_width"]), str(cfg["camera_height"])]
                proc = self.popen(command)
                try:
                    status = proc.wait(timeout=cfg["camera_timeout_s"])
                except subprocess.TimeoutExpired:
                    raise RuntimeError("camera process timed out")
                if status != 0:
                    raise RuntimeError("camera process failed (%s)" % status)
            size = temporary.stat().st_size
            if size <= 0 or size > cfg["max_file_bytes"] or total + size > cfg["max_total_bytes"] or shutil.disk_usage(directory).free < cfg["min_free_bytes"]:
                raise RuntimeError("storage limit exceeded after capture")
            os.replace(temporary, target)
            return target
        finally:
            try:
                if proc is not None:
                    _stop_process(proc)
            finally:
                temporary.unlink(missing_ok=True)


def worker_signal(signum, frame):
    raise SystemExit("worker interrupted by signal %s" % signum)


class CameraSessionCancelled(Exception):
    """A requested shutdown interrupted camera startup or capture."""


class CameraSession:
    def __init__(self, camera, stopping=None):
        self.camera = camera
        self.stopping = stopping or threading.Event()
        self.process = self.pipe = None
        self.started = False

    def __enter__(self):
        if self.camera.mode != 'mock':
            ctx = multiprocessing.get_context('spawn')
            self.pipe, child = ctx.Pipe()
            self.process = ctx.Process(target=_session_worker, args=(child, self.camera.config))
            try:
                self.process.start()
                self.started = True
                child.close()
                self._receive('ready', self.camera.config['camera_timeout_s'])
            except BaseException as exc:
                child.close()
                self.close(require_clean=isinstance(exc, AutofocusFailed))
                raise
        return self

    def _receive(self, expected, timeout):
        deadline = time.monotonic() + timeout
        while True:
            if self.stopping.is_set():
                raise CameraSessionCancelled('camera session cancelled')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('camera session timed out')
            if self.pipe.poll(min(.1, remaining)):
                try:
                    result, detail = self.pipe.recv()
                except EOFError as exc:
                    raise RuntimeError('camera session exited') from exc
                if result == 'autofocus_failed' and expected == 'ready':
                    raise AutofocusFailed(detail)
                if result != expected:
                    raise RuntimeError('camera session failed: %s' % detail)
                return
            if not self.process.is_alive():
                raise RuntimeError('camera session exited')

    def _capture(self, path):
        try:
            self.pipe.send(str(path))
            self._receive('captured', self.camera.config['camera_capture_timeout_s'] + 1)
        except BaseException:
            # Stop the child before Camera.capture removes the partial file.
            self.close()
            raise

    def capture(self, request_id):
        return self.camera.capture(request_id, self)

    def close(self, require_clean=False):
        process, pipe = self.process, self.pipe
        self.process = self.pipe = None
        try:
            if process is not None:
                try:
                    if self.started:
                        forced = False
                        if process.is_alive():
                            try:
                                pipe.send(None)
                            except (BrokenPipeError, EOFError, OSError):
                                pass
                            process.join(2)
                        if process.is_alive():
                            forced = True
                            process.terminate()
                            process.join(2)
                        if process.is_alive():
                            process.kill()
                            process.join(2)
                        if process.is_alive():
                            raise RuntimeError('camera process did not stop')
                        if forced and require_clean:
                            raise RuntimeError('camera process required forced shutdown')
                        if process.exitcode != 0 and not forced:
                            raise RuntimeError('camera process exited with code %s' % process.exitcode)
                finally:
                    if not self.started or not process.is_alive():
                        process.close()
        finally:
            if pipe is not None:
                pipe.close()
            self.started = False

    def __exit__(self, *args):
        self.close()
