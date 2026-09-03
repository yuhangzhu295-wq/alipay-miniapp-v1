"""Warm the resident LaMa model after IOPaint starts and publish warm state."""
from __future__ import annotations

import base64
import json
import os
import time

import cv2
import numpy as np
import requests


IOPAINT_URL = os.environ.get("IOPAINT_URL", "http://127.0.0.1:8081").rstrip("/")
RUNTIME_PATH = os.environ.get("IOPAINT_RUNTIME_PATH", "/run/iopaint-lama-runtime.json")
WARM_PATH = os.environ.get("IOPAINT_WARM_PATH", "/run/iopaint-lama-warm.json")


def _encode(image):
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("warmup image encoding failed")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def _runtime():
    with open(RUNTIME_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main():
    deadline = time.monotonic() + 90
    session = requests.Session()
    while time.monotonic() < deadline:
        try:
            response = session.get(IOPAINT_URL + "/api/v1/model", timeout=2)
            if response.status_code == 200 and str(response.json().get("name", "")).lower() == "lama":
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        raise RuntimeError("IOPaint did not become ready for warmup")

    image = np.zeros((96, 96, 3), dtype=np.uint8)
    image[:, :, 0] = np.linspace(40, 210, 96, dtype=np.uint8)
    image[:, :, 1] = 145
    image[:, :, 2] = np.linspace(210, 40, 96, dtype=np.uint8)
    mask = np.zeros((96, 96), dtype=np.uint8)
    cv2.circle(mask, (48, 48), 12, 255, thickness=-1)
    payload = {
        "image": _encode(image),
        "mask": _encode(mask),
        "hd_strategy": "CROP",
        "hd_strategy_crop_margin": 32,
        "hd_strategy_crop_trigger_size": 800,
        "sd_keep_unmasked_area": True,
        "sd_mask_blur": 3,
        "sd_strength": 0.85,
        "prompt": "startup-warmup",
        "negative_prompt": "",
    }
    started = time.perf_counter()
    response = session.post(IOPAINT_URL + "/api/v1/inpaint", json=payload, timeout=120)
    warmup_ms = int((time.perf_counter() - started) * 1000)
    response.raise_for_status()
    runtime = _runtime()
    state = {
        "pid": int(runtime["pid"]),
        "model": "lama",
        "modelWarm": True,
        "lastWarmupMs": warmup_ms,
        "warmedAtEpoch": time.time(),
        "torchThreads": int(runtime.get("torchThreads") or 0),
        "interopThreads": int(runtime.get("interopThreads") or 0),
    }
    temp_path = WARM_PATH + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=True, separators=(",", ":"))
    os.replace(temp_path, WARM_PATH)
    print("[watermark-hd-warmup] " + json.dumps(state, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
