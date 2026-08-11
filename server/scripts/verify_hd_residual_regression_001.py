"""Run the real strict-local HD chain for the user's faded residual regression sample."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from services import hd_inpaint  # noqa: E402


def decode(data: bytes, flags: int = cv2.IMREAD_COLOR) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), flags)
    if image is None:
        raise RuntimeError("image decode failed")
    return image


def encode(image: np.ndarray) -> bytes:
    ok, payload = cv2.imencode(".png", image, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])
    if not ok:
        raise RuntimeError("image encode failed")
    return payload.tobytes()


def save(path: Path, image: np.ndarray) -> None:
    path.write_bytes(encode(image))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--mask", required=True)
    parser.add_argument("--mask-dilation-px", type=int, default=5)
    parser.add_argument("--max-residual-score", type=float, default=0.06)
    parser.add_argument(
        "--output",
        default=str(ROOT / "reports" / "final-visual-convergence" / "hd-residual-regression-001"),
    )
    args = parser.parse_args()
    source_path = Path(args.source)
    mask_path = Path(args.mask)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    source_bytes = source_path.read_bytes()
    mask_bytes = mask_path.read_bytes()
    source = decode(source_bytes)
    user_mask = decode(mask_bytes, cv2.IMREAD_GRAYSCALE)
    if user_mask.shape != source.shape[:2]:
        user_mask = cv2.resize(user_mask, (source.shape[1], source.shape[0]), interpolation=cv2.INTER_NEAREST)
    user_mask = np.where(user_mask > 0, 255, 0).astype(np.uint8)
    dilation_px = max(3, min(12, int(args.mask_dilation_px)))
    allowed = cv2.dilate(
        user_mask,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilation_px * 2 + 1, dilation_px * 2 + 1)),
        iterations=1,
    )

    captures: list[dict[str, np.ndarray]] = []
    original_single = hd_inpaint._do_hd_inpaint_single

    def capture_single(img_bytes: bytes, roi_mask_bytes: bytes, *call_args: Any, **call_kwargs: Any):
        result = original_single(img_bytes, roi_mask_bytes, *call_args, **call_kwargs)
        captures.append({
            "result": decode(result["bytes"]),
            "mask": decode(roi_mask_bytes, cv2.IMREAD_GRAYSCALE),
        })
        return result

    hd_inpaint._do_hd_inpaint_single = capture_single
    try:
        result = hd_inpaint.do_hd_inpaint(
            source_bytes,
            encode(user_mask),
            strength="medium",
            preserve_detail=True,
            request_id="HD-RESIDUAL-REGRESSION-001",
            smart_expand=False,
            mask_dilation_px=dilation_px,
        )
    finally:
        hd_inpaint._do_hd_inpaint_single = original_single

    final = decode(result["bytes"])
    debug = result.get("debug") or {}
    outside = allowed == 0
    outside_changed = int(np.count_nonzero(np.any(final[outside] != source[outside], axis=1)))
    retry_mask = captures[1]["mask"] if len(captures) > 1 else np.zeros_like(user_mask)
    first = captures[0]["result"] if captures else final
    final_residual_mask, final_residual = hd_inpaint._strict_local_residual_analysis(
        source,
        final,
        allowed,
    )

    stages = [source, user_mask, allowed, first, retry_mask, final_residual_mask, final]
    names = [
        "original", "user-mask", "allowed-mask", "first-lama",
        "retry-mask", "final-residual-mask", "final",
    ]
    for name, stage in zip(names, stages):
        save(output / f"{name}.png", stage)

    x, y, width, height = cv2.boundingRect(cv2.findNonZero(allowed))
    padding = max(60, int(round(max(width, height) * 1.8)))
    x1, y1 = max(0, x - padding), max(0, y - padding)
    x2, y2 = min(source.shape[1], x + width + padding), min(source.shape[0], y + height + padding)
    zooms = []
    for label, stage in (("original", source), ("final", final)):
        crop = cv2.cvtColor(stage[y1:y2, x1:x2], cv2.COLOR_BGR2RGB)
        image = Image.fromarray(crop)
        image.thumbnail((720, 480), Image.Resampling.LANCZOS)
        panel = Image.new("RGB", (730, 520), "white")
        panel.paste(image, ((730 - image.width) // 2, 4))
        ImageDraw.Draw(panel).text((10, 495), label, fill=(15, 22, 32), font=ImageFont.load_default())
        zooms.append(panel)
    zoom_sheet = Image.new("RGB", (1460, 520), (228, 231, 236))
    zoom_sheet.paste(zooms[0], (0, 0))
    zoom_sheet.paste(zooms[1], (730, 0))
    zoom_sheet.save(output / "target-zoom-before-after.jpg", quality=96)

    frames = []
    for name, stage in zip(names, stages):
        rgb = cv2.cvtColor(stage, cv2.COLOR_GRAY2RGB) if stage.ndim == 2 else cv2.cvtColor(stage, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        image.thumbnail((300, 220), Image.Resampling.LANCZOS)
        panel = Image.new("RGB", (310, 255), "white")
        panel.paste(image, ((310 - image.width) // 2, 4))
        ImageDraw.Draw(panel).text((8, 232), name, fill=(15, 22, 32), font=ImageFont.load_default())
        frames.append(panel)
    sheet = Image.new("RGB", (310 * len(frames), 255), (228, 231, 236))
    for index, frame in enumerate(frames):
        sheet.paste(frame, (index * 310, 0))
    sheet.save(output / "five-stage-contact-sheet.jpg", quality=94)

    first_score = float(debug.get("firstPassResidualScore") or 0)
    final_score = float(final_residual["visualResidualScore"])
    report = {
        "id": "HD-RESIDUAL-REGRESSION-001",
        "passed": bool(
            result.get("engine") == "lama"
            and result.get("fallbackUsed") is False
            and debug.get("maskPolicy") == "strict_local"
            and debug.get("smartExpand") is False
            and int(debug.get("lamaCallCount") or 0) <= 2
            and int(debug.get("residualOutsideAllowedPixels") or 0) == 0
            and outside_changed == 0
            and final_score <= first_score + 1e-9
            and final_score <= float(args.max_residual_score)
        ),
        "firstPassResidualScore": first_score,
        "finalResidualScore": final_score,
        "secondPassTriggered": bool(debug.get("secondPassTriggered")),
        "secondPassAccepted": bool(debug.get("secondPassAccepted")),
        "lamaCallCount": int(debug.get("lamaCallCount") or 0),
        "maxResidualScore": float(args.max_residual_score),
        "maskDilationPx": dilation_px,
        "watermarkResidualRatio": float(final_residual["watermarkResidualRatio"]),
        "watermarkResidualEdgeRatio": float(final_residual["watermarkResidualEdgeRatio"]),
        "watermarkResidualChromaRatio": float(final_residual["watermarkResidualChromaRatio"]),
        "residualMaskPixels": int(final_residual["residualMaskPixels"]),
        "strictChromaCleanupApplied": bool(debug.get("strictChromaCleanupApplied")),
        "strictBackgroundCompletionApplied": bool(
            debug.get("strictBackgroundCompletionApplied")
        ),
        "strictBackgroundCompletionKernel": int(
            debug.get("strictBackgroundCompletionKernel") or 0
        ),
        "strictBackgroundCompletionLaplacianMean": float(
            debug.get("strictBackgroundCompletionLaplacianMean") or 0
        ),
        "strictBackgroundCompletionChromaSeedRatio": float(
            debug.get("strictBackgroundCompletionChromaSeedRatio") or 0
        ),
        "strictBackgroundCompletionRetainedRatio": float(
            debug.get("strictBackgroundCompletionRetainedRatio") or 0
        ),
        "outsideAllowedChangedPixels": outside_changed,
        "residualOutsideAllowedPixels": int(debug.get("residualOutsideAllowedPixels") or 0),
        "engine": result.get("engine"),
        "fallbackUsed": result.get("fallbackUsed"),
        "artifacts": str(output),
    }
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
