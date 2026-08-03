"""Verify compact stroke transport and ROI-only watermark processing."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np


SERVER_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SERVER_ROOT.parent
sys.path.insert(0, str(SERVER_ROOT))

from services.manual_inpaint import ManualInpaintError
from services.stroke_inpaint import process_stroke_inpaint


def _expect_error(image_bytes: bytes, payload: dict[str, object]) -> bool:
    try:
        process_stroke_inpaint(image_bytes, json.dumps(payload), quality="quick")
    except ManualInpaintError:
        return True
    return False


def main() -> int:
    width, height = 4096, 3072
    x = np.linspace(0, 255, width, dtype=np.uint8)
    y = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[:, :, 0] = x
    image[:, :, 1] = y
    image[:, :, 2] = ((x[None, :].astype(np.uint16) + y.astype(np.uint16)) // 2).astype(np.uint8)
    cv2.putText(image, "WATERMARK", (3200, 2960), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (255, 255, 255), 8)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise AssertionError("failed to encode synthetic source")
    image_bytes = encoded.tobytes()

    payload = {
        "coordinateSpace": "normalized",
        "originalWidth": width,
        "originalHeight": height,
        "displayWidth": 375,
        "displayHeight": 281,
        "strokes": [
            {
                "type": "brush",
                "brushSizeRatio": 0.022,
                "points": [
                    {"x": 0.775, "y": 0.963},
                    {"x": 0.995, "y": 0.963},
                ],
            }
        ],
    }
    strokes_json = json.dumps(payload, separators=(",", ":"))
    result = process_stroke_inpaint(image_bytes, strokes_json, quality="quick", strength="low")
    output = cv2.imdecode(np.frombuffer(result["bytes"], dtype=np.uint8), cv2.IMREAD_COLOR)
    if output is None:
        raise AssertionError("failed to decode repaired result")

    debug = result["debug"]
    roi = debug["roi"]
    outside = np.ones((height, width), dtype=bool)
    outside[roi["y"]:roi["y"] + roi["height"], roi["x"]:roi["x"] + roi["width"]] = False
    outside_changed = int(np.count_nonzero(np.any(output[outside] != image[outside], axis=1)))

    page_text = (PROJECT_ROOT / "pages" / "tool-detail" / "tool-detail.js").read_text(encoding="utf-8")
    api_text = (PROJECT_ROOT / "utils" / "watermarkApi.js").read_text(encoding="utf-8")
    canvas_text = (PROJECT_ROOT / "utils" / "watermarkCanvas.js").read_text(encoding="utf-8")
    main_text = (SERVER_ROOT / "main.py").read_text(encoding="utf-8")
    checks = {
        "largeOutputDimensionsPreserved": output.shape[:2] == (height, width),
        "compactStrokePayload": len(strokes_json.encode("utf-8")) < 2048,
        "roiIsSmallerThanOriginal": debug["roiPixelRatio"] < 0.20,
        "edgeContextAdded": debug["roiReflectBorder"]["right"] > 0 or debug["roiReflectBorder"]["bottom"] > 0,
        "outsideRoiPixelsUnchanged": outside_changed == 0 and debug["outsideRoiChangedPixels"] == 0,
        "quickEngineIsTruthful": result["engine"] == "opencv_quick" and not result["fallbackUsed"],
        "pageDoesNotExportMask": "exportValidatedMask(" not in page_text,
        "pageUsesStrokeTransport": "getStrokeTransportPayload(" in page_text and "strokeTransportOnly: true" in page_text,
        "apiUsesRemoveV2": "/api/watermark/remove-v2" in api_text,
        "base64MaskRemovedFromFlow": "maskBase64" not in page_text + api_text + main_text,
        "emptyStrokesRejected": _expect_error(image_bytes, {**payload, "strokes": []}),
        "dimensionMismatchRejected": _expect_error(image_bytes, {**payload, "originalWidth": width - 1}),
        "canvasExportsCompactPayload": "getStrokeTransportPayload" in canvas_text,
    }
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "sourceSize": f"{width}x{height}",
        "sourceBytes": len(image_bytes),
        "avoidedFrontendRgbaBytes": width * height * 4,
        "strokePayloadBytes": len(strokes_json.encode("utf-8")),
        "roi": roi,
        "roiPixelRatio": debug["roiPixelRatio"],
        "outsideRoiChangedPixels": outside_changed,
        "outputSize": debug["outputSize"],
        "engine": result["engine"],
        "fallbackUsed": result["fallbackUsed"],
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
