"""Spring visit lifetime: sensor loop stays responsive while one photo is processed."""
import logging
import math
import threading
import time
import uuid

from .spring import get_event_status


class AsyncSpringController:
    def __init__(self, sensor, camera, config, integration, clock=time.monotonic, status_lookup=get_event_status):
        self.sensor, self.camera, self.config, self.integration = sensor, camera, config, integration
        self.clock, self.status_lookup = clock, status_lookup
        self.state = 'ARMED'
        self.near_count = self.far_count = self.attempts = self.failures = 0
        self.latched_at = self.last_true = self.last_lookup = None
        self.event_id = None
        self.job = None
        self.job_error = None
        self.terminal = False
        self.verified_detected = False
        self.session_ready = threading.Event()
        self.stopping = threading.Event()

    def _work(self, request_id, distance):
        event_id = None
        stage = 'event'
        try:
            if self.stopping.is_set():
                return
            event_id = self.integration.create_event(request_id, distance)
            self.event_id = event_id
            self.session_ready.set()
            logging.info('event request_id=%s event_id=%s result=created', request_id, event_id)
            if self.stopping.is_set():
                return
            stage = 'capture'
            path = self.camera.capture(request_id)
            logging.info('capture request_id=%s event_id=%s result=success path=%s', request_id, event_id, path)
            if self.stopping.is_set():
                return
            stage = 'upload'
            self.integration.upload(event_id, path, request_id, finish=False)
            logging.info('upload request_id=%s event_id=%s result=success', request_id, event_id)
        except BaseException as exc:
            self.job_error = exc
            logging.error('%s request_id=%s event_id=%s result=failed reason=%s', stage, request_id, event_id, exc)
            self.integration.abort()

    def cancel(self):
        self.stopping.set()

    def busy(self):
        return self.job is not None and self.job.is_alive()

    def check(self):
        if self.job_error is not None:
            self.failures = 1
            raise RuntimeError('Spring photo job failed: %s' % self.job_error)
        self.integration.events.check()

    def step(self, reading):
        self.check()
        now = self.clock()
        value = reading.distance_cm
        valid = value is not None and math.isfinite(value) and 2 <= value <= 400 and not reading.error
        logging.info('sensor distance_cm=%s error=%s state=%s', value, reading.error, self.state)
        if self.state == 'ARMED':
            self.near_count = self.near_count + 1 if valid and value <= self.config['near_cm'] else 0
            if self.near_count >= self.config['consecutive']:
                self.state = 'LATCHED'
                self.latched_at = self.last_true = now
                self.attempts += 1
                request_id = uuid.uuid4().hex
                self.job = threading.Thread(target=self._work, args=(request_id, value), daemon=True)
                self.job.start()
            return
        self.far_count = self.far_count + 1 if valid and value >= self.config['far_cm'] else 0
        present = valid and value < self.config['far_cm']
        gap = now - self.last_true
        if gap >= 10:
            if self.job.is_alive():
                return
            self.check()
            if not self.terminal and present and self.verified_detected and now - self.last_lookup < 2:
                self.verified_detected = False
                self.last_true = self.clock()
                self.integration.events.publish_presence()
                return
            if not self.terminal and (self.last_lookup is None or now - self.last_lookup >= 1):
                self.last_lookup = now
                try:
                    status = self.status_lookup(self.config, self.event_id)
                except Exception:
                    self.integration.abort()
                    raise
                self.check()
                if status != 'DETECTED':
                    self.terminal = True
                    self.verified_detected = False
                else:
                    self.verified_detected = True
                    self.last_lookup = self.clock()
            if self.terminal and self.far_count >= self.config['consecutive'] and now - self.latched_at >= self.config['cooldown_s']:
                self.integration.events.finish()
                self.state, self.near_count, self.far_count = 'ARMED', 0, 0
                self.last_lookup, self.terminal = None, False
                self.verified_detected = False
                self.session_ready.clear()
                logging.info('controller state=ARMED result=rearmed')
        elif present and self.session_ready.is_set() and gap >= self.config['presence_interval_s']:
            # A reading is obtained on this iteration; never send while far or invalid.
            self.last_true = self.clock()
            self.integration.events.publish_presence()

    def close(self):
        if self.job is not None:
            # Each network operation and the camera child have bounded deadlines.
            timeout = (self.config['presence_ack_timeout_s'] + self.config['event_timeout_s'] +
                       self.config['camera_timeout_s'] + self.config['http_timeout_s'] + 10)
            self.job.join(timeout)
            if self.job.is_alive():
                self.integration.abort()
                raise RuntimeError('photo job did not stop within shutdown deadline')
            self.check()
