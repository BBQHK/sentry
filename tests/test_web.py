import unittest

from sentry.config import load_settings, default_config_path
from sentry.driver import SimDriver
from sentry.gimbal import Gimbal
from sentry.web import create_app


class FakeCamera:
    def __init__(self):
        self.low_light = False
        self.connected = False
        self.message = "test camera"
        self.jpeg = b"\xff\xd8\xff\xd9"

    def get_jpeg(self):
        return self.jpeg

    def stream(self):
        yield b""

    def set_low_light(self, enabled):
        self.low_light = enabled

    def status(self):
        return {
            "connected": self.connected,
            "message": self.message,
            "low_light": self.low_light,
            "device": 0,
        }


class WebTests(unittest.TestCase):
    def setUp(self):
        settings = load_settings(default_config_path())
        self.gimbal = Gimbal(settings, SimDriver(), "simulation", armed=False)
        self.camera = FakeCamera()
        self.client = create_app(settings, self.gimbal, self.camera).test_client()

    def test_console_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Arm gimbal", response.data)
        script = self.client.get("/static/app.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn(b'feed.src = "/video"', script.data)
        self.assertEqual(self.client.get("/static/app.css").status_code, 200)

    def test_target_and_arm_round_trip(self):
        response = self.client.post("/api/target", json={"pan": 180, "tilt": 90, "speed": 200})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["gimbal"]["target"]["pan"], 180)
        self.assertFalse(body["gimbal"]["armed"])
        self.gimbal._tick(1)
        self.assertEqual(self.gimbal.driver.writes, [])

        armed = self.client.post("/api/arm", json={"armed": True})
        self.assertTrue(armed.get_json()["gimbal"]["armed"])
        self.gimbal._tick(0.02)
        self.assertEqual(self.gimbal.driver.writes[-1], (180, 90))

    def test_bad_json(self):
        response = self.client.post("/api/target", data="nope", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_low_light_flag(self):
        response = self.client.post("/api/camera", json={"low_light": True})
        self.assertTrue(response.get_json()["camera"]["low_light"])
