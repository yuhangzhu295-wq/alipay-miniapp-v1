#!/usr/bin/env python3
"""Ground-truth regression tests for strict-local HD watermark repair.

Each case starts with a clean image, overlays a synthetic watermark, and sends
only a normal client stroke payload through the production HD path.  Ground
truth is used solely to evaluate output; it is never supplied to the service.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np


SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from services import hd_inpaint
from services.stroke_inpaint import build_mask_from_strokes, process_stroke_inpaint


SEED = 20260808


def _encode(image: np.ndarray) -> bytes:
    ok, data = cv2.imencode(".png", image, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return data.tobytes()


def _decode(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("PNG decoding failed")
    return image


def _client_payload(width: int, height: int, left: int, top: int, right: int, bottom: int) -> dict[str, Any]:
    display_width = 430
    display_height = round(display_width * height / float(width))
    # A user normally paints a single horizontal pass across a label.  The
    # brush intentionally gives the model a modest antialiasing margin only.
    brush_ratio = max(0.035, min(0.12, (bottom - top + 10) / float(display_height)))
    center_y = (top + bottom) * 0.5 / float(height)
    return {
        "coordinateSpace": "normalized",
        "originalWidth": width,
        "originalHeight": height,
        "displayWidth": display_width,
        "displayHeight": display_height,
        "strokes": [{
            "type": "brush",
            "brushSizeRatio": brush_ratio,
            "points": [
                {"x": max(0.01, (left - 5) / float(width)), "y": center_y},
                {"x": min(0.99, (right + 5) / float(width)), "y": center_y},
            ],
        }],
    }


def _background(kind: str, width: int, height: int, rng: random.Random) -> np.ndarray:
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    if kind == "dark_city":
        base = np.zeros((height, width, 3), dtype=np.float32)
        base[:, :, 0] = 20 + 18 * yy / height + 8 * np.sin(xx / 41)
        base[:, :, 1] = 14 + 13 * yy / height
        base[:, :, 2] = 10 + 18 * yy / height
        image = np.clip(base, 0, 255).astype(np.uint8)
        for x in range(0, width, 42):
            roof = rng.randrange(height // 7, height * 2 // 3)
            cv2.rectangle(image, (x, roof), (min(width - 1, x + 30), height), (31, 26, 34), -1)
            for light_y in range(roof + 9, height - 5, 19):
                cv2.rectangle(image, (x + 7, light_y), (x + 12, light_y + 4), (110, 145, 172), -1)
        return image
    if kind == "paper":
        image = np.full((height, width, 3), 246, dtype=np.uint8)
        for y in range(42, height, 46):
            cv2.line(image, (26, y), (width - 26, y), (204, 204, 204), 1)
        for x in range(40, width, 170):
            cv2.line(image, (x, 24), (x, height - 25), (219, 219, 219), 1)
        cv2.putText(image, "RECEIPT 2026", (35, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (75, 75, 75), 2, cv2.LINE_AA)
        return image
    if kind == "gradient":
        image = np.zeros((height, width, 3), dtype=np.uint8)
        image[:, :, 0] = np.clip(80 + 110 * xx / width, 0, 255)
        image[:, :, 1] = np.clip(45 + 95 * yy / height, 0, 255)
        image[:, :, 2] = np.clip(130 - 85 * xx / width, 0, 255)
        cv2.circle(image, (width // 3, height // 2), height // 4, (180, 140, 75), -1, cv2.LINE_AA)
        return image
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:] = (176, 162, 148)
    for x in range(-height, width, 26):
        cv2.line(image, (x, 0), (x + height, height), (195, 178, 156), 2, cv2.LINE_AA)
        cv2.line(image, (x + 9, 0), (x - height + 9, height), (151, 138, 126), 1, cv2.LINE_AA)
    return image


def _overlay(clean: np.ndarray, color: tuple[int, int, int], alpha: float, x: int, y: int, text: str) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]:
    marked = clean.copy()
    layer = clean.copy()
    scale = 0.82
    thickness = 2
    (text_width, text_height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    left = max(8, min(clean.shape[1] - text_width - 8, x))
    top = max(text_height + 8, min(clean.shape[0] - baseline - 8, y))
    cv2.putText(layer, text, (left, top), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)
    cv2.addWeighted(layer, alpha, marked, 1.0 - alpha, 0, marked)
    target = np.zeros(clean.shape[:2], dtype=np.uint8)
    cv2.putText(target, text, (left, top), cv2.FONT_HERSHEY_SIMPLEX, scale, 255, thickness + 3, cv2.LINE_AA)
    return marked, target, (left, top - text_height - baseline - 5, left + text_width, top + baseline + 5)


def _masked_mae(left: np.ndarray, right: np.ndarray, mask: np.ndarray) -> float:
    selected = mask > 0
    if not np.any(selected):
        return 0.0
    return float(np.mean(np.abs(left.astype(np.float32)[selected] - right.astype(np.float32)[selected])))


def _save(path: Path, image: np.ndarray) -> None:
    path.write_bytes(_encode(image))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/watermark-hd-residual/ground-truth-suite")
    parser.add_argument("--cases", type=int, default=12)
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    backgrounds = ("dark_city", "paper", "gradient", "texture")
    colors = ((244, 244, 244), (208, 208, 208), (65, 65, 220), (220, 120, 45))
    positions = ((0.67, 0.84), (0.08, 0.84), (0.67, 0.18), (0.31, 0.52))
    cases = []

    for index in range(args.cases):
        width = (920, 1024, 760)[index % 3]
        height = (580, 640, 920)[index % 3]
        clean = _background(backgrounds[index % len(backgrounds)], width, height, rng)
        position = positions[index % len(positions)]
        marked, target, rect = _overlay(
            clean,
            colors[index % len(colors)],
            (0.48, 0.62, 0.72)[index % 3],
            int(width * position[0]),
            int(height * position[1]),
            "@WATERMARK 2026",
        )
        payload = _client_payload(width, height, *rect)
        user_mask, _ = build_mask_from_strokes(payload, width, height)
        allowed_mask, allowed_debug = hd_inpaint.derive_allowed_mask(
            marked,
            user_mask,
            max_dilation_px=6,
        )
        started = time.perf_counter()
        result = process_stroke_inpaint(
            _encode(marked),
            json.dumps(payload, separators=(",", ":")),
            quality="hd",
            strength="medium",
            preserve_detail=True,
            request_id=f"ground-truth-{index:02d}",
            smart_expand=False,
            mask_dilation_px=6,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        repaired = _decode(result["bytes"])
        debug = result.get("debug") or {}
        before_error = _masked_mae(marked, clean, target)
        after_error = _masked_mae(repaired, clean, target)
        outside = allowed_mask == 0
        outside_changed = int(np.count_nonzero(np.any(marked[outside] != repaired[outside], axis=1)))
        checks = {
            "realLama": result.get("engine") == "lama" and result.get("fallbackUsed") is False,
            "sizePreserved": repaired.shape == marked.shape,
            "outsideAllowedMaskExact": outside_changed == 0 and int(debug.get("outsideAllowedMaskChangedPixels") or 0) == 0,
            "watermarkErrorReduced": after_error <= before_error * 0.58,
            "boundedLamaCalls": 1 <= int(debug.get("lamaCallCount") or 0) <= 2,
        }
        case_dir = output / f"case-{index:02d}"
        case_dir.mkdir(exist_ok=True)
        _save(case_dir / "clean.png", clean)
        _save(case_dir / "watermarked.png", marked)
        _save(case_dir / "user-mask.png", user_mask)
        _save(case_dir / "target-mask.png", target)
        _save(case_dir / "repaired.png", repaired)
        row = {
            "case": index,
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "background": backgrounds[index % len(backgrounds)],
            "sourceSize": f"{width}x{height}",
            "clientMs": elapsed_ms,
            "beforeTargetMae": round(before_error, 4),
            "afterTargetMae": round(after_error, 4),
            "improvement": round(1.0 - after_error / max(before_error, 0.0001), 4),
            "outsideAllowedMaskChangedPixels": outside_changed,
            "allowedMaskDilationPx": allowed_debug.get("allowedDilationPx"),
            "debug": {key: debug.get(key) for key in ("lamaCallCount", "postCleanup", "tiledPatternCleanupEligible", "outsideAllowedMaskChangedPixels", "secondPassTriggered", "finalResidualScore")},
        }
        (case_dir / "report.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        cases.append(row)
        print(json.dumps({"case": index, "status": row["status"], "improvement": row["improvement"]}, ensure_ascii=False))

    report = {
        "status": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL",
        "seed": SEED,
        "caseCount": len(cases),
        "passed": sum(case["status"] == "PASS" for case in cases),
        "cases": cases,
    }
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(output / "report.json")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
