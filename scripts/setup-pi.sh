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
# Keep the hardware I2C bus on GPIO2/GPIO3 for the other project.
if command -v raspi-config >/dev/null; then
  sudo raspi-config nonint do_i2c 0 || true
fi

# Sentry's own bus: SDA GPIO23 (pin 16), SCL GPIO24 (pin 18).
OVERLAY='dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=23,i2c_gpio_scl=24'
BOOT=""
if [[ -f /boot/firmware/config.txt ]]; then
  BOOT=/boot/firmware/config.txt
elif [[ -f /boot/config.txt ]]; then
  BOOT=/boot/config.txt
fi
if [[ -n "$BOOT" ]]; then
  if grep -q 'i2c_gpio_sda=23' "$BOOT"; then
    echo "Software I2C overlay already present in $BOOT"
  else
    echo "$OVERLAY" | sudo tee -a "$BOOT" >/dev/null
    echo "Added $OVERLAY to $BOOT"
    echo "Reboot before starting Sentry."
  fi
else
  echo "Add this line to the Pi boot config, then reboot:"
  echo "  $OVERLAY"
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
echo "After reboot, i2cdetect -y 3 should list 40."
