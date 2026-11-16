import argparse
import logging
import signal
import sys
import time
from .camera import Camera, worker, worker_signal
from .config import load_config
from .controller import Controller
from .sensor import HCSR04, MockSensor


def _shutdown_signal(signum, frame):
    raise KeyboardInterrupt()


def main(argv=None):
    parser = argparse.ArgumentParser(description="HC-SR04 proximity / Camera Module 3 local capture")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "sensor", "camera"):
        p = sub.add_parser(name)
        p.add_argument("--mode", required=True, choices=("mock", "hardware"))
        p.add_argument("--config")
        if name == "run":
            p.add_argument("--max-captures", type=int, default=None, help="exit after this many capture attempts")
    p = sub.add_parser("_worker", help=argparse.SUPPRESS)
    p.add_argument("path")
    p.add_argument("settle", type=float)
    p.add_argument("af_timeout", type=float)
    p.add_argument("capture_timeout", type=float)
    p.add_argument("width", type=int)
    p.add_argument("height", type=int)
    args = parser.parse_args(argv)
    if args.command == "_worker":
        signal.signal(signal.SIGTERM, worker_signal)
        signal.signal(signal.SIGINT, worker_signal)
        worker(args.path, args.settle, args.af_timeout, args.capture_timeout, args.width, args.height)
        return 0
    signal.signal(signal.SIGTERM, _shutdown_signal)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        cfg = load_config(args.config)
        if args.command == "run" and args.max_captures is not None and args.max_captures < 1:
            raise ValueError("--max-captures must be positive")
        logging.info("mode=%s command=%s", args.mode.upper(), args.command)
        camera = Camera(cfg, args.mode)
        if args.command == "camera":
            import uuid
            request_id = uuid.uuid4().hex
            path = camera.capture(request_id)
            logging.info("capture request_id=%s result=success path=%s", request_id, path)
            return 0
        sensor = MockSensor(cfg["mock_readings"]) if args.mode == "mock" else HCSR04(cfg["trigger_bcm"], cfg["echo_bcm"], cfg["echo_timeout_s"])
        controller = Controller(sensor, camera, cfg)
        try:
            while True:
                try:
                    reading = sensor.read()
                except StopIteration:
                    logging.info("mock sensor input finished")
                    break
                if args.command == "sensor":
                    logging.info("sensor distance_cm=%s error=%s", reading.distance_cm, reading.error)
                else:
                    controller.step(reading)
                    if args.max_captures and controller.attempts >= args.max_captures:
                        break
                time.sleep(cfg["interval_s"])
        finally:
            sensor.close()
        return 1 if controller.failures else 0
    except KeyboardInterrupt:
        logging.info("shutdown requested")
        return 130
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        logging.error("result=failed reason=%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
