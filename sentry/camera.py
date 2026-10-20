"""USB camera capture, plus a generated picture when no camera is present."""

from __future__ import annotations

import logging
import os
import threading
import time

from sentry.config import Settings

log = logging.getLogger(__name__)


class Camera:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.pose = None
        self.connected = False
        self.message = "Starting camera"
        self.low_light = False
        self.cap = None
        self._jpeg: bytes | None = None
        self._cv2 = None
        self._np = None
        self._cv2_failed = False
        self._last_open_attempt = 0.0
        self._lock = threading.Lock()
        self._cap_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="sentry-camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        with self._cap_lock:
            if self.cap is not None:
                self.cap.release()
                self.cap = None

    def get_jpeg(self) -> bytes | None:
        with self._lock:
            return self._jpeg

    def stream(self):
        period = 1 / max(1, self.settings.camera_fps)
        while True:
            frame = self.get_jpeg()
            if frame is None:
                time.sleep(0.05)
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(period)

    def set_low_light(self, enabled: bool) -> None:
        """Best-effort exposure boost. Many IR cameras ignore it and switch IR on their own."""
        self.low_light = enabled
        with self._cap_lock:
            if self.cap is not None and self._cv2 is not None:
                _apply_low_light(self._cv2, self.cap, enabled)

    def status(self) -> dict:
        return {
            "connected": self.connected,
            "message": self.message,
            "low_light": self.low_light,
            "device": self.settings.camera_device,
        }

    def _loop(self) -> None:
        self._ensure_cv2()
        if self._cv2 is None:
            return
        period = 1 / max(1, self.settings.camera_fps)
        while not self._stop.is_set():
            started = time.monotonic()
            frame = self._read()
            if frame is None and started - self._last_open_attempt > 5:
                self._open()
                frame = self._read()
            if frame is None:
                frame = self._placeholder()
            else:
                frame = self._fit(frame)
            self._publish(frame)
            delay = period - (time.monotonic() - started)
            if delay > 0:
                self._stop.wait(delay)

    def _ensure_cv2(self) -> None:
        if self._cv2 is not None or self._cv2_failed:
            return
        try:
            import cv2
            import numpy as np
        except ImportError:
            self._cv2_failed = True
            self.connected = False
            self.message = "OpenCV is not installed"
            log.warning("OpenCV is not installed; the video page has no frames.")
            return
        self._cv2 = cv2
        self._np = np
        try:
            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
        except Exception:
            pass

    def _open(self) -> None:
        self._last_open_attempt = time.monotonic()
        cv2 = self._cv2
        if cv2 is None:
            return
        with self._cap_lock:
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            cap = _open_capture(
                cv2,
                self.settings.camera_device,
                self.settings.camera_width,
                self.settings.camera_height,
                self.settings.camera_fps,
            )
            if cap is None:
                self.connected = False
                self.message = "No USB camera detected"
                return
            if self.low_light:
                _apply_low_light(cv2, cap, True)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.cap = cap
            self.connected = True
            self.message = f"USB camera {width}×{height}"
        log.info("Camera %s opened at %dx%d", self.settings.camera_device, width, height)

    def _read(self):
        with self._cap_lock:
            cap = self.cap
            if cap is None:
                return None
            ok, frame = cap.read()
        if not ok:
            return None
        return frame

    def _fit(self, frame):
        height, width = frame.shape[:2]
        max_w = self.settings.camera_width
        max_h = self.settings.camera_height
        if width <= max_w and height <= max_h:
            return frame
        scale = min(max_w / width, max_h / height)
        size = (max(1, int(width * scale)), max(1, int(height * scale)))
        return self._cv2.resize(frame, size)

    def _placeholder(self):
        cv2 = self._cv2
        np = self._np
        width = self.settings.camera_width
        height = self.settings.camera_height
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:] = (14, 20, 12)
        pan, tilt = self.pose() if self.pose else (
            self.settings.pan.center,
            self.settings.tilt.center,
        )
        x = _map_span(pan, self.settings.pan.min_angle, self.settings.pan.max_angle, width)
        y = _map_span(tilt, self.settings.tilt.min_angle, self.settings.tilt.max_angle, height)
        y = height - y
        dim = (50, 80, 42)
        accent = (92, 242, 210)
        cv2.line(frame, (0, y), (width, y), dim, 1)
        cv2.line(frame, (x, 0), (x, height), dim, 1)
        cv2.circle(frame, (x, y), 22, accent, 1, cv2.LINE_AA)
        cv2.circle(frame, (x, y), 3, accent, -1, cv2.LINE_AA)
        cv2.putText(
            frame,
            f"PAN {pan:05.1f}   TILT {tilt:05.1f}",
            (24, height - 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            accent,
            1,
            cv2.LINE_AA,
        )
        return frame

    def _publish(self, frame) -> None:
        ok, encoded = self._cv2.imencode(
            ".jpg",
            frame,
            [int(self._cv2.IMWRITE_JPEG_QUALITY), int(self.settings.jpeg_quality)],
        )
        if not ok:
            return
        with self._lock:
            self._jpeg = encoded.tobytes()


def _map_span(value: float, low: float, high: float, length: int) -> int:
    span = high - low
    if span <= 0:
        return length // 2
    fraction = (value - low) / span
    fraction = max(0.0, min(1.0, fraction))
    margin = int(length * 0.12)
    usable = max(1, length - 2 * margin)
    return margin + int(fraction * usable)


def _open_capture(cv2, device, width: int, height: int, fps: int):
    api = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_V4L2
    cap = cv2.VideoCapture(device, api)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    return cap


def _apply_low_light(cv2, cap, enabled: bool) -> None:
    if enabled:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
        cap.set(cv2.CAP_PROP_EXPOSURE, 500)
        cap.set(cv2.CAP_PROP_GAIN, 128)
    else:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)
