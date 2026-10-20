import time
import unittest

from sentry.config import AxisConfig, Settings
from sentry.driver import SimDriver
from sentry.gimbal import Gimbal


def settings(**overrides) -> Settings:
    pan = overrides.pop("pan", AxisConfig(0, 0, 270, 135, False))
    tilt = overrides.pop("tilt", AxisConfig(1, 0, 270, 135, False))
    base = dict(
        host="127.0.0.1",
        port=8080,
        camera_device=0,
        camera_width=320,
        camera_height=240,
        camera_fps=10,
        jpeg_quality=80,
        i2c_address=0x40,
        pwm_frequency=50,
        min_pulse_us=500,
        max_pulse_us=2500,
        actuation_range=270,
        default_speed=100,
        arm_on_start=False,
        pan=pan,
        tilt=tilt,
    )
    base.update(overrides)
    return Settings(**base)


def gimbal(armed=False, tilt_invert=False):
    tilt = AxisConfig(1, 0, 270, 135, tilt_invert)
    driver = SimDriver()
    head = Gimbal(settings(tilt=tilt), driver, "simulation", armed=armed)
    return head, driver


class GimbalTests(unittest.TestCase):
    def test_disarmed_motion_does_not_pulse(self):
        head, driver = gimbal()
        head.set_stick(1, 0, speed=100)
        head._tick(0.1)
        self.assertAlmostEqual(head.pan, 145)
        self.assertEqual(driver.writes, [])

    def test_arming_sends_the_shown_angle(self):
        head, driver = gimbal()
        head.set_target(180, 100, speed=200)
        head._tick(1)
        self.assertEqual(driver.writes, [])
        head.set_armed(True)
        head._tick(0.02)
        self.assertEqual(driver.writes[-1], (180, 100))

    def test_invert_mirrors_inside_the_window(self):
        head, driver = gimbal(armed=True, tilt_invert=True)
        head.set_target(135, 0, speed=240)
        head._tick(1)
        pan, tilt = driver.writes[-1]
        self.assertEqual(pan, 135)
        self.assertEqual(tilt, 270)

    def test_stick_stops_when_the_browser_goes_quiet(self):
        head, _driver = gimbal()
        head.set_stick(1, 0, speed=100)
        head._tick(0.1)
        parked = head.pan
        head._stick_at = 0
        head._tick(0.1)
        self.assertEqual(head.pan, parked)

    def test_stick_cannot_pass_the_limit(self):
        head, _driver = gimbal()
        head.set_stick(1, 0, speed=240)
        for _ in range(40):
            head._stick_at = time.monotonic()
            head._tick(0.1)
        self.assertEqual(head.pan, 270)

    def test_final_fraction_of_a_move_is_still_sent(self):
        head, driver = gimbal(armed=True)
        head._tick(0.02)
        driver.writes.clear()
        head.set_target(head.pan + 0.2, None, speed=100)
        head._tick(0.02)
        self.assertAlmostEqual(driver.writes[-1][0], 135.2, places=3)

    def test_slow_moves_pulse_before_they_arrive(self):
        head, driver = gimbal(armed=True)
        head._tick(0.02)
        driver.writes.clear()
        head.set_target(180, None, speed=15)
        for _ in range(10):
            head._tick(0.02)
        self.assertGreaterEqual(len(driver.writes), 2)
        self.assertGreater(driver.writes[-1][0], 135)
        self.assertLess(driver.writes[-1][0], 180)

    def test_disarm_releases_once(self):
        head, driver = gimbal(armed=True)
        head.set_armed(False)
        head.set_armed(False)
        self.assertEqual(driver.releases, 1)

    def test_speed_is_clamped(self):
        head, _driver = gimbal()
        head.set_target(None, None, speed=1)
        self.assertEqual(head.speed, 15)
        head.set_target(None, None, speed=9999)
        self.assertEqual(head.speed, 240)
