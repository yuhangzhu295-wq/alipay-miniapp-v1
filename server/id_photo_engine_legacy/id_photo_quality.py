"""Quality checks for generated ID photos.

The checks are based on the final downloadable image plus composition metrics
from the face-driven composer. They deliberately avoid using UI screenshots:
a file must be the requested size, use the requested background color, be
centered, and stay within a standard head/shoulder composition before the
frontend can mark it downloadable.
"""
from __future__ import annotations

import os
from typing import Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image


CROP_FAIL_CODES = {
    "ID_PHOTO_TOP_PADDING_BAD",
    "ID_PHOTO_TOP_PADDING_TOO_SMALL",
    "ID_PHOTO_TOP_PADDING_TOO_LARGE",
    "ID_PHOTO_BOTTOM_PADDING_BAD",
    "ID_PHOTO_HEAD_SIZE_BAD",
    "ID_PHOTO_HEAD_TOO_SMALL",
    "ID_PHOTO_HEAD_TOO_LARGE",
    "ID_PHOTO_HEAD_WIDTH_BAD",
    "ID_PHOTO_SHOULDER_WIDTH_BAD",
    "ID_PHOTO_SHOULDER_TOO_NARROW",
    "ID_PHOTO_SHOULDER_TOO_WIDE",
    "ID_PHOTO_FACE_NOT_CENTERED",
    "ID_PHOTO_FACE_TOO_SMALL",
    "ID_PHOTO_BODY_TOO_MUCH",
    "ID_PHOTO_SUBJECT_OUTSIDE_CANVAS",
    "ID_PHOTO_SIDE_SAFETY_BAD",
}

MATTING_FAIL_CODES = {
    "ID_PHOTO_HAIR_BACKGROUND_HOLE",
    "ID_PHOTO_FACE_BACKGROUND_HOLE",
    "ID_PHOTO_BODY_ALPHA_MISSING",
    "ID_PHOTO_MATTING_BACKGROUND_LEAK",
    "ID_PHOTO_SIDE_BACKGROUND_RESIDUAL",
    "ID_PHOTO_BLACK_BACK_PANEL",
    "ID_PHOTO_USED_FOREGROUND_MISSING",
}

FAST_WARNING_CODES = {"ID_PHOTO_EDGE_HALO"}


def split_quality_fail_reasons(fail_reasons):
    reasons = list(dict.fromkeys(fail_reasons or []))
    crop = [code for code in reasons if code in CROP_FAIL_CODES]
    matting = [code for code in reasons if code in MATTING_FAIL_CODES]
    warnings = [code for code in reasons if code in FAST_WARNING_CODES]
    other = [code for code in reasons if code not in CROP_FAIL_CODES | MATTING_FAIL_CODES | FAST_WARNING_CODES]
    return {
        "cropFailReasons": crop,
        "mattingFailReasons": matting,
        "fastWarningReasons": warnings,
        "outputFailReasons": other,
    }



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


def _composition_thresholds(width_px: int, height_px: int, composition_profile=None) -> Dict[str, float]:
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

    thresholds = {
        "topMin": top_min,
        "topMax": top_max,
        "bottomMin": 0.0,
        "bottomMax": 0.33,
        "headHeightMin": 0.58,
        "headHeightMax": 0.70,
        "headWidthMin": 0.40 if aspect < 0.70 else 0.42,
        "headWidthMax": head_width_max,
        "shoulderMin": 0.75,
        "shoulderMax": 1.0,
        "centerMax": 0.045 if small_canvas else 0.04,
        "sideSafetyMin": 0.0,
        # The lower torso normally exits an ID-photo canvas.  Chin-to-bottom is
        # the composition safety metric; requiring a blue strip below the body
        # makes half-body inputs shrink until the face is unusably small.
        "bottomSafetyMin": 0.0,
    }
    profile = composition_profile or {}
    profile_fields = {
        "headWidthRatioMin": "headWidthMin",
        "headWidthRatioMax": "headWidthMax",
        "headHeightRatioMin": "headHeightMin",
        "headHeightRatioMax": "headHeightMax",
        "topMarginRatioMin": "topMin",
        "topMarginRatioMax": "topMax",
        "shoulderWidthRatioMin": "shoulderMin",
        "shoulderWidthRatioMax": "shoulderMax",
    }
    for profile_key, threshold_key in profile_fields.items():
        value = profile.get(profile_key)
        if value is not None:
            thresholds[threshold_key] = float(value)
    if profile.get("sideSafetyRatio") is not None:
        thresholds["sideSafetyMin"] = float(profile["sideSafetyRatio"])
    if profile.get("bottomSafetyRatio") is not None:
        thresholds["bottomSafetyMin"] = float(profile["bottomSafetyRatio"])
    thresholds["chinBottomMin"] = (
        float(profile["chinBottomRatioMin"])
        if profile.get("chinBottomRatioMin") is not None
        else None
    )
    thresholds["chinBottomMax"] = (
        float(profile["chinBottomRatioMax"])
        if profile.get("chinBottomRatioMax") is not None
        else None
    )
    return thresholds


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
    metrics: Dict[str, object] | None = None,
) -> Dict[str, float]:
    import os
    composed_mask = None
    if metrics:
        mask_path = metrics.get("composedMaskPath")
        if mask_path and os.path.exists(mask_path):
            try:
                composed_mask = Image.open(mask_path).convert("L")
            except Exception:
                pass

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
    skin_like = (
        (rgb[:, :, 0] > 92)
        & (rgb[:, :, 1] > 52)
        & (rgb[:, :, 2] > 38)
        & (rgb[:, :, 0] >= rgb[:, :, 1] - 8)
        & (rgb[:, :, 1] >= rgb[:, :, 2] - 8)
        & (rgb[:, :, 0] > rgb[:, :, 2] + 12)
        & (sat > 16)
        & (brightness < 245)
    )

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
    # Skin at the ear/forehead/cheek boundary is naturally bright and can be
    # low-saturation on gray backgrounds.  Only protect inner foreground skin;
    # outer-band pixels remain strict so true background residue still fails.
    skin_edge_protect = skin_like & inner_band.astype(bool) & hair_region
    white_halo = white_halo & ~skin_edge_protect
    gray_halo = gray_halo & ~skin_edge_protect
    if composed_mask:
        mask_arr = np.asarray(composed_mask)
        if max_y:
            mask_arr = mask_arr[:max(2, min(mask_arr.shape[0], int(max_y))), :]
        gray_halo = gray_halo & (mask_arr < 220)
        white_halo = white_halo & (mask_arr < 220)

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


def _face_background_hole_metrics(
    image: Image.Image,
    expected_rgb: Tuple[int, int, int],
    metrics: Dict[str, object],
) -> Dict[str, float]:
    face_box = metrics.get("outputFaceBox") or {}
    width = int(float(face_box.get("width") or 0))
    height = int(float(face_box.get("height") or 0))
    if width <= 8 or height <= 8:
        return {
            "faceBackgroundHoleRatio": 0.0,
            "faceBackgroundHoleMaxComponentRatio": 0.0,
            "faceBackgroundHolePixels": 0,
            "faceBackgroundHoleMaxComponentPixels": 0,
        }

    img = image.convert("RGB")
    w, h = img.size
    left = max(0, int(float(face_box.get("x") or 0) + width * 0.22))
    top = max(0, int(float(face_box.get("y") or 0) + height * 0.15))
    right = min(w, int(float(face_box.get("x") or 0) + width * 0.78))
    bottom = min(h, int(float(face_box.get("y") or 0) + height * 0.85))
    if right <= left or bottom <= top:
        return {
            "faceBackgroundHoleRatio": 0.0,
            "faceBackgroundHoleMaxComponentRatio": 0.0,
            "faceBackgroundHolePixels": 0,
            "faceBackgroundHoleMaxComponentPixels": 0,
        }

    import os
    composed_mask = None
    mask_path = metrics.get("composedMaskPath")
    if mask_path and os.path.exists(mask_path):
        try:
            composed_mask = Image.open(mask_path).convert("L")
        except Exception:
            pass

    arr = np.asarray(img.crop((left, top, right, bottom))).astype(np.int16)
    mask_arr = None
    if composed_mask:
        mask_arr = np.asarray(composed_mask.crop((left, top, right, bottom)))

    bg = np.asarray(expected_rgb, dtype=np.int16)
    diff = np.linalg.norm(arr - bg, axis=2)
    close = (diff <= 28).astype("uint8")
    if mask_arr is not None:
        close = (close & (mask_arr < 240)).astype("uint8")

    # The bottom edge of the face box can touch shirt/collar; it is not part
    # of the facial skin surface.  Keep the check focused on the face core so
    # real collars or dark hair do not count as holes.
    core_h = close.shape[0]
    if core_h > 24:
        close[int(core_h * 0.88):, :] = 0

    # Red/blue backgrounds can be close to legitimate foreground details such
    # as lips, blush, glasses reflections, or clothing near the chin.  A true
    # matting hole is a flat, contiguous patch of the exact target background,
    # so require low local texture before counting it as a face hole.
    gray = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    mean = cv2.blur(gray.astype(np.float32), (5, 5))
    mean_sq = cv2.blur((gray.astype(np.float32) ** 2), (5, 5))
    local_std = np.sqrt(np.maximum(mean_sq - mean ** 2, 0.0))
    close = (close & (local_std < 4.5)).astype("uint8")

    hole_pixels = int(np.count_nonzero(close))
    area = max(1, close.shape[0] * close.shape[1])
    max_component = 0
    if hole_pixels:
        components, labels, stats, _ = cv2.connectedComponentsWithStats(close, 8)
        if components > 1:
            max_component = int(np.max(stats[1:, cv2.CC_STAT_AREA]))
    return {
        "faceBackgroundHoleRatio": round(hole_pixels / float(area), 6),
        "faceBackgroundHoleMaxComponentRatio": round(max_component / float(area), 6),
        "faceBackgroundHolePixels": hole_pixels,
        "faceBackgroundHoleMaxComponentPixels": max_component,
    }


def _black_back_panel_metrics(
    image: Image.Image,
    expected_rgb: Tuple[int, int, int],
    metrics: Dict[str, object],
) -> Dict[str, float]:
    face_box = metrics.get("outputFaceBox") or {}
    fw = float(face_box.get("width") or 0)
    fh = float(face_box.get("height") or 0)
    if fw <= 8 or fh <= 8:
        return {
            "blackBackPanelRatio": 0.0,
            "blackBackPanelMaxComponentRatio": 0.0,
            "blackBackPanelPixels": 0,
            "blackBackPanelMaxComponentPixels": 0,
            "backgroundOpaqueBlobRatio": 0.0,
            "nonHumanDarkPanelRatio": 0.0,
        }

    arr = np.asarray(image.convert("RGB")).astype(np.float32)
    h, w = arr.shape[:2]
    fx = float(face_box.get("x") or 0)
    fy = float(face_box.get("y") or 0)
    cx = fx + fw * 0.5
    yy, xx = np.indices((h, w))
    lateral = np.abs(xx - cx)
    brightness = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    bg = np.asarray(expected_rgb, dtype=np.float32).reshape(1, 1, 3)
    bg_dist = np.linalg.norm(arr - bg, axis=2)

    face_hair_protect = (
        ((xx - cx) / (fw * 0.72)) ** 2
        + ((yy - (fy + fh * 0.38)) / (fh * 0.96)) ** 2
        <= 1.0
    )
    central_neck_protect = (
        (lateral <= fw * 0.24)
        & (yy >= fy + fh * 0.72)
        & (yy <= fy + fh * 1.70)
    )
    lower_clothing_protect = yy >= fy + fh * 1.06
    pocket = (
        (yy >= fy - fh * 0.22)
        & (yy <= fy + fh * 1.08)
        & (lateral >= fw * 0.30)
        & (lateral <= fw * 1.34)
        & ~face_hair_protect
        & ~central_neck_protect
        & ~lower_clothing_protect
    )
    side_neck_panel = (
        (yy >= fy + fh * 0.55)
        & (yy <= fy + fh * 1.06)
        & (lateral >= fw * 0.26)
        & (lateral <= fw * 1.30)
        & ~central_neck_protect
        & ~lower_clothing_protect
    )
    import os
    composed_mask = None
    mask_path = metrics.get("composedMaskPath")
    if mask_path and os.path.exists(mask_path):
        try:
            composed_mask = Image.open(mask_path).convert("L")
        except Exception:
            pass

    panel = (
        (pocket | side_neck_panel)
        & (bg_dist > 35.0)
        & (brightness < 72.0)
        & (chroma < 88.0)
    )
    if composed_mask:
        mask_arr = np.asarray(composed_mask)
        panel = panel & (mask_arr < 180)

    panel_u8 = cv2.morphologyEx(panel.astype("uint8"), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    panel_u8 = cv2.morphologyEx(panel_u8, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8), iterations=1)
    pixels = int(np.count_nonzero(panel_u8))
    max_component = 0
    if pixels:
        n, _, stats, _ = cv2.connectedComponentsWithStats(panel_u8, 8)
        if n > 1:
            max_component = int(np.max(stats[1:, cv2.CC_STAT_AREA]))
    area = max(1, w * h)
    return {
        "blackBackPanelRatio": round(pixels / float(area), 6),
        "blackBackPanelMaxComponentRatio": round(max_component / float(area), 6),
        "blackBackPanelPixels": pixels,
        "blackBackPanelMaxComponentPixels": max_component,
        "backgroundOpaqueBlobRatio": round(max_component / float(area), 6),
        "nonHumanDarkPanelRatio": round(max_component / float(area), 6),
    }


def _side_residual_artifact_metrics(
    image: Image.Image,
    expected_rgb: Tuple[int, int, int],
    metrics: Dict[str, object],
) -> Dict[str, float]:
    face_box = metrics.get("outputFaceBox") or {}
    fw = float(face_box.get("width") or 0)
    fh = float(face_box.get("height") or 0)
    if fw <= 8 or fh <= 8:
        return {
            "sideBoundaryLinePixels": 0,
            "sideBoundaryLineMaxComponentPixels": 0,
            "sideBoundaryLineRatio": 0.0,
            "sideResidualArtifactPixels": 0,
            "sideResidualArtifactMaxComponentPixels": 0,
            "sideResidualArtifactRatio": 0.0,
        }

    arr = np.asarray(image.convert("RGB")).astype(np.float32)
    h, w = arr.shape[:2]
    fx = float(face_box.get("x") or 0)
    fy = float(face_box.get("y") or 0)
    cx = fx + fw * 0.5
    yy, xx = np.indices((h, w))
    lateral = np.abs(xx - cx)
    brightness = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    bg = np.asarray(expected_rgb, dtype=np.float32)
    bg_dist = np.linalg.norm(arr - bg, axis=2)
    near_bg = cv2.dilate((bg_dist <= 38.0).astype("uint8"), np.ones((13, 13), np.uint8), iterations=1).astype(bool)

    face_core = (
        ((xx - cx) / (fw * 0.72)) ** 2
        + ((yy - (fy + fh * 0.58)) / (fh * 0.98)) ** 2
        <= 1.0
    )
    central_neck = (
        (lateral <= fw * 0.16)
        & (yy >= fy + fh * 0.74)
        & (yy <= fy + fh * 1.62)
    )
    skin_like = (
        (arr[:, :, 0] > 92)
        & (arr[:, :, 1] > 48)
        & (arr[:, :, 2] > 34)
        & (arr[:, :, 0] >= arr[:, :, 1] - 8)
        & (arr[:, :, 1] >= arr[:, :, 2] - 8)
        & (arr[:, :, 0] > arr[:, :, 2] + 14)
        & (chroma > 20.0)
        & (brightness < 245.0)
    )
    side_zone = (
        (yy >= fy + fh * 0.54)
        & (yy <= fy + fh * 1.86)
        & (lateral >= fw * 0.18)
        & (lateral <= fw * 1.92)
        & ~face_core
        & ~central_neck
        & ~skin_like
        & near_bg
        & (bg_dist > 42.0)
    )
    line_seed = side_zone & (brightness < 126.0) & (chroma < 172.0)
    texture_seed = (
        side_zone
        & (yy >= fy + fh * 1.18)
        & (lateral >= fw * 0.70)
        & (
            ((brightness < 82.0) & (chroma < 150.0))
            | ((brightness > 196.0) & (chroma < 78.0))
            | (chroma > 88.0)
        )
    )

    def summarize(seed: np.ndarray, max_area: int) -> Tuple[int, int]:
        seed_u8 = cv2.morphologyEx(seed.astype("uint8"), cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8), iterations=1)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(seed_u8, 8)
        pixels = 0
        max_component = 0
        for label in range(1, n):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < 4 or area > max_area:
                continue
            x = int(stats[label, cv2.CC_STAT_LEFT])
            y = int(stats[label, cv2.CC_STAT_TOP])
            cw = int(stats[label, cv2.CC_STAT_WIDTH])
            ch = int(stats[label, cv2.CC_STAT_HEIGHT])
            density = float(area) / float(max(1, cw * ch))
            elongated = cw >= max(8, ch * 2.0) or ch >= max(8, cw * 2.0)
            diagonal = density <= 0.64 and cw >= max(8, int(fw * 0.08)) and ch >= max(8, int(fh * 0.08))
            side_anchored = x <= int(cx - fw * 0.88) or (x + cw) >= int(cx + fw * 0.88)
            upper = y <= int(fy + fh * 1.92)
            if upper and (elongated or diagonal or side_anchored):
                pixels += area
                max_component = max(max_component, area)
        return pixels, max_component

    line_pixels, line_max = summarize(line_seed, 1400)
    residual_pixels, residual_max = summarize(texture_seed, 1200)
    area = max(1, w * h)
    return {
        "sideBoundaryLinePixels": int(line_pixels),
        "sideBoundaryLineMaxComponentPixels": int(line_max),
        "sideBoundaryLineRatio": round(line_pixels / float(area), 6),
        "sideResidualArtifactPixels": int(residual_pixels),
        "sideResidualArtifactMaxComponentPixels": int(residual_max),
        "sideResidualArtifactRatio": round(residual_pixels / float(area), 6),
    }


def _hair_background_hole_metrics(
    image: Image.Image,
    expected_rgb: Tuple[int, int, int],
    metrics: Dict[str, object],
) -> Dict[str, float]:
    face_box = metrics.get("outputFaceBox") or {}
    fw = float(face_box.get("width") or 0)
    fh = float(face_box.get("height") or 0)
    if fw <= 8 or fh <= 8:
        return {
            "hairBackgroundHolePixels": 0,
            "hairBackgroundHoleMaxComponentPixels": 0,
            "hairBackgroundHoleRatio": 0.0,
        }

    arr = np.asarray(image.convert("RGB")).astype(np.float32)
    h, w = arr.shape[:2]
    foreground_mask = np.ones((h, w), dtype=bool)
    mask_path = metrics.get("composedMaskPath")
    if isinstance(mask_path, str) and mask_path and os.path.exists(mask_path):
        try:
            mask = Image.open(mask_path).convert("L")
            if mask.size != (w, h):
                mask = mask.resize((w, h), Image.Resampling.BILINEAR)
            foreground_mask = np.asarray(mask) > 18
        except Exception:
            foreground_mask = np.ones((h, w), dtype=bool)
    fx = float(face_box.get("x") or 0)
    fy = float(face_box.get("y") or 0)
    cx = fx + fw * 0.5
    yy, xx = np.indices((h, w))
    lateral = np.abs(xx - cx)
    brightness = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    bg = np.asarray(expected_rgb, dtype=np.float32)
    bg_dist = np.linalg.norm(arr - bg, axis=2)

    hair_zone = (
        (yy >= fy - fh * 0.20)
        & (yy <= fy + fh * 0.66)
        & (lateral <= fw * 1.08)
    )
    face_core = (
        ((xx - cx) / (fw * 0.48)) ** 2
        + ((yy - (fy + fh * 0.57)) / (fh * 0.72)) ** 2
        <= 1.0
    )
    dark_hair = (
        hair_zone
        & foreground_mask
        & (brightness < 122.0)
        & (chroma <= 148.0)
    )
    if int(np.count_nonzero(dark_hair)) < 24:
        return {
            "hairBackgroundHolePixels": 0,
            "hairBackgroundHoleMaxComponentPixels": 0,
            "hairBackgroundHoleRatio": 0.0,
        }

    row_has = np.any(dark_hair, axis=1)
    left = np.argmax(dark_hair, axis=1)
    right = w - 1 - np.argmax(dark_hair[:, ::-1], axis=1)
    interior_margin = max(3, int(fw * 0.035))
    inside_hair_span = row_has[:, None] & (xx >= left[:, None]) & (xx <= right[:, None])
    inside_hair_core = row_has[:, None] & (xx >= left[:, None] + interior_margin) & (xx <= right[:, None] - interior_margin)
    close_size = max(9, int(fw * 0.16) | 1)
    hair_envelope = cv2.morphologyEx(
        dark_hair.astype("uint8"),
        cv2.MORPH_CLOSE,
        np.ones((close_size, close_size), np.uint8),
        iterations=1,
    ).astype(bool)
    hair_envelope = cv2.dilate(hair_envelope.astype("uint8"), np.ones((5, 5), np.uint8), iterations=1).astype(bool)
    near_hair = cv2.dilate(dark_hair.astype("uint8"), np.ones((9, 9), np.uint8), iterations=1).astype(bool)
    seed = (
        hair_zone
        & hair_envelope
        & near_hair
        & inside_hair_span
        & inside_hair_core
        & ~foreground_mask
        & ~face_core
    )
    seed_u8 = cv2.morphologyEx(seed.astype("uint8"), cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8), iterations=1)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(seed_u8, 8)
    pixels = 0
    max_component = 0
    for label in range(1, n):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < 3 or area > max(900, int(h * w * 0.02)):
            continue
        pixels += area
        max_component = max(max_component, area)
    area_total = max(1, w * h)
    return {
        "hairBackgroundHolePixels": int(pixels),
        "hairBackgroundHoleMaxComponentPixels": int(max_component),
        "hairBackgroundHoleRatio": round(pixels / float(area_total), 6),
    }


def _body_alpha_hole_metrics(
    image: Image.Image,
    expected_rgb: Tuple[int, int, int],
    metrics: Dict[str, object],
) -> Dict[str, float]:
    face_box = metrics.get("outputFaceBox") or {}
    fw = float(face_box.get("width") or 0)
    fh = float(face_box.get("height") or 0)
    if fw <= 8 or fh <= 8:
        return {
            "shoulderAlphaMissingRatio": 0.0,
            "clothingAlphaMissingRatio": 0.0,
            "bodyRegionBackgroundHoleRatio": 0.0,
            "torsoCutoutRatio": 0.0,
            "leftShoulderCutoutRatio": 0.0,
            "rightShoulderCutoutRatio": 0.0,
            "foregroundCompletenessRatio": 1.0,
            "humanBodyConnectedComponentRatio": 1.0,
            "bodyBackgroundHoleMaxComponentPixels": 0,
        }

    import os
    mask_arr = None
    mask_path = metrics.get("composedMaskPath")
    if mask_path and os.path.exists(mask_path):
        try:
            mask_arr = np.asarray(Image.open(mask_path).convert("L"))
        except Exception:
            mask_arr = None

    arr = np.asarray(image.convert("RGB")).astype(np.float32)
    h, w = arr.shape[:2]
    fx = float(face_box.get("x") or 0)
    fy = float(face_box.get("y") or 0)
    cx = fx + fw * 0.5
    yy, xx = np.indices((h, w))
    lateral = np.abs(xx - cx)

    torso_zone = (
        (yy >= fy + fh * 1.22)
        & (yy <= fy + fh * 2.45)
        & (lateral <= fw * 0.78)
    )
    left_shoulder_zone = (
        (yy >= fy + fh * 1.30)
        & (yy <= fy + fh * 2.42)
        & (xx >= cx - fw * 1.72)
        & (xx <= cx - fw * 0.36)
    )
    right_shoulder_zone = (
        (yy >= fy + fh * 1.30)
        & (yy <= fy + fh * 2.42)
        & (xx >= cx + fw * 0.36)
        & (xx <= cx + fw * 1.72)
    )
    body_zone = torso_zone | left_shoulder_zone | right_shoulder_zone
    body_area = max(1, int(np.count_nonzero(body_zone)))

    bg = np.asarray(expected_rgb, dtype=np.float32)
    diff = np.linalg.norm(arr - bg, axis=2)
    gray = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    mean = cv2.blur(gray.astype(np.float32), (5, 5))
    mean_sq = cv2.blur(gray.astype(np.float32) ** 2, (5, 5))
    local_std = np.sqrt(np.maximum(mean_sq - mean ** 2, 0.0))
    bg_like_hole = (diff <= 28.0) & (local_std < 5.5)
    if mask_arr is not None and mask_arr.shape == (h, w):
        fg = mask_arr > 48
        row_has_fg = np.any(fg, axis=1)
        left = np.argmax(fg, axis=1)
        right = w - 1 - np.argmax(fg[:, ::-1], axis=1)
        inside_foreground_span = (
            row_has_fg[:, None]
            & (xx >= left[:, None])
            & (xx <= right[:, None])
        )
        # Natural empty space outside the shoulder line is expected in ID-photo
        # crops.  Only count background-colored pixels that are inside the row
        # silhouette span; otherwise normal space around sloped shoulders is
        # incorrectly reported as clothing/alpha loss.
        missing = body_zone & (mask_arr < 64) & bg_like_hole & inside_foreground_span
    else:
        missing = body_zone & bg_like_hole

    left_area = max(1, int(np.count_nonzero(left_shoulder_zone)))
    right_area = max(1, int(np.count_nonzero(right_shoulder_zone)))
    torso_area = max(1, int(np.count_nonzero(torso_zone)))
    body_missing = int(np.count_nonzero(missing))
    max_component = 0
    if body_missing:
        n, _, stats, _ = cv2.connectedComponentsWithStats(missing.astype("uint8"), 8)
        if n > 1:
            max_component = int(np.max(stats[1:, cv2.CC_STAT_AREA]))

    fg_component_ratio = 1.0
    if mask_arr is not None and mask_arr.shape == (h, w):
        fg = (mask_arr > 48).astype("uint8")
        total = int(np.count_nonzero(fg))
        if total > 0:
            n, _, stats, _ = cv2.connectedComponentsWithStats(fg, 8)
            largest = int(np.max(stats[1:, cv2.CC_STAT_AREA])) if n > 1 else total
            fg_component_ratio = largest / float(max(1, total))

    shoulder_missing = max(
        float(np.count_nonzero(missing & left_shoulder_zone)) / left_area,
        float(np.count_nonzero(missing & right_shoulder_zone)) / right_area,
    )
    clothing_missing = body_missing / float(body_area)
    return {
        "shoulderAlphaMissingRatio": round(shoulder_missing, 6),
        "clothingAlphaMissingRatio": round(clothing_missing, 6),
        "bodyRegionBackgroundHoleRatio": round(clothing_missing, 6),
        "torsoCutoutRatio": round(float(np.count_nonzero(missing & torso_zone)) / torso_area, 6),
        "leftShoulderCutoutRatio": round(float(np.count_nonzero(missing & left_shoulder_zone)) / left_area, 6),
        "rightShoulderCutoutRatio": round(float(np.count_nonzero(missing & right_shoulder_zone)) / right_area, 6),
        "foregroundCompletenessRatio": round(max(0.0, 1.0 - clothing_missing), 6),
        "humanBodyConnectedComponentRatio": round(fg_component_ratio, 6),
        "bodyBackgroundHoleMaxComponentPixels": max_component,
    }


def _bottom_watermark_metrics(
    image: Image.Image,
    expected_rgb: Tuple[int, int, int],
    metrics: Dict[str, object],
) -> Dict[str, float]:
    import os
    composed_mask = None
    mask_path = metrics.get("composedMaskPath")
    if mask_path and os.path.exists(mask_path):
        try:
            composed_mask = Image.open(mask_path).convert("L")
        except Exception:
            pass

    arr = np.asarray(image.convert("RGB")).astype(np.float32)
    h, w = arr.shape[:2]
    bg = np.asarray(expected_rgb, dtype=np.float32)
    yy, xx = np.indices((h, w))
    bg_dist = np.linalg.norm(arr - bg, axis=2)
    brightness = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    region = (yy >= int(h * 0.80)) & (xx >= int(w * 0.54))
    # Bottom-right watermarks are usually compact bright/blue/white text or a
    # small logo.  Dark suit pixels are ignored so normal clothing can stay.
    residual = region & (bg_dist > 34.0) & (brightness > 92.0) & (chroma < 150.0)
    if composed_mask:
        mask_arr = np.asarray(composed_mask)
        residual = residual & (mask_arr < 180)

    residual_u8 = cv2.morphologyEx(residual.astype("uint8"), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8), iterations=1)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(residual_u8, 8)
    
    # Identify foreground (clothing/person) in the bottom-right region
    fg = region & (bg_dist > 15.0)
    fg_u8 = fg.astype("uint8")
    n_fg, labels_fg, stats_fg, _ = cv2.connectedComponentsWithStats(fg_u8, 8)
    
    clothing_mask = np.zeros_like(residual_u8)
    for label in range(1, n_fg):
        area = int(stats_fg[label, cv2.CC_STAT_AREA])
        if area > 300:
            clothing_mask[labels_fg == label] = 255
            
    if np.any(clothing_mask):
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        dilated_clothing = cv2.dilate(clothing_mask, kernel)
    else:
        dilated_clothing = np.zeros_like(residual_u8)
        
    small_pixels = 0
    components = 0
    max_component = 0
    for label in range(1, n):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area > 300:
            continue
        # Check overlap with dilated clothing region
        component_mask = (labels == label)
        if np.any(component_mask & (dilated_clothing > 0)):
            continue
        max_component = max(max_component, area)
        if 2 <= area <= 220:
            small_pixels += area
            components += 1
    region_area = max(1, int(np.count_nonzero(region)))
    return {
        "bottomRightTextResidual": small_pixels,
        "watermarkResidualRatio": round(small_pixels / float(region_area), 6),
        "bottomWatermarkResidualRatio": round(small_pixels / float(region_area), 6),
        "watermarkLikeComponentRatio": round(max_component / float(region_area), 6),
        "watermarkLikeComponents": components,
    }


def build_quality_report(
    image_path,
    width_px,
    height_px,
    bg_color,
    metrics=None,
    debug=None,
    composition_profile=None,
):
    metrics = metrics or {}
    debug = debug or {}
    checks: Dict[str, object] = {}
    fail_reasons: List[str] = []
    score = 100

    try:
        image = Image.open(image_path).convert("RGB")
    except Exception:
        split = split_quality_fail_reasons(["BACKGROUND_COMPOSE_FAILED"])
        return {
            "passed": False,
            "mattingPass": True,
            "cropPass": True,
            "score": 0,
            "checks": {},
            "failReasons": ["BACKGROUND_COMPOSE_FAILED"],
            **split,
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
    halo = _edge_halo_metrics(image, expected_rgb, foreground_box, halo_max_y, metrics)
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
    face_holes = _face_background_hole_metrics(image, expected_rgb, metrics)
    checks.update(face_holes)
    body_holes = _body_alpha_hole_metrics(image, expected_rgb, metrics)
    checks.update(body_holes)
    black_panel = _black_back_panel_metrics(image, expected_rgb, metrics)
    checks.update(black_panel)
    side_residual = _side_residual_artifact_metrics(image, expected_rgb, metrics)
    checks.update(side_residual)
    hair_holes = _hair_background_hole_metrics(image, expected_rgb, metrics)
    checks.update(hair_holes)
    watermark = _bottom_watermark_metrics(image, expected_rgb, metrics)
    checks.update(watermark)
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
    face_hole_failed = (
        not pure_white_bg
        and (
            face_holes["faceBackgroundHoleRatio"] > 0.012
            or face_holes["faceBackgroundHoleMaxComponentRatio"] > 0.004
            or face_holes["faceBackgroundHoleMaxComponentPixels"] > 48
        )
    )
    if face_hole_failed:
        fail_reasons.append("ID_PHOTO_FACE_BACKGROUND_HOLE")
        score -= 30
    body_alpha_failed = (
        body_holes["shoulderAlphaMissingRatio"] > 0.36
        or body_holes["clothingAlphaMissingRatio"] > 0.24
        or body_holes["bodyRegionBackgroundHoleRatio"] > 0.24
        or body_holes["torsoCutoutRatio"] > 0.18
        or body_holes["bodyBackgroundHoleMaxComponentPixels"] > 520
        or body_holes["humanBodyConnectedComponentRatio"] < 0.94
    )
    if body_alpha_failed:
        fail_reasons.append("ID_PHOTO_BODY_ALPHA_MISSING")
        score -= 34
    black_panel_failed = (
        black_panel["blackBackPanelRatio"] > 0.006
        or black_panel["blackBackPanelMaxComponentRatio"] > 0.0035
        or black_panel["blackBackPanelMaxComponentPixels"] > 420
    )
    if black_panel_failed:
        fail_reasons.append("ID_PHOTO_BLACK_BACK_PANEL")
        score -= 34
    background_sheet_signal = float(metrics.get("remainingBackgroundSheetRatio") or 0) > 0.006
    head_side_signal = float(metrics.get("remainingHeadSideBackgroundRatio") or 0) > 0.003
    # Neutral gray is close to low-saturation clothing edges, so component size
    # alone is not enough evidence of retained source background.
    side_residual_max_limit = 900 if neutral_gray_bg else 520
    side_residual_failed = (
        side_residual["sideBoundaryLineMaxComponentPixels"] > 760
        or side_residual["sideResidualArtifactMaxComponentPixels"] > side_residual_max_limit
        or (side_residual["sideBoundaryLineMaxComponentPixels"] > 520 and head_side_signal)
        or (side_residual["sideResidualArtifactMaxComponentPixels"] > 260 and background_sheet_signal)
        or (side_residual["sideResidualArtifactPixels"] > 900 and (background_sheet_signal or head_side_signal))
    )
    if side_residual_failed:
        fail_reasons.append("ID_PHOTO_SIDE_BACKGROUND_RESIDUAL")
        score -= 34
    trusted_model_alpha = bool(metrics.get("trustedAlpha")) and metrics.get("mattingModel") == "birefnet-v1-lite"
    checks["trustedModelAlpha"] = trusted_model_alpha
    hair_hole_failed = not trusted_model_alpha and (
        hair_holes["hairBackgroundHoleMaxComponentPixels"] > 18
        or hair_holes["hairBackgroundHolePixels"] > 64
    )
    if hair_hole_failed:
        fail_reasons.append("ID_PHOTO_HAIR_BACKGROUND_HOLE")
        score -= 34
    watermark_failed = (
        watermark["bottomRightTextResidual"] > 32
        and watermark["watermarkLikeComponents"] >= 3
    )
    if watermark_failed:
        fail_reasons.append("ID_PHOTO_BOTTOM_WATERMARK_RESIDUAL")
        score -= 24

    top = float(metrics.get("topPaddingRatio") or 0)
    bottom = float(metrics.get("bottomPaddingRatio") or 0)
    head_h = float(metrics.get("headHeightRatio") or metrics.get("headRatio") or 0)
    profile = composition_profile or metrics.get("compositionProfile") or {}
    use_profile_head_width = (
        profile.get("headWidthRatioMin") is not None
        or profile.get("headWidthRatioMax") is not None
    )
    head_w = float(
        (metrics.get("profileHeadWidthRatio") if use_profile_head_width else None)
        or metrics.get("headWidthRatio")
        or 0
    )
    shoulder = float(metrics.get("shoulderWidthRatio") or metrics.get("foregroundWidthRatio") or 0)
    center = float(metrics.get("faceCenterOffset") or 0)
    fg_h = float(metrics.get("foregroundHeightRatio") or 0)
    side_safety = float(metrics.get("sideSafetyRatio") or 0)
    bottom_safety = float(metrics.get("bottomSafetyRatio") or bottom)
    subject_within_canvas = metrics.get("subjectWithinCanvas") is not False

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
        "shoulderTouchEdge": shoulder > float(profile.get("shoulderWidthRatioMax") or 1.0),
        "subjectWithinCanvas": subject_within_canvas,
        "sideSafetyRatio": round(side_safety, 4),
        "bottomSafetyRatio": round(bottom_safety, 4),
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
    matting_failed = not trusted_model_alpha and (
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

    thresholds = _composition_thresholds(int(width_px), int(height_px), profile)
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
    require(subject_within_canvas, "ID_PHOTO_SUBJECT_OUTSIDE_CANVAS", 20)
    require(side_safety >= thresholds["sideSafetyMin"], "ID_PHOTO_SIDE_SAFETY_BAD", 8)
    require(bottom_safety >= thresholds["bottomSafetyMin"], "ID_PHOTO_BOTTOM_PADDING_BAD", 8)
    chin_bottom = float(metrics.get("chinBottomRatio") or 0)
    checks["chinBottomRatio"] = round(chin_bottom, 4)
    if thresholds.get("chinBottomMin") is not None:
        require(chin_bottom >= thresholds["chinBottomMin"], "ID_PHOTO_BOTTOM_PADDING_BAD", 8)
    if thresholds.get("chinBottomMax") is not None:
        require(chin_bottom <= thresholds["chinBottomMax"], "ID_PHOTO_BOTTOM_PADDING_BAD", 8)
    require(checks["usedForegroundPng"], "ID_PHOTO_USED_FOREGROUND_MISSING", 20)
    # Cleanup composedMaskPath in normal production requests. Verification can
    # keep this file for pixel-level alpha diagnostics.
    mask_path = metrics.get("composedMaskPath")
    if mask_path and os.path.exists(mask_path) and os.environ.get("ID_PHOTO_KEEP_COMPOSED_MASK") != "1":
        try:
            os.remove(mask_path)
        except Exception:
            pass

    split = split_quality_fail_reasons(fail_reasons)
    matting_pass = not split["mattingFailReasons"]
    crop_pass = not split["cropFailReasons"]
    output_pass = not split["outputFailReasons"]
    fast_result_usable = matting_pass and output_pass
    status = "PASS"
    if not (matting_pass and crop_pass and output_pass):
        status = "FAIL"
    elif split["fastWarningReasons"]:
        status = "FAST_WARNING"
    return {
        "passed": matting_pass and crop_pass and output_pass,
        "status": status,
        "mattingPass": matting_pass,
        "cropPass": crop_pass,
        "fastResultUsable": fast_result_usable,
        "detailRecommended": bool(split["fastWarningReasons"]),
        "detailReasons": split["fastWarningReasons"],
        "score": max(0, min(100, round(score, 2))),
        "checks": checks,
        "failReasons": fail_reasons,
        **split,
        "metrics": {
            **metrics,
            "backgroundEdgeBadSamples": edge_bad,
            **halo,
            **face_holes,
            **body_holes,
            **black_panel,
            **side_residual,
            **watermark,
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


def validate_composition_metrics(metrics, composition_profile=None, width_px=295, height_px=413):
    if not metrics:
        return {
            "success": False,
            "code": "BACKGROUND_COMPOSE_FAILED",
            "message": "底色生成失败，请重新选择底色或重新上传照片。",
        }
    thresholds = _composition_thresholds(width_px, height_px, composition_profile)
    failures = []
    top = float(metrics.get("topPaddingRatio") or 0)
    head_h = float(metrics.get("headHeightRatio") or metrics.get("headRatio") or 0)
    profile = composition_profile or metrics.get("compositionProfile") or {}
    use_profile_head_width = (
        profile.get("headWidthRatioMin") is not None
        or profile.get("headWidthRatioMax") is not None
    )
    head_w = float(
        (metrics.get("profileHeadWidthRatio") if use_profile_head_width else None)
        or metrics.get("headWidthRatio")
        or 0
    )
    shoulder = float(metrics.get("shoulderWidthRatio") or metrics.get("foregroundWidthRatio") or 0)
    center = float(metrics.get("faceCenterOffset") or 0)
    side_safety = float(metrics.get("sideSafetyRatio") or 0)
    bottom_safety = float(metrics.get("bottomSafetyRatio") or metrics.get("bottomPaddingRatio") or 0)
    subject_within_canvas = metrics.get("subjectWithinCanvas") is not False
    if top < thresholds["topMin"]:
        failures.extend(["ID_PHOTO_TOP_PADDING_BAD", "ID_PHOTO_TOP_PADDING_TOO_SMALL"])
    elif top > thresholds["topMax"]:
        failures.extend(["ID_PHOTO_TOP_PADDING_BAD", "ID_PHOTO_TOP_PADDING_TOO_LARGE"])
    if head_h < thresholds["headHeightMin"]:
        failures.extend(["ID_PHOTO_HEAD_SIZE_BAD", "ID_PHOTO_HEAD_TOO_SMALL"])
    elif head_h > thresholds["headHeightMax"]:
        failures.extend(["ID_PHOTO_HEAD_SIZE_BAD", "ID_PHOTO_HEAD_TOO_LARGE"])
    if not thresholds["headWidthMin"] <= head_w <= thresholds["headWidthMax"]:
        failures.append("ID_PHOTO_HEAD_WIDTH_BAD")
    if shoulder < thresholds["shoulderMin"]:
        failures.extend(["ID_PHOTO_SHOULDER_WIDTH_BAD", "ID_PHOTO_SHOULDER_TOO_NARROW"])
    elif shoulder > thresholds["shoulderMax"]:
        failures.extend(["ID_PHOTO_SHOULDER_WIDTH_BAD", "ID_PHOTO_SHOULDER_TOO_WIDE"])
    if center > thresholds["centerMax"]:
        failures.append("ID_PHOTO_FACE_NOT_CENTERED")
    if not subject_within_canvas:
        failures.append("ID_PHOTO_SUBJECT_OUTSIDE_CANVAS")
    if side_safety < thresholds["sideSafetyMin"]:
        failures.append("ID_PHOTO_SIDE_SAFETY_BAD")
    if bottom_safety < thresholds["bottomSafetyMin"]:
        failures.append("ID_PHOTO_BOTTOM_PADDING_BAD")
    if float(metrics.get("faceHeightRatio") or 0) < 0.20:
        failures.append("ID_PHOTO_FACE_TOO_SMALL")
    chin_bottom = float(metrics.get("chinBottomRatio") or 0)
    if thresholds.get("chinBottomMin") is not None and chin_bottom < thresholds["chinBottomMin"]:
        failures.append("ID_PHOTO_BOTTOM_PADDING_BAD")
    if thresholds.get("chinBottomMax") is not None and chin_bottom > thresholds["chinBottomMax"]:
        failures.append("ID_PHOTO_BOTTOM_PADDING_BAD")
    failures = list(dict.fromkeys(failures))
    return {
        "success": not failures,
        "cropPass": not failures,
        "cropFailReasons": failures,
        "code": failures[0] if failures else "",
        "message": "构图已按当前规格校验。" if not failures else "当前照片构图不符合所选规格。",
        "targetRange": thresholds,
    }
