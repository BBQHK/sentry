import tempfile
import unittest
from pathlib import Path

from sentry.config import ConfigError, default_config_path, load_settings

ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_shipped_file(self):
        settings = load_settings(default_config_path())
        self.assertEqual(settings.pan.channel, 0)
        self.assertEqual(settings.tilt.channel, 1)
        self.assertEqual(settings.actuation_range, 270)
        self.assertEqual(settings.min_pulse_us, 500)
        self.assertEqual(settings.max_pulse_us, 2500)
        self.assertEqual(settings.pan.center, 135)
        self.assertFalse(settings.arm_on_start)

    def test_missing_file(self):
        with self.assertRaises(ConfigError):
            load_settings(ROOT / "missing.toml")

    def test_shared_channel_is_rejected(self):
        raw = (ROOT / "config.toml").read_text(encoding="utf-8")
        raw = raw.replace("channel = 1", "channel = 0", 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(raw, encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_settings(path)

    def test_center_outside_the_window_is_rejected(self):
        raw = (ROOT / "config.toml").read_text(encoding="utf-8")
        raw = raw.replace("center = 135", "center = 10", 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(raw, encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_settings(path)
