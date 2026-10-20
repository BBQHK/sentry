# Sentry

Sentry is a small console for a Raspberry Pi 5 that streams a USB camera and aims it with two servos. Open it in a browser on the same network: watch the picture, pan and tilt with a joystick, sliders, or the keyboard.

The servos are not driven until you press **Arm gimbal**. On a PC, the same program runs with simulated servos so you can try the page before the Pi is wired.

## Hardware

- Raspberry Pi 5
- PCA9685 16-channel PWM driver
- Two Hiwonder LD-3015MG servos (0–270°, 500–2500 µs at 50 Hz, 6–7.4 V)
- USB camera (IR illumination on the camera is automatic; Sentry shows whatever the camera sends)
- A separate **6 V** supply for the servos, **3 A minimum, 5 A is more comfortable**

Each servo's minimum working current is 1 A, and stall current is higher. Do not power them from the Pi's 5 V pin. 5 V is also below the servo's rated range. Stay at 6 V unless you have checked that the capacitor on the PCA9685's servo rail is rated above your supply. Many clone boards are not happy at 7.4 V.

These servos are strong enough to pinch a finger or crack a printed bracket. Keep hands clear when you arm, and start with the camera removed.

## Wire it

This matches the blue PCA9685 in the project photo: servo sockets along the bottom, green **POWER** screw terminal on top, round capacitor on the left. Logic power (**VCC**) and servo power (green terminal) are already separate on this board. There is no jumper to pull. Leave the **A0–A5** pads unsoldered so the I2C address stays `0x40`.

Use the **left** header. Top to bottom, with the servo sockets facing you along the bottom:

| Left header | Connect to |
| --- | --- |
| GND | Pi pin 6 (GND) |
| OE | leave open (the board already enables the outputs) |
| SCL | Pi pin 5 (GPIO3) |
| SDA | Pi pin 3 (GPIO2) |
| VCC | Pi pin 1 (**3.3 V**, not 5 V) |

The right-hand header repeats those same signals for daisy-chaining. Use one side only.

Servo power goes only to the green terminal:

- Screw toward the round capacitor: supply **negative** (GND)
- Screw toward the black chip, the one marked **V+**: supply **+6 V**

That ground is the same net as the GND pin, so the Pi and the servo supply share a ground once both are connected. Bring up the Pi first, then turn on the 6 V supply. Turn the 6 V supply off first when you shut down.

Each servo socket is three pins. The legend in the middle of the row reads outward from the chip:

| Pin (outer edge last) | Color on the board | LD-3015MG wire |
| --- | --- | --- |
| GND, closest to the chip | black | black |
| V+, middle | red | red |
| PWM, outer edge | yellow | white |

Channel **0** is the leftmost socket (pan). Channel **1** is the next one (tilt).

The camera plugs into a Pi USB port. A camera with bright IR LEDs may need a powered hub if it browns out the port.

## Calibrate the horns

135° is the middle of the LD-3015MG's 270° travel (a 1500 µs pulse), not 90°. The software limits in `config.toml` are narrower than that so a typical bracket does not drive into itself. The horn's 25-tooth spline seats in 14.4° steps, so the last trim is the `center` value.

1. Leave the camera off the bracket.
2. Start Sentry, open the page, and press Arm. Both servos go to the angles on screen (135° by default).
3. Turn off the servo supply.
4. Fit each horn so the head sits where you want "forward" and "level", then tighten it.
5. Turn the supply back on, arm again, and nudge `min_angle` / `max_angle` until the picture can cover the view you want without hitting the frame.
6. If right/left or up/down is backwards, set that axis's `invert` to `true` and restart.

`invert` mirrors the axis inside your min/max window. It does not change the pulse range.

## Try it on a PC

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m sentry
```

Open http://127.0.0.1:8080. The header says **Simulation**. A USB webcam on the PC is used if one is present; otherwise the page draws a reticle you can move. Arming does not talk to a servo driver.

## Install on the Pi 5

Raspberry Pi OS Bookworm, 64-bit. Python 3.11 or newer.

```bash
bash scripts/setup-pi.sh
```

The script creates `.venv`, installs the Python packages, and turns on I2C. Then:

```bash
sudo usermod -aG i2c,video $USER
```

Log out and back in. Copy the project onto the Pi first (the script runs from the repo root). Reboot if `i2cdetect` does not show the board:

```bash
i2cdetect -y 1
```

Address `40` should appear. `70` is the PCA9685 all-call address and can show up as well.

```bash
.venv/bin/python -m sentry
```

From another computer on the LAN, open `http://<pi-ip>:8080`. The terminal prints that address when it starts.

There is no login on the page. Run it on a network you trust.

## Use the page

- **Arm gimbal** sends pulses. Until then you can aim the on-screen controls without moving hardware. Arming moves the servos straight to the angles shown.
- Drag the joystick, the sliders, or hold W A S D / arrow keys. Speed is degrees per second.
- **Center** returns to the configured center, at that speed.
- **Esc** disarms. Disarming stops the pulses, so a heavy camera can droop.
- **1 2 3** recall presets stored in this browser. Turn on **Store**, then click a number to save the current angles.
- Double-click the picture for fullscreen. **Save frame** downloads the current JPEG.
- **Brighter exposure** asks the camera for more gain. A lot of IR webcams ignore it and turn their own LEDs on in the dark.

Stopping Sentry does not clear the PCA9685. The chip keeps the last pulse and the servos stay held until you disarm, power off the servo supply, or start Sentry again (the board resets on the next Arm).

## Run at boot

Edit `User`, `Group`, and the paths in `deploy/sentry.service` if the account is not `pi`.

```bash
sudo cp deploy/sentry.service /etc/systemd/system/sentry.service
sudo systemctl daemon-reload
sudo systemctl enable --now sentry
journalctl -u sentry -f
```

## Troubleshooting

| What you see | What to check |
| --- | --- |
| Arm fails, I2C error in the page | `i2cdetect -y 1` shows `40`. User is in group `i2c`. I2C was enabled, then the Pi was rebooted. SDA is pin 3, SCL is pin 5, logic is 3.3 V. |
| Servo buzzes or twitches | Common ground is connected. Servo supply can actually deliver the current. Pulse still 500–2500 µs at 50 Hz. |
| Servo slams into the bracket | Power off. Narrow `min_angle` / `max_angle`. Reseat the horn at center. |
| Camera pill says no camera | `v4l2-ctl --list-devices`. Set `camera.device` to the other index (`0` or `1`, or `/dev/video0`). User is in group `video`. Try another USB port. |
| Picture is dark at night | The camera's IR LEDs usually need the scene to be dark, and they need enough USB power. |
| Page will not load from a laptop | Pi and laptop are on the same LAN. The process was started with host `0.0.0.0`. |
| `pip install` of OpenCV fails on the Pi | `sudo apt install python3-opencv`, recreate the venv with `python3 -m venv --system-site-packages .venv`, and install Flask and the servo library from `requirements.txt` without the OpenCV line. |

## Layout

| Path | Role |
| --- | --- |
| `config.toml` | Address, pulse range, travel limits, camera device |
| `sentry/camera.py` | USB capture and the placeholder picture |
| `sentry/driver.py` | PCA9685 via ServoKit, opened on the first armed move |
| `sentry/gimbal.py` | Speed limit, joystick timeout, arm/disarm |
| `sentry/web.py` | Pages and `/api` |
| `sentry/static/` | The browser console |
