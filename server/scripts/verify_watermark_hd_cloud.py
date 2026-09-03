"""Run the scoped watermark quick/HD production regression matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests


def _encode_png(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("fixture encoding failed")
    return encoded.tobytes()


def _invoice_fixture(width: int, height: int, label: str) -> np.ndarray:
    image = np.full((height, width, 3), 248, dtype=np.uint8)
    margin = max(18, width // 40)
    top = max(45, height // 12)
    bottom = height - max(30, height // 14)
    line_color = (118, 118, 118)
    for y in np.linspace(top, bottom, 10, dtype=int):
        cv2.line(image, (margin, int(y)), (width - margin, int(y)), line_color, max(1, width // 1800))
    for x in np.linspace(margin, width - margin, 6, dtype=int):
        cv2.line(image, (int(x), top), (int(x), bottom), line_color, max(1, width // 1800))
    scale = max(0.55, min(2.0, width / 1600.0))
    cv2.putText(image, f"INVOICE {label}", (margin, max(32, top - 16)), cv2.FONT_HERSHEY_SIMPLEX, scale, (35, 35, 35), max(1, int(scale * 2)))
    cv2.putText(image, "TEXT TABLE 2026-08-07", (margin * 2, top + max(30, height // 14)), cv2.FONT_HERSHEY_SIMPLEX, scale * 0.65, (65, 65, 65), max(1, int(scale)))
    stamp_center = (int(width * 0.78), int(height * 0.76))
    cv2.circle(image, stamp_center, max(18, width // 28), (70, 70, 205), max(2, width // 1000))
    cv2.putText(image, "STAMP", (stamp_center[0] - max(28, width // 45), stamp_center[1] + 5), cv2.FONT_HERSHEY_SIMPLEX, scale * 0.55, (70, 70, 205), max(1, int(scale)))
    qr_x, qr_y = int(width * 0.82), int(height * 0.13)
    cell = max(3, width // 260)
    for row in range(9):
        for col in range(9):
            if ((row * 3 + col * 5 + row * col) % 7) < 3:
                cv2.rectangle(image, (qr_x + col * cell, qr_y + row * cell), (qr_x + (col + 1) * cell - 1, qr_y + (row + 1) * cell - 1), (15, 15, 15), -1)
    return image


def _stroke_payload(rects: list[tuple[float, float, float, float]]) -> dict[str, Any]:
    return {
        "coordinateSpace": "normalized",
        "strokes": [
            {"type": "maskRect", "x": x, "y": y, "w": width, "h": height}
            for x, y, width, height in rects
        ],
    }


def _brush_payload(lines: list[tuple[float, float, float, float, float]]) -> dict[str, Any]:
    return {
        "coordinateSpace": "normalized",
        "strokes": [
            {
                "type": "brush",
                "brushSizeRatio": brush_size_ratio,
                "points": [{"x": x1, "y": y1}, {"x": x2, "y": y2}],
            }
            for x1, y1, x2, y2, brush_size_ratio in lines
        ],
    }


def _overlay_watermark(image: np.ndarray, lines: list[tuple[float, float, float, float, float]]) -> np.ndarray:
    overlay = image.copy()
    height, width = image.shape[:2]
    for x1, y1, x2, y2, brush_size_ratio in lines:
        start = (int(round(x1 * width)), int(round(y1 * height)))
        end = (int(round(x2 * width)), int(round(y2 * height)))
        thickness = max(2, int(round(brush_size_ratio * width * 0.55)))
        cv2.line(overlay, start, end, (60, 60, 215), thickness, cv2.LINE_AA)
    return cv2.addWeighted(overlay, 0.45, image, 0.55, 0)


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile / 100.0 * len(ordered)) - 1))
    return round(ordered[index], 1)


def _decode(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("result image decode failed")
    return image


def _outside_changed(source: np.ndarray, result: np.ndarray, roi_boxes: list[dict[str, int]]) -> int:
    if source.shape != result.shape:
        return -1
    outside = np.ones(source.shape[:2], dtype=bool)
    for box in roi_boxes:
        x = max(0, int(box["x"]))
        y = max(0, int(box["y"]))
        x2 = min(source.shape[1], x + int(box["width"]))
        y2 = min(source.shape[0], y + int(box["height"]))
        outside[y:y2, x:x2] = False
    changed = np.any(source != result, axis=2) & outside
    return int(np.count_nonzero(changed))


def _absolute_url(base_url: str, value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return base_url.rstrip("/") + "/" + value.lstrip("/")


def _request(
    session: requests.Session,
    base_url: str,
    source_bytes: bytes,
    width: int,
    height: int,
    strokes: dict[str, Any],
    quality: str,
    operation: str,
) -> tuple[dict[str, Any], bytes, float, bool]:
    request_id = f"cloud-matrix-{operation}-{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    response = session.post(
        base_url.rstrip("/") + "/api/watermark/remove-v2",
        files={"image": ("fixture.png", source_bytes, "image/png")},
        data={
            "strokesJson": json.dumps(strokes, separators=(",", ":")),
            "originalWidth": str(width),
            "originalHeight": str(height),
            "displayWidth": str(width),
            "displayHeight": str(height),
            "quality": quality,
            "strength": "medium",
            "preserveDetail": "true",
            "requestId": request_id,
        },
        timeout=180,
    )
    client_ms = round((time.perf_counter() - started) * 1000, 1)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(str(payload))
    result_url = _absolute_url(base_url, payload["resultUrl"])
    first = session.get(result_url, timeout=60)
    second = session.get(result_url, timeout=60)
    first.raise_for_status()
    second.raise_for_status()
    preview_download_consistent = hashlib.sha256(first.content).hexdigest() == hashlib.sha256(second.content).hexdigest() == payload.get("fileHash")
    return payload, first.content, client_ms, preview_download_consistent


def _hd_checks(source_bytes: bytes, payload: dict[str, Any], result_bytes: bytes, preview_ok: bool, reference_bytes: bytes | None = None) -> dict[str, Any]:
    source = _decode(source_bytes)
    result = _decode(result_bytes)
    debug = payload.get("debug") or {}
    outside = _outside_changed(source, result, debug.get("eachRoiBox") or [])
    checks = {
        "actualEngineLama": debug.get("actualEngine") == "lama" and payload.get("engine") == "lama",
        "fallbackDisabled": payload.get("fallbackUsed") is False and debug.get("fallbackUsed") is False,
        "modelWarm": debug.get("modelWarm") is True and int(debug.get("modelLoadMs") or 0) == 0,
        "callCountBounded": 1 <= int(debug.get("lamaCallCount") or 0) <= 2,
        "outputSizePreserved": source.shape == result.shape,
        "outsideRoiExact": outside == 0 and int(debug.get("outsideRoiChangedPixels") or 0) == 0,
        "previewDownloadConsistent": preview_ok,
    }
    quality = {}
    if reference_bytes is not None:
        reference = _decode(reference_bytes)
        source_mae = float(np.mean(np.abs(source.astype(np.int16) - reference.astype(np.int16))))
        result_mae = float(np.mean(np.abs(result.astype(np.int16) - reference.astype(np.int16))))
        quality = {
            "sourceReferenceMae": round(source_mae, 4),
            "resultReferenceMae": round(result_mae, 4),
            "relativeMae": round(result_mae / max(0.0001, source_mae), 4),
        }
        checks["qualityNotRegressed"] = result_mae <= source_mae
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "quality": quality,
        "independentOutsideRoiChangedPixels": outside,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://tupzjianzhao.chat")
    parser.add_argument("--actual-invoice", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    actual_bytes = Path(args.actual_invoice).read_bytes()
    actual_image = _decode(actual_bytes)
    small_lines = [(0.38, 0.455, 0.54, 0.455, 0.022)]
    full_hd_lines = [(0.34, 0.49, 0.48, 0.49, 0.018), (0.49, 0.515, 0.62, 0.515, 0.018)]
    scan_lines = [(0.66, 0.735, 0.84, 0.735, 0.026)]
    four_k_lines = [
        (0.31, 0.40, 0.73, 0.40, 0.020),
        (0.31, 0.45, 0.73, 0.45, 0.020),
        (0.31, 0.50, 0.73, 0.50, 0.020),
    ]
    fixtures = [
        {
            "name": "actual-slow-invoice-far-rois",
            "class": "small",
            "bytes": actual_bytes,
            "size": (actual_image.shape[1], actual_image.shape[0]),
            "strokes": _stroke_payload([(0.06, 0.10, 0.07, 0.06), (0.80, 0.77, 0.08, 0.07)]),
            "coverage": ["actual invoice", "far ROIs", "text", "table"],
        },
        {
            "name": "small-single-text",
            "class": "small",
            "size": (640, 480),
            "lines": small_lines,
            "strokes": _brush_payload(small_lines),
            "coverage": ["small image", "small mask", "single ROI", "text"],
        },
        {
            "name": "full-hd-near-rois",
            "class": "medium",
            "size": (1920, 1080),
            "lines": full_hd_lines,
            "strokes": _brush_payload(full_hd_lines),
            "coverage": ["1920x1080", "medium mask", "near ROIs", "table"],
        },
        {
            "name": "scan-stamp-complex",
            "class": "medium",
            "size": (3200, 2200),
            "lines": scan_lines,
            "strokes": _brush_payload(scan_lines),
            "coverage": ["3000px scan", "stamp", "complex background", "single ROI"],
        },
        {
            "name": "four-k-large-qr-nearby",
            "class": "large",
            "size": (4096, 3072),
            "lines": four_k_lines,
            "strokes": _brush_payload(four_k_lines),
            "coverage": ["4096x3072", "large mask", "QR nearby", "large ROI"],
        },
    ]
    for fixture in fixtures:
        if "bytes" not in fixture:
            width, height = fixture["size"]
            clean = _invoice_fixture(width, height, fixture["name"])
            fixture["reference"] = _encode_png(clean)
            fixture["bytes"] = _encode_png(_overlay_watermark(clean, fixture["lines"]))

    session = requests.Session()
    rows: list[dict[str, Any]] = []
    for fixture in fixtures:
        width, height = fixture["size"]
        row: dict[str, Any] = {
            "name": fixture["name"],
            "class": fixture["class"],
            "size": f"{width}x{height}",
            "coverage": fixture["coverage"],
            "operations": {},
        }
        try:
            quick, _, quick_ms, quick_preview = _request(session, args.base_url, fixture["bytes"], width, height, fixture["strokes"], "quick", fixture["name"] + "-quick")
            row["operations"]["quick"] = {
                "status": "PASS" if quick.get("success") and quick_preview else "FAIL",
                "clientMs": quick_ms,
                "engine": quick.get("engine"),
                "previewDownloadConsistent": quick_preview,
            }
            hd, hd_bytes, hd_ms, hd_preview = _request(session, args.base_url, fixture["bytes"], width, height, fixture["strokes"], "hd", fixture["name"] + "-hd")
            hd_result = _hd_checks(fixture["bytes"], hd, hd_bytes, hd_preview, fixture.get("reference"))
            hd_result.update({"clientMs": hd_ms, "debug": hd.get("debug") or {}})
            row["operations"]["hd"] = hd_result

            retry, retry_bytes, retry_ms, retry_preview = _request(session, args.base_url, fixture["bytes"], width, height, fixture["strokes"], "hd", fixture["name"] + "-retry")
            retry_result = _hd_checks(fixture["bytes"], retry, retry_bytes, retry_preview, fixture.get("reference"))
            retry_result.update({"clientMs": retry_ms, "sameHashAsInitial": retry.get("fileHash") == hd.get("fileHash"), "debug": retry.get("debug") or {}})
            row["operations"]["hdRetry"] = retry_result

            continue_strokes = _stroke_payload([(0.08, 0.82, 0.10, 0.06)])
            continued, continue_bytes, continue_ms, continue_preview = _request(session, args.base_url, hd_bytes, width, height, continue_strokes, "hd", fixture["name"] + "-continue")
            continue_result = _hd_checks(hd_bytes, continued, continue_bytes, continue_preview)
            continue_result.update({"clientMs": continue_ms, "debug": continued.get("debug") or {}})
            row["operations"]["continueLocalRepair"] = continue_result
            row["status"] = "PASS" if all(item["status"] == "PASS" for item in row["operations"].values()) else "FAIL"
        except Exception as exc:
            row["status"] = "FAIL"
            row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
        print(json.dumps({"name": row["name"], "status": row["status"]}, ensure_ascii=True), flush=True)

    hd_rows = [(row["class"], row.get("operations", {}).get("hd", {})) for row in rows]
    performance = {}
    for roi_class in ("small", "medium", "large"):
        values = [float(item.get("clientMs") or 0) for current_class, item in hd_rows if current_class == roi_class and item.get("status") == "PASS"]
        performance[roi_class] = {
            "runs": len(values),
            "p50Ms": round(statistics.median(values), 1) if values else 0,
            "p95ObservedMs": _percentile(values, 95),
            "maxMs": round(max(values), 1) if values else 0,
        }
    max_calls = max(
        [int(operation.get("debug", {}).get("lamaCallCount") or 0) for row in rows for operation in row.get("operations", {}).values()]
        or [0]
    )
    report = {
        "status": "PASS" if all(row["status"] == "PASS" for row in rows) else "FAIL",
        "baseUrl": args.base_url,
        "sampleCount": len(rows),
        "performance": performance,
        "maxLamaCallCount": max_calls,
        "rows": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "performance": performance, "maxLamaCallCount": max_calls}, ensure_ascii=True, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
