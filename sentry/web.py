"""HTTP console: video stream and gimbal commands."""

from __future__ import annotations

import math
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from sentry import __version__
from sentry.config import Settings

STATIC = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings, gimbal, camera) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    def state() -> dict:
        return {
            "version": __version__,
            "gimbal": gimbal.snapshot(),
            "camera": camera.status(),
        }

    @app.get("/")
    def index():
        response = send_from_directory(STATIC, "index.html")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/video")
    def video():
        return Response(
            camera.stream(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/snapshot.jpg")
    def snapshot():
        frame = camera.get_jpeg()
        if not frame:
            return jsonify(error="No frame yet"), 503
        return Response(frame, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/state")
    def api_state():
        return jsonify(state())

    @app.post("/api/target")
    def api_target():
        data, error = _object()
        if error:
            return error
        try:
            pan = _number(data.get("pan"), "pan")
            tilt = _number(data.get("tilt"), "tilt")
            speed = _number(data.get("speed"), "speed")
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        gimbal.set_target(pan, tilt, speed)
        return jsonify(state())

    @app.post("/api/stick")
    def api_stick():
        data, error = _object()
        if error:
            return error
        try:
            x = _number(data.get("x", 0), "x")
            y = _number(data.get("y", 0), "y")
            speed = _number(data.get("speed"), "speed")
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        if x is None or y is None:
            return jsonify(error="x and y are required"), 400
        gimbal.set_stick(x, y, speed)
        return jsonify(state())

    @app.post("/api/center")
    def api_center():
        gimbal.center()
        return jsonify(state())

    @app.post("/api/arm")
    def api_arm():
        data, error = _object()
        if error:
            return error
        if "armed" not in data:
            return jsonify(error="armed is required"), 400
        gimbal.set_armed(bool(data["armed"]))
        return jsonify(state())

    @app.post("/api/camera")
    def api_camera():
        data, error = _object()
        if error:
            return error
        if "low_light" in data:
            camera.set_low_light(bool(data["low_light"]))
        return jsonify(state())

    return app


def _object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify(error="Expected a JSON object"), 400)
    return data, None


def _number(value, name: str) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a number")
    return number
