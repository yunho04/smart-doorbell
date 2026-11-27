import math
import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class Reading:
    distance_cm: Optional[float]
    sampled_at: float
    error: Optional[str] = None


class MockSensor:
    def __init__(self, readings):
        self.readings = iter(readings)

    def read(self):
        value = next(self.readings)  # finite input: StopIteration means normal EOF
        return Reading(None, time.monotonic(), "mock error") if value == "error" else Reading(float(value), time.monotonic())

    def close(self):
        pass


class RPiGPIOHCSR04:
    """Poll a fresh HC-SR04 echo with bounded waits; GPIO is imported lazily."""
    def __init__(self, trigger, echo, timeout=0.1, settle=0.2, pulse=0.01,
                 gpio=None, clock=time.monotonic, sleep=time.sleep):
        if gpio is None:
            import RPi.GPIO as gpio
        self.gpio, self.trigger, self.echo = gpio, trigger, echo
        self.timeout, self.settle, self.pulse = timeout, settle, pulse
        self.clock, self.sleep = clock, sleep
        self.last_trigger, self.closed, self.configured = None, False, []
        try:
            gpio.setmode(gpio.BCM)
            gpio.setup(trigger, gpio.OUT, initial=gpio.LOW)
            self.configured.append(trigger)
            gpio.setup(echo, gpio.IN, pull_up_down=gpio.PUD_OFF)
            self.configured.append(echo)
        except BaseException:
            self.close()
            raise

    def _wait_for(self, level):
        deadline = self.clock() + self.timeout
        while self.clock() < deadline:
            if self.gpio.input(self.echo) == level:
                return self.clock()
        return None

    def read(self):
        if self.closed:
            raise RuntimeError("sensor is closed")
        self.sleep(self.settle)
        if self.last_trigger is not None:
            self.sleep(max(0, 0.06 - (self.clock() - self.last_trigger)))
        sampled = self.clock()
        if self.gpio.input(self.echo) != self.gpio.LOW:
            return Reading(None, sampled, "echo already high")
        try:
            self.last_trigger = self.clock()
            self.gpio.output(self.trigger, self.gpio.HIGH)
            self.sleep(self.pulse)
        finally:
            self.gpio.output(self.trigger, self.gpio.LOW)
        rise = self._wait_for(self.gpio.HIGH)
        if rise is None:
            return Reading(None, sampled, "echo rise timeout")
        fall = self._wait_for(self.gpio.LOW)
        if fall is None:
            return Reading(None, sampled, "echo fall timeout")
        duration = fall - rise
        distance = duration * 34300 / 2
        if not math.isfinite(duration) or duration <= 0 or not 2 <= distance <= 400:
            return Reading(None, sampled, "echo out of range")
        return Reading(distance, sampled)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.trigger in self.configured:
                self.gpio.output(self.trigger, self.gpio.LOW)
        finally:
            if self.configured:
                self.gpio.cleanup(self.configured)


class HCSR04:
    """Read one fresh echo pulse per trigger using gpiozero's public pin API."""
    def __init__(self, trigger, echo, timeout=0.1, factory=None, settle=0.2, pulse=0.01):
        if factory is None:
            from gpiozero.pins.lgpio import LGPIOFactory
            factory = LGPIOFactory()
        self.factory = factory
        self.trigger_number, self.echo_number = trigger, echo
        self.trigger = self.echo = None
        self.last_trigger = None
        self.closed = False
        self.timeout = timeout
        self.settle, self.pulse = settle, pulse
        self.lock = threading.Lock()
        self.event = threading.Event()
        self.active = False
        try:
            factory.reserve_pins(self, trigger, echo)
            self.trigger = factory.pin(trigger)
            self.echo = factory.pin(echo)
            self.trigger.function = "output"
            self.trigger.state = False
            self.echo.function = "input"
            self.echo.edges = "both"
            self.echo.when_changed = self._changed
        except BaseException:
            self.close()
            raise

    def _conflicts_with(self, other):
        return True

    def _changed(self, ticks, state):
        with self.lock:
            if (not self.active or self.event.is_set() or
                not 0 <= self.factory.ticks_diff(ticks, self.start_tick) <= self.timeout):
                return
            if state:
                if self.rise is not None:
                    self.problem = "duplicate rising edge"
                    self.event.set()
                else:
                    self.rise = ticks
            elif self.rise is None:
                self.problem = "falling edge before rising edge"
                self.event.set()
            else:
                self.duration = self.factory.ticks_diff(ticks, self.rise)
                self.event.set()

    def read(self):
        if self.closed:
            raise RuntimeError("sensor is closed")
        time.sleep(self.settle)
        now = time.monotonic()
        if self.last_trigger is not None:
            time.sleep(max(0, 0.06 - (now - self.last_trigger)))
        sampled = time.monotonic()
        with self.lock:
            self.active = False
            self.event.clear()
            self.rise = self.duration = self.problem = None
            if self.echo.state:
                return Reading(None, sampled, "echo already high")
            self.start_tick = self.factory.ticks()
            self.active = True
        try:
            self.last_trigger = time.monotonic()
            self.trigger.state = True
            time.sleep(self.pulse)
            self.trigger.state = False
            self.event.wait(self.timeout)
        finally:
            self.trigger.state = False
            with self.lock:
                self.active = False
        if self.problem:
            return Reading(None, sampled, self.problem)
        if self.duration is None:
            return Reading(None, sampled, "echo timeout")
        distance = self.duration * 34300 / 2
        if not math.isfinite(distance) or not 2 <= distance <= 400:
            return Reading(None, sampled, "echo out of range")
        return Reading(distance, sampled)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.active = False
        errors = []
        def attempt(action):
            try:
                action()
            except Exception as exc:
                errors.append(exc)
        if self.echo is not None:
            attempt(lambda: setattr(self.echo, "when_changed", None))
        if self.trigger is not None:
            attempt(lambda: setattr(self.trigger, "state", False))
        for pin in (self.echo, self.trigger):
            if pin is not None:
                attempt(pin.close)
        attempt(lambda: self.factory.release_pins(self, self.trigger_number, self.echo_number))
        attempt(self.factory.close)
        if errors:
            raise RuntimeError("sensor cleanup failed: " + str(errors[0]))
