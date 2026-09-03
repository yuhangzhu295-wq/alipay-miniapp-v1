#!/usr/bin/env python3
"""Exercise HD inpainting with six strict-local, real-LaMa cases.

This is a regression suite, not part of the production decision path.  Every
case runs the same normalized-stroke API as the client and stores the stages
needed for manual review.  The production algorithm receives no case name,
source path, target location, or watermark-specific classification.
"""
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


def _decode(data: bytes, flags: int = cv2.IMREAD_COLOR) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), flags)
    if image is None:
        raise RuntimeError("Unable to decode image")
    return image


def _encode_png(image: np.ndarray) -> bytes:
    ok, data = cv2.imencode(".png", image, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])
    if not ok:
        raise RuntimeError("Unable to encode PNG")
    return data.tobytes()


def _save(path: Path, image: np.ndarray) -> None:
    path.write_bytes(_encode_png(image))


def _payload(width: int, height: int, points: list[tuple[float, float]], brush: float) -> dict[str, Any]:
    return {
        "coordinateSpace": "normalized",
        "originalWidth": width,
        "originalHeight": height,
        "displayWidth": 430,
        "displayHeight": round(430 * height / float(width)),
        "strokes": [{
            "type": "brush",
            "brushSizeRatio": brush,
            "points": [{"x": x, "y": y} for x, y in points],
        }],
    }


def _resize_to_canvas(image: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    height, width = shape
    if image.shape[:2] == shape:
        return image
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_NEAREST)


def _roi_stage_to_canvas(
    source: np.ndarray,
    stage: np.ndarray,
    stage_mask: np.ndarray,
    debug: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    """Return an engine ROI stage on the source canvas using production rules."""
    detail = (debug.get("roiDetails") or [{}])[0]
    box = detail.get("roiBox") or (debug.get("eachRoiBox") or [{}])[0]
    borders = detail.get("roiReflectBorder") or {}
    x, y = int(box.get("x") or 0), int(box.get("y") or 0)
    width, height = int(box.get("width") or 0), int(box.get("height") or 0)
    top, left = int(borders.get("top") or 0), int(borders.get("left") or 0)
    if width <= 0 or height <= 0:
        return source.copy(), np.zeros(source.shape[:2], dtype=np.uint8)
    stage_roi = stage[top:top + height, left:left + width]
    mask_roi = stage_mask[top:top + height, left:left + width]
    if stage_roi.shape[:2] != (height, width):
        stage_roi = cv2.resize(stage_roi, (width, height), interpolation=cv2.INTER_NEAREST)
    if mask_roi.shape[:2] != (height, width):
        mask_roi = cv2.resize(mask_roi, (width, height), interpolation=cv2.INTER_NEAREST)
    canvas = source.copy()
    region = canvas[y:y + height, x:x + width]
    region[mask_roi > 0] = stage_roi[mask_roi > 0]
    canvas[y:y + height, x:x + width] = region
    canvas_mask = np.zeros(source.shape[:2], dtype=np.uint8)
    canvas_mask[y:y + height, x:x + width] = mask_roi
    return canvas, canvas_mask


def _capture_stages(source_bytes: bytes, payload: dict[str, Any], case_dir: Path, request_id: str) -> dict[str, Any]:
    source = _decode(source_bytes)
    height, width = source.shape[:2]
    user_mask, mask_debug = build_mask_from_strokes(payload, width, height)
    allowed_mask, allowed_debug = hd_inpaint.derive_allowed_mask(source, user_mask, max_dilation_px=6)
    captures: dict[str, Any] = {"first": None, "first_mask": None, "residual": None}
    original_analysis = hd_inpaint._strict_local_residual_analysis

    def capture_analysis(original: np.ndarray, candidate: np.ndarray, mask: np.ndarray):
        residual, metrics = original_analysis(original, candidate, mask)
        if captures["first"] is None:
            captures["first"] = candidate.copy()
            captures["first_mask"] = mask.copy()
            captures["residual"] = residual.copy()
        return residual, metrics

    hd_inpaint._strict_local_residual_analysis = capture_analysis
    started = time.perf_counter()
    try:
        result = process_stroke_inpaint(
            source_bytes,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            quality="hd",
            strength="medium",
            preserve_detail=True,
            request_id=request_id,
            smart_expand=False,
            mask_dilation_px=6,
        )
    finally:
        hd_inpaint._strict_local_residual_analysis = original_analysis
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    final = _decode(result["bytes"])
    debug = result.get("debug") or {}
    first_engine = captures["first"] if captures["first"] is not None else final
    first_mask = captures["first_mask"] if captures["first_mask"] is not None else allowed_mask
    residual = captures["residual"]
    if residual is None:
        residual, _metrics = original_analysis(source, first_engine, first_mask)
    first, _first_stage_mask = _roi_stage_to_canvas(source, first_engine, first_mask, debug)
    _residual_canvas, residual_canvas_mask = _roi_stage_to_canvas(
        np.zeros_like(source),
        np.dstack([residual, residual, residual]),
        residual,
        debug,
    )
    residual_canvas = residual_canvas_mask

    case_dir.mkdir(parents=True, exist_ok=True)
    _save(case_dir / "original.png", source)
    _save(case_dir / "user-mask.png", user_mask)
    _save(case_dir / "allowed-mask.png", allowed_mask)
    _save(case_dir / "first-lama.png", first)
    _save(case_dir / "residual-mask.png", residual_canvas)
    _save(case_dir / "final.png", final)

    final_residual, final_metrics = original_analysis(source, final, allowed_mask)
    outside = allowed_mask == 0
    outside_changed = int(np.count_nonzero(np.any(final[outside] != source[outside], axis=1)))
    checks = {
        "realLama": result.get("engine") == "lama" and result.get("fallbackUsed") is False,
        "sizePreserved": final.shape == source.shape,
        "outsideAllowedExact": outside_changed == 0 and int(debug.get("outsideAllowedMaskChangedPixels") or 0) == 0,
        "residualInsideAllowed": int(final_metrics["residualOutsideAllowedPixels"]) == 0,
        "boundedLamaCalls": 1 <= int(debug.get("lamaCallCount") or 0) <= 2,
        "residualDidNotRegress": float(final_metrics["visualResidualScore"]) <= float(
            original_analysis(source, first, allowed_mask)[1]["visualResidualScore"]
        ) + 0.000001,
        "samePreviewDownloadArtifact": np.array_equal(final, _decode((case_dir / "final.png").read_bytes())),
    }
    if bool(debug.get("secondPassTriggered")):
        checks["retryMeaningfullyImproved"] = float(final_metrics["visualResidualScore"]) <= float(
            original_analysis(source, first, allowed_mask)[1]["visualResidualScore"]
        ) * 0.95
    row = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "sourceSize": f"{width}x{height}",
        "clientMs": elapsed_ms,
        "mask": mask_debug,
        "allowedMaskPixels": int(cv2.countNonZero(allowed_mask)),
        "firstResidual": original_analysis(source, first, allowed_mask)[1],
        "finalResidual": final_metrics,
        "outsideAllowedChangedPixels": outside_changed,
        "outputSha256": hashlib.sha256(result["bytes"]).hexdigest(),
        "debug": {
            key: debug.get(key)
            for key in (
                "engine", "fallbackUsed", "lamaCallCount", "allowedDilationPx",
                "secondPassTriggered", "secondPassAccepted", "secondPassMaskPixels",
                "firstPassResidualScore", "secondResidualScore", "finalResidualScore",
                "selectedPass", "strictResidualCompletionApplied",
                "strictResidualCompletionPixels", "strictResidualCompletionKernel",
                "strictResidualCompletionExpansionPx",
                "outsideAllowedMaskChangedPixels", "residualOutsideAllowedPixels",
            )
        },
    }
    (case_dir / "case-report.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--night", default=r"C:\Users\zyu33\Desktop\95bbc432fea8e38717d8b9db471f08bd.jpg")
    parser.add_argument("--document", default=r"C:\Users\zyu33\Desktop\9987bf3fcefe724f692e76d2d783dfa9.jpg")
    parser.add_argument("--photo", default=r"C:\Users\zyu33\Desktop\3df344cba6fc0f060f39009777200e96.jpg")
    parser.add_argument("--output", default="reports/watermark-hd-residual/strict-local-suite")
    args = parser.parse_args()

    # These are deliberately client-style strokes for a small localized region.
    # They only define regression inputs; production code does not consume them.
    definitions = [
        ("night", Path(args.night), [
            ("lower-right-full", [(0.842, 0.915), (0.978, 0.915), (0.978, 0.968), (0.842, 0.968)], 0.095),
            ("lower-right-small", [(0.875, 0.935), (0.965, 0.935)], 0.050),
        ]),
        ("document", Path(args.document), [
            ("bottom-right-stamp", [(0.760, 0.800), (0.915, 0.875)], 0.070),
            ("top-center-stamp", [(0.435, 0.075), (0.565, 0.135)], 0.055),
        ]),
        ("photo", Path(args.photo), [
            ("bottom-right-watermark", [(0.770, 0.870), (0.960, 0.870)], 0.050),
            ("bottom-right-label", [(0.805, 0.925), (0.960, 0.925)], 0.040),
        ]),
    ]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for group, source_path, cases in definitions:
        if not source_path.is_file():
            raise FileNotFoundError(f"Missing source image: {source_path}")
        source_bytes = source_path.read_bytes()
        source = _decode(source_bytes)
        for name, points, brush in cases:
            payload = _payload(source.shape[1], source.shape[0], points, brush)
            case_name = f"{group}-{name}"
            row = _capture_stages(source_bytes, payload, output / case_name, case_name)
            row.update({"case": case_name, "group": group, "source": str(source_path)})
            rows.append(row)
            print(json.dumps({"case": case_name, "status": row["status"], "calls": row["debug"].get("lamaCallCount")}, ensure_ascii=False))

    difficult_retry = any(row["debug"].get("secondPassTriggered") for row in rows)
    simple_single_pass = any(not row["debug"].get("secondPassTriggered") for row in rows)
    status = "PASS" if all(row["status"] == "PASS" for row in rows) and difficult_retry and simple_single_pass else "FAIL"
    report = {
        "status": status,
        "caseCount": len(rows),
        "allRealLama": all(row["checks"]["realLama"] for row in rows),
        "allOutsideAllowedExact": all(row["checks"]["outsideAllowedExact"] for row in rows),
        "difficultRetryObserved": difficult_retry,
        "simpleSinglePassObserved": simple_single_pass,
        "cases": rows,
    }
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# HD Strict-Local Residual Suite", "", f"- Status: {status}", f"- Cases: {len(rows)}/6", f"- Difficult retry observed: {difficult_retry}", f"- Simple single-pass observed: {simple_single_pass}", ""]
    for row in rows:
        lines.append(
            f"- {row['case']}: {row['status']}; {row['clientMs']} ms; "
            f"LaMa={row['debug'].get('lamaCallCount')}; retry={row['debug'].get('secondPassTriggered')}; "
            f"outside={row['outsideAllowedChangedPixels']}; residual={row['finalResidual']['visualResidualScore']}"
        )
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "report": str(output / "report.json")}, ensure_ascii=False))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
