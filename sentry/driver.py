"""PCA9685 output, and a stand-in used off the Pi."""

from __future__ import annotations

import logging
import sys
import threading

from sentry.config import Settings

log = logging.getLogger(__name__)


class SimDriver:
    """Records commands. Used on a PC, and on a Pi when hardware will not open."""

    def __init__(self) -> None:
        self.writes: list[tuple[float, float]] = []
        self.releases = 0

    def write(self, pan: float, tilt: float) -> None:
        self.writes.append((float(pan), float(tilt)))

    def release(self) -> None:
        self.releases += 1

    def close(self) -> None:
        return None


class Pca9685Driver:
    """Drives two LD-3015MG servos. The chip is left alone until the first pulse."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._kit = None
        self._i2c = None

    def write(self, pan: float, tilt: float) -> None:
        self._ensure()
        self._set(self._settings.pan.channel, pan)
        self._set(self._settings.tilt.channel, tilt)

    def release(self) -> None:
        if self._kit is None:
            return
        # Duty cycle 0 stops the pulse. The servo loses holding torque.
        for channel in (self._settings.pan.channel, self._settings.tilt.channel):
            self._kit.servo[channel].angle = None

    def close(self) -> None:
        i2c = self._i2c
        self._i2c = None
        self._kit = None
        if i2c is not None:
            try:
                i2c.deinit()
            except Exception:
                log.debug("I2C deinit failed", exc_info=True)

    def _ensure(self) -> None:
        if self._kit is not None:
            return
        from adafruit_servokit import ServoKit

        settings = self._settings
        try:
            i2c = _open_i2c(settings.i2c_bus)
        except RuntimeError as exc:
            raise RuntimeError(
                f"{exc} Sentry expects /dev/i2c-{settings.i2c_bus} "
                "(SDA GPIO23 = pin 16, SCL GPIO24 = pin 18). "
                "Add dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=23,i2c_gpio_scl=24 "
                "to /boot/firmware/config.txt and reboot. The default I2C pins are left free."
            ) from exc
        try:
            kit = ServoKit(
                channels=16,
                i2c=i2c,
                address=settings.i2c_address,
                frequency=settings.pwm_frequency,
            )
            for channel in (settings.pan.channel, settings.tilt.channel):
                servo = kit.servo[channel]
                # Angle 0 → min pulse, angle actuation_range → max pulse.
                servo.actuation_range = settings.actuation_range
                servo.set_pulse_width_range(settings.min_pulse_us, settings.max_pulse_us)
        except Exception:
            try:
                i2c.deinit()
            except Exception:
                log.debug("I2C deinit after a failed open failed", exc_info=True)
            raise
        self._i2c = i2c
        self._kit = kit
        log.info(
            "PCA9685 on I2C bus %d at 0x%02X, %d Hz, pan channel %d, tilt channel %d",
            settings.i2c_bus,
            settings.i2c_address,
            settings.pwm_frequency,
            settings.pan.channel,
            settings.tilt.channel,
        )

    def _set(self, channel: int, angle: float) -> None:
        span = float(self._settings.actuation_range)
        clamped = max(0.0, min(span, float(angle)))
        self._kit.servo[channel].angle = clamped


class _BusI2C:
    """I2C bus opened by number, so Sentry can avoid the default GPIO2/GPIO3 bus."""

    def __init__(self, bus_num: int) -> None:
        from adafruit_blinka.microcontroller.generic_linux.i2c import I2C as LinuxI2C

        self._i2c = LinuxI2C(bus_num)
        self._lock = threading.RLock()

    def try_lock(self) -> bool:
        return self._lock.acquire(blocking=False)

    def unlock(self) -> None:
        self._lock.release()

    def deinit(self) -> None:
        self._i2c = None

    def scan(self):
        return self._i2c.scan()

    def readfrom_into(self, address, buffer, *, start=0, end=None):
        if start != 0 or end is not None:
            if end is None:
                end = len(buffer)
            buffer = memoryview(buffer)[start:end]
        return self._i2c.readfrom_into(address, buffer, stop=True)

    def writeto(self, address, buffer, *, start=0, end=None):
        if isinstance(buffer, str):
            buffer = bytes([ord(x) for x in buffer])
        if start != 0 or end is not None:
            if end is None:
                return self._i2c.writeto(address, memoryview(buffer)[start:], stop=True)
            return self._i2c.writeto(address, memoryview(buffer)[start:end], stop=True)
        return self._i2c.writeto(address, buffer, stop=True)

    def writeto_then_readfrom(
        self,
        address,
        buffer_out,
        buffer_in,
        *,
        out_start=0,
        out_end=None,
        in_start=0,
        in_end=None,
        stop=False,
    ):
        return self._i2c.writeto_then_readfrom(
            address,
            buffer_out,
            buffer_in,
            out_start=out_start,
            out_end=out_end,
            in_start=in_start,
            in_end=in_end,
            stop=stop,
        )


def _open_i2c(bus_num: int) -> _BusI2C:
    return _BusI2C(bus_num)


def build_driver(settings: Settings, *, simulate: bool) -> tuple[SimDriver | Pca9685Driver, str]:
    if simulate or not sys.platform.startswith("linux"):
        if simulate:
            log.info("Servo output is simulated (--simulate).")
        else:
            log.info("Servo output is simulated (this is not Linux).")
        return SimDriver(), "simulation"
    log.info("PCA9685 stays idle until the gimbal is armed.")
    return Pca9685Driver(settings), "hardware"
