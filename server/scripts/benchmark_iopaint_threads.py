"""Benchmark one warmed IOPaint thread configuration with repeatable input."""
from __future__ import annotations

import argparse
import base64
import json
import statistics
import time
from pathlib import Path

import cv2
import numpy as np
import requests


def _encode(image):
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("benchmark fixture encoding failed")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def _fixture():
    width, height = 384, 256
    image = np.full((height, width, 3), 247, dtype=np.uint8)
    for y in range(28, height, 34):
        cv2.line(image, (18, y), (width - 18, y), (110, 110, 110), 1)
    for x in range(18, width, 92):
        cv2.line(image, (x, 28), (x, height - 24), (135, 135, 135), 1)
    cv2.putText(image, "INVOICE 2026", (36, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (45, 45, 45), 1)
    cv2.putText(image, "WATERMARK", (228, 208), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (80, 80, 180), 2)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.rectangle(mask, (220, 185), (365, 218), 255, thickness=-1)
    return image, mask


def _percentile(values, percentile):
    ordered = sorted(values)
    if not ordered:
        return 0
    rank = max(0, min(len(ordered) - 1, int(np.ceil((percentile / 100.0) * len(ordered))) - 1))
    return ordered[rank]


def _proc_stats(pid):
    status = {"rssMb": 0.0, "swapMb": 0.0, "threads": 0}
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        status["cpuTicks"] = int(fields[13]) + int(fields[14])
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                status["rssMb"] = round(int(line.split()[1]) / 1024.0, 1)
            elif line.startswith("VmSwap:"):
                status["swapMb"] = round(int(line.split()[1]) / 1024.0, 1)
            elif line.startswith("Threads:"):
                status["threads"] = int(line.split()[1])
    except Exception:
        status["cpuTicks"] = 0
    cpu_fields = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
    status["systemIowaitTicks"] = int(cpu_fields[4]) if len(cpu_fields) > 4 else 0
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8081")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--output", required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    runtime = json.loads(Path("/run/iopaint-lama-runtime.json").read_text(encoding="utf-8"))
    warm = json.loads(Path("/run/iopaint-lama-warm.json").read_text(encoding="utf-8"))
    pid = int(runtime["pid"])
    image, mask = _fixture()
    payload = {
        "image": _encode(image),
        "mask": _encode(mask),
        "hd_strategy": "CROP",
        "hd_strategy_crop_margin": 64,
        "hd_strategy_crop_trigger_size": 800,
        "sd_keep_unmasked_area": True,
        "sd_mask_blur": 3,
        "sd_strength": 0.85,
        "prompt": "",
        "negative_prompt": "",
    }
    session = requests.Session()
    before = _proc_stats(pid)
    rows = []
    for index in range(args.runs):
        payload["prompt"] = f"thread-ab-{args.label}-{index + 1}"
        started = time.perf_counter()
        response = session.post(args.base_url.rstrip("/") + "/api/v1/inpaint", json=payload, timeout=120)
        wall_ms = int((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        rows.append({
            "run": index + 1,
            "wallMs": wall_ms,
            "inferenceMs": int(response.headers.get("X-IOPaint-Inference-Ms", 0)),
            "outputEncodeMs": int(response.headers.get("X-IOPaint-Output-Encode-Ms", 0)),
            "totalMs": int(response.headers.get("X-IOPaint-Total-Ms", wall_ms)),
            "responseBytes": len(response.content),
        })
    after = _proc_stats(pid)
    inference = [row["inferenceMs"] for row in rows]
    wall = [row["wallMs"] for row in rows]
    report = {
        "label": args.label,
        "runs": len(rows),
        "pid": pid,
        "modelWarm": bool(warm.get("modelWarm") and int(warm.get("pid") or 0) == pid),
        "torchThreads": int(runtime.get("torchThreads") or 0),
        "interopThreads": int(runtime.get("interopThreads") or 0),
        "inputSize": f"{image.shape[1]}x{image.shape[0]}",
        "summary": {
            "inferenceP50Ms": int(statistics.median(inference)),
            "inferenceP95Ms": _percentile(inference, 95),
            "inferenceMaxMs": max(inference),
            "wallP50Ms": int(statistics.median(wall)),
            "wallP95Ms": _percentile(wall, 95),
            "wallMaxMs": max(wall),
            "processCpuTicks": int(after["cpuTicks"] - before["cpuTicks"]),
            "systemIowaitTicks": int(after["systemIowaitTicks"] - before["systemIowaitTicks"]),
            "rssBeforeMb": before["rssMb"],
            "rssAfterMb": after["rssMb"],
            "swapBeforeMb": before["swapMb"],
            "swapAfterMb": after["swapMb"],
            "processThreads": after["threads"],
        },
        "rows": rows,
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
