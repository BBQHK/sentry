"""python -m sentry"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
from dataclasses import replace
from pathlib import Path

from sentry.camera import Camera
from sentry.config import ConfigError, default_config_path, load_settings
from sentry.driver import build_driver
from sentry.gimbal import Gimbal
from sentry.web import create_app

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sentry pan-tilt camera console")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.toml")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--simulate", action="store_true", help="Do not open the PCA9685")
    parser.add_argument("--arm", action="store_true", help="Arm the gimbal as soon as the server starts")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        settings = load_settings(args.config or default_config_path())
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.host:
        settings = replace(settings, host=args.host)
    if args.port:
        settings = replace(settings, port=args.port)

    driver, mode = build_driver(settings, simulate=args.simulate)
    gimbal = Gimbal(settings, driver, mode, armed=args.arm or settings.arm_on_start)
    camera = Camera(settings)
    camera.pose = gimbal.angles
    gimbal.start()
    camera.start()
    app = create_app(settings, gimbal, camera)

    _log_url(settings.host, settings.port)
    try:
        app.run(host=settings.host, port=settings.port, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        pass
    finally:
        camera.stop()
        gimbal.stop()
    return 0


def _log_url(host: str, port: int) -> None:
    if host in {"0.0.0.0", "::"}:
        lan = _lan_ip()
        if lan:
            log.info("Open http://%s:%s on this network", lan, port)
        log.info("Also listening on http://127.0.0.1:%s", port)
    else:
        log.info("Open http://%s:%s", host, port)


def _lan_ip() -> str | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
    except OSError:
        return None
    if ip.startswith("127."):
        return None
    return ip


if __name__ == "__main__":
    raise SystemExit(main())
