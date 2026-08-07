"""Verify the user's strict-local HD regression through the real remove-v2 API."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from services import hd_inpaint  # noqa: E402
from services.stroke_inpaint import build_mask_from_strokes  # noqa: E402


def decode(data: bytes, flags: int = cv2.IMREAD_COLOR) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), flags)
    if image is None:
        raise RuntimeError("image decode failed")
    return image


def encode(image: np.ndarray) -> bytes:
    ok, data = cv2.imencode(".png", image, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])
    if not ok:
        raise RuntimeError("image encode failed")
    return data.tobytes()


def mask_rect_strokes(mask: np.ndarray) -> list[dict[str, float | str]]:
    height, width = mask.shape
    strokes: list[dict[str, float | str]] = []
    for y in range(height):
        xs = np.flatnonzero(mask[y] > 0)
        if xs.size == 0:
            continue
        run_start = int(xs[0])
        previous = run_start
        for value in xs[1:]:
            current = int(value)
            if current != previous + 1:
                strokes.append({
                    "type": "maskRect",
                    "x": run_start / width,
                    "y": y / height,
                    "w": (previous + 1 - run_start) / width,
                    "h": 1 / height,
                })
                run_start = current
            previous = current
        strokes.append({
            "type": "maskRect",
            "x": run_start / width,
            "y": y / height,
            "w": (previous + 1 - run_start) / width,
            "h": 1 / height,
        })
    if len(strokes) > 500:
        raise RuntimeError(f"mask reconstruction needs {len(strokes)} strokes; limit is 500")
    return strokes


def save_zoom(path: Path, original: np.ndarray, final: np.ndarray, allowed: np.ndarray) -> None:
    x, y, width, height = cv2.boundingRect(cv2.findNonZero(allowed))
    padding = max(60, int(round(max(width, height) * 1.8)))
    x1, y1 = max(0, x - padding), max(0, y - padding)
    x2 = min(original.shape[1], x + width + padding)
    y2 = min(original.shape[0], y + height + padding)
    sheet = Image.new("RGB", (1460, 520), (228, 231, 236))
    for index, (label, stage) in enumerate((("original", original), ("remove-v2 final", final))):
        crop = cv2.cvtColor(stage[y1:y2, x1:x2], cv2.COLOR_BGR2RGB)
        image = Image.fromarray(crop)
        image.thumbnail((710, 480), Image.Resampling.LANCZOS)
        panel = Image.new("RGB", (730, 520), "white")
        panel.paste(image, ((730 - image.width) // 2, 4))
        ImageDraw.Draw(panel).text((10, 495), label, fill=(15, 22, 32), font=ImageFont.load_default())
        sheet.paste(panel, (index * 730, 0))
    sheet.save(path, quality=96)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--source", required=True)
    parser.add_argument("--mask", required=True)
    parser.add_argument("--mask-dilation-px", type=int, default=5)
    parser.add_argument("--max-residual-score", type=float, default=0.06)
    parser.add_argument(
        "--output",
        default=str(ROOT / "reports" / "final-visual-convergence" / "hd-remove-v2-api-regression"),
    )
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    source_path = Path(args.source)
    mask_path = Path(args.mask)
    source_bytes = source_path.read_bytes()
    original = decode(source_bytes)
    user_mask = decode(mask_path.read_bytes(), cv2.IMREAD_GRAYSCALE)
    if user_mask.shape != original.shape[:2]:
        user_mask = cv2.resize(user_mask, (original.shape[1], original.shape[0]), interpolation=cv2.INTER_NEAREST)
    user_mask = np.where(user_mask > 0, 255, 0).astype(np.uint8)

    payload = {
        "coordinateSpace": "normalized",
        "strokes": mask_rect_strokes(user_mask),
    }
    reconstructed, _ = build_mask_from_strokes(
        {**payload, "originalWidth": original.shape[1], "originalHeight": original.shape[0]},
        original.shape[1],
        original.shape[0],
    )
    intersection = int(cv2.countNonZero(cv2.bitwise_and(user_mask, reconstructed)))
    union = int(cv2.countNonZero(cv2.bitwise_or(user_mask, reconstructed)))
    mask_iou = intersection / float(max(1, union))
    dilation = max(3, min(12, int(args.mask_dilation_px)))
    allowed = cv2.dilate(
        reconstructed,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilation * 2 + 1, dilation * 2 + 1)),
        iterations=1,
    )

    request_id = f"HD-REMOVE-V2-REGRESSION-{int(time.time())}"
    with source_path.open("rb") as source_file:
        response = requests.post(
            args.base_url.rstrip("/") + "/api/watermark/remove-v2",
            files={"image": (source_path.name, source_file, "image/jpeg")},
            data={
                "strokesJson": json.dumps(payload, separators=(",", ":")),
                "originalWidth": original.shape[1],
                "originalHeight": original.shape[0],
                "displayWidth": original.shape[1],
                "displayHeight": original.shape[0],
                "quality": "hd",
                "strength": "medium",
                "preserveDetail": "true",
                "requestId": request_id,
                "smartExpand": "false",
                "maskDilationPx": dilation,
            },
            timeout=120,
        )
    body = response.json()
    if response.status_code != 200 or not body.get("success"):
        raise RuntimeError(f"remove-v2 failed status={response.status_code}: {body}")
    result_url = str(body.get("resultUrl") or body.get("imageUrl") or "")
    result_response = requests.get(args.base_url.rstrip("/") + result_url, timeout=30)
    result_response.raise_for_status()
    final = decode(result_response.content)
    if final.shape != original.shape:
        raise RuntimeError(f"output size changed: {final.shape} != {original.shape}")

    outside = allowed == 0
    outside_changed = int(np.count_nonzero(np.any(final[outside] != original[outside], axis=1)))
    residual_mask, residual = hd_inpaint._strict_local_residual_analysis(original, final, allowed)
    debug = body.get("debug") or {}
    report = {
        "passed": bool(
            body.get("engine") == "lama"
            and body.get("fallbackUsed") is False
            and debug.get("maskPolicy") == "strict_local"
            and debug.get("smartExpand") is False
            and int(debug.get("lamaCallCount") or 0) <= 2
            and int(debug.get("residualOutsideAllowedPixels") or 0) == 0
            and outside_changed == 0
            and mask_iou >= 0.999
            and float(residual["visualResidualScore"]) <= float(args.max_residual_score)
        ),
        "httpStatus": response.status_code,
        "requestId": request_id,
        "engine": body.get("engine"),
        "fallbackUsed": body.get("fallbackUsed"),
        "maskPolicy": debug.get("maskPolicy"),
        "smartExpand": debug.get("smartExpand"),
        "maskDilationPx": dilation,
        "strokeCount": len(payload["strokes"]),
        "maskReconstructionIoU": round(mask_iou, 6),
        "lamaCallCount": int(debug.get("lamaCallCount") or 0),
        "firstPassResidualScore": float(debug.get("firstPassResidualScore") or 0),
        "finalResidualScore": float(residual["visualResidualScore"]),
        "maxResidualScore": float(args.max_residual_score),
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
        "originalSize": [original.shape[1], original.shape[0]],
        "finalSize": [final.shape[1], final.shape[0]],
        "resultUrl": result_url,
        "outputPath": body.get("outputPath"),
        "artifacts": str(output.resolve()),
    }
    (output / "original.png").write_bytes(encode(original))
    (output / "user-mask.png").write_bytes(encode(user_mask))
    (output / "reconstructed-mask.png").write_bytes(encode(reconstructed))
    (output / "allowed-mask.png").write_bytes(encode(allowed))
    (output / "final-residual-mask.png").write_bytes(encode(residual_mask))
    (output / "final.png").write_bytes(encode(final))
    save_zoom(output / "target-zoom-before-after.jpg", original, final, allowed)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
