"""Quality checks for generated ID photos.

The checks are based on the final downloadable image plus composition metrics
from the face-driven composer. They deliberately avoid using UI screenshots:
a file must be the requested size, use the requested background color, be
centered, and stay within a standard head/shoulder composition before the
frontend can mark it downloadable.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image


def invalid_input(message="请上传清晰的真人正面照片。"):
    return {
        "success": False,
        "code": "INVALID_ID_PHOTO_INPUT",
        "message": message,
    }


def _hex_to_rgb(value: str, fallback="#1A73E8") -> Tuple[int, int, int]:
    value = (value or fallback).strip()
    if not value.startswith("#") or len(value) != 7:
        value = fallback
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def _close(pixel, expected, tolerance=18) -> bool:
    return all(abs(int(pixel[i]) - expected[i]) <= tolerance for i in range(3))


def _inside_box(x: int, y: int, box: Dict[str, float] | None, pad: int = 4) -> bool:
    if not box:
        return False
    left = int(float(box.get("x") or 0)) - pad
    top = int(float(box.get("y") or 0)) - pad
    right = left + int(float(box.get("width") or 0)) + pad * 2
    bottom = top + int(float(box.get("height") or 0)) + pad * 2
    return left <= x <= right and top <= y <= bottom


def _composition_thresholds(width_px: int, height_px: int) -> Dict[str, float]:
    """Return size-aware gates for final ID-photo composition.

    The old checks used one-inch ratios for every output. That falsely rejects
    narrow or very small official formats: a 90x120 or 210x370 file can be
    visually correct while one pixel of top padding or a narrow canvas pushes
    normalized ratios outside the one-inch envelope.
    """
    w = max(1, int(width_px))
    h = max(1, int(height_px))
    aspect = w / float(h)
    small_canvas = w < 180 or h < 240

    top_min = 0.064 if small_canvas else 0.066
    top_max = 0.125 if small_canvas else 0.123
    head_width_max = 0.84
    if aspect < 0.70:
        head_width_max = min(1.04, 0.84 + (0.70 - aspect) * 1.28)
    if small_canvas:
        head_width_max = min(1.06, head_width_max + 0.03)

    return {
        "topMin": top_min,
        "topMax": top_max,
        "bottomMin": 0.0,
        "bottomMax": 0.30,
        "headHeightMin": 0.58,
        "headHeightMax": 0.70,
        "headWidthMin": 0.40 if aspect < 0.70 else 0.42,
        "headWidthMax": head_width_max,
        "shoulderMin": 0.75,
        "shoulderMax": 1.0,
        "centerMax": 0.045 if small_canvas else 0.04,
    }


def _sample_background_purity(
    image: Image.Image,
    expected_rgb: Tuple[int, int, int],
    foreground_box: Dict[str, float] | None = None,
) -> Tuple[float, int]:
    points = []
    w, h = image.size
    for x in range(0, w, max(1, w // 24)):
        for y in (3, h - 4):
            if not _inside_box(x, y, foreground_box):
                points.append(image.getpixel((x, y)))
    for y in range(0, h, max(1, h // 32)):
        for x in (3, w - 4):
            if not _inside_box(x, y, foreground_box):
                points.append(image.getpixel((x, y)))
    if len(points) < 8:
        for x, y in [(3, 3), (w - 4, 3), (3, h - 4), (w - 4, h - 4), (w // 2, 3)]:
            points.append(image.getpixel((x, y)))
    bad = sum(0 if _close(px, expected_rgb) else 1 for px in points)
    return (1.0 - bad / float(max(1, len(points)))), bad


def _edge_halo_metrics(
    image: Image.Image,
    expected_rgb: Tuple[int, int, int],
    foreground_box: Dict[str, float] | None = None,
    max_y: int | None = None,
) -> Dict[str, float]:
    arr = np.asarray(image.convert("RGB")).astype(np.int16)
    if max_y:
        arr = arr[:max(2, min(arr.shape[0], int(max_y))), :, :]
    bg = np.asarray(expected_rgb, dtype=np.int16)
    diff = np.linalg.norm(arr - bg, axis=2)
    fg = (diff > 34).astype("uint8")
    if foreground_box:
        x = max(0, int(float(foreground_box.get("x") or 0)) - 6)
        y = max(0, int(float(foreground_box.get("y") or 0)) - 6)
        w = int(float(foreground_box.get("width") or 0)) + 12
        h = int(float(foreground_box.get("height") or 0)) + 12
        boxed = np.zeros_like(fg)
        boxed[y:min(fg.shape[0], y + h), x:min(fg.shape[1], x + w)] = 1
        fg = fg * boxed
    empty_metrics = {
        "edgeHaloRatio": 0.0,
        "edgeLightHaloRatio": 0.0,
        "edgeGrayHaloRatio": 0.0,
        "edgeWhiteHaloRatio": 0.0,
        "edgeBrightnessDelta": 0.0,
        "edgeSaturationDrop": 0.0,
        "hairEdgeHaloRatio": 0.0,
        "alphaTransitionWidth": 0.0,
        "foregroundLeakRatio": 0.0,
        "backgroundContaminationScore": 0.0,
        "edgeBandPixels": 0,
    }
    if int(np.count_nonzero(fg)) < 64:
        return empty_metrics

    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(fg, kernel, iterations=2)
    eroded = cv2.erode(fg, kernel, iterations=1)
    outer_band = ((dilated > 0) & (fg == 0)).astype(bool)
    inner_band = ((fg > 0) & (eroded == 0)).astype(bool)
    band = outer_band | inner_band
    band_count = int(np.count_nonzero(band))
    if band_count == 0:
        return empty_metrics

    rgb = arr.astype(np.float32)
    maxc = np.max(rgb, axis=2)
    minc = np.min(rgb, axis=2)
    sat = maxc - minc
    brightness = np.mean(rgb, axis=2)

    ys = np.where(fg > 0)[0]
    top = int(ys.min()) if ys.size else 0
    bottom = int(ys.max()) if ys.size else arr.shape[0] - 1
    hair_limit = top + int((bottom - top + 1) * 0.56)
    y_grid = np.indices(fg.shape)[0]
    hair_region = y_grid <= hair_limit

    inspect_band = outer_band | (inner_band & hair_region)
    inspect_count = max(1, int(np.count_nonzero(inspect_band)))
    outer_count = max(1, int(np.count_nonzero(outer_band)))
    hair_count = max(1, int(np.count_nonzero(inspect_band & hair_region)))

    bg_brightness = float(np.mean(bg))
    bg_saturation = float(np.max(bg) - np.min(bg))
    residual = inspect_band & (diff > 24)
    white_halo = residual & (brightness > max(210.0, bg_brightness + 32.0)) & (sat < 46)
    gray_halo = (
        residual
        & (brightness > max(150.0, bg_brightness + 18.0))
        & (brightness < 230)
        & (sat < 28)
    )
    light_halo = white_halo | (gray_halo & (brightness > 170))
    hair_halo = (white_halo | gray_halo) & hair_region
    neutral_gray_bg = bg_saturation < 24 and 80.0 <= bg_brightness <= 205.0
    leak_diff_threshold = 54.0 if neutral_gray_bg else 30.0
    leak_brightness_threshold = max(132.0, bg_brightness + (28.0 if neutral_gray_bg else 16.0))
    leak_saturation_threshold = 56.0 if neutral_gray_bg else 72.0
    foreground_leak = (
        outer_band
        & (diff > leak_diff_threshold)
        & (sat < leak_saturation_threshold)
        & (brightness > leak_brightness_threshold)
    )
    halo = white_halo | gray_halo | foreground_leak
    halo_pixels = white_halo | gray_halo
    if int(np.count_nonzero(halo_pixels)):
        edge_brightness_delta = float(np.mean(brightness[halo_pixels]) - bg_brightness)
        edge_saturation_drop = float(bg_saturation - np.mean(sat[halo_pixels]))
    else:
        edge_brightness_delta = 0.0
        edge_saturation_drop = 0.0
    white_ratio = float(np.count_nonzero(white_halo)) / inspect_count
    gray_ratio = float(np.count_nonzero(gray_halo)) / inspect_count
    hair_ratio = float(np.count_nonzero(hair_halo)) / hair_count
    leak_ratio = float(np.count_nonzero(foreground_leak)) / outer_count
    contamination = max(white_ratio, gray_ratio, hair_ratio, leak_ratio)
    return {
        "edgeHaloRatio": round(float(np.count_nonzero(halo)) / band_count, 6),
        "edgeLightHaloRatio": round(float(np.count_nonzero(light_halo)) / band_count, 6),
        "edgeGrayHaloRatio": round(float(np.count_nonzero(gray_halo)) / band_count, 6),
        "edgeWhiteHaloRatio": round(white_ratio, 6),
        "edgeBrightnessDelta": round(edge_brightness_delta, 4),
        "edgeSaturationDrop": round(edge_saturation_drop, 4),
        "hairEdgeHaloRatio": round(hair_ratio, 6),
        "alphaTransitionWidth": round(float(np.count_nonzero(inner_band)) / max(1, int(np.count_nonzero(fg))), 6),
        "foregroundLeakRatio": round(leak_ratio, 6),
        "backgroundContaminationScore": round(contamination, 6),
        "edgeBandPixels": band_count,
    }


def build_quality_report(image_path, width_px, height_px, bg_color, metrics=None, debug=None):
    metrics = metrics or {}
    debug = debug or {}
    checks: Dict[str, object] = {}
    fail_reasons: List[str] = []
    score = 100

    try:
        image = Image.open(image_path).convert("RGB")
    except Exception:
        return {
            "passed": False,
            "score": 0,
            "checks": {},
            "failReasons": ["BACKGROUND_COMPOSE_FAILED"],
            "metrics": metrics,
        }

    expected_rgb = _hex_to_rgb(bg_color)
    output_size_correct = image.size == (int(width_px), int(height_px))
    checks["outputSizeCorrect"] = output_size_correct
    if not output_size_correct:
        fail_reasons.append("OUTPUT_SIZE_INVALID")
        score -= 40

    foreground_box = metrics.get("outputForegroundBox") or None
    purity, edge_bad = _sample_background_purity(image, expected_rgb, foreground_box)
    outfit_anchor = metrics.get("outfitAnchor") or {}
    halo_max_y = outfit_anchor.get("neckY") if metrics.get("outfitApplied") else None
    halo = _edge_halo_metrics(image, expected_rgb, foreground_box, halo_max_y)
    checks["backgroundPureColor"] = purity >= 0.985
    checks["backgroundPurity"] = round(purity, 4)
    checks["edgeArtifactScore"] = round(1 - purity, 4)
    checks["edgeHaloRatio"] = halo["edgeHaloRatio"]
    checks["edgeLightHaloRatio"] = halo["edgeLightHaloRatio"]
    checks["edgeGrayHaloRatio"] = halo["edgeGrayHaloRatio"]
    checks["edgeWhiteHaloRatio"] = halo["edgeWhiteHaloRatio"]
    checks["edgeBrightnessDelta"] = halo["edgeBrightnessDelta"]
    checks["edgeSaturationDrop"] = halo["edgeSaturationDrop"]
    checks["hairEdgeHaloRatio"] = halo["hairEdgeHaloRatio"]
    checks["alphaTransitionWidth"] = (
        (metrics.get("edgeCleanup") or {}).get("alphaTransitionWidth")
        or halo["alphaTransitionWidth"]
    )
    checks["foregroundLeakRatio"] = halo["foregroundLeakRatio"]
    checks["backgroundContaminationScore"] = halo["backgroundContaminationScore"]
    checks["edgeBandPixels"] = halo["edgeBandPixels"]
    if purity < 0.985:
        fail_reasons.append("ID_PHOTO_BACKGROUND_NOT_PURE")
        score -= 18
    bg_brightness = sum(expected_rgb) / 3.0
    bg_saturation = max(expected_rgb) - min(expected_rgb)
    pure_white_bg = bg_saturation < 20 and bg_brightness > 235
    neutral_gray_bg = bg_saturation < 24 and 80.0 <= bg_brightness <= 205.0
    foreground_leak_limit = 0.10 if neutral_gray_bg else 0.02
    gray_halo_limit = 0.06 if neutral_gray_bg else 0.035
    hair_halo_limit = 0.065 if neutral_gray_bg else 0.025
    edge_failed = (
        halo["edgeWhiteHaloRatio"] > 0.015
        or halo["hairEdgeHaloRatio"] > hair_halo_limit
        or halo["foregroundLeakRatio"] > foreground_leak_limit
        or (halo["edgeGrayHaloRatio"] > gray_halo_limit and not pure_white_bg)
    )
    if (not pure_white_bg) and edge_failed:
        fail_reasons.append("ID_PHOTO_EDGE_HALO")
        score -= 18

    top = float(metrics.get("topPaddingRatio") or 0)
    bottom = float(metrics.get("bottomPaddingRatio") or 0)
    head_h = float(metrics.get("headHeightRatio") or metrics.get("headRatio") or 0)
    head_w = float(metrics.get("headWidthRatio") or 0)
    shoulder = float(metrics.get("shoulderWidthRatio") or metrics.get("foregroundWidthRatio") or 0)
    center = float(metrics.get("faceCenterOffset") or 0)
    fg_h = float(metrics.get("foregroundHeightRatio") or 0)

    checks.update({
        "faceDetected": bool(metrics.get("faceDetected", True)),
        "singleFace": int(metrics.get("faceCount") or 1) == 1,
        "humanPortrait": bool(metrics.get("realPerson", True)),
        "notAnime": metrics.get("imageType", "real_person") not in {"anime", "cartoon", "illustration"},
        "topPaddingRatio": round(top, 4),
        "bottomPaddingRatio": round(bottom, 4),
        "headHeightRatio": round(head_h, 4),
        "headWidthRatio": round(head_w, 4),
        "shoulderWidthRatio": round(shoulder, 4),
        "faceCenterXRatio": round(0.5 + min(0.49, center), 4),
        "faceCenterYRatio": round(float((metrics.get("outputFaceBox") or {}).get("y", 0)) / max(1, int(height_px)), 4),
        "bodyTooMuch": fg_h > 0.95 and head_h < 0.58,
        "shoulderTouchEdge": False,
        "holeAreaRatio": round(float(metrics.get("holeAreaRatio") or 0), 4),
        "originalBackgroundLeak": purity < 0.985,
        "usedForegroundPng": debug.get("usedForegroundPng") is True,
        "usedOriginalImageDirectly": debug.get("usedOriginalImageDirectly") is True,
        "previewEqualsDownload": True,
    })
    background_leak = float(metrics.get("backgroundLeakRatio") or 0)
    tightness = float(metrics.get("foregroundTightnessScore") or 1)
    edge_leak = float(metrics.get("edgeLeakScore") or 0)
    halo_score = float(metrics.get("haloScore") or 0)
    coverage = float(metrics.get("subjectCoverageScore") or 1)
    mask_overflow = float(metrics.get("maskOverflowRatio") or 0)
    invalid_retention = float(metrics.get("invalidBackgroundRetentionScore") or 0)
    background_sheet = float(metrics.get("remainingBackgroundSheetRatio") or 0)
    head_side_background = float(metrics.get("remainingHeadSideBackgroundRatio") or 0)
    matting_refine = metrics.get("mattingRefine") or {}
    overtrim_fallback = bool(metrics.get("overTrimFallbackUsed") or matting_refine.get("overTrimFallbackUsed"))
    checks.update({
        "backgroundLeakRatio": round(background_leak, 6),
        "foregroundTightnessScore": round(tightness, 6),
        "edgeLeakScore": round(edge_leak, 6),
        "haloScore": round(halo_score, 6),
        "subjectCoverageScore": round(coverage, 6),
        "maskOverflowRatio": round(mask_overflow, 6),
        "invalidBackgroundRetentionScore": round(invalid_retention, 6),
        "remainingBackgroundSheetRatio": round(background_sheet, 6),
        "remainingHeadSideBackgroundRatio": round(head_side_background, 6),
        "overTrimFallbackUsed": overtrim_fallback,
        "mattingBackgroundLeakOk": background_leak <= 0.045 and mask_overflow <= 0.045,
        "mattingForegroundTightnessOk": tightness >= 0.90,
        "mattingSubjectCoverageOk": coverage >= 0.55,
        "mattingInvalidRetentionOk": invalid_retention <= 0.075,
        "mattingBackgroundSheetOk": background_sheet <= 0.018,
        "mattingHeadSideBackgroundOk": head_side_background <= 0.006,
    })
    matting_failed = (
        not checks["mattingBackgroundLeakOk"]
        or not checks["mattingForegroundTightnessOk"]
        or not checks["mattingSubjectCoverageOk"]
        or not checks["mattingInvalidRetentionOk"]
        or not checks["mattingBackgroundSheetOk"]
        or not checks["mattingHeadSideBackgroundOk"]
    )
    if matting_failed:
        fail_reasons.append("ID_PHOTO_MATTING_BACKGROUND_LEAK")
        score -= 22

    def require(condition, code, penalty):
        nonlocal score
        if not condition:
            fail_reasons.append(code)
            score -= penalty

    thresholds = _composition_thresholds(int(width_px), int(height_px))
    checks["compositionThresholds"] = thresholds

    require(thresholds["topMin"] <= top <= thresholds["topMax"], "ID_PHOTO_TOP_PADDING_BAD", 10)
    if top < thresholds["topMin"]:
        fail_reasons.append("ID_PHOTO_TOP_PADDING_TOO_SMALL")
    if top > thresholds["topMax"]:
        fail_reasons.append("ID_PHOTO_TOP_PADDING_TOO_LARGE")
    require(thresholds["bottomMin"] <= bottom <= thresholds["bottomMax"], "ID_PHOTO_BOTTOM_PADDING_BAD", 8)
    require(thresholds["headHeightMin"] <= head_h <= thresholds["headHeightMax"], "ID_PHOTO_HEAD_SIZE_BAD", 12)
    if head_h < thresholds["headHeightMin"]:
        fail_reasons.append("ID_PHOTO_HEAD_TOO_SMALL")
    if head_h > thresholds["headHeightMax"]:
        fail_reasons.append("ID_PHOTO_HEAD_TOO_LARGE")
    require(thresholds["headWidthMin"] <= head_w <= thresholds["headWidthMax"], "ID_PHOTO_HEAD_WIDTH_BAD", 8)
    require(thresholds["shoulderMin"] <= shoulder <= thresholds["shoulderMax"], "ID_PHOTO_SHOULDER_WIDTH_BAD", 10)
    if shoulder < thresholds["shoulderMin"]:
        fail_reasons.append("ID_PHOTO_SHOULDER_TOO_NARROW")
    if shoulder > thresholds["shoulderMax"]:
        fail_reasons.append("ID_PHOTO_SHOULDER_TOO_WIDE")
    require(center <= thresholds["centerMax"], "ID_PHOTO_FACE_NOT_CENTERED", 8)
    require(not checks["bodyTooMuch"], "ID_PHOTO_BODY_TOO_MUCH", 10)
    require(checks["usedForegroundPng"], "ID_PHOTO_USED_FOREGROUND_MISSING", 20)
    require(not checks["usedOriginalImageDirectly"], "ID_PHOTO_USED_ORIGINAL_IMAGE_DIRECTLY", 30)

    return {
        "passed": score >= 85 and not fail_reasons,
        "score": max(0, min(100, round(score, 2))),
        "checks": checks,
        "failReasons": fail_reasons,
        "metrics": {
            **metrics,
            "backgroundEdgeBadSamples": edge_bad,
            **halo,
        },
    }


def validate_final_output(image_path, width_px, height_px, bg_color):
    report = build_quality_report(image_path, width_px, height_px, bg_color)
    if not report["checks"].get("outputSizeCorrect"):
        return {
            "success": False,
            "code": "OUTPUT_SIZE_INVALID",
            "message": "生成尺寸异常，请重新选择规格后重试。",
            "qualityReport": report,
        }
    # Background purity needs the foreground box; it is checked after compose
    # metrics are merged in compose_prepared_id_photo.
    return {"success": True, "qualityReport": report}


def validate_composition_metrics(metrics):
    if not metrics:
        return {
            "success": False,
            "code": "BACKGROUND_COMPOSE_FAILED",
            "message": "底色生成失败，请重新选择底色或重新上传照片。",
        }
    if metrics.get("faceCenterOffset", 0) > 0.08:
        return {
            "success": False,
            "code": "ID_PHOTO_FACE_NOT_CENTERED",
            "message": "当前照片构图不适合自动生成，请重新上传头肩清晰照片。",
        }
    if metrics.get("faceHeightRatio", 0) < 0.20:
        return {
            "success": False,
            "code": "ID_PHOTO_FACE_TOO_SMALL",
            "message": "当前照片人脸过小，请重新上传清晰正面照片。",
        }
    return {"success": True}
