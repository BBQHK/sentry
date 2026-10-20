"""Joystick, slew limiting, and the arm switch for the pan/tilt head."""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Protocol

from sentry.config import AxisConfig, Settings

log = logging.getLogger(__name__)

MIN_SPEED = 15.0
MAX_SPEED = 240.0
STICK_TIMEOUT_S = 0.5


class ServoDriver(Protocol):
    def write(self, pan: float, tilt: float) -> None: ...

    def release(self) -> None: ...

    def close(self) -> None: ...


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def approach(current: float, target: float, step: float) -> float:
    if target > current:
        return min(target, current + step)
    return max(target, current - step)


class Gimbal:
    def __init__(
        self,
        settings: Settings,
        driver: ServoDriver,
        mode: str,
        *,
        armed: bool = False,
    ) -> None:
        self.settings = settings
        self.driver = driver
        self.mode = mode
        self.error: str | None = None
        self.pan = float(settings.pan.center)
        self.tilt = float(settings.tilt.center)
        self.target_pan = self.pan
        self.target_tilt = self.tilt
        self.speed = float(settings.default_speed)
        self.armed = armed
        self._stick = (0.0, 0.0)
        self._stick_at = 0.0
        self._written: tuple[float, float] | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="sentry-gimbal", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        self.driver.close()

    def angles(self) -> tuple[float, float]:
        with self._lock:
            return self.pan, self.tilt

    def set_target(self, pan: float | None, tilt: float | None, speed: float | None = None) -> None:
        with self._lock:
            if speed is not None:
                self.speed = clamp(speed, MIN_SPEED, MAX_SPEED)
            if pan is not None:
                self.target_pan = clamp(pan, self.settings.pan.min_angle, self.settings.pan.max_angle)
            if tilt is not None:
                self.target_tilt = clamp(tilt, self.settings.tilt.min_angle, self.settings.tilt.max_angle)
            self._stick = (0.0, 0.0)

    def set_stick(self, x: float, y: float, speed: float | None = None) -> None:
        mag = math.hypot(x, y)
        if mag > 1:
            x /= mag
            y /= mag
        x = clamp(x, -1.0, 1.0)
        y = clamp(y, -1.0, 1.0)
        with self._lock:
            if speed is not None:
                self.speed = clamp(speed, MIN_SPEED, MAX_SPEED)
            self._stick = (x, y)
            self._stick_at = time.monotonic()

    def center(self) -> None:
        with self._lock:
            self.target_pan = float(self.settings.pan.center)
            self.target_tilt = float(self.settings.tilt.center)
            self._stick = (0.0, 0.0)

    def set_armed(self, armed: bool) -> None:
        with self._lock:
            was = self.armed
            self.armed = armed
            if not armed:
                self._stick = (0.0, 0.0)
        if was and not armed:
            self._release()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "pan": round(self.pan, 1),
                "tilt": round(self.tilt, 1),
                "target": {"pan": round(self.target_pan, 1), "tilt": round(self.target_tilt, 1)},
                "speed": round(self.speed, 1),
                "armed": self.armed,
                "limits": {
                    "pan": [self.settings.pan.min_angle, self.settings.pan.max_angle],
                    "tilt": [self.settings.tilt.min_angle, self.settings.tilt.max_angle],
                },
                "center": {
                    "pan": self.settings.pan.center,
                    "tilt": self.settings.tilt.center,
                },
                "channels": {
                    "pan": self.settings.pan.channel,
                    "tilt": self.settings.tilt.channel,
                },
                "driver": {"mode": self.mode, "error": self.error},
            }

    def _loop(self) -> None:
        last = time.monotonic()
        while not self._stop.wait(0.02):
            now = time.monotonic()
            dt = min(0.1, max(0.0, now - last))
            last = now
            try:
                self._tick(dt)
            except Exception as exc:
                log.warning("Servo command failed: %s", exc)
                with self._lock:
                    self.error = str(exc)
                    was = self.armed
                    self.armed = False
                if was:
                    self._release()

    def _tick(self, dt: float) -> None:
        with self._lock:
            # A dropped browser tab must not keep driving the head.
            if time.monotonic() - self._stick_at > STICK_TIMEOUT_S:
                self._stick = (0.0, 0.0)
            sx, sy = self._stick
            step = self.speed * dt
            if sx or sy:
                self.pan = clamp(
                    self.pan + sx * step,
                    self.settings.pan.min_angle,
                    self.settings.pan.max_angle,
                )
                # Positive stick Y raises the tilt angle. Flip invert_tilt if that is backwards.
                self.tilt = clamp(
                    self.tilt + sy * step,
                    self.settings.tilt.min_angle,
                    self.settings.tilt.max_angle,
                )
                self.target_pan = self.pan
                self.target_tilt = self.tilt
            else:
                self.pan = approach(self.pan, self.target_pan, step)
                self.tilt = approach(self.tilt, self.target_tilt, step)
            pan = self.pan
            tilt = self.tilt
            armed = self.armed
            written = self._written
        if not armed:
            return
        # Tenth-of-a-degree steps match the on-screen readout and still
        # keep up at the slowest speed (15°/s). Identical commands are skipped.
        if (
            written is not None
            and round(pan, 1) == round(written[0], 1)
            and round(tilt, 1) == round(written[1], 1)
        ):
            return
        self.driver.write(
            _hardware_angle(pan, self.settings.pan),
            _hardware_angle(tilt, self.settings.tilt),
        )
        with self._lock:
            if not self.armed:
                should_release = True
            else:
                self._written = (pan, tilt)
                self.error = None
                should_release = False
        if should_release:
            self._release()

    def _release(self) -> None:
        try:
            self.driver.release()
        except Exception as exc:
            log.warning("Servo release failed: %s", exc)
            with self._lock:
                self.error = str(exc)
        with self._lock:
            self._written = None


def _hardware_angle(angle: float, axis: AxisConfig) -> float:
    if axis.invert:
        return axis.min_angle + axis.max_angle - angle
    return angle
