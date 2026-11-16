import os
import shutil
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path


def _png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 128, 72, 8, 2, 0, 0, 0)) +
            chunk(b"tEXt", b"Description\x00MOCK image - not a camera capture") +
            chunk(b"IDAT", zlib.compress((b"\x00" + b"\x66\x99\xcc" * 128) * 72)) + chunk(b"IEND", b""))


def worker(path, settle, af_timeout, capture_timeout, width, height, camera_class=None):
    if camera_class is None:
        from picamera2 import Picamera2
        camera_class = Picamera2
    camera = camera_class()
    started = False
    try:
        camera.configure(camera.create_still_configuration(main={"size": (width, height)}))
        camera.start(show_preview=False)
        started = True
        time.sleep(settle)
        if not camera.wait(camera.autofocus_cycle(wait=False), timeout=af_timeout):
            raise RuntimeError("autofocus failed")
        camera.wait(camera.capture_file(str(path), wait=False), timeout=capture_timeout)
    finally:
        try:
            if started:
                camera.stop()
        finally:
            camera.close()


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
