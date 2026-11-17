import logging
import math
import time
import uuid


class Controller:
    def __init__(self, sensor, camera, config, clock=time.monotonic, integration=None):
        self.sensor, self.camera, self.config, self.clock = sensor, camera, config, clock
        self.state, self.near_count, self.far_count, self.latched_at = "ARMED", 0, 0, None
        self.integration = integration
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
                event_id = None
                stage = "event" if self.integration else "capture"
                try:
                    event_id = self.integration.create_event(request_id, value) if self.integration else None
                    if self.integration:
                        logging.info("event request_id=%s event_id=%s result=created", request_id, event_id)
                    stage = "capture"
                    path = self.camera.capture(request_id)
                    logging.info("capture request_id=%s event_id=%s result=success path=%s", request_id, event_id, path)
                    if self.integration:
                        stage = "upload"
                        self.integration.upload(event_id, path, request_id)
                        logging.info("upload request_id=%s event_id=%s result=success", request_id, event_id)
                except Exception as exc:
                    if self.integration:
                        self.integration.abort()
                    self.failures += 1
                    logging.error("%s request_id=%s event_id=%s result=failed reason=%s", stage, request_id, event_id, exc)
                finally:
                    self.latched_at = self.clock()
        else:
            self.far_count = self.far_count + 1 if valid and value >= self.config["far_cm"] else 0
            if self.far_count >= self.config["consecutive"] and self.clock() - self.latched_at >= self.config["cooldown_s"]:
                self.state, self.near_count, self.far_count = "ARMED", 0, 0
                logging.info("controller state=ARMED result=rearmed")
