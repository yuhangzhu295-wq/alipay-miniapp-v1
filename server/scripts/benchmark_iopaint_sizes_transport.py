"""Benchmark HD inference sizes and local Backend-to-IOPaint transport options."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import statistics
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
import requests


def _percentile(values, percentile):
    ordered = sorted(values)
    if not ordered:
        return 0
    index = max(0, min(len(ordered) - 1, math.ceil(percentile / 100.0 * len(ordered)) - 1))
    return int(ordered[index])


def _encode(image):
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("image encoding failed")
    return encoded.tobytes()


def _fixture(max_edge):
    width = int(max_edge)
    height = int(round(max_edge * 0.70))
    image = np.full((height, width, 3), 246, dtype=np.uint8)
    for y in np.linspace(45, height - 35, 10, dtype=int):
        cv2.line(image, (25, int(y)), (width - 25, int(y)), (95, 95, 95), 1)
    for x in np.linspace(25, width - 25, 7, dtype=int):
        cv2.line(image, (int(x), 45), (int(x), height - 35), (110, 110, 110), 1)
    scale = max_edge / 1000.0
    cv2.putText(image, "INVOICE TABLE QR STAMP", (40, 34), cv2.FONT_HERSHEY_SIMPLEX, max(0.5, scale), (35, 35, 35), max(1, int(scale * 2)))
    x1, y1 = int(width * 0.34), int(height * 0.46)
    x2, y2 = int(width * 0.69), int(height * 0.58)
    cv2.putText(image, "WATERMARK", (x1, int((y1 + y2) / 2)), cv2.FONT_HERSHEY_SIMPLEX, max(0.6, scale * 1.2), (65, 65, 205), max(2, int(scale * 3)))
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.rectangle(mask, (x1 - 12, y1), (x2, y2), 255, -1)
    return image, mask


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def _outside_changed(source, result, mask):
    outside = mask == 0
    return int(np.count_nonzero(np.any(source != result, axis=2) & outside))


def _size_benchmark(session, base_url, label, max_edge, runs):
    image, mask = _fixture(max_edge)
    image_bytes = _encode(image)
    mask_bytes = _encode(mask)
    payload = {
        "image": _b64(image_bytes),
        "mask": _b64(mask_bytes),
        "hd_strategy": "CROP",
        "hd_strategy_crop_margin": 64,
        "hd_strategy_crop_trigger_size": 800,
        "sd_keep_unmasked_area": True,
        "sd_mask_blur": 3,
        "sd_strength": 0.85,
        "prompt": "",
        "negative_prompt": "",
    }
    rows = []
    for index in range(runs):
        payload["prompt"] = f"size-ab-{label}-{index + 1}"
        started = time.perf_counter()
        response = session.post(base_url.rstrip("/") + "/api/v1/inpaint", json=payload, timeout=240)
        wall_ms = int((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        result = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
        if result is None:
            raise RuntimeError("IOPaint output decode failed")
        mask_pixels = mask > 0
        red_before = float(np.mean(image[mask_pixels, 2].astype(np.float32) - image[mask_pixels, 1].astype(np.float32)))
        red_after = float(np.mean(result[mask_pixels, 2].astype(np.float32) - result[mask_pixels, 1].astype(np.float32)))
        rows.append({
            "run": index + 1,
            "wallMs": wall_ms,
            "inferenceMs": int(response.headers.get("X-IOPaint-Inference-Ms", 0)),
            "totalMs": int(response.headers.get("X-IOPaint-Total-Ms", wall_ms)),
            "outsideChangedPixels": _outside_changed(image, result, mask),
            "outputSizePreserved": result.shape == image.shape,
            "watermarkRedResidualRatio": round(abs(red_after) / max(1.0, abs(red_before)), 4),
            "outputSha256": hashlib.sha256(response.content).hexdigest(),
        })
    wall = [row["wallMs"] for row in rows]
    inference = [row["inferenceMs"] for row in rows]
    return {
        "label": label,
        "inputSize": f"{image.shape[1]}x{image.shape[0]}",
        "maxEdge": max_edge,
        "runs": runs,
        "summary": {
            "wallP50Ms": int(statistics.median(wall)),
            "wallP95Ms": _percentile(wall, 95),
            "inferenceP50Ms": int(statistics.median(inference)),
            "inferenceP95Ms": _percentile(inference, 95),
            "outsideChangedPixelsMax": max(row["outsideChangedPixels"] for row in rows),
            "outputSizePreserved": all(row["outputSizePreserved"] for row in rows),
            "watermarkRedResidualRatioMax": max(row["watermarkRedResidualRatio"] for row in rows),
        },
        "rows": rows,
    }


def _time_operation(operation, runs=20):
    values = []
    for _ in range(runs):
        started = time.perf_counter()
        operation()
        values.append((time.perf_counter() - started) * 1000)
    return {
        "runs": runs,
        "p50Ms": round(statistics.median(values), 3),
        "p95Ms": round(sorted(values)[math.ceil(0.95 * len(values)) - 1], 3),
        "maxMs": round(max(values), 3),
    }


def _transport_benchmark(base_url):
    image, mask = _fixture(1024)
    image_bytes = _encode(image)
    mask_bytes = _encode(mask)

    def base64_json():
        body = json.dumps({"image": _b64(image_bytes), "mask": _b64(mask_bytes)}, separators=(",", ":"))
        parsed = json.loads(body)
        base64.b64decode(parsed["image"])
        base64.b64decode(parsed["mask"])

    def multipart():
        _, body = requests.models.RequestEncodingMixin._encode_files(
            {"image": ("image.png", image_bytes, "image/png"), "mask": ("mask.png", mask_bytes, "image/png")},
            {},
        )
        len(body)

    def temporary_files():
        image_path = mask_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False) as image_file:
                image_file.write(image_bytes)
                image_path = image_file.name
            with tempfile.NamedTemporaryFile(delete=False) as mask_file:
                mask_file.write(mask_bytes)
                mask_path = mask_file.name
            Path(image_path).read_bytes()
            Path(mask_path).read_bytes()
        finally:
            for value in (image_path, mask_path):
                if value and os.path.exists(value):
                    os.unlink(value)

    openapi = requests.get(base_url.rstrip("/") + "/openapi.json", timeout=20).json()
    paths = sorted(openapi.get("paths", {}).keys())
    return {
        "inputImageBytes": len(image_bytes),
        "inputMaskBytes": len(mask_bytes),
        "base64Json": {**_time_operation(base64_json), "supportedByInstalledIOPaint": "/api/v1/inpaint" in paths},
        "multipartBinary": {**_time_operation(multipart), "supportedByInstalledIOPaint": any("multipart" in path for path in paths)},
        "temporaryFiles": {**_time_operation(temporary_files), "supportedByInstalledIOPaint": False},
        "directReusableAdapter": {"supportedByInstalledIOPaint": False, "reason": "The installed IOPaint service exposes an HTTP model manager, not an import-stable adapter API."},
        "availablePaths": paths,
        "selected": "base64JsonPersistentSession",
        "selectionReason": "It is the installed stable API; measured encode/decode overhead is small relative to LaMa inference and the persistent Session reuses localhost connections.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8081")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    session = requests.Session()
    variants = []
    for label, max_edge in (
        ("small-768", 768),
        ("small-1024", 1024),
        ("medium-1024", 1024),
        ("medium-1280", 1280),
        ("large-1280", 1280),
        ("large-1536", 1536),
    ):
        result = _size_benchmark(session, args.base_url, label, max_edge, args.runs)
        variants.append(result)
        print(json.dumps({"label": label, "summary": result["summary"]}, ensure_ascii=True), flush=True)
    report = {
        "status": "PASS" if all(item["summary"]["outsideChangedPixelsMax"] == 0 and item["summary"]["outputSizePreserved"] for item in variants) else "FAIL",
        "sizeVariants": variants,
        "transport": _transport_benchmark(args.base_url),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "transport": report["transport"]}, ensure_ascii=True, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
