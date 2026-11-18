import os
import logging
import shutil
import struct
import subprocess
import sys
import time
import zlib
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path


def _png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 128, 72, 8, 2, 0, 0, 0)) +
            chunk(b"tEXt", b"Description\x00MOCK image - not a camera capture") +
            chunk(b"IDAT", zlib.compress((b"\x00" + b"\x66\x99\xcc" * 128) * 72)) + chunk(b"IEND", b""))


def worker(path, settle, af_timeout, capture_timeout, width, height, camera_class=None, controls=None, clock=None):
    if camera_class is None:
        from picamera2 import Picamera2
        camera_class = Picamera2
    if controls is None:
        from libcamera import controls
    if clock is None:
        clock = time.monotonic
    camera = camera_class()
    started = False
    try:
        camera.configure(camera.create_still_configuration(
            main={"size": (width, height)}, buffer_count=3, queue=False,
            controls={"AfMode": controls.AfModeEnum.Manual,
                      "FrameDurationLimits": (33333, 100000)}))
        camera.start(show_preview=False)
        started = True
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
                    raise RuntimeError("autofocus failed")
                if state not in (controls.AfStateEnum.Idle, controls.AfStateEnum.Scanning):
                    raise RuntimeError("unsupported autofocus metadata: AfState=%r" % (state,))
        except (TimeoutError, FutureTimeoutError) as exc:
            _flush_timed_out_job(camera)
            raise RuntimeError("autofocus timed out after %s seconds (last AfState=%s)" % (af_timeout, last_state)) from exc
        try:
            camera.wait(camera.capture_file(str(path), wait=False), timeout=capture_timeout)
        except (TimeoutError, FutureTimeoutError) as exc:
            _flush_timed_out_job(camera)
            raise RuntimeError("capture timed out after %s seconds" % capture_timeout) from exc
    finally:
        try:
            if started:
                camera.stop()
        finally:
            camera.close()


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

    def capture(self, request_id):
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
                temporary.write_bytes(_png())
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
