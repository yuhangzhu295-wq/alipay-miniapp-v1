"""Portrait matting for ID-photo generation.

Preferred future engine: MODNet. Current production engine: rembg
u2net_human_seg with OpenCV mask post-processing.
"""
from io import BytesIO
import os
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageOps


_REMBG_SESSION = None
_REMBG_MODEL = None
_REMBG_ERROR = None
_MODNET_ERROR = "MODNet is not configured; fallback to rembg"


def _read_rgba(image_input):
    if isinstance(image_input, bytes):
        img = Image.open(BytesIO(image_input))
    else:
        img = Image.open(image_input)
    return ImageOps.exif_transpose(img).convert("RGBA")


def _get_rembg_session():
    global _REMBG_SESSION, _REMBG_MODEL, _REMBG_ERROR
    if _REMBG_SESSION is not None:
        return _REMBG_SESSION
    if _REMBG_ERROR:
        return None
    try:
        from rembg import new_session

        for model in ("u2net_human_seg", "u2net", "isnet-general-use"):
            try:
                _REMBG_SESSION = new_session(model)
                _REMBG_MODEL = model
                print(f"[id-photo] rembg session ready model={model}", flush=True)
                return _REMBG_SESSION
            except Exception as exc:
                _REMBG_ERROR = str(exc)
                print(f"[id-photo] rembg model failed model={model}: {exc}", flush=True)
        return None
    except Exception as exc:
        _REMBG_ERROR = str(exc)
        print(f"[id-photo] rembg unavailable: {exc}", flush=True)
        return None


def _remove_small_components(binary, face_box):
    h, w = binary.shape[:2]
    n, labels, stats, _ = cv2.connectedComponentsWithStats((binary > 0).astype("uint8"), 8)
    if n <= 1:
        return binary
    keep_label = 0
    if face_box:
        cx = int(face_box["x"] + face_box["width"] / 2)
        cy = int(face_box["y"] + face_box["height"] / 2)
        cx = int(np.clip(cx, 0, w - 1))
        cy = int(np.clip(cy, 0, h - 1))
        keep_label = int(labels[cy, cx])
    if keep_label <= 0:
        keep_label = int(1 + np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    keep = np.zeros_like(binary)
    keep[labels == keep_label] = 255
    return keep


def _face_values(face_box):
    if not face_box:
        return None
    fx = float(face_box.get("x") or 0)
    fy = float(face_box.get("y") or 0)
    fw = max(1.0, float(face_box.get("width") or 1))
    fh = max(1.0, float(face_box.get("height") or 1))
    return fx, fy, fw, fh, fx + fw * 0.5


def _subject_prior(shape, face_box, extra_dilate=0):
    """Build a permissive head/shoulder prior from the detected face.

    Rembg occasionally returns a single connected mask that contains both the
    person and a large piece of the original wall.  Connected-component cleanup
    cannot remove that because it is attached to hair or shoulders.  The prior
    marks where a valid ID-photo subject can reasonably exist without hard
    coding any sample image.
    """
    h, w = shape[:2]
    allowed = np.ones((h, w), dtype=bool)
    core = np.zeros((h, w), dtype=bool)
    if not face_box:
        return allowed, core, {
            "hasFacePrior": False,
            "allowedRatio": 1.0,
            "coreRatio": 0.0,
        }

    fx, fy, fw, fh, cx = _face_values(face_box)
    yy, xx = np.indices((h, w))

    head_cy = fy + fh * 0.47
    head = (((xx - cx) / (fw * 1.12)) ** 2 + ((yy - head_cy) / (fh * 1.24)) ** 2) <= 1.0
    hair = (
        (xx >= cx - fw * 1.38)
        & (xx <= cx + fw * 1.38)
        & (yy >= fy - fh * 0.62)
        & (yy <= fy + fh * 2.10)
    )
    neck = (
        (xx >= cx - fw * 0.42)
        & (xx <= cx + fw * 0.42)
        & (yy >= fy + fh * 0.78)
        & (yy <= fy + fh * 1.62)
    )

    torso = np.zeros((h, w), dtype=np.uint8)
    y_top = int(np.clip(fy + fh * 1.05, 0, h - 1))
    y_mid = int(np.clip(fy + fh * 1.78, 0, h - 1))
    y_bottom = int(np.clip(fy + fh * 3.10, 0, h - 1))
    shoulder = fw * 2.25
    waist = fw * 1.62
    points = np.array(
        [
            [int(cx - fw * 0.64), y_top],
            [int(cx + fw * 0.64), y_top],
            [int(cx + shoulder), y_mid],
            [int(cx + waist), y_bottom],
            [int(cx - waist), y_bottom],
            [int(cx - shoulder), y_mid],
        ],
        dtype=np.int32,
    )
    points[:, 0] = np.clip(points[:, 0], 0, w - 1)
    points[:, 1] = np.clip(points[:, 1], 0, h - 1)
    cv2.fillPoly(torso, [points], 1)

    allowed = head | hair | neck | (torso > 0)
    if extra_dilate:
        k = max(3, int(extra_dilate) | 1)
        allowed = cv2.dilate(allowed.astype("uint8"), np.ones((k, k), np.uint8), iterations=1) > 0

    face_core = (((xx - cx) / (fw * 0.56)) ** 2 + ((yy - (fy + fh * 0.52)) / (fh * 0.72)) ** 2) <= 1.0
    neck_core = (
        (xx >= cx - fw * 0.26)
        & (xx <= cx + fw * 0.26)
        & (yy >= fy + fh * 0.78)
        & (yy <= fy + fh * 1.30)
    )
    core = face_core | neck_core
    return allowed, core, {
        "hasFacePrior": True,
        "allowedRatio": round(float(np.count_nonzero(allowed)) / float(max(1, h * w)), 6),
        "coreRatio": round(float(np.count_nonzero(core)) / float(max(1, h * w)), 6),
    }


def _grabcut_subject_mask(image, raw_alpha, face_box, allowed, core):
    if image is None or not face_box:
        return None, {"grabCutUsed": False, "grabCutReason": "missing_image_or_face"}

    try:
        rgb = np.asarray(image.convert("RGB"))
        h, w = raw_alpha.shape[:2]
        if rgb.shape[0] != h or rgb.shape[1] != w:
            return None, {"grabCutUsed": False, "grabCutReason": "shape_mismatch"}

        mask = np.full((h, w), cv2.GC_BGD, dtype=np.uint8)
        raw_probable = raw_alpha > 6
        high_conf = raw_alpha > 170
        mask[allowed & raw_probable] = cv2.GC_PR_FGD
        mask[allowed & high_conf] = cv2.GC_PR_FGD
        mask[core] = cv2.GC_FGD
        mask[~allowed] = cv2.GC_BGD
        mask[(raw_alpha <= 2) & ~core] = cv2.GC_BGD

        if int(np.count_nonzero(mask == cv2.GC_FGD)) < 16:
            return None, {"grabCutUsed": False, "grabCutReason": "not_enough_foreground_seed"}
        if int(np.count_nonzero(mask == cv2.GC_BGD)) < 16:
            return None, {"grabCutUsed": False, "grabCutReason": "not_enough_background_seed"}

        bgd = np.zeros((1, 65), np.float64)
        fgd = np.zeros((1, 65), np.float64)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        cv2.grabCut(bgr, mask, None, bgd, fgd, 3, cv2.GC_INIT_WITH_MASK)
        subject = (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)
        subject = subject & allowed
        subject = cv2.morphologyEx(subject.astype("uint8"), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1) > 0
        return subject.astype("uint8") * 255, {
            "grabCutUsed": True,
            "grabCutForegroundRatio": round(float(np.count_nonzero(subject)) / float(max(1, h * w)), 6),
        }
    except Exception as exc:
        return None, {"grabCutUsed": False, "grabCutReason": str(exc)}


def _subject_protection_mask(shape, face_box, core):
    protected = np.array(core, dtype=bool, copy=True)
    if not face_box:
        return protected

    h, w = shape[:2]
    fx, fy, fw, fh, cx = _face_values(face_box)
    yy, xx = np.indices((h, w))
    face_cy = fy + fh * 0.54
    face = (((xx - cx) / (fw * 0.78)) ** 2 + ((yy - face_cy) / (fh * 0.92)) ** 2) <= 1.0
    ears_and_jaw = (
        (xx >= cx - fw * 0.78)
        & (xx <= cx + fw * 0.78)
        & (yy >= fy - fh * 0.05)
        & (yy <= fy + fh * 1.12)
    )
    neck_and_center_chest = (
        (xx >= cx - fw * 0.58)
        & (xx <= cx + fw * 0.58)
        & (yy >= fy + fh * 0.78)
        & (yy <= fy + fh * 2.55)
    )
    protected |= face | ears_and_jaw | neck_and_center_chest
    return cv2.dilate(protected.astype("uint8"), np.ones((5, 5), np.uint8), iterations=1) > 0


def _inner_edge(fg, iterations=2):
    if not np.any(fg):
        return np.zeros_like(fg, dtype=bool)
    kernel = np.ones((3, 3), np.uint8)
    near_background = cv2.dilate((~fg).astype("uint8"), kernel, iterations=iterations) > 0
    return fg & near_background


def _source_background_profile(image, raw_alpha, allowed):
    rgb = np.asarray(image.convert("RGB")).astype(np.float32)
    h, w = raw_alpha.shape[:2]
    border = np.zeros((h, w), dtype=bool)
    pad = max(4, int(min(h, w) * 0.035))
    border[:pad, :] = True
    border[-pad:, :] = True
    border[:, :pad] = True
    border[:, -pad:] = True

    candidates = ((raw_alpha <= 8) & (border | ~allowed)) | (border & (raw_alpha <= 32))
    if int(np.count_nonzero(candidates)) < 64:
        candidates = raw_alpha <= 4
    if int(np.count_nonzero(candidates)) < 64:
        candidates = np.zeros((h, w), dtype=bool)
        corner = max(8, int(min(h, w) * 0.08))
        candidates[:corner, :corner] = True
        candidates[:corner, -corner:] = True
        candidates[-corner:, :corner] = True
        candidates[-corner:, -corner:] = True

    count = int(np.count_nonzero(candidates))
    if count <= 0:
        return rgb, np.array([245.0, 245.0, 245.0], dtype=np.float32), 0
    return rgb, np.median(rgb[candidates], axis=0).astype(np.float32), count


def _remove_background_sheets(binary, raw_alpha, image, face_box, allowed, core):
    debug = {
        "backgroundSheetRemovedPixels": 0,
        "backgroundSheetCandidateRatio": 0.0,
        "remainingBackgroundSheetRatio": 0.0,
        "headSideBackgroundRemovedPixels": 0,
        "remainingHeadSideBackgroundRatio": 0.0,
        "sourceBackgroundRgb": [],
        "sourceBackgroundSamples": 0,
    }
    if image is None or not face_box:
        debug["backgroundSheetReason"] = "missing_image_or_face"
        return binary, debug

    fg = binary > 0
    if not np.any(fg):
        debug["backgroundSheetReason"] = "empty_mask"
        return binary, debug

    rgb, bg, sample_count = _source_background_profile(image, raw_alpha, allowed)
    debug["sourceBackgroundRgb"] = [round(float(v), 2) for v in bg.tolist()]
    debug["sourceBackgroundSamples"] = sample_count

    maxc = rgb.max(axis=2)
    minc = rgb.min(axis=2)
    chroma = maxc - minc
    brightness = rgb.mean(axis=2)
    bg_brightness = float(bg.mean())
    bg_chroma = float(bg.max() - bg.min())
    color_distance = np.linalg.norm(rgb - bg, axis=2)
    strict_distance = 30.0 if bg_chroma < 54.0 else 42.0
    background_like = (color_distance <= strict_distance) | (
        (np.abs(brightness - bg_brightness) <= 30.0)
        & (np.abs(chroma - bg_chroma) <= 28.0)
        & (color_distance <= strict_distance + 22.0)
    )
    if bg_brightness > 168.0 and bg_chroma < 80.0:
        background_like |= (
            (brightness >= bg_brightness - 38.0)
            & (chroma <= bg_chroma + 54.0)
            & (color_distance <= strict_distance + 36.0)
        )

    protected = _subject_protection_mask(binary.shape, face_box, core)
    boundary = _inner_edge(fg, iterations=2)
    boundary_zone = cv2.dilate(boundary.astype("uint8"), np.ones((5, 5), np.uint8), iterations=1) > 0
    low_confidence = raw_alpha < 252

    h, w = raw_alpha.shape[:2]
    fx, fy, fw, fh, cx = _face_values(face_box)
    yy, xx = np.indices((h, w))
    lateral = np.abs(xx - cx)
    # Rembg can keep source wall inside concave areas beside ears, jaw, and
    # neck. These pockets are protected by the face prior, so they need an
    # explicit side-zone pass while still preserving skin and clothing.
    head_side_zone = (
        (yy >= fy - fh * 0.22)
        & (yy <= fy + fh * 1.26)
        & (lateral >= fw * 0.34)
        & (lateral <= fw * 1.30)
    )
    neck_side_zone = (
        (yy >= fy + fh * 0.68)
        & (yy <= fy + fh * 1.84)
        & (lateral >= fw * 0.16)
        & (lateral <= fw * 1.08)
    )
    central_face_or_neck = (
        (((xx - cx) / (fw * 0.56)) ** 2 + ((yy - (fy + fh * 0.55)) / (fh * 0.78)) ** 2 <= 1.0)
        | (
            (lateral <= fw * 0.15)
            & (yy >= fy + fh * 0.80)
            & (yy <= fy + fh * 1.70)
        )
    )
    skin_like = (
        (rgb[:, :, 0] > 92)
        & (rgb[:, :, 1] > 52)
        & (rgb[:, :, 2] > 36)
        & (rgb[:, :, 0] >= rgb[:, :, 1] - 8)
        & (rgb[:, :, 1] >= rgb[:, :, 2] - 4)
        & (rgb[:, :, 0] > rgb[:, :, 2] + 18)
        & (chroma > 24)
    )
    hair_like = (
        (brightness < 84.0)
        & (chroma <= 62.0)
        & (yy <= fy + fh * 1.05)
    )
    lower_subject_zone = yy >= fy + fh * 0.98
    dark_clothing_like = lower_subject_zone & (
        ((brightness < 116.0) & (chroma <= 178.0))
        | ((brightness < 158.0) & (chroma >= 28.0) & (chroma <= 196.0))
    )
    saturated_clothing_like = lower_subject_zone & (brightness < 218.0) & (chroma > 54.0)
    light_clothing_like = (
        (yy >= fy + fh * 1.02)
        & (lateral <= fw * 0.66)
        & (brightness >= 132.0)
        & (brightness <= 250.0)
        & (chroma <= 82.0)
    )
    clothing_like = dark_clothing_like | saturated_clothing_like | light_clothing_like
    side_pocket = (
        (head_side_zone | neck_side_zone)
        & ~central_face_or_neck
        & ~skin_like
        & ~hair_like
        & ~clothing_like
    )
    side_neutral_sheet = (
        side_pocket
        & (brightness >= 48.0)
        & (brightness <= 242.0)
        & (chroma <= max(112.0, bg_chroma + 78.0))
        & (
            background_like
            | (color_distance <= 168.0)
            | ((np.abs(brightness - bg_brightness) <= 156.0) & (chroma <= 104.0))
        )
    )
    side_candidate = fg & side_neutral_sheet

    candidate = (fg & background_like & ~protected & (low_confidence | boundary_zone)) | side_candidate
    seed = (fg & background_like & ~protected & boundary_zone) | (side_candidate & boundary_zone)
    debug["backgroundSheetCandidateRatio"] = round(
        float(np.count_nonzero(candidate)) / float(max(1, np.count_nonzero(fg))),
        6,
    )
    if int(np.count_nonzero(seed)) <= 0:
        remaining = fg & background_like & ~protected & boundary_zone
        remaining_head_side = fg & side_neutral_sheet & boundary_zone
        debug["remainingBackgroundSheetRatio"] = round(
            float(np.count_nonzero(remaining)) / float(max(1, np.count_nonzero(fg))),
            6,
        )
        debug["remainingHeadSideBackgroundRatio"] = round(
            float(np.count_nonzero(remaining_head_side)) / float(max(1, np.count_nonzero(fg))),
            6,
        )
        return binary, debug

    candidate_u8 = cv2.morphologyEx(candidate.astype("uint8"), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(candidate_u8, 8)
    remove = np.zeros_like(fg)
    for label in range(1, n):
        comp = labels == label
        comp_is_side_pocket = bool(np.any(comp & side_candidate))
        if not np.any(comp & seed) and not comp_is_side_pocket:
            continue
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < 8:
            continue
        mean_alpha = float(np.mean(raw_alpha[comp]))
        edge_fraction = float(np.count_nonzero(comp & boundary_zone)) / float(max(1, area))
        if comp_is_side_pocket:
            remove |= comp
        elif mean_alpha < 248.0 or edge_fraction > 0.08 or area > int(binary.size * 0.0012):
            remove |= comp

    if np.any(remove):
        fg = fg & ~remove
        binary = np.where(fg, 255, 0).astype("uint8")
        binary = _remove_small_components(binary, face_box)

    remaining = (binary > 0) & background_like & ~protected & boundary_zone
    remaining_head_side = (binary > 0) & side_neutral_sheet & boundary_zone
    debug["backgroundSheetRemovedPixels"] = int(np.count_nonzero(remove))
    debug["headSideBackgroundRemovedPixels"] = int(np.count_nonzero(remove & side_pocket))
    debug["remainingBackgroundSheetRatio"] = round(
        float(np.count_nonzero(remaining)) / float(max(1, np.count_nonzero(binary))),
        6,
    )
    debug["remainingHeadSideBackgroundRatio"] = round(
        float(np.count_nonzero(remaining_head_side)) / float(max(1, np.count_nonzero(binary))),
        6,
    )
    return binary, debug


def _matting_leak_metrics(binary, face_box, prior_allowed=None):
    h, w = binary.shape[:2]
    fg = binary > 0
    area = int(np.count_nonzero(fg))
    if area <= 0:
        return {
            "backgroundLeakRatio": 1.0,
            "foregroundTightnessScore": 0.0,
            "edgeLeakScore": 1.0,
            "haloScore": 1.0,
            "subjectCoverageScore": 0.0,
            "maskOverflowRatio": 1.0,
            "invalidBackgroundRetentionScore": 1.0,
        }

    if prior_allowed is None:
        prior_allowed, _, _ = _subject_prior(binary.shape, face_box, extra_dilate=7)
    overflow = fg & ~prior_allowed
    border = np.zeros_like(fg)
    border_pad = max(3, int(min(h, w) * 0.018))
    border[:border_pad, :] = True
    border[-border_pad:, :] = True
    border[:, :border_pad] = True
    border[:, -border_pad:] = True
    edge_leak = fg & border

    coverage = 0.0
    if face_box:
        x = max(0, int(face_box["x"]))
        y = max(0, int(face_box["y"]))
        x2 = min(w, x + int(face_box["width"]))
        y2 = min(h, y + int(face_box["height"]))
        if x2 > x and y2 > y:
            coverage = float(np.mean(fg[y:y2, x:x2]))

    mask_overflow = float(np.count_nonzero(overflow)) / float(area)
    edge_leak_ratio = float(np.count_nonzero(edge_leak)) / float(area)
    if face_box:
        _, _, fw, fh, _ = _face_values(face_box)
        expected_max_area = min(h * w, max(1.0, fw * fh * 8.6))
        loose_area_ratio = max(0.0, (area - expected_max_area) / float(max(1.0, area)))
    else:
        loose_area_ratio = 0.0
    invalid_score = max(mask_overflow, edge_leak_ratio, loose_area_ratio)
    return {
        "backgroundLeakRatio": round(mask_overflow, 6),
        "foregroundTightnessScore": round(max(0.0, 1.0 - invalid_score), 6),
        "edgeLeakScore": round(edge_leak_ratio, 6),
        "haloScore": round(max(mask_overflow, edge_leak_ratio), 6),
        "subjectCoverageScore": round(coverage, 6),
        "maskOverflowRatio": round(mask_overflow, 6),
        "invalidBackgroundRetentionScore": round(invalid_score, 6),
    }


def postprocess_alpha(alpha, face_box=None, image=None, return_debug=False):
    arr = np.asarray(alpha.convert("L"))
    binary = np.where(arr > 12, 255, 0).astype("uint8")
    raw_component = _remove_small_components(binary, face_box)
    allowed, core, prior_debug = _subject_prior(binary.shape, face_box, extra_dilate=9)
    if face_box:
        binary = np.where((binary > 0) & allowed, 255, 0).astype("uint8")
    grab_binary, grab_debug = _grabcut_subject_mask(image, arr, face_box, allowed, core)
    if grab_binary is not None:
        binary = np.where(((binary > 0) & (grab_binary > 0)) | core, 255, 0).astype("uint8")
    else:
        binary = np.where((binary > 0) | core, 255, 0).astype("uint8")
    binary = _remove_small_components(binary, face_box)
    kernel = np.ones((5, 5), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    binary, sheet_debug = _remove_background_sheets(binary, arr, image, face_box, allowed, core)
    raw_area = int(np.count_nonzero(raw_component))
    refined_area_before_erode = int(np.count_nonzero(binary))
    removed_from_raw = 0.0
    if raw_area > 0:
        removed_from_raw = float(np.count_nonzero((raw_component > 0) & (binary == 0))) / float(raw_area)
    raw_ratio = raw_area / float(max(1, arr.shape[0] * arr.shape[1]))
    refined_ratio_before_erode = refined_area_before_erode / float(max(1, arr.shape[0] * arr.shape[1]))
    overtrim_fallback = bool(
        raw_area > 0
        and 0.08 <= raw_ratio <= 0.72
        and removed_from_raw > 0.30
        and refined_ratio_before_erode < 0.16
    )
    if overtrim_fallback:
        binary = cv2.morphologyEx(raw_component, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
        sheet_debug["overTrimFallbackUsed"] = True
        sheet_debug["overTrimFallbackReason"] = "refined_mask_removed_too_much_from_raw_component"
        sheet_debug["overTrimFallbackRawRatio"] = round(raw_ratio, 6)
        sheet_debug["overTrimFallbackRemovedFromRaw"] = round(removed_from_raw, 6)
        sheet_debug["overTrimFallbackRefinedRatioBefore"] = round(
            refined_ratio_before_erode,
            6,
        )
    else:
        sheet_debug["overTrimFallbackUsed"] = False
        if raw_area > 0 and removed_from_raw > 0.30:
            sheet_debug["overTrimFallbackRejected"] = True
            sheet_debug["overTrimFallbackRejectedReason"] = "refined_mask_still_large_enough_background_safety_first"
            sheet_debug["overTrimFallbackRemovedFromRaw"] = round(removed_from_raw, 6)
            sheet_debug["overTrimFallbackRefinedRatioBefore"] = round(refined_ratio_before_erode, 6)
    # Avoid expanding rembg masks into the original background. Expanding is a
    # common source of white/gray halos on blue/red ID-photo backgrounds.
    binary = cv2.erode(binary, np.ones((3, 3), np.uint8), iterations=1)
    feather = cv2.GaussianBlur(binary, (5, 5), 0)
    debug = {
        **prior_debug,
        **grab_debug,
        **sheet_debug,
        **_matting_leak_metrics(binary, face_box, allowed),
        "rawMaskNonZeroRatio": round(float(np.count_nonzero(arr > 12)) / float(max(1, arr.shape[0] * arr.shape[1])), 6),
        "refinedMaskNonZeroRatio": round(float(np.count_nonzero(binary)) / float(max(1, arr.shape[0] * arr.shape[1])), 6),
    }
    if return_debug:
        return Image.fromarray(feather, "L"), binary, debug
    return Image.fromarray(feather, "L"), binary


def clean_refined_foreground_rgba(rgba, face_box=None):
    arr = np.asarray(rgba.convert("RGBA")).astype(np.float32).copy()
    alpha = arr[:, :, 3]
    fg = alpha > 2
    if not np.any(fg):
        return Image.fromarray(arr.astype(np.uint8), "RGBA"), {"foregroundRgbCleanedPixels": 0}

    rgb = arr[:, :, :3]
    opaque = (alpha > 202).astype(np.float32)
    denom = cv2.GaussianBlur(opaque, (11, 11), 0)
    weighted = cv2.GaussianBlur(rgb * opaque[:, :, None], (11, 11), 0)
    near = np.zeros_like(rgb)
    valid = denom > 0.01
    near[valid] = weighted[valid] / denom[valid, None]
    near[~valid] = rgb[~valid]

    edge = _inner_edge(fg, iterations=3)
    protected = _subject_protection_mask(alpha.shape, face_box, np.zeros_like(fg))
    transition = edge & (alpha > 2) & (alpha < 235) & ~protected
    cleaned = int(np.count_nonzero(transition & valid))
    if cleaned:
        strength = np.zeros_like(alpha, dtype=np.float32)
        strength[transition & valid] = np.clip((235.0 - alpha[transition & valid]) / 235.0, 0.18, 0.72)
        rgb[:] = rgb * (1.0 - strength[:, :, None]) + near * strength[:, :, None]
    arr[:, :, :3] = np.clip(rgb, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGBA"), {"foregroundRgbCleanedPixels": cleaned}


def _quality(binary, face_box):
    h, w = binary.shape[:2]
    area = int(np.count_nonzero(binary))
    area_ratio = area / float(max(1, w * h))
    n, labels, stats, _ = cv2.connectedComponentsWithStats((binary > 0).astype("uint8"), 8)
    largest_ratio = 0
    if n > 1 and area > 0:
        largest_ratio = int(np.max(stats[1:, cv2.CC_STAT_AREA])) / float(area)
    face_inside = False
    if face_box:
        x = max(0, int(face_box["x"]))
        y = max(0, int(face_box["y"]))
        x2 = min(w, x + int(face_box["width"]))
        y2 = min(h, y + int(face_box["height"]))
        if x2 > x and y2 > y:
            face_inside = float(np.mean(binary[y:y2, x:x2] > 0)) >= 0.55
    allowed, _, _ = _subject_prior(binary.shape, face_box, extra_dilate=9)
    return {
        "maskNonZeroRatio": round(area_ratio, 6),
        "largestComponentRatio": round(largest_ratio, 6),
        "faceInsideMask": face_inside,
        "connectedComponents": max(0, n - 1),
        **_matting_leak_metrics(binary, face_box, allowed),
    }


def _modnet_available():
    weight = os.environ.get("MODNET_WEIGHT_PATH", "")
    return bool(weight and os.path.exists(weight))


def matte_person(image_input, face_box=None):
    image = _read_rgba(image_input)
    engine = "rembg"
    model = _REMBG_MODEL or "u2net_human_seg"

    if _modnet_available():
        # MODNet hook is intentionally non-blocking for this iteration. The
        # project can point MODNET_WEIGHT_PATH here later without changing API.
        pass

    session = _get_rembg_session()
    if session is None:
        return {
            "success": False,
            "code": "MATTING_ENGINE_UNAVAILABLE",
            "message": "人像抠图服务暂不可用，请稍后重试。",
            "engine": "rembg",
            "debug": {"error": _REMBG_ERROR},
        }

    try:
        from rembg import remove

        src = BytesIO()
        image.convert("RGB").save(src, format="PNG")
        matting_mode = "alpha_matting"
        alpha_error = None
        try:
            out = remove(
                src.getvalue(),
                session=session,
                alpha_matting=True,
                alpha_matting_foreground_threshold=235,
                alpha_matting_background_threshold=12,
                alpha_matting_erode_size=8,
            )
        except Exception as exc:
            alpha_error = str(exc)
            matting_mode = "standard_fallback"
            print(f"[id-photo] rembg alpha matting fallback: {exc}", flush=True)
            out = remove(src.getvalue(), session=session, alpha_matting=False)
        rgba = Image.open(BytesIO(out)).convert("RGBA")
        alpha, binary, refine_debug = postprocess_alpha(rgba.getchannel("A"), face_box, image=image, return_debug=True)
        rgba.putalpha(alpha)
        quality = _quality(binary, face_box)
        quality["mattingRefine"] = refine_debug
        rgba, foreground_debug = clean_refined_foreground_rgba(rgba, face_box)
        quality["mattingRefine"].update(foreground_debug)
        quality.update({
            key: refine_debug[key]
            for key in (
                "backgroundLeakRatio",
                "foregroundTightnessScore",
                "edgeLeakScore",
                "haloScore",
                "subjectCoverageScore",
                "maskOverflowRatio",
                "invalidBackgroundRetentionScore",
                "backgroundSheetCandidateRatio",
                "remainingBackgroundSheetRatio",
                "backgroundSheetRemovedPixels",
                "remainingHeadSideBackgroundRatio",
                "headSideBackgroundRemovedPixels",
                "overTrimFallbackUsed",
                "overTrimFallbackRemovedFromRaw",
                "overTrimFallbackRawRatio",
            )
            if key in refine_debug
        })
        quality.update(foreground_debug)
        quality["alphaMattingMode"] = matting_mode
        if alpha_error:
            quality["alphaMattingFallbackReason"] = alpha_error
        if quality["maskNonZeroRatio"] < 0.025 or not quality["faceInsideMask"]:
            return {
                "success": False,
                "code": "MASK_QUALITY_FAILED",
                "message": "人像抠图不完整，请重新上传清晰正面照片。",
                "engine": engine,
                "model": model,
                "quality": quality,
            }
        foreground_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
        mask_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
        rgba.save(foreground_path, format="PNG")
        alpha.save(mask_path, format="PNG")
        return {
            "success": True,
            "foregroundPath": foreground_path,
            "maskPath": mask_path,
            "engine": engine,
            "model": _REMBG_MODEL or model,
            "alphaMattingMode": matting_mode,
            "quality": quality,
        }
    except Exception as exc:
        return {
            "success": False,
            "code": "MATTING_FAILED",
            "message": "人像抠图失败，请重新上传清晰正面照片。",
            "engine": engine,
            "model": model,
            "debug": {"error": str(exc)},
        }


def matting_status():
    return {
        "modnetAvailable": _modnet_available(),
        "modnetMessage": "configured" if _modnet_available() else _MODNET_ERROR,
        "rembgAvailable": _get_rembg_session() is not None,
        "rembgModel": _REMBG_MODEL,
        "rembgError": _REMBG_ERROR,
    }
