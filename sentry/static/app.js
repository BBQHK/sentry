const feed = document.querySelector("#feed");
const viewfinder = document.querySelector("#viewfinder");
const crosshair = document.querySelector("#crosshair");
const videoMessage = document.querySelector("#video-message");
const linkError = document.querySelector("#link-error");
const modePill = document.querySelector("#mode-pill");
const cameraPill = document.querySelector("#camera-pill");
const armPill = document.querySelector("#arm-pill");
const readPan = document.querySelector("#read-pan");
const readTilt = document.querySelector("#read-tilt");
const armButton = document.querySelector("#arm-button");
const armHint = document.querySelector("#arm-hint");
const servoError = document.querySelector("#servo-error");
const stick = document.querySelector("#stick");
const knob = document.querySelector("#knob");
const panSlider = document.querySelector("#pan-slider");
const tiltSlider = document.querySelector("#tilt-slider");
const speedSlider = document.querySelector("#speed-slider");
const panValue = document.querySelector("#pan-value");
const tiltValue = document.querySelector("#tilt-value");
const speedValue = document.querySelector("#speed-value");
const panLabel = document.querySelector("#pan-label");
const tiltLabel = document.querySelector("#tilt-label");
const centerButton = document.querySelector("#center-button");
const storeMode = document.querySelector("#store-mode");
const presetHint = document.querySelector("#preset-hint");
const crossToggle = document.querySelector("#crosshair-toggle");
const lowLight = document.querySelector("#low-light-toggle");

let armed = false;
let store = false;
const keys = new Set();
const joy = { x: 0, y: 0, active: false };
let pointerId = null;

feed.src = "/video";
if (localStorage.getItem("sentry.crosshair") === "0") {
  crossToggle.checked = false;
  crosshair.hidden = true;
}

function degrees(value) {
  return `${Number(value).toFixed(1)}°`;
}

function normalize(x, y) {
  const mag = Math.hypot(x, y);
  if (mag > 1) return { x: x / mag, y: y / mag };
  return { x, y };
}

async function post(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function setOnline(online) {
  linkError.hidden = online;
}

function setSlider(slider, label, value, suffix) {
  if (document.activeElement !== slider) slider.value = value;
  const shown = document.activeElement === slider ? slider.value : value;
  label.textContent = `${Number(shown).toFixed(1)}${suffix}`;
}

function applyState(state) {
  const gimbal = state.gimbal;
  const camera = state.camera;
  armed = gimbal.armed;

  modePill.textContent = gimbal.driver.mode === "hardware" ? "PCA9685" : "Simulation";
  modePill.classList.toggle("warn", gimbal.driver.mode !== "hardware");
  cameraPill.textContent = camera.connected ? "Camera" : "No camera";
  cameraPill.classList.toggle("bad", !camera.connected);
  armPill.textContent = gimbal.armed ? "Armed" : "Idle";
  armPill.classList.toggle("hot", gimbal.armed);

  readPan.textContent = `PAN ${degrees(gimbal.pan)}`;
  readTilt.textContent = `TILT ${degrees(gimbal.tilt)}`;
  panLabel.textContent = `Pan · ch ${gimbal.channels.pan}`;
  tiltLabel.textContent = `Tilt · ch ${gimbal.channels.tilt}`;

  panSlider.min = gimbal.limits.pan[0];
  panSlider.max = gimbal.limits.pan[1];
  tiltSlider.min = gimbal.limits.tilt[0];
  tiltSlider.max = gimbal.limits.tilt[1];
  setSlider(panSlider, panValue, gimbal.pan, "°");
  setSlider(tiltSlider, tiltValue, gimbal.tilt, "°");
  setSlider(speedSlider, speedValue, gimbal.speed, "°/s");

  armButton.textContent = gimbal.armed ? "Disarm" : "Arm gimbal";
  armButton.classList.toggle("on", gimbal.armed);
  armButton.setAttribute("aria-pressed", String(gimbal.armed));
  armHint.textContent = gimbal.armed
    ? "Servos are holding these angles. Disarm stops the pulses and they can droop."
    : "Arming moves the servos to the angles below. Stay clear of the bracket.";

  if (gimbal.driver.error) {
    servoError.hidden = false;
    servoError.textContent = gimbal.driver.error;
  } else {
    servoError.hidden = true;
  }

  videoMessage.hidden = camera.connected;
  videoMessage.textContent = camera.message || "";
  if (document.activeElement !== lowLight) lowLight.checked = camera.low_light;
  setOnline(true);
}

async function poll() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    if (!response.ok) throw new Error("status");
    applyState(await response.json());
  } catch {
    setOnline(false);
  }
}

armButton.addEventListener("click", async () => {
  armButton.disabled = true;
  try {
    applyState(await post("/api/arm", { armed: !armed }));
  } catch (error) {
    servoError.hidden = false;
    servoError.textContent = error.message;
  } finally {
    armButton.disabled = false;
  }
});

centerButton.addEventListener("click", () => {
  post("/api/center", {}).then(applyState).catch(() => setOnline(false));
});

panSlider.addEventListener("input", () => {
  panValue.textContent = degrees(panSlider.value);
  post("/api/target", {
    pan: Number(panSlider.value),
    speed: Number(speedSlider.value),
  }).then(applyState).catch(() => setOnline(false));
});

tiltSlider.addEventListener("input", () => {
  tiltValue.textContent = degrees(tiltSlider.value);
  post("/api/target", {
    tilt: Number(tiltSlider.value),
    speed: Number(speedSlider.value),
  }).then(applyState).catch(() => setOnline(false));
});

speedSlider.addEventListener("input", () => {
  speedValue.textContent = `${Number(speedSlider.value).toFixed(1)}°/s`;
});

speedSlider.addEventListener("change", () => {
  post("/api/target", { speed: Number(speedSlider.value) }).catch(() => setOnline(false));
});

lowLight.addEventListener("change", () => {
  post("/api/camera", { low_light: lowLight.checked }).then(applyState).catch(() => setOnline(false));
});

crossToggle.addEventListener("change", () => {
  crosshair.hidden = !crossToggle.checked;
  localStorage.setItem("sentry.crosshair", crossToggle.checked ? "1" : "0");
});

function presets() {
  try {
    const saved = JSON.parse(localStorage.getItem("sentry.presets") || "null");
    if (Array.isArray(saved) && saved.length === 3) return saved;
  } catch {
    /* ignore broken storage */
  }
  return [null, null, null];
}

function savePresets(items) {
  localStorage.setItem("sentry.presets", JSON.stringify(items));
  refreshPresetTitles(items);
}

function refreshPresetTitles(items) {
  document.querySelectorAll("[data-preset]").forEach((button) => {
    const item = items[Number(button.dataset.preset)];
    button.title = item ? `Pan ${item.pan}°, tilt ${item.tilt}°` : "Empty";
  });
}

refreshPresetTitles(presets());

storeMode.addEventListener("click", () => {
  store = !store;
  storeMode.setAttribute("aria-pressed", String(store));
  presetHint.textContent = store
    ? "Store is on. Click a number to save the current angles."
    : "Click a number to move there. Turn on Store, then click a number to save the current view.";
});

document.querySelectorAll("[data-preset]").forEach((button) => {
  button.addEventListener("click", () => {
    const index = Number(button.dataset.preset);
    const items = presets();
    if (store) {
      items[index] = {
        pan: Number(panSlider.value),
        tilt: Number(tiltSlider.value),
      };
      savePresets(items);
      store = false;
      storeMode.setAttribute("aria-pressed", "false");
      presetHint.textContent = `Saved preset ${index + 1}.`;
      return;
    }
    const item = items[index];
    if (!item) {
      presetHint.textContent = `Preset ${index + 1} is empty. Turn on Store to save it.`;
      return;
    }
    post("/api/target", {
      pan: item.pan,
      tilt: item.tilt,
      speed: Number(speedSlider.value),
    }).then(applyState).catch(() => setOnline(false));
  });
});

function placeKnob(dx, dy) {
  knob.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;
}

function moveStick(event) {
  const rect = stick.getBoundingClientRect();
  const radius = rect.width / 2 - 28;
  let dx = event.clientX - (rect.left + rect.width / 2);
  let dy = event.clientY - (rect.top + rect.height / 2);
  const mag = Math.hypot(dx, dy);
  if (mag > radius) {
    dx = (dx / mag) * radius;
    dy = (dy / mag) * radius;
  }
  joy.x = dx / radius;
  joy.y = -dy / radius;
  joy.active = true;
  placeKnob(dx, dy);
}

stick.addEventListener("pointerdown", (event) => {
  pointerId = event.pointerId;
  stick.setPointerCapture(event.pointerId);
  moveStick(event);
});

stick.addEventListener("pointermove", (event) => {
  if (event.pointerId !== pointerId) return;
  moveStick(event);
});

function endStick(event) {
  if (event.pointerId !== pointerId) return;
  pointerId = null;
  joy.x = 0;
  joy.y = 0;
  joy.active = false;
  placeKnob(0, 0);
}

stick.addEventListener("pointerup", endStick);
stick.addEventListener("pointercancel", endStick);

function controlVector() {
  if (joy.active) return normalize(joy.x, joy.y);
  let x = 0;
  let y = 0;
  if (keys.has("arrowleft") || keys.has("a")) x -= 1;
  if (keys.has("arrowright") || keys.has("d")) x += 1;
  if (keys.has("arrowup") || keys.has("w")) y += 1;
  if (keys.has("arrowdown") || keys.has("s")) y -= 1;
  return normalize(x, y);
}

window.addEventListener("keydown", (event) => {
  const tag = event.target && event.target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  const key = event.key.toLowerCase();
  if (["arrowup", "arrowdown", "arrowleft", "arrowright"].includes(key)) {
    event.preventDefault();
  }
  if (key === "escape") {
    post("/api/arm", { armed: false }).then(applyState).catch(() => setOnline(false));
    return;
  }
  if (key === "c" && !event.repeat) {
    post("/api/center", {}).then(applyState).catch(() => setOnline(false));
  }
  if (["1", "2", "3"].includes(key) && !event.repeat && !store) {
    document.querySelector(`[data-preset="${Number(key) - 1}"]`).click();
  }
  keys.add(key);
});

window.addEventListener("keyup", (event) => {
  keys.delete(event.key.toLowerCase());
});

window.addEventListener("blur", () => {
  keys.clear();
  joy.active = false;
  joy.x = 0;
  joy.y = 0;
  placeKnob(0, 0);
});

let lastSent = { x: 0, y: 0 };
let stickBusy = false;
let stickPending = null;

async function sendStick(vector) {
  stickPending = vector;
  if (stickBusy) return;
  stickBusy = true;
  while (stickPending) {
    const next = stickPending;
    stickPending = null;
    try {
      applyState(await post("/api/stick", {
        x: next.x,
        y: next.y,
        speed: Number(speedSlider.value),
      }));
    } catch {
      setOnline(false);
    }
  }
  stickBusy = false;
}

setInterval(() => {
  const vector = controlVector();
  if (vector.x === 0 && vector.y === 0 && lastSent.x === 0 && lastSent.y === 0) return;
  lastSent = vector;
  sendStick(vector);
}, 100);

viewfinder.addEventListener("dblclick", () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else viewfinder.requestFullscreen();
});

poll();
setInterval(poll, 400);
