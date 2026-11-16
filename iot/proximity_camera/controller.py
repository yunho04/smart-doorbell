import logging
import math
import time
import uuid


class Controller:
    def __init__(self, sensor, camera, config, clock=time.monotonic):
        self.sensor, self.camera, self.config, self.clock = sensor, camera, config, clock
        self.state, self.near_count, self.far_count, self.latched_at = "ARMED", 0, 0, None
        self.attempts = 0
        self.failures = 0

    def step(self, reading):
        value = reading.distance_cm
        valid = value is not None and math.isfinite(value) and 2 <= value <= 400 and not reading.error
        logging.info("sensor distance_cm=%s error=%s state=%s", value, reading.error, self.state)
        if self.state == "ARMED":
            self.near_count = self.near_count + 1 if valid and value <= self.config["near_cm"] else 0
            if self.near_count >= self.config["consecutive"]:
                self.state = "LATCHED"
                self.far_count = 0
                self.attempts += 1
                request_id = uuid.uuid4().hex
                try:
                    path = self.camera.capture(request_id)
                    logging.info("capture request_id=%s result=success path=%s", request_id, path)
                except Exception as exc:
                    self.failures += 1
                    logging.error("capture request_id=%s result=failed reason=%s", request_id, exc)
                finally:
                    self.latched_at = self.clock()
        else:
            self.far_count = self.far_count + 1 if valid and value >= self.config["far_cm"] else 0
            if self.far_count >= self.config["consecutive"] and self.clock() - self.latched_at >= self.config["cooldown_s"]:
                self.state, self.near_count, self.far_count = "ARMED", 0, 0
                logging.info("controller state=ARMED result=rearmed")
