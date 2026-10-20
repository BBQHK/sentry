"""Load and check config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """The config file is missing or has a value the servos should not use."""


@dataclass(frozen=True, slots=True)
class AxisConfig:
    channel: int
    min_angle: float
    max_angle: float
    center: float
    invert: bool


@dataclass(frozen=True, slots=True)
class Settings:
    host: str
    port: int
    camera_device: int | str
    camera_width: int
    camera_height: int
    camera_fps: int
    jpeg_quality: int
    i2c_address: int
    pwm_frequency: int
    min_pulse_us: int
    max_pulse_us: int
    actuation_range: int
    default_speed: float
    arm_on_start: bool
    pan: AxisConfig
    tilt: AxisConfig


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config.toml"


def load_settings(path: Path) -> Settings:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} is empty")
    return _settings_from(data)


def _settings_from(data: dict) -> Settings:
    server = _table(data, "server")
    camera = _table(data, "camera")
    board = _table(data, "pca9685")
    servos = _table(data, "servos")

    host = _req(server, "host", "server")
    if not isinstance(host, str) or not host.strip():
        raise ConfigError("server.host must be a hostname or IP")

    port = _int(server, "port", "server")
    if not 1 <= port <= 65535:
        raise ConfigError("server.port must be between 1 and 65535")

    device = _req(camera, "device", "camera")
    if isinstance(device, bool) or not isinstance(device, (int, str)):
        raise ConfigError("camera.device must be an integer index or a device path")

    width = _int(camera, "width", "camera")
    height = _int(camera, "height", "camera")
    if not 160 <= width <= 1920:
        raise ConfigError("camera.width must be between 160 and 1920")
    if not 120 <= height <= 1080:
        raise ConfigError("camera.height must be between 120 and 1080")

    fps = _int(camera, "fps", "camera")
    if not 1 <= fps <= 60:
        raise ConfigError("camera.fps must be between 1 and 60")

    quality = _int(camera, "jpeg_quality", "camera")
    if not 1 <= quality <= 100:
        raise ConfigError("camera.jpeg_quality must be between 1 and 100")

    address = _int(board, "address", "pca9685")
    if not 0x03 <= address <= 0x77:
        raise ConfigError("pca9685.address is not a valid 7-bit I2C address")

    frequency = _int(board, "frequency", "pca9685")
    if not 40 <= frequency <= 60:
        raise ConfigError("pca9685.frequency must stay between 40 and 60 Hz for the LD-3015MG")

    min_pulse = _int(servos, "min_pulse_us", "servos")
    max_pulse = _int(servos, "max_pulse_us", "servos")
    if not 200 <= min_pulse < max_pulse <= 3000:
        raise ConfigError("servo pulse widths must satisfy 200 <= min_pulse_us < max_pulse_us <= 3000")

    actuation = _int(servos, "actuation_range", "servos")
    if not 1 <= actuation <= 270:
        raise ConfigError("servos.actuation_range must be between 1 and 270")

    speed = _float(servos, "default_speed", "servos")
    if not 15 <= speed <= 240:
        raise ConfigError("servos.default_speed must be between 15 and 240 degrees per second")

    arm_on_start = _bool(servos, "arm_on_start", "servos")
    pan = _axis(_table(servos, "pan"), "pan", actuation)
    tilt = _axis(_table(servos, "tilt"), "tilt", actuation)
    if pan.channel == tilt.channel:
        raise ConfigError("pan and tilt must use different PCA9685 channels")

    return Settings(
        host=host.strip(),
        port=port,
        camera_device=device,
        camera_width=width,
        camera_height=height,
        camera_fps=fps,
        jpeg_quality=quality,
        i2c_address=address,
        pwm_frequency=frequency,
        min_pulse_us=min_pulse,
        max_pulse_us=max_pulse,
        actuation_range=actuation,
        default_speed=speed,
        arm_on_start=arm_on_start,
        pan=pan,
        tilt=tilt,
    )


def _axis(table: dict, name: str, actuation: int) -> AxisConfig:
    label = f"servos.{name}"
    channel = _int(table, "channel", label)
    if not 0 <= channel <= 15:
        raise ConfigError(f"{label}.channel must be between 0 and 15")
    min_angle = _float(table, "min_angle", label)
    max_angle = _float(table, "max_angle", label)
    center = _float(table, "center", label)
    invert = _bool(table, "invert", label)
    if not 0 <= min_angle < max_angle <= actuation:
        raise ConfigError(f"{label} must satisfy 0 <= min_angle < max_angle <= {actuation}")
    if not min_angle <= center <= max_angle:
        raise ConfigError(f"{label}.center must sit between min_angle and max_angle")
    return AxisConfig(channel, min_angle, max_angle, center, invert)


def _table(data: dict, key: str) -> dict:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a table")
    return value


def _req(table: dict, key: str, label: str):
    if key not in table:
        raise ConfigError(f"Missing {label}.{key}")
    return table[key]


def _int(table: dict, key: str, label: str) -> int:
    value = _req(table, key, label)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{label}.{key} must be an integer")
    return value


def _float(table: dict, key: str, label: str) -> float:
    value = _req(table, key, label)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{label}.{key} must be a number")
    return float(value)


def _bool(table: dict, key: str, label: str) -> bool:
    value = _req(table, key, label)
    if not isinstance(value, bool):
        raise ConfigError(f"{label}.{key} must be true or false")
    return value
