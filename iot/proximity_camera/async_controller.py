"""Manage a Spring visit while sensor reads and camera uploads run independently."""
import http.client
import logging
from contextlib import nullcontext
import math
import threading
import time
import uuid

from .camera import AutofocusFailed, CameraSessionCancelled
from .spring import get_event_status
from .mqtt import MQTTStateError
from .vision import analyze_image


def _next_slot(previous, now, interval):
    slot = previous + interval
    if slot <= now:
        slot += (math.floor((now - slot) / interval) + 1) * interval
    return slot


class AsyncSpringController:
    def __init__(self, sensor, camera, config, integration, clock=time.monotonic, status_lookup=get_event_status, max_attempts=None):
        self.sensor, self.camera, self.config, self.integration = sensor, camera, config, integration
        self.clock, self.status_lookup = clock, status_lookup
        self.max_attempts = max_attempts
        self.state = 'ARMED'
        self.near_count = self.far_count = self.attempts = self.failures = 0
        self.latched_at = self.last_true = self.last_lookup = None
        self.event_id = None
        self.job = None
        self.job_error = None
        self.next_reconnect = 0
        self.reconnected = False
        self.terminal = False
        self.verified_detected = False
        self.session_ready = threading.Event()
        self.stopping = threading.Event()
        self.session_ended = threading.Event()
        self.periodic_stop = threading.Event()
        self.initial_complete = threading.Event()
        self.vision_allowed = threading.Event()
        self.vision_allowed.set()

    def _work(self, request_id, distance):
        event_id = None
        stage = 'event'
        active_frame_id = request_id
        try:
            if self.stopping.is_set():
                return
            event_id = self.integration.create_event(request_id, distance)
            self.event_id = event_id
            self.session_ready.set()
            logging.info('event request_id=%s event_id=%s result=created', request_id, event_id)
            if self.stopping.is_set():
                return
            enabled = bool(self.config['vision_base_url'])
            stage = 'capture'
            with (self.camera.session(self.stopping) if enabled else nullcontext(self.camera)) as camera:
                if self.stopping.is_set() or self.session_ended.is_set():
                    return
                path = camera.capture(request_id)
                logging.info('capture request_id=%s event_id=%s result=success path=%s', request_id, event_id, path)
                if self.stopping.is_set() or self.session_ended.is_set():
                    return
                stage = 'upload'
                self.integration.upload(event_id, path, request_id, finish=False)
                logging.info('upload request_id=%s event_id=%s result=success', request_id, event_id)
                if enabled:
                    # The representative is sent first, unless the visit has paused or ended.
                    while True:
                        while not self.vision_allowed.wait(.1):
                            if self.stopping.is_set() or self.session_ended.is_set() or self.periodic_stop.is_set():
                                return
                        if self.stopping.is_set() or self.session_ended.is_set():
                            return
                        stage = 'mqtt'
                        self.integration.events.check()
                        if self.stopping.is_set() or self.session_ended.is_set():
                            return
                        if self.vision_allowed.is_set():
                            break
                    first_start = time.monotonic()
                    stage = 'vision'
                    analyze_image(self.config, event_id, path)
                    logging.info('vision request_id=%s event_id=%s result=success', request_id, event_id)
                    stage = 'mqtt'
                    self.integration.events.check()
                self.initial_complete.set()
                if not enabled or (self.max_attempts is not None and self.attempts >= self.max_attempts):
                    return
                interval = self.config['vision_interval_s']
                next_slot = _next_slot(first_start, time.monotonic(), interval)
                sequence = 0
                while not (self.periodic_stop.is_set() or self.stopping.is_set() or self.session_ended.is_set()):
                    if not self.vision_allowed.is_set():
                        while not self.vision_allowed.wait(.1):
                            if self.periodic_stop.is_set() or self.stopping.is_set() or self.session_ended.is_set():
                                return
                        next_slot = time.monotonic() + interval
                    remaining = next_slot - time.monotonic()
                    if remaining > 0:
                        self.periodic_stop.wait(min(.1, remaining))
                        continue
                    if not self.vision_allowed.is_set() or self.stopping.is_set() or self.session_ended.is_set() or self.periodic_stop.is_set():
                        continue
                    sequence += 1
                    frame_id = '%s_%06d' % (request_id, sequence)
                    active_frame_id = frame_id
                    stage = 'capture'
                    path = camera.capture(frame_id)
                    logging.info('capture request_id=%s event_id=%s result=success path=%s', frame_id, event_id, path)
                    if not self.vision_allowed.is_set() or self.stopping.is_set() or self.session_ended.is_set() or self.periodic_stop.is_set():
                        continue
                    stage = 'mqtt'
                    self.integration.events.check()
                    if not self.vision_allowed.is_set() or self.stopping.is_set() or self.session_ended.is_set() or self.periodic_stop.is_set():
                        continue
                    stage = 'vision'
                    analyze_image(self.config, event_id, path)
                    logging.info('vision request_id=%s event_id=%s result=success path=%s', frame_id, event_id, path)
                    stage = 'mqtt'
                    self.integration.events.check()
                    stage = 'cleanup'
                    path.unlink()
                    next_slot = _next_slot(next_slot, time.monotonic(), interval)
        except CameraSessionCancelled:
            logging.info('camera request_id=%s event_id=%s result=cancelled', active_frame_id, event_id)
        except BaseException as exc:
            if isinstance(exc, AutofocusFailed) and stage == 'capture' and event_id is not None:
                logging.warning('capture request_id=%s event_id=%s result=skipped reason=autofocus_failed', active_frame_id, event_id)
                self.failures = 1
                self.initial_complete.set()
            else:
                self.job_error = exc
                logging.error('%s request_id=%s event_id=%s result=failed reason=%s', stage, active_frame_id, event_id, exc)
                self.integration.abort()

    def cancel(self):
        self.stopping.set()

    def initial_done(self):
        return self.initial_complete.is_set() or (self.job_error is not None and self.job is not None and not self.job.is_alive())

    def busy(self):
        return self.job is not None and self.job.is_alive()

    def check(self):
        if self.job_error is not None:
            if isinstance(self.job_error, MQTTStateError):
                raise self.job_error
            self.failures = 1
            raise RuntimeError('Spring photo job failed: %s' % self.job_error)
        self.integration.events.check()

    def step(self, reading):
        if self.state in ('RECOVERING', 'SAFE_HOLD'):
            return self._recovery_step(reading)
        try:
            return self._step(reading)
        except MQTTStateError as exc:
            self.failures = 1
            self.recovery_idle = self.state == 'ARMED'
            self.session_ended.set()
            self.periodic_stop.set()
            self.vision_allowed.clear()
            self.state = ('RECOVERING' if (self.event_id is not None or self.recovery_idle) and
                          exc.failure_reason in ('disconnected', 'puback_timeout', 'publish_failed')
                          else 'SAFE_HOLD')
            logging.error('controller state=%s reason=%s event_id=%s; %s', self.state,
                          exc.failure_reason, self.event_id,
                          'waiting for recovery' if self.state == 'RECOVERING' else 'operator intervention required')

    def _recovery_step(self, reading):
        if self.job_error is not None and not isinstance(self.job_error, MQTTStateError):
            self.check()
        if self.state == 'SAFE_HOLD':
            return
        now = self.clock()
        value = reading.distance_cm
        valid = value is not None and math.isfinite(value) and 2 <= value <= 400 and not reading.error
        self.far_count = self.far_count + 1 if valid and value >= self.config['far_cm'] else 0
        if self.busy():
            return
        if not self.recovery_idle and not self.terminal:
            if self.last_lookup is not None and now - self.last_lookup < 2:
                return
            self.last_lookup = now
            try:
                status = self.status_lookup(self.config, self.event_id)
            except (OSError, http.client.HTTPException) as exc:
                logging.warning('Spring event lookup temporarily unavailable: %s', exc)
                return
            self.terminal = status in ('ANALYZING', 'COMPLETED')
            if not self.terminal:
                return
        if not self.reconnected:
            if now < self.next_reconnect:
                return
            try:
                self.integration.reconnect()
                self.reconnected = True
            except (OSError, MQTTStateError) as exc:
                self.next_reconnect = self.clock() + 3
                if isinstance(exc, MQTTStateError) and exc.failure_reason == 'unexpected_created':
                    self.state = 'SAFE_HOLD'
                    logging.error('controller state=SAFE_HOLD reason=unexpected_created; operator intervention required')
                else:
                    logging.warning('mqtt reconnect failed: %s', exc)
                return
        try:
            self.integration.events.check()
        except MQTTStateError as exc:
            if exc.failure_reason == 'unexpected_created':
                self.state = 'SAFE_HOLD'
                logging.error('controller state=SAFE_HOLD reason=unexpected_created; operator intervention required')
            else:
                self.reconnected = False
                self.next_reconnect = self.clock() + 3
            return
        if (self.recovery_idle or
                (self.far_count >= self.config['consecutive'] and
                 now - self.latched_at >= self.config['cooldown_s'])):
            self._reset()

    def _reset(self):
        self.state, self.near_count, self.far_count = 'ARMED', 0, 0
        self.failures = 0
        self.last_lookup, self.terminal = None, False
        self.verified_detected = False
        self.event_id = None
        self.job_error = None
        self.reconnected = False
        self.session_ready.clear()
        self.session_ended.clear()
        self.periodic_stop.clear()
        self.initial_complete.clear()
        self.vision_allowed.set()
        logging.info('controller state=ARMED result=rearmed')

    def _step(self, reading):
        self.check()
        now = self.clock()
        value = reading.distance_cm
        valid = value is not None and math.isfinite(value) and 2 <= value <= 400 and not reading.error
        logging.info('sensor distance_cm=%s error=%s state=%s', value, reading.error, self.state)
        if self.state == 'ARMED':
            self.near_count = self.near_count + 1 if valid and value <= self.config['near_cm'] else 0
            if self.near_count >= self.config['consecutive']:
                self.state = 'LATCHED'
                self.event_id = None
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
            self.vision_allowed.clear()
            if self.event_id is None:
                return
            if not self.config['vision_base_url'] and self.job.is_alive():
                return
            self.check()
            if not self.terminal and present and self.verified_detected and now - self.last_lookup < 2:
                self.verified_detected = False
                self.integration.events.publish_presence()
                self.last_true = self.clock()
                self.vision_allowed.set()
                return
            if not self.terminal and (self.last_lookup is None or now - self.last_lookup >= 1):
                self.last_lookup = now
                self.verified_detected = False
                try:
                    status = self.status_lookup(self.config, self.event_id)
                except (OSError, http.client.HTTPException) as exc:
                    logging.warning('Spring event lookup temporarily unavailable: %s', exc)
                    return
                self.check()
                if status != 'DETECTED':
                    self.terminal = True
                    self.session_ended.set()
                    self.verified_detected = False
                else:
                    self.verified_detected = True
                    self.last_lookup = self.clock()
            if self.terminal and not self.busy() and self.far_count >= self.config['consecutive'] and now - self.latched_at >= self.config['cooldown_s']:
                # The main loop must observe the final attempt before rearming clears it.
                if self.max_attempts is not None and self.attempts >= self.max_attempts and self.initial_complete.is_set():
                    return
                self.integration.events.finish()
                self._reset()
        elif present and self.session_ready.is_set() and gap >= self.config['presence_interval_s']:
            # A reading is obtained on this iteration; never send while far or invalid.
            self.integration.events.publish_presence()
            self.last_true = self.clock()

    def close(self, check=True):
        self.periodic_stop.set()
        if self.job is not None:
            # Each network operation and the camera child have bounded deadlines.
            timeout = (self.config['presence_ack_timeout_s'] + self.config['event_timeout_s'] +
                       self.config['camera_timeout_s'] + self.config['http_timeout_s'] + 10)
            if self.config['vision_base_url']:
                timeout += (self.config['vision_timeout_s'] +
                            self.config['camera_capture_timeout_s'] + 1)
            self.job.join(timeout)
            if self.job.is_alive():
                self.integration.abort()
                raise RuntimeError('photo job did not stop within shutdown deadline')
            if check and (self.state not in ('RECOVERING', 'SAFE_HOLD') or
                          (self.job_error is not None and not isinstance(self.job_error, MQTTStateError))):
                self.check()
