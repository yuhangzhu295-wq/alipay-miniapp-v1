"""Portrait matting for ID-photo generation.

Current production order: HivisionIDPhotos, then rembg as a recorded fallback.
Both paths use the same OpenCV mask post-processing before composition.
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
    y_top = int(np.clip(fy + fh * 0.88, 0, h - 1))
    y_mid = int(np.clip(fy + fh * 1.78, 0, h - 1))
    y_bottom = int(np.clip(fy + fh * 3.10, 0, h - 1))
    # Keep the ID-photo subject generous enough for natural shoulders, but
    # avoid accepting full-width arms, doors, walls, or watermark strips as
    # foreground in head-shoulder output.
    shoulder = fw * 1.82
    waist = fw * 1.32
    points = np.array(
        [
            [int(cx - fw * 0.55), y_top],
            [int(cx + fw * 0.55), y_top],
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
    face = (((xx - cx) / (fw * 0.56)) ** 2 + ((yy - face_cy) / (fh * 0.78)) ** 2) <= 1.0
    ears_and_jaw = (
        (xx >= cx - fw * 0.62)
        & (xx <= cx + fw * 0.62)
        & (yy >= fy - fh * 0.05)
        & (yy <= fy + fh * 1.12)
    )
    neck_and_center_chest = (
        (xx >= cx - fw * 0.38)
        & (xx <= cx + fw * 0.38)
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
        (
            (brightness < 92.0)
            & (chroma <= 88.0)
            & (yy <= fy + fh * 1.12)
        )
        | (
            (yy >= fy - fh * 0.50)
            & (yy <= fy + fh * 0.66)
            & (lateral <= fw * 1.18)
            & (brightness < 148.0)
            & (chroma <= 132.0)
        )
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
    top_hair_zone = (
        (yy >= fy - fh * 0.62)
        & (yy <= fy + fh * 0.22)
        & (lateral <= fw * 1.22)
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
    top_neutral_sheet = (
        top_hair_zone
        & (brightness >= max(142.0, bg_brightness - 52.0))
        & (brightness <= 246.0)
        & (chroma <= max(118.0, bg_chroma + 72.0))
        & (
            background_like
            | (color_distance <= 118.0)
            | ((np.abs(brightness - bg_brightness) <= 96.0) & (chroma <= 82.0))
        )
    )
    side_candidate = fg & (side_neutral_sheet | top_neutral_sheet)

    candidate = (fg & background_like & ~protected & (low_confidence | boundary_zone)) | side_candidate
    seed = (fg & background_like & ~protected & boundary_zone) | (side_candidate & boundary_zone)
    debug["backgroundSheetCandidateRatio"] = round(
        float(np.count_nonzero(candidate)) / float(max(1, np.count_nonzero(fg))),
        6,
    )
    if int(np.count_nonzero(seed)) <= 0:
        remaining = fg & background_like & ~protected & boundary_zone
        remaining_head_side = fg & (side_neutral_sheet | top_neutral_sheet) & boundary_zone
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
    remaining_head_side = (binary > 0) & (side_neutral_sheet | top_neutral_sheet) & boundary_zone
    debug["backgroundSheetRemovedPixels"] = int(np.count_nonzero(remove))
    debug["headSideBackgroundRemovedPixels"] = int(np.count_nonzero(remove & (side_pocket | top_hair_zone)))
    debug["remainingBackgroundSheetRatio"] = round(
        float(np.count_nonzero(remaining)) / float(max(1, np.count_nonzero(binary))),
        6,
    )
    debug["remainingHeadSideBackgroundRatio"] = round(
        float(np.count_nonzero(remaining_head_side)) / float(max(1, np.count_nonzero(binary))),
        6,
    )
    return binary, debug


def _repair_shoulder_alpha(binary, raw_alpha, image, face_box, allowed):
    debug = {"shoulderAlphaRepairedPixels": 0, "shoulderAlphaCandidatePixels": 0}
    if image is None or not face_box:
        return binary, debug
    
    rgb, bg, _ = _source_background_profile(image, raw_alpha, allowed)
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
        
    foreground_like = ~background_like
    
    h, w = binary.shape[:2]
    fx, fy, fw, fh, cx = _face_values(face_box)
    yy, xx = np.indices((h, w))
    
    body_zone = (
        (yy >= fy + fh * 0.95)
        & (yy <= fy + fh * 3.35)
        & (xx >= cx - fw * 2.75)
        & (xx <= cx + fw * 2.75)
    )
    shoulder_zone = (
        (yy >= fy + fh * 1.02)
        & (yy <= fy + fh * 2.35)
        & (xx >= cx - fw * 2.15)
        & (xx <= cx + fw * 2.15)
    )
    # Preserve real clothing even when it is dark, white, or saturated.  The
    # background filter stays color-generic; no sample-specific clothing colors
    # are baked in here.
    clothing_texture = (
        (brightness < 232.0)
        & (
            (chroma > 24.0)
            | (brightness < 168.0)
            | (np.abs(brightness - bg_brightness) > 42.0)
        )
    )
    
    repair_allowed = cv2.dilate(allowed.astype("uint8"), np.ones((13, 13), np.uint8), iterations=1) > 0
    candidate_holes = (
        (body_zone | shoulder_zone)
        & repair_allowed
        & foreground_like
        & clothing_texture
        & (binary == 0)
    )
    debug["shoulderAlphaCandidatePixels"] = int(np.count_nonzero(candidate_holes))
    
    if np.count_nonzero(candidate_holes) > 0:
        n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
        if n > 1:
            largest_label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
            main_body = labels == largest_label
            
            repaired = binary.copy()
            dilated_body = cv2.dilate((main_body).astype("uint8"), np.ones((57, 57), np.uint8))
            n_holes, hole_labels, hole_stats, _ = cv2.connectedComponentsWithStats(candidate_holes.astype("uint8"), 8)
            added_pixels = 0
            for i in range(1, n_holes):
                hole_comp = hole_labels == i
                if np.any(hole_comp & (dilated_body > 0)):
                    area = int(hole_stats[i, cv2.CC_STAT_AREA])
                    if area < max(8, int((h * w) * 0.00003)):
                        continue
                    repaired[hole_comp] = 255
                    added_pixels += area
                    
            if added_pixels > 0:
                repaired = cv2.morphologyEx(repaired, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
                debug["shoulderAlphaRepairedPixels"] = added_pixels
                return repaired, debug
                
    return binary, debug


def _remove_dark_side_line_artifacts(binary, raw_alpha, image, face_box):
    """Drop thin dark old-background lines glued to the side silhouette."""
    debug = {"darkSideLineRemovedPixels": 0, "darkSideLineMaxComponent": 0}
    if image is None or not face_box:
        return binary, debug

    fg = binary > 0
    if int(np.count_nonzero(fg)) < 64:
        return binary, debug

    rgb = np.asarray(image.convert("RGB"))
    if rgb.shape[:2] != binary.shape[:2]:
        return binary, debug

    h, w = binary.shape[:2]
    fx, fy, fw, fh, cx = _face_values(face_box)
    yy, xx = np.indices((h, w))
    lateral = np.abs(xx - cx)
    brightness = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)

    boundary_kernel = np.ones((5, 5), np.uint8)
    boundary = fg & (
        cv2.dilate((~fg).astype("uint8"), boundary_kernel, iterations=1).astype(bool)
        | (raw_alpha < 252)
    )
    face_core = (
        ((xx - cx) / (fw * 0.72)) ** 2
        + ((yy - (fy + fh * 0.54)) / (fh * 0.96)) ** 2
        <= 1.0
    )
    central_neck_or_clothes = (
        (yy >= fy + fh * 0.78)
        & (yy <= fy + fh * 2.75)
        & (lateral <= fw * 0.46)
    )
    hair_core = (
        (yy <= fy + fh * 1.04)
        & (lateral <= fw * 0.94)
        & (brightness < 96.0)
    )
    side_zone = (
        (yy >= fy + fh * 0.62)
        & (yy <= fy + fh * 2.62)
        & (lateral >= fw * 0.34)
        & (lateral <= fw * 2.20)
    )
    candidate = (
        fg
        & boundary
        & side_zone
        & ~face_core
        & ~central_neck_or_clothes
        & ~hair_core
        & (brightness < 92.0)
        & (chroma < 126.0)
        & (raw_alpha > 6)
    )
    if int(np.count_nonzero(candidate)) < 4:
        return binary, debug

    candidate_u8 = cv2.morphologyEx(candidate.astype("uint8"), cv2.MORPH_OPEN, np.ones((1, 3), np.uint8), iterations=1)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(candidate_u8, 8)
    remove = np.zeros_like(fg)
    max_component = 0
    for label in range(1, n):
        comp = labels == label
        area = int(stats[label, cv2.CC_STAT_AREA])
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        cw = int(stats[label, cv2.CC_STAT_WIDTH])
        ch = int(stats[label, cv2.CC_STAT_HEIGHT])
        max_component = max(max_component, area)
        if area < 4 or area > max(1200, int(h * w * 0.006)):
            continue
        density = float(area) / float(max(1, cw * ch))
        elongated = cw >= max(10, ch * 2.0) or ch >= max(10, cw * 2.0)
        diagonal_thin = density <= 0.46 and cw >= max(10, int(fw * 0.12)) and ch >= max(10, int(fh * 0.12))
        side_anchored = x <= int(cx - fw * 0.72) or (x + cw) >= int(cx + fw * 0.72)
        low_subject_overlap = not np.any(comp & central_neck_or_clothes)
        upper_or_side = y <= int(fy + fh * 2.48) and side_anchored
        if (elongated or diagonal_thin) and upper_or_side and low_subject_overlap:
            remove |= comp

    if np.any(remove):
        cleaned = np.array(fg, copy=True)
        cleaned[remove] = False
        cleaned_u8 = (cleaned.astype("uint8") * 255)
        cleaned_u8 = _remove_small_components(cleaned_u8, face_box)
        debug["darkSideLineRemovedPixels"] = int(np.count_nonzero(fg & (cleaned_u8 == 0)))
        debug["darkSideLineMaxComponent"] = int(max_component)
        return cleaned_u8, debug

    debug["darkSideLineMaxComponent"] = int(max_component)
    return binary, debug


def _remove_detached_row_artifacts(binary, face_box):
    """Drop side-row alpha shelves that are disconnected from the subject.

    Human-matting models sometimes attach a horizontal wall/floor strip to the
    mask near the shoulder line.  Color checks alone are unsafe because suits
    can be black and shirts can be white, so this pass keeps the row interval
    that is continuous with the central head/neck/torso corridor and removes
    detached side intervals.  It is constrained to the head/shoulder crop area
    used by ID-photo composition.
    """
    debug = {"detachedRowArtifactRemovedPixels": 0, "detachedRowArtifactRows": 0}
    if not face_box:
        return binary, debug

    fg = binary > 0
    if int(np.count_nonzero(fg)) < 64:
        return binary, debug

    h, w = binary.shape[:2]
    fx, fy, fw, fh, cx = _face_values(face_box)
    y_start = max(0, int(fy + fh * 0.70))
    y_end = min(h - 1, int(fy + fh * 3.05))
    if y_end <= y_start:
        return binary, debug

    remove = np.zeros_like(fg)
    removed_rows = 0
    for y in range(y_start, y_end + 1):
        xs = np.flatnonzero(fg[y])
        if xs.size <= 0:
            continue

        starts = []
        ends = []
        start = int(xs[0])
        prev = int(xs[0])
        for raw_x in xs[1:]:
            x = int(raw_x)
            if x == prev + 1:
                prev = x
            else:
                starts.append(start)
                ends.append(prev)
                start = x
                prev = x
        starts.append(start)
        ends.append(prev)
        t = float(np.clip((y - (fy + fh * 0.80)) / max(1.0, fh * 1.65), 0.0, 1.0))
        central_half = fw * (0.42 + 1.02 * t)
        central_left = cx - central_half
        central_right = cx + central_half

        # A single over-wide row interval is usually a lower arm/table/wall
        # shelf attached to the body mask.  Trim only the far side tails; keep
        # the central shoulder/chest corridor intact.
        if y >= fy + fh * 1.50:
            tail_left_limit = int(max(0, round(cx - fw * 1.50)))
            tail_right_limit = int(min(w - 1, round(cx + fw * 1.50)))
            for left, right in zip(starts, ends):
                width = right - left + 1
                touches_frame = left <= 1 or right >= w - 2
                too_wide = width >= max(24, int(fw * 2.70))
                if touches_frame or too_wide:
                    if left < tail_left_limit:
                        remove[y, left : min(right, tail_left_limit - 1) + 1] = True
                    if right > tail_right_limit:
                        remove[y, max(left, tail_right_limit + 1) : right + 1] = True

        if len(starts) <= 1:
            if np.any(remove[y]):
                removed_rows += 1
            continue

        # The central corridor widens smoothly from the neck to the shoulders.
        # Rows outside this corridor must remain close to a kept interval;
        # otherwise they are independent old-background shelves.
        keep = [False] * len(starts)
        for idx, (left, right) in enumerate(zip(starts, ends)):
            if right >= central_left and left <= central_right:
                keep[idx] = True

        # Keep tiny nearby wisps that connect visually to the central subject.
        for idx, (left, right) in enumerate(zip(starts, ends)):
            if keep[idx]:
                continue
            kept_gaps = []
            for kept_idx, kept in enumerate(keep):
                if not kept:
                    continue
                if right < starts[kept_idx]:
                    kept_gaps.append(starts[kept_idx] - right)
                elif left > ends[kept_idx]:
                    kept_gaps.append(left - ends[kept_idx])
                else:
                    kept_gaps.append(0)
            gap = min(kept_gaps) if kept_gaps else 9999
            width = right - left + 1
            if gap <= max(7, int(fw * 0.08)) and width <= max(8, int(fw * 0.30)):
                keep[idx] = True

        row_removed = False
        for idx, (left, right) in enumerate(zip(starts, ends)):
            width = right - left + 1
            if keep[idx] or width < 3:
                continue
            remove[y, left : right + 1] = True
            row_removed = True
        if row_removed:
            removed_rows += 1

    if np.any(remove):
        cleaned = np.array(fg, copy=True)
        cleaned[remove] = False
        cleaned_u8 = (cleaned.astype("uint8") * 255)
        cleaned_u8 = _remove_small_components(cleaned_u8, face_box)
        debug["detachedRowArtifactRemovedPixels"] = int(np.count_nonzero(fg & (cleaned_u8 == 0)))
        debug["detachedRowArtifactRows"] = removed_rows
        return cleaned_u8, debug
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


def clean_bottom_right_watermark(binary, face_box, image=None):
    if not face_box:
        return binary
    h, w = binary.shape[:2]
    region_y = int(h * 0.78)
    region_x = int(w * 0.52)
    if h - region_y < 10 or w - region_x < 10:
        return binary
    mask_region = binary[region_y:, region_x:].copy()
    
    scale_factor = max(1.0, w / 295.0)
    k_size = max(5, int(5 * scale_factor) | 1)
    kernel = np.ones((k_size, k_size), np.uint8)
    eroded = cv2.erode(mask_region, kernel, iterations=1)
    reconstructed = eroded.copy()
    iters = max(12, int(12 * scale_factor))
    for _ in range(iters):
        dilated = cv2.dilate(reconstructed, np.ones((3, 3), np.uint8))
        reconstructed = cv2.bitwise_and(dilated, mask_region)
        
    watermark_mask = None
    if image is not None:
        orig_arr = np.asarray(image.convert("RGB"))
        if orig_arr.shape[0] == h and orig_arr.shape[1] == w:
            gray = cv2.cvtColor(orig_arr[region_y:, region_x:, :3], cv2.COLOR_RGB2GRAY)
            th_k_size = max(9, int(9 * scale_factor) | 1)
            th_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (th_k_size, th_k_size))
            tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, th_kernel)
            _, watermark_mask = cv2.threshold(tophat, 24, 255, cv2.THRESH_BINARY)
            
    if watermark_mask is None:
        watermark_mask = mask_region & ~reconstructed

    if np.count_nonzero(watermark_mask) > 0:
        n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(watermark_mask, 8)
        # Use a small fixed 5x5 dilation to handle suit edge alignment
        clothing_dilated = cv2.dilate(reconstructed, np.ones((5, 5), np.uint8))
        
        inpaint_mask = np.zeros_like(mask_region)
        erase_mask = np.zeros_like(mask_region)
        
        scale = (w * h) / 121835.0
        min_area = max(2, int(2 * scale))
        max_area = max(280, int(280 * scale))
        
        for label in range(1, n_labels):
            comp = labels == label
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < min_area or area > max_area:
                continue
            if np.any(comp & (clothing_dilated > 0)):
                inpaint_mask[comp] = 255
            else:
                erase_mask[comp] = 255
                
        dilate_k_size = max(3, int(3 * scale_factor) | 1)
        dilate_kernel = np.ones((dilate_k_size, dilate_k_size), np.uint8)
        if np.count_nonzero(inpaint_mask) > 0:
            inpaint_mask = cv2.dilate(inpaint_mask, dilate_kernel, iterations=1)
            reconstructed[inpaint_mask > 0] = 255
        if np.count_nonzero(erase_mask) > 0:
            erase_mask = cv2.dilate(erase_mask, dilate_kernel, iterations=1)
            reconstructed[erase_mask > 0] = 0
                
    binary_clean = binary.copy()
    binary_clean[region_y:, region_x:] = reconstructed
    return binary_clean


def _postprocess_trusted_alpha(alpha, face_box=None, return_debug=False):
    arr = np.asarray(alpha.convert("L"))
    binary = np.where(arr > 12, 255, 0).astype("uint8")
    binary = _remove_small_components(binary, face_box)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)

    # Preserve the model's soft boundary while removing pixels belonging to
    # detached components. Large transparent gaps between limbs stay intact.
    refined = arr.copy()
    refined[binary == 0] = 0
    added = (binary > 0) & (refined <= 12)
    refined[added] = 180
    feather = cv2.GaussianBlur(refined, (3, 3), 0)
    allowed, _, prior_debug = _subject_prior(binary.shape, face_box, extra_dilate=9)
    debug = {
        **prior_debug,
        **_matting_leak_metrics(binary, face_box, allowed),
        "trustedAlphaPath": True,
        "trustedAlphaAddedPixels": int(np.count_nonzero(added)),
        "rawMaskNonZeroRatio": round(float(np.count_nonzero(arr > 12)) / float(max(1, arr.size)), 6),
        "refinedMaskNonZeroRatio": round(float(np.count_nonzero(binary)) / float(max(1, arr.size)), 6),
    }
    if return_debug:
        return Image.fromarray(feather, "L"), binary, debug
    return Image.fromarray(feather, "L"), binary


def postprocess_alpha(alpha, face_box=None, image=None, return_debug=False, preserve_detail=False):
    if preserve_detail:
        return _postprocess_trusted_alpha(alpha, face_box=face_box, return_debug=return_debug)
    arr = np.asarray(alpha.convert("L"))
    binary = np.where(arr > 12, 255, 0).astype("uint8")
    raw_component = _remove_small_components(binary, face_box)
    allowed, core, prior_debug = _subject_prior(binary.shape, face_box, extra_dilate=9)
    if face_box:
        binary = np.where((binary > 0) & allowed, 255, 0).astype("uint8")
    grab_binary, grab_debug = _grabcut_subject_mask(image, arr, face_box, allowed, core)
    if grab_binary is not None:
        if face_box and image is not None:
            h, w = binary.shape[:2]
            fx, fy, fw, fh, cx = _face_values(face_box)
            yy, xx = np.indices((h, w))
            rgb, bg, _ = _source_background_profile(image, arr, allowed)
            brightness = rgb.mean(axis=2)
            chroma = rgb.max(axis=2) - rgb.min(axis=2)
            bg_brightness = float(bg.mean())
            body_preserve = (
                (yy >= fy + fh * 0.92)
                & (yy <= fy + fh * 3.35)
                & (xx >= cx - fw * 2.55)
                & (xx <= cx + fw * 2.55)
                & (binary > 0)
                & (allowed > 0)
                & (
                    (arr > 42)
                    | (chroma > 34.0)
                    | (brightness < 164.0)
                    | (np.abs(brightness - bg_brightness) > 46.0)
                )
            )
        else:
            body_preserve = np.zeros_like(binary, dtype=bool)
        binary = np.where((((binary > 0) & (grab_binary > 0)) | body_preserve), 255, 0).astype("uint8")
    else:
        binary = np.where(binary > 0, 255, 0).astype("uint8")

    # Fill internal holes to prevent background holes in the face/neck/body
    h, w = binary.shape[:2]
    padded = cv2.copyMakeBorder(binary, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    flood_filled = padded.copy()
    ff_mask = np.zeros((h + 4, w + 4), np.uint8)
    cv2.floodFill(flood_filled, ff_mask, (0, 0), 255)
    flood_filled_inverted = cv2.bitwise_not(flood_filled)
    binary = binary | flood_filled_inverted[1:-1, 1:-1]

    # Clean bottom-right watermark
    binary = clean_bottom_right_watermark(binary, face_box, image=image)

    binary = _remove_small_components(binary, face_box)
    kernel = np.ones((5, 5), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    binary, sheet_debug = _remove_background_sheets(binary, arr, image, face_box, allowed, core)
    binary, repair_debug = _repair_shoulder_alpha(binary, arr, image, face_box, allowed)
    binary, dark_line_debug = _remove_dark_side_line_artifacts(binary, arr, image, face_box)
    binary, row_artifact_debug = _remove_detached_row_artifacts(binary, face_box)
    raw_area = int(np.count_nonzero(raw_component))
    refined_area_before_erode = int(np.count_nonzero(binary))
    removed_from_raw = 0.0
    if raw_area > 0:
        removed_from_raw = float(np.count_nonzero((raw_component > 0) & (binary == 0))) / float(raw_area)
    raw_ratio = raw_area / float(max(1, arr.shape[0] * arr.shape[1]))
    refined_ratio_before_erode = refined_area_before_erode / float(max(1, arr.shape[0] * arr.shape[1]))
    background_sheet_evidence = bool(
        float(sheet_debug.get("backgroundSheetCandidateRatio") or 0) > 0.01
        or float(sheet_debug.get("remainingBackgroundSheetRatio") or 0) > 0.008
        or float(sheet_debug.get("remainingHeadSideBackgroundRatio") or 0) > 0.008
    )
    overtrim_fallback = bool(
        raw_area > 0
        and 0.08 <= raw_ratio <= 0.72
        and removed_from_raw > 0.30
        and refined_ratio_before_erode < 0.16
        and not background_sheet_evidence
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
    # Do not globally erode the subject after shoulder repair. A full-mask
    # erosion creates the rectangular clothing/shoulder cutouts visible in the
    # mini-program preview. Edge cleanup and quality gates handle residue later.
    feather = cv2.GaussianBlur(binary, (5, 5), 0)
    debug = {
        **prior_debug,
        **grab_debug,
        **sheet_debug,
        **repair_debug,
        **dark_line_debug,
        **row_artifact_debug,
        **_matting_leak_metrics(binary, face_box, allowed),
        "rawMaskNonZeroRatio": round(float(np.count_nonzero(arr > 12)) / float(max(1, arr.shape[0] * arr.shape[1])), 6),
        "refinedMaskNonZeroRatio": round(float(np.count_nonzero(binary)) / float(max(1, arr.shape[0] * arr.shape[1])), 6),
    }
    if return_debug:
        return Image.fromarray(feather, "L"), binary, debug
    return Image.fromarray(feather, "L"), binary


def clean_refined_foreground_rgba(rgba, face_box=None, image=None):
    arr = np.asarray(rgba.convert("RGBA")).copy()
    h, w = arr.shape[:2]
    
    # Inpaint clothing watermark in bottom-right corner
    if face_box and image is not None:
        region_y = int(h * 0.78)
        region_x = int(w * 0.52)
        if h - region_y >= 10 and w - region_x >= 10:
            orig_arr = np.asarray(image.convert("RGB"))
            if orig_arr.shape[0] == h and orig_arr.shape[1] == w:
                gray = cv2.cvtColor(orig_arr[region_y:, region_x:, :3], cv2.COLOR_RGB2GRAY)
                
                scale_factor = max(1.0, w / 295.0)
                th_k_size = max(9, int(9 * scale_factor) | 1)
                th_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (th_k_size, th_k_size))
                tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, th_kernel)
                _, watermark_mask = cv2.threshold(tophat, 24, 255, cv2.THRESH_BINARY)
                
                if np.count_nonzero(watermark_mask) > 0:
                    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(watermark_mask, 8)
                    clean_mask = np.zeros_like(watermark_mask)
                    
                    scale = (w * h) / 121835.0
                    min_area = max(2, int(2 * scale))
                    max_area = max(280, int(280 * scale))
                    
                    for label in range(1, n_labels):
                        area = int(stats[label, cv2.CC_STAT_AREA])
                        if min_area <= area <= max_area:
                            clean_mask[labels == label] = 255
                    
                    if np.count_nonzero(clean_mask) > 0:
                        dilate_k_size = max(3, int(3 * scale_factor) | 1)
                        clean_mask = cv2.dilate(clean_mask, np.ones((dilate_k_size, dilate_k_size), np.uint8), iterations=1)
                        rgb_region = arr[region_y:, region_x:, :3]
                        inpainted_rgb = cv2.inpaint(rgb_region, clean_mask, 3, cv2.INPAINT_TELEA)
                        arr[region_y:, region_x:, :3] = inpainted_rgb

    arr_f32 = arr.astype(np.float32)
    alpha = arr_f32[:, :, 3]
    fg = alpha > 2
    if not np.any(fg):
        return Image.fromarray(arr.astype(np.uint8), "RGBA"), {"foregroundRgbCleanedPixels": 0}

    rgb = arr_f32[:, :, :3]
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
    
    # Erode alpha for thin outline residuals
    if image is not None:
        rgb_raw = np.asarray(image.convert("RGB")).astype(np.float32)
        maxc = rgb_raw.max(axis=2)
        minc = rgb_raw.min(axis=2)
        sat = maxc - minc
        brightness = rgb_raw.mean(axis=2)
        bg_residue = edge & (sat < 40) & (brightness > 130) & ~protected
        if np.any(bg_residue):
            arr_f32[bg_residue, 3] = np.clip(arr_f32[bg_residue, 3] - 120, 0, 255)
            alpha = arr_f32[:, :, 3]

    cleaned = int(np.count_nonzero(transition & valid))
    if cleaned > 0:
        strength = np.zeros_like(alpha, dtype=np.float32)
        strength[transition & valid] = np.clip((235.0 - alpha[transition & valid]) / 235.0, 0.18, 0.72)
        rgb[:] = rgb * (1.0 - strength[:, :, None]) + near * strength[:, :, None]
    arr_f32[:, :, :3] = np.clip(rgb, 0, 255)
    return Image.fromarray(arr_f32.astype(np.uint8), "RGBA"), {"foregroundRgbCleanedPixels": cleaned}


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


def _finalize_matting_rgba(rgba, face_box, image, engine, model, matting_mode, extra_debug=None, alpha_error=None):
    trusted_alpha = bool((extra_debug or {}).get("trustedAlpha"))
    alpha, binary, refine_debug = postprocess_alpha(
        rgba.getchannel("A"),
        face_box,
        image=image,
        return_debug=True,
        preserve_detail=trusted_alpha,
    )
    rgba.putalpha(alpha)
    quality = _quality(binary, face_box)
    quality["mattingRefine"] = refine_debug
    if extra_debug:
        quality["mattingRefine"]["engineDebug"] = extra_debug
    if trusted_alpha:
        foreground_debug = {
            "foregroundRgbCleanedPixels": 0,
            "foregroundRgbCleanupSkipped": "trusted model alpha preserves headwear and fine edges",
        }
    else:
        rgba, foreground_debug = clean_refined_foreground_rgba(rgba, face_box, image=image)
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
    quality["mattingEngine"] = engine
    quality["mattingModel"] = model
    quality["trustedAlpha"] = trusted_alpha
    if alpha_error:
        quality["alphaMattingFallbackReason"] = alpha_error
    fail_reasons = []
    if quality["maskNonZeroRatio"] < 0.025:
        fail_reasons.append("mask_too_small")
    if not quality["faceInsideMask"]:
        fail_reasons.append("face_missing_from_mask")
    if not trusted_alpha and float(quality.get("remainingBackgroundSheetRatio") or 0) > 0.035:
        fail_reasons.append("background_sheet_retained")
    if not trusted_alpha and (
        float(quality.get("invalidBackgroundRetentionScore") or 0) > 0.32
        and float(quality.get("edgeLeakScore") or 0) > 0.12
    ):
        fail_reasons.append("background_leak_too_large")
    quality["mattingPassed"] = not fail_reasons
    quality["mattingFailReasons"] = fail_reasons
    if fail_reasons:
        return {
            "success": False,
            "code": "MASK_QUALITY_FAILED",
            "message": "Portrait matting is incomplete. Please upload a clear front-facing photo.",
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
        "model": model,
        "alphaMattingMode": matting_mode,
        "quality": quality,
    }


def matte_person(
    image_input,
    face_box=None,
    prefer_detail=False,
    preferred_model="",
    request_id="",
    allow_fallback=True,
    timeout=180,
):
    image = _read_rgba(image_input)
    fallback_debug = None

    try:
        from id_photo_engines.hivision.runner import get_model_routing, run_human_matting

        routing = get_model_routing()
        requested_model = preferred_model or routing.get("detail" if prefer_detail else "standard") or None
        hivision = run_human_matting(
            image,
            model=requested_model,
            request_id=request_id,
            timeout=timeout,
            allow_model_fallback=allow_fallback,
        )
        if hivision.get("success"):
            return _finalize_matting_rgba(
                hivision["rgba"],
                face_box,
                image,
                "hivision",
                hivision.get("model") or "hivision_modnet",
                "hivision_human_matting",
                extra_debug={
                    **(hivision.get("debug") or {}),
                    "preferDetail": bool(prefer_detail),
                    "preferredModel": preferred_model or "",
                    "requestedModel": requested_model,
                },
            )
        fallback_debug = hivision.get("debug") or {"error": hivision.get("message")}
        if not allow_fallback:
            return {
                "success": False,
                "code": hivision.get("code") or "FAST_MODEL_FAILED",
                "message": hivision.get("message") or "快速抠图暂不可用，请稍后重试。",
                "engine": "hivision",
                "model": requested_model or "hivision_modnet",
                "debug": fallback_debug,
            }
        print(f"[id-photo] Hivision matting fallback: {hivision.get('code')} {hivision.get('message')}", flush=True)
    except Exception as exc:
        fallback_debug = {"error": repr(exc)}
        if not allow_fallback:
            return {
                "success": False,
                "code": "FAST_MODEL_FAILED",
                "message": "快速抠图暂不可用，请稍后重试。",
                "engine": "hivision",
                "model": "hivision_modnet",
                "debug": fallback_debug,
            }
        print(f"[id-photo] Hivision matting exception fallback: {exc}", flush=True)

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
        return _finalize_matting_rgba(
            rgba,
            face_box,
            image,
            engine,
            _REMBG_MODEL or model,
            matting_mode,
            extra_debug={"hivisionFallback": fallback_debug} if fallback_debug else None,
            alpha_error=alpha_error,
        )
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
    try:
        from id_photo_engines.hivision.runner import production_ready, available_models

        hivision_ready, hivision_reason = production_ready()
        hivision_models = available_models()
    except Exception as exc:
        hivision_ready = False
        hivision_reason = repr(exc)
        hivision_models = []
    return {
        "hivisionAvailable": hivision_ready,
        "hivisionMessage": hivision_reason,
        "hivisionModels": hivision_models,
        "modnetAvailable": _modnet_available(),
        "modnetMessage": "configured" if _modnet_available() else _MODNET_ERROR,
        "rembgAvailable": _get_rembg_session() is not None,
        "rembgModel": _REMBG_MODEL,
        "rembgError": _REMBG_ERROR,
    }
