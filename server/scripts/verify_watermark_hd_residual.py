#!/usr/bin/env python3
"""Verify HD colored-watermark expansion and residual cleanup."""
from __future__ import annotations

import argparse
import hashlib
import json
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


def _encode_png(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return encoded.tobytes()


def _decode(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("Image decoding failed")
    return image


def _hue_distance(hue: np.ndarray, center: int) -> np.ndarray:
    delta = np.abs(hue.astype(np.int16) - int(center))
    return np.minimum(delta, 180 - delta)


def _payload(width: int, height: int, x1: float, y1: float, x2: float, y2: float, brush: float) -> dict[str, Any]:
    return {
        "coordinateSpace": "normalized",
        "originalWidth": width,
        "originalHeight": height,
        "displayWidth": 430,
        "displayHeight": round(430 * height / float(width)),
        "strokes": [{
            "type": "brush",
            "brushSizeRatio": brush,
            "points": [{"x": x1, "y": y1}, {"x": x2, "y": y2}],
        }],
    }


def _independent_target(image: np.ndarray, user_mask: np.ndarray) -> tuple[np.ndarray, int]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    selected = user_mask > 0
    seed = selected & (saturation >= 50) & (value >= 35)
    if int(np.count_nonzero(seed)) < 32:
        return np.zeros_like(user_mask), -1
    histogram = np.bincount(hue[seed], minlength=180).astype(np.float32)
    smoothed = sum(np.roll(histogram, offset) for offset in range(-2, 3))
    dominant_hue = int(np.argmax(smoothed))
    distance = _hue_distance(hue, dominant_hue)

    x, y, width, height = cv2.boundingRect(cv2.findNonZero(user_mask))
    area = int(cv2.countNonZero(user_mask))
    brush_estimate = max(2.0, min(float(min(width, height)), area / float(max(width, height))))
    padding = min(256, max(32, int(round(max(width, height) * 0.60)), int(round(brush_estimate * 2.5))))
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(image.shape[1], x + width + padding)
    y2 = min(image.shape[0], y + height + padding)
    candidate = np.zeros_like(user_mask)
    candidate[y1:y2, x1:x2] = np.where(
        (distance[y1:y2, x1:x2] <= 10)
        & (saturation[y1:y2, x1:x2] >= 20)
        & (value[y1:y2, x1:x2] >= 35),
        255,
        0,
    ).astype(np.uint8)

    bridge_size = int(round(max(brush_estimate * 0.28, min(image.shape[:2]) * 0.022)))
    bridge_size = max(5, min(31, bridge_size))
    if bridge_size % 2 == 0:
        bridge_size += 1
    bridged = cv2.dilate(
        candidate,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (bridge_size, bridge_size)),
        iterations=1,
    )
    count, labels, _stats, _centroids = cv2.connectedComponentsWithStats(bridged, connectivity=8)
    labels_to_keep = [
        label
        for label in range(1, count)
        if np.any((labels == label) & selected)
    ]
    target = np.where(np.isin(labels, labels_to_keep) & (candidate > 0), 255, 0).astype(np.uint8)
    return target, dominant_hue


def _outside_roi_changed(source: np.ndarray, result: np.ndarray, boxes: list[dict[str, int]]) -> int:
    outside = np.ones(source.shape[:2], dtype=bool)
    for box in boxes:
        x1 = max(0, int(box["x"]))
        y1 = max(0, int(box["y"]))
        x2 = min(source.shape[1], x1 + int(box["width"]))
        y2 = min(source.shape[0], y1 + int(box["height"]))
        outside[y1:y2, x1:x2] = False
    return int(np.count_nonzero(np.any(source != result, axis=2) & outside))


def _line_retention(source: np.ndarray, result: np.ndarray, target: np.ndarray) -> dict[str, Any]:
    if cv2.countNonZero(target) <= 0:
        return {"row": -1, "ratio": 1.0}
    _x, y, _width, height = cv2.boundingRect(cv2.findNonZero(target))
    source_gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
    result_gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    left = int(round(source.shape[1] * 0.05))
    right = int(round(source.shape[1] * 0.95))
    candidates = []
    for row in range(max(0, y), min(source.shape[0], y + height)):
        dark_pixels = int(np.count_nonzero(source_gray[row, left:right] < 180))
        if dark_pixels >= int((right - left) * 0.35):
            candidates.append((dark_pixels, row))
    if not candidates:
        return {"row": -1, "ratio": 1.0}
    _dark_pixels, row = max(candidates)
    source_dark = int(np.count_nonzero(source_gray[row, left:right] < 180))
    result_dark = int(np.count_nonzero(result_gray[row, left:right] < 180))
    return {
        "row": row,
        "sourceDarkPixels": source_dark,
        "resultDarkPixels": result_dark,
        "ratio": round(result_dark / float(max(1, source_dark)), 6),
    }


def _run_actual_case(
    name: str,
    source_bytes: bytes,
    source: np.ndarray,
    payload: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    user_mask, _mask_debug = build_mask_from_strokes(payload, source.shape[1], source.shape[0])
    target, dominant_hue = _independent_target(source, user_mask)
    started = time.perf_counter()
    result = process_stroke_inpaint(
        source_bytes,
        json.dumps(payload, separators=(",", ":")),
        quality="hd",
        strength="medium",
        preserve_detail=True,
        request_id=f"residual-{name}",
    )
    client_ms = round((time.perf_counter() - started) * 1000, 1)
    output = _decode(result["bytes"])
    debug = result.get("debug") or {}

    output_path = output_dir / f"{name}.png"
    output_path.write_bytes(result["bytes"])
    hsv = cv2.cvtColor(output, cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    residual = (
        (target > 0)
        & (_hue_distance(hue, dominant_hue) <= 14)
        & (saturation >= 10)
        & (value >= 30)
    )
    target_pixels = int(cv2.countNonZero(target))
    residual_pixels = int(np.count_nonzero(residual))
    residual_ratio = round(residual_pixels / float(max(1, target_pixels)), 6)
    luminance_residual = hd_inpaint._build_thin_watermark_mask(output, target)
    luminance_residual_pixels = int(cv2.countNonZero(luminance_residual))
    luminance_residual_ratio = round(luminance_residual_pixels / float(max(1, target_pixels)), 6)
    outside_changed = _outside_roi_changed(source, output, debug.get("eachRoiBox") or [])
    line = _line_retention(source, output, target)
    checks = {
        "realLama": result.get("engine") == "lama" and result.get("fallbackUsed") is False,
        "outputSizePreserved": output.shape == source.shape,
        "chromaticExpansionApplied": debug.get("chromaticMaskExpanded") is True,
        "chromaticRetryApplied": debug.get("chromaticRetryApplied") is True,
        "residualColorBelowFivePercent": residual_ratio <= 0.05,
        "luminanceResidualBelowEightPercent": luminance_residual_ratio <= 0.08,
        "longDocumentLinePreserved": float(line["ratio"]) >= 0.90,
        "outsideRoiExact": outside_changed == 0 and int(debug.get("outsideRoiChangedPixels") or 0) == 0,
        "lamaCallsBounded": 1 <= int(debug.get("lamaCallCount") or 0) <= 2,
        "underTenSeconds": client_ms <= 10000,
    }
    return {
        "name": name,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "clientMs": client_ms,
        "targetPixels": target_pixels,
        "residualColorPixels": residual_pixels,
        "residualColorRatio": residual_ratio,
        "luminanceResidualPixels": luminance_residual_pixels,
        "luminanceResidualRatio": luminance_residual_ratio,
        "lineRetention": line,
        "outsideRoiChangedPixels": outside_changed,
        "outputSha256": hashlib.sha256(result["bytes"]).hexdigest(),
        "debug": {
            key: debug.get(key)
            for key in (
                "chromaticExpansionPixels", "chromaticIntentPixels", "chromaticComponentCount",
                "chromaticResidualPixels", "chromaticResidualMaskPixels", "chromaticRetryApplied",
                "chromaticLuminanceCleanupApplied", "chromaticLuminanceCleanupPixels",
                "mergedRoiCount", "eachRoiBox", "lamaCallCount", "retryReason", "totalDurationMs",
            )
        },
    }


def _synthetic_blue_case(output_dir: Path) -> dict[str, Any]:
    width, height = 1000, 700
    image = np.full((height, width, 3), 248, dtype=np.uint8)
    cv2.line(image, (40, 520), (960, 520), (55, 55, 55), 3, cv2.LINE_AA)
    cv2.putText(image, "INVOICE 2026", (80, 110), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (40, 40, 40), 2, cv2.LINE_AA)
    blue_target = np.zeros((height, width), dtype=np.uint8)
    cv2.circle(blue_target, (780, 510), 112, 255, 7, cv2.LINE_AA)
    cv2.circle(blue_target, (780, 510), 96, 255, 4, cv2.LINE_AA)
    cv2.putText(blue_target, "BLUE", (716, 492), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 255, 3, cv2.LINE_AA)
    cv2.putText(blue_target, "2026", (735, 548), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 255, 3, cv2.LINE_AA)
    image[blue_target > 0] = (220, 75, 35)
    unrelated_red = np.zeros((height, width), dtype=np.uint8)
    cv2.circle(unrelated_red, (190, 180), 58, 255, 5, cv2.LINE_AA)
    image[unrelated_red > 0] = (35, 35, 220)

    payload = _payload(width, height, 0.70, 0.73, 0.87, 0.73, 0.045)
    user_mask, _debug = build_mask_from_strokes(payload, width, height)
    processing_mask, intent, expansion_debug = hd_inpaint._expand_chromatic_watermark_mask(image, user_mask)
    blue_coverage = int(cv2.countNonZero(cv2.bitwise_and(intent, blue_target)))
    blue_pixels = int(cv2.countNonZero(blue_target))
    unrelated_overlap = int(cv2.countNonZero(cv2.bitwise_and(intent, unrelated_red)))
    coverage_ratio = round(blue_coverage / float(max(1, blue_pixels)), 6)
    checks = {
        "blueStampExpanded": expansion_debug.get("chromaticMaskExpanded") is True,
        "blueCoverageAtLeastEightyPercent": coverage_ratio >= 0.80,
        "unrelatedRedStampUntouched": unrelated_overlap == 0,
        "processingMaskContainsUserMask": cv2.countNonZero(cv2.bitwise_and(user_mask, cv2.bitwise_not(processing_mask))) == 0,
    }
    overlay = image.copy()
    overlay[intent > 0] = (0, 255, 0)
    overlay = cv2.addWeighted(image, 0.65, overlay, 0.35, 0)
    (output_dir / "synthetic-blue-expansion.png").write_bytes(_encode_png(overlay))
    return {
        "name": "synthetic-blue-generalization",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "blueTargetPixels": blue_pixels,
        "blueCoveredPixels": blue_coverage,
        "blueCoverageRatio": coverage_ratio,
        "unrelatedRedOverlapPixels": unrelated_overlap,
        "debug": expansion_debug,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", default="reports/watermark-hd-residual/verification")
    args = parser.parse_args()

    source_path = Path(args.source)
    source_bytes = source_path.read_bytes()
    source = _decode(source_bytes)
    height, width = source.shape[:2]
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = [
        ("center-horizontal", _payload(width, height, 0.725, 0.855, 0.925, 0.855, 0.050)),
        ("short-center", _payload(width, height, 0.765, 0.855, 0.875, 0.855, 0.040)),
        ("lower-arc", _payload(width, height, 0.735, 0.925, 0.905, 0.925, 0.038)),
    ]
    actual = []
    for name, payload in cases:
        row = _run_actual_case(name, source_bytes, source, payload, output_dir)
        actual.append(row)
        print(json.dumps({"name": name, "status": row["status"], "clientMs": row["clientMs"]}))
    synthetic = _synthetic_blue_case(output_dir)
    status = "PASS" if all(row["status"] == "PASS" for row in actual) and synthetic["status"] == "PASS" else "FAIL"
    report = {
        "status": status,
        "source": str(source_path),
        "sourceSize": f"{width}x{height}",
        "actualCases": actual,
        "generalization": synthetic,
    }
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# HD Watermark Residual Verification",
        "",
        f"- Status: {status}",
        f"- Source: `{source_path}`",
        f"- Size: `{width}x{height}`",
        "",
    ]
    for row in actual:
        lines.append(
            f"- {row['name']}: {row['status']}; {row['clientMs']} ms; "
            f"residual={row['residualColorRatio']:.4f}; line={row['lineRetention']['ratio']:.4f}; "
            f"luminance={row['luminanceResidualRatio']:.4f}; "
            f"calls={row['debug']['lamaCallCount']}"
        )
    lines.append(
        f"- synthetic-blue-generalization: {synthetic['status']}; "
        f"coverage={synthetic['blueCoverageRatio']:.4f}; unrelated-red-overlap={synthetic['unrelatedRedOverlapPixels']}"
    )
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "report": str(output_dir / "report.json")}))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
