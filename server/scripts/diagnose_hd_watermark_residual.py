#!/usr/bin/env python3
"""Save the production HD repair stages for one manually supplied stroke payload."""
from __future__ import annotations

import argparse
import json
import sys
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


def _decode(data: bytes, flags: int = cv2.IMREAD_COLOR) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), flags)
    if image is None:
        raise RuntimeError("Image decoding failed")
    return image


def _save(path: Path, image: np.ndarray) -> None:
    path.write_bytes(_encode_png(image))


def _resize_to_canvas(image: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    height, width = shape
    if image.shape[:2] == shape:
        return image
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_NEAREST)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--strokes", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mask-dilation-px", type=int, default=5)
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    source_path = Path(args.source)
    source_bytes = source_path.read_bytes()
    source = _decode(source_bytes)
    payload = json.loads(Path(args.strokes).read_text(encoding="utf-8-sig"))
    height, width = source.shape[:2]
    user_mask, mask_debug = build_mask_from_strokes(payload, width, height)
    dilation_px = max(1, min(6, int(args.mask_dilation_px)))
    allowed_mask, allowed_debug = hd_inpaint.derive_allowed_mask(
        source,
        user_mask,
        max_dilation_px=dilation_px,
    )

    captures: dict[str, Any] = {
        "first": None,
        "firstMask": None,
        "firstResidualMask": None,
        "firstResidualMetrics": None,
        "secondMask": None,
    }
    original_analysis = hd_inpaint._strict_local_residual_analysis

    def capture_analysis(original: np.ndarray, candidate: np.ndarray, mask: np.ndarray):
        residual, metrics = original_analysis(original, candidate, mask)
        if captures["first"] is None:
            captures["first"] = candidate.copy()
            captures["firstMask"] = mask.copy()
            captures["firstResidualMask"] = residual.copy()
            captures["firstResidualMetrics"] = metrics
        return residual, metrics

    hd_inpaint._strict_local_residual_analysis = capture_analysis
    try:
        result = process_stroke_inpaint(
            source_bytes,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            quality="hd",
            strength="medium",
            preserve_detail=True,
            request_id="hd-residual-diagnostic",
            smart_expand=False,
            mask_dilation_px=dilation_px,
        )
    finally:
        hd_inpaint._strict_local_residual_analysis = original_analysis

    final = _decode(result["bytes"])
    first = captures["first"] if captures["first"] is not None else final
    first_mask = captures["firstMask"] if captures["firstMask"] is not None else allowed_mask
    residual_mask = captures["firstResidualMask"]
    residual_metrics = captures["firstResidualMetrics"]
    if residual_mask is None or residual_metrics is None:
        residual_mask, residual_metrics = original_analysis(first, first, first_mask)
    outside_changed = int(np.count_nonzero(np.any(final[allowed_mask == 0] != source[allowed_mask == 0], axis=1)))

    _save(output / "original.png", source)
    _save(output / "user-mask.png", user_mask)
    _save(output / "allowed-mask.png", allowed_mask)
    _save(output / "first-lama.png", _resize_to_canvas(first, source.shape[:2]))
    _save(output / "residual-mask.png", _resize_to_canvas(residual_mask, source.shape[:2]))
    _save(output / "final.png", final)
    report = {
        "source": str(source_path),
        "sourceSize": f"{width}x{height}",
        "maskDilationPx": dilation_px,
        "allowedMask": allowed_debug,
        "mask": mask_debug,
        "firstResidual": residual_metrics,
        "secondLamaMaskPixels": int(
            ((result.get("debug") or {}).get("secondPassMaskPixels") or 0)
        ),
        "outsideAllowedChangedPixels": outside_changed,
        "pipelineDebug": result.get("debug") or {},
    }
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "firstResidual": residual_metrics,
        "secondLamaMaskPixels": report["secondLamaMaskPixels"],
        "outsideAllowedChangedPixels": outside_changed,
        "secondPassTriggered": bool((result.get("debug") or {}).get("secondPassTriggered")),
        "lamaCallCount": int((result.get("debug") or {}).get("lamaCallCount") or 0),
        "output": str(output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
