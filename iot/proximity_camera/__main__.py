import argparse
import logging
import signal
import sys
import time
from .camera import Camera, worker, worker_signal
from .config import load_config, validate_spring_config
from .controller import Controller
from .sensor import HCSR04, MockSensor, RPiGPIOHCSR04


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
            p.add_argument("--spring", action="store_true", help="enable real MQTT and Spring HTTP integration")
            p.add_argument("--max-captures", type=int, default=None, help="exit after this many capture attempts")
    p = sub.add_parser("_worker", help=argparse.SUPPRESS)
    p.add_argument("path")
    p.add_argument("settle", type=float)
    p.add_argument("af_timeout", type=float)
    p.add_argument("capture_timeout", type=float)
    p.add_argument("width", type=int)
    p.add_argument("height", type=int)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "_worker":
        signal.signal(signal.SIGTERM, worker_signal)
        signal.signal(signal.SIGINT, worker_signal)
        try:
            worker(args.path, args.settle, args.af_timeout, args.capture_timeout, args.width, args.height)
            return 0
        except RuntimeError as exc:
            logging.error("camera worker result=failed reason=%s", exc)
            return 1
    signal.signal(signal.SIGTERM, _shutdown_signal)
    try:
        cfg = load_config(args.config)
        if args.command == "run" and args.max_captures is not None and args.max_captures < 1:
            raise ValueError("--max-captures must be positive")
        if args.command == "run" and args.spring:
            validate_spring_config(cfg)
        logging.info("mode=%s command=%s", args.mode.upper(), args.command)
        camera = Camera(cfg, args.mode)
        if args.command == "camera":
            import uuid
            request_id = uuid.uuid4().hex
            path = camera.capture(request_id)
            logging.info("capture request_id=%s result=success path=%s", request_id, path)
            return 0
        if args.mode == "mock":
            sensor = MockSensor(cfg["mock_readings"])
        else:
            logging.info("sensor backend=%s trigger_bcm=%s echo_bcm=%s settle_s=%s pulse_s=%s interval_s=%s echo_timeout_s=%s",
                         cfg["sensor_backend"], cfg["trigger_bcm"], cfg["echo_bcm"], cfg["sensor_settle_s"],
                         cfg["trigger_pulse_s"], cfg["interval_s"], cfg["echo_timeout_s"])
            sensor_class = RPiGPIOHCSR04 if cfg["sensor_backend"] == "rpi_gpio" else HCSR04
            sensor = sensor_class(cfg["trigger_bcm"], cfg["echo_bcm"], cfg["echo_timeout_s"],
                                  settle=cfg["sensor_settle_s"], pulse=cfg["trigger_pulse_s"])
        integration = None
        try:
            if args.command == "run" and args.spring:
                from .mqtt import EventClient
                from .spring import SpringIntegration
                events = EventClient(cfg)
                events.start()
                integration = SpringIntegration(cfg, events)
                logging.info("spring=REAL mqtt=REAL http=REAL sensor_camera_mode=%s", args.mode.upper())
            if integration:
                from .async_controller import AsyncSpringController
                controller = AsyncSpringController(sensor, camera, cfg, integration)
            else:
                controller = Controller(sensor, camera, cfg)
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
                    if (args.max_captures and controller.attempts >= args.max_captures and
                            (not integration or not controller.busy())):
                        break
                time.sleep(cfg["interval_s"])
        except BaseException:
            if integration and "controller" in locals():
                controller.cancel()
            raise
        finally:
            try:
                if integration and "controller" in locals():
                    controller.close()
            finally:
                try:
                    if integration:
                        integration.close()
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
