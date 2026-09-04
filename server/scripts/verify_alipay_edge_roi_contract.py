"""Verify the Alipay HD ROI contract without calling the real LaMa service."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np


SERVER_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SERVER_ROOT.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from services.manual_inpaint import ManualInpaintError  # noqa: E402
from services import stroke_inpaint  # noqa: E402


def _encode(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise AssertionError("failed to encode synthetic ROI")
    return encoded.tobytes()


def main() -> int:
    source_width, source_height = 1200, 2400
    roi_x, roi_y, roi_width, roi_height = 480, 1680, 180, 140
    roi = np.zeros((roi_height, roi_width, 3), dtype=np.uint8)
    roi[:, :, 0] = np.arange(roi_width, dtype=np.uint8)
    roi[:, :, 1] = np.arange(roi_height, dtype=np.uint8)[:, None]
    roi[:, :, 2] = 120
    payload = {
        "coordinateSpace": "normalized",
        "originalWidth": roi_width,
        "originalHeight": roi_height,
        "displayWidth": 360,
        "displayHeight": 280,
        "strokes": [{
            "type": "maskRect",
            "x": 0.25,
            "y": 0.30,
            "w": 0.25,
            "h": 0.20,
        }],
    }
    strokes_json = json.dumps(payload, separators=(",", ":"))
    original_call = stroke_inpaint._call_iopaint
    call_count = 0

    def fake_iopaint(image, mask, **_kwargs):
        nonlocal call_count
        call_count += 1
        repaired = np.full_like(image, (11, 101, 211))
        return repaired, {"engine": "lama", "mocked": True}

    stroke_inpaint._call_iopaint = fake_iopaint
    try:
        result = stroke_inpaint.process_roi_stroke_inpaint(
            _encode(roi),
            strokes_json,
            source_width,
            source_height,
            roi_x,
            roi_y,
            roi_width,
            roi_height,
            request_id="alipay-roi-contract",
            mask_dilation_px=5,
            original_upload_bytes=source_width * source_height * 3,
        )
        try:
            stroke_inpaint.process_roi_stroke_inpaint(
                _encode(roi),
                strokes_json,
                source_width,
                source_height,
                roi_x,
                roi_y,
                roi_width - 1,
                roi_height,
            )
            invalid_geometry_rejected = False
        except ManualInpaintError:
            invalid_geometry_rejected = True
    finally:
        stroke_inpaint._call_iopaint = original_call

    patch = cv2.imdecode(np.frombuffer(result["bytes"], dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if patch is None or patch.ndim != 3 or patch.shape[2] != 4:
        raise AssertionError("ROI result must be an RGBA patch")
    mask, _ = stroke_inpaint.build_mask_from_strokes(payload, roi_width, roi_height)
    allowed = cv2.dilate(
        mask,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
        iterations=1,
    )
    alpha = patch[:, :, 3]
    outside = allowed == 0
    expected_bgr = np.array([11, 101, 211], dtype=np.uint8)
    api_text = (PROJECT_ROOT / "alipay" / "utils" / "watermarkApi.js").read_text(encoding="utf-8")
    server_text = (SERVER_ROOT / "main.py").read_text(encoding="utf-8")
    debug = result["debug"]
    checks = {
        "roiMode": result["backendMode"] == "roi_lama" and debug.get("roiMode") is True,
        "lamaReceivesRoiOnly": call_count == 1 and debug.get("lamaInputIsRoi") is True,
        "roiDimensionsPreserved": patch.shape[:2] == (roi_height, roi_width),
        "rgbaPatchReturned": patch.shape[2] == 4,
        "outsideMaskAlphaIsZero": int(np.count_nonzero(alpha[outside])) == 0,
        "allowedMaskCarriesRepairedPixels": bool(np.all(patch[:, :, :3][allowed > 0] == expected_bgr)),
        "sourceGeometryRecorded": debug.get("originalSize") == f"{source_width}x{source_height}",
        "roiCoordinatesRecorded": debug.get("roiBox") == {
            "x": roi_x,
            "y": roi_y,
            "width": roi_width,
            "height": roi_height,
        },
        "substantialPixelReduction": debug.get("roiPixelRatio", 1) < 0.02,
        "invalidGeometryRejected": invalid_geometry_rejected,
        "derivedUploadUsesSourceSafety": "sourceAssetId" in api_text and "_uploadVerifiedDerivedFile" in api_text,
        "serverBindsSourceAsset": "_assert_verified_source_safety" in server_text and "CONTENT_SAFETY_SOURCE_MISMATCH" in server_text,
        "edgeRoiRestrictedToHd": "ROI_MODE_HD_ONLY" in server_text,
    }
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "originalPixels": source_width * source_height,
        "roiPixels": roi_width * roi_height,
        "pixelReductionRatio": round(1 - (roi_width * roi_height) / float(source_width * source_height), 6),
        "debug": debug,
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
