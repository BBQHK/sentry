#!/usr/bin/env bash
# Install Sentry's dependencies on Raspberry Pi OS and enable I2C.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v apt-get >/dev/null; then
  echo "This script is for Raspberry Pi OS." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y python3-pip python3-venv python3-dev i2c-tools python3-libgpiod v4l-utils
if command -v raspi-config >/dev/null; then
  sudo raspi-config nonint do_i2c 0 || true
fi

python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt

echo
if ! id -nG "$USER" | grep -qw i2c || ! id -nG "$USER" | grep -qw video; then
  echo "Add your user to the i2c and video groups, then log out and back in:"
  echo "  sudo usermod -aG i2c,video $USER"
  echo
fi
echo "Start Sentry:"
echo "  .venv/bin/python -m sentry"
echo
echo "If i2cdetect does not list 40, reboot once after enabling I2C."
