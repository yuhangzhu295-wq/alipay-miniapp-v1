"""Face-driven ID-photo composition."""
from PIL import Image, ImageDraw, ImageFilter
import cv2
import numpy as np
import time


def _hex_to_rgb(value, fallback="#1a73e8"):
    value = (value or fallback).strip()
    if not value.startswith("#") or len(value) != 7:
        value = fallback
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))



def _mask_edge_band(fg):
    kernel = np.ones((3, 3), np.uint8)
    src = fg.astype(np.uint8)
    dilated = cv2.dilate(src, kernel, iterations=2).astype(bool)
    eroded = cv2.erode(src, kernel, iterations=7).astype(bool)
    return dilated & ~eroded


def _estimate_matte_background(rgb, alpha, edge_band):
    maxc = rgb.max(axis=2)
    minc = rgb.min(axis=2)
    chroma = maxc - minc
    brightness = rgb.mean(axis=2)
    candidates = (
        edge_band
        & (alpha >= 8)
        & (alpha <= 210)
        & (brightness >= 125)
        & (chroma <= 72)
    )
    if int(np.count_nonzero(candidates)) < 16:
        candidates = (
            edge_band
            & (alpha >= 4)
            & (alpha <= 170)
            & (brightness >= 155)
            & (chroma <= 92)
        )
    if int(np.count_nonzero(candidates)) < 16:
        return np.array([245.0, 245.0, 245.0], dtype=np.float32), 0
    return np.median(rgb[candidates], axis=0).astype(np.float32), int(np.count_nonzero(candidates))


def _nearby_opaque_foreground(rgb, alpha):
    high = (alpha > 198).astype(np.float32)
    kernel = (11, 11)
    denom = cv2.GaussianBlur(high, kernel, 0)
    weighted = cv2.GaussianBlur(rgb * high[:, :, None], kernel, 0)
    near = np.zeros_like(rgb)
    valid = denom > 0.01
    near[valid] = weighted[valid] / denom[valid, None]
    near[~valid] = rgb[~valid]
    return near, valid


def _nearby_dark_foreground(rgb, alpha, hair_region):
    luma = rgb.mean(axis=2)
    dark = ((alpha > 160) & hair_region & (luma < 118)).astype(np.float32)
    kernel = (15, 15)
    denom = cv2.GaussianBlur(dark, kernel, 0)
    weighted = cv2.GaussianBlur(rgb * dark[:, :, None], kernel, 0)
    near = np.zeros_like(rgb)
    valid = denom > 0.006
    near[valid] = weighted[valid] / denom[valid, None]
    near[~valid] = rgb[~valid]
    return near, valid


def _face_protection_mask(shape, face_box):
    if not face_box:
        return np.zeros(shape, dtype=bool)
    fx = float(face_box.get("x") or 0)
    fy = float(face_box.get("y") or 0)
    fw = max(1.0, float(face_box.get("width") or 1))
    fh = max(1.0, float(face_box.get("height") or 1))
    yy, xx = np.indices(shape)
    cx = fx + fw * 0.5
    cy = fy + fh * 0.54
    rx = fw * 0.62
    ry = fh * 0.82
    ellipse = (((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2) <= 1.0
    face_rect = (
        (xx >= fx - fw * 0.08)
        & (xx <= fx + fw * 1.08)
        & (yy >= fy - fh * 0.18)
        & (yy <= fy + fh * 1.06)
    )
    return ellipse | face_rect


def _clean_edge_halo(layer, bg_rgb, face_box=None, source_background_rgb=None):
    """Decontaminate semi-transparent matte edges before background compose.

    Rembg-like matting can keep the source photo's pale wall/white background
    RGB in hair and shoulder transition pixels. If those pixels are composited
    directly on a blue/red/gray ID-photo background, they become a visible
    white or gray outline. This pass only targets low-saturation transition
    pixels on the alpha boundary, reconstructs cleaner foreground color, and
    trims tiny bright low-alpha remnants without globally eroding hair.
    """
    arr = np.asarray(layer).astype(np.float32).copy()
    if arr.ndim != 3 or arr.shape[2] != 4:
        return layer, {"edgeHaloPixelsCleaned": 0}
    alpha = arr[:, :, 3]
    fg = alpha > 3
    if not np.any(fg):
        return layer, {"edgeHaloPixelsCleaned": 0}

    edge_band = _mask_edge_band(fg)
    rgb = arr[:, :, :3]
    maxc = rgb.max(axis=2)
    minc = rgb.min(axis=2)
    chroma = maxc - minc
    brightness = rgb.mean(axis=2)
    bg = np.array(bg_rgb, dtype=np.float32)
    bg_luma = float(bg.mean())
    face_protect = _face_protection_mask(fg.shape, face_box)
    old_bg, old_bg_samples = _estimate_matte_background(rgb, alpha, edge_band)
    if isinstance(source_background_rgb, (list, tuple)) and len(source_background_rgb) == 3:
        try:
            old_bg = np.array([float(v) for v in source_background_rgb], dtype=np.float32)
            old_bg_samples = max(1, old_bg_samples)
        except Exception:
            pass
    near_fg, near_valid = _nearby_opaque_foreground(rgb, alpha)
    near_brightness = near_fg.mean(axis=2)
    ys = np.where(fg)[0]
    top = int(ys.min()) if ys.size else 0
    bottom = int(ys.max()) if ys.size else arr.shape[0] - 1
    y_grid = np.indices(fg.shape)[0]
    hair_region = y_grid <= top + int((bottom - top + 1) * 0.58)
    dark_near, dark_valid = _nearby_dark_foreground(rgb, alpha, hair_region)
    dark_brightness = dark_near.mean(axis=2)
    old_bg_chroma = float(old_bg.max() - old_bg.min())
    old_bg_luma = float(old_bg.mean())
    old_bg_blueish = bool(old_bg_chroma >= 48.0 and old_bg[2] > old_bg[0] + 34.0 and old_bg[2] > old_bg[1] + 18.0)
    old_bg_reddish = bool(old_bg_chroma >= 48.0 and old_bg[0] > old_bg[1] + 26.0 and old_bg[0] > old_bg[2] + 26.0)
    old_bg_colored = old_bg_blueish or old_bg_reddish or old_bg_chroma >= 70.0
    old_bg_dist = np.linalg.norm(rgb - old_bg, axis=2)

    transition = edge_band & (alpha >= 5)
    white_halo = transition & (chroma <= 58) & (brightness >= max(150.0, bg_luma + 22.0))
    gray_halo = transition & (chroma <= 34) & (brightness >= 92.0) & (brightness <= 226.0)
    low_alpha_haze = transition & (alpha < 82) & (brightness >= 94.0) & (chroma <= 96)
    near_dark_hair = near_valid & (near_brightness < 92.0)
    hair_light_rim = (
        transition
        & hair_region
        & ((near_dark_hair & (brightness > near_brightness + 28.0)) | (dark_valid & (brightness > dark_brightness + 24.0)))
        & (brightness > 112.0)
        & (chroma < 110)
    )
    source_color_direction = np.zeros_like(fg, dtype=bool)
    if old_bg_colored:
        if old_bg_blueish:
            source_color_direction = (
                (rgb[:, :, 2] > rgb[:, :, 0] + 6.0)
                & (rgb[:, :, 2] >= rgb[:, :, 1] - 18.0)
            )
        elif old_bg_reddish:
            source_color_direction = (
                (rgb[:, :, 0] > rgb[:, :, 1] + 10.0)
                & (rgb[:, :, 0] > rgb[:, :, 2] + 10.0)
            )
        else:
            source_color_direction = old_bg_dist <= 118.0
    source_colored_rim = (
        transition
        & old_bg_colored
        & source_color_direction
        & ~face_protect
        & (brightness >= max(18.0, old_bg_luma * 0.16))
        & (chroma >= 18.0)
        & (
            (old_bg_dist <= 172.0)
            | (hair_region & near_valid & (brightness > near_brightness + 4.0))
            | (hair_region & dark_valid & (brightness > dark_brightness + 4.0))
            | hair_region
        )
    )
    hair_background_leak = (
        hair_region
        & ~face_protect
        & dark_valid
        & (chroma < 32)
        & (brightness > max(150.0, bg_luma + 12.0))
        & (brightness > dark_brightness + 46.0)
    )
    # Some matting outputs contain opaque pieces of the original pale wall
    # beside hair.  They are not alpha-transition pixels, so normal edge
    # decontamination only recolors them.  Treat low-saturation bright sheets
    # in the upper hair area as old background, while protecting the face oval.
    neutral_bg_sheet = (
        hair_region
        & ~face_protect
        & (alpha > 60)
        & (chroma < 60)
        & (brightness > max(145.0, bg_luma - 15.0))
    )
    side_bg_sheet = np.zeros_like(fg, dtype=bool)
    if face_box:
        fx = float(face_box.get("x") or 0)
        fy = float(face_box.get("y") or 0)
        fw = max(1.0, float(face_box.get("width") or 1))
        fh = max(1.0, float(face_box.get("height") or 1))
        yy, xx = np.indices(fg.shape)
        cx = fx + fw * 0.5
        lateral = np.abs(xx - cx)
        side_zone = (
            (yy >= fy + fh * 0.42)
            & (yy <= fy + fh * 1.86)
            & (lateral >= fw * 0.18)
            & (lateral <= fw * 1.24)
        )
        core_face_neck = (
            (((xx - cx) / (fw * 0.34)) ** 2 + ((yy - (fy + fh * 0.55)) / (fh * 0.64)) ** 2 <= 1.0)
            | (
                (lateral <= fw * 0.13)
                & (yy >= fy + fh * 0.72)
                & (yy <= fy + fh * 1.62)
            )
        )
        skin_like = (
            (rgb[:, :, 0] > 92)
            & (rgb[:, :, 1] > 48)
            & (rgb[:, :, 2] > 34)
            & (rgb[:, :, 0] >= rgb[:, :, 1] - 8)
            & (rgb[:, :, 1] >= rgb[:, :, 2] - 6)
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
        source_bg_like = (
            (alpha > 8)
            & (chroma <= 118)
            & (brightness >= 48.0)
            & (brightness <= 246.0)
            & (
                (np.linalg.norm(rgb - old_bg, axis=2) <= 156.0)
                | ((brightness >= 58.0) & (chroma <= 104.0))
            )
        )
        side_candidates = side_zone & source_bg_like & ~core_face_neck & ~skin_like & ~hair_like & ~clothing_like
        side_seed = side_candidates & (edge_band | (alpha < 252))
        if int(np.count_nonzero(side_candidates)):
            n, labels, stats, _ = cv2.connectedComponentsWithStats(side_candidates.astype("uint8"), 8)
            for label in range(1, n):
                comp = labels == label
                area = int(stats[label, cv2.CC_STAT_AREA])
                if area < 3:
                    continue
                mean_chroma = float(np.mean(chroma[comp]))
                mean_brightness = float(np.mean(brightness[comp]))
                seeded = bool(np.any(comp & side_seed))
                large_neutral_sheet = area >= 18 and mean_chroma <= 108.0 and mean_brightness >= 50.0
                if mean_chroma <= 104.0 and (seeded or large_neutral_sheet):
                    side_bg_sheet |= comp
    halo = white_halo | gray_halo | low_alpha_haze | hair_light_rim | source_colored_rim | hair_background_leak | neutral_bg_sheet | side_bg_sheet

    cleaned = int(np.count_nonzero(halo))
    trimmed = 0
    decontaminated = 0
    if cleaned:
        alpha_norm = np.clip(alpha / 255.0, 0.16, 1.0)
        reconstructed = (rgb - (1.0 - alpha_norm[:, :, None]) * old_bg) / alpha_norm[:, :, None]
        reconstructed = np.clip(reconstructed, 0, 255)

        strength = np.zeros_like(alpha, dtype=np.float32)
        strength[low_alpha_haze] = np.maximum(strength[low_alpha_haze], 0.42)
        strength[gray_halo] = np.maximum(strength[gray_halo], 0.62)
        strength[white_halo] = np.maximum(strength[white_halo], 0.76)
        strength[hair_light_rim] = np.maximum(strength[hair_light_rim], 0.84)
        strength[source_colored_rim] = np.maximum(strength[source_colored_rim], 0.78)
        strength[source_colored_rim & hair_region] = np.maximum(strength[source_colored_rim & hair_region], 0.90)
        strength *= halo.astype(np.float32)

        rebuilt = rgb * (1.0 - strength[:, :, None]) + reconstructed * strength[:, :, None]
        neighbor_mix = halo & near_valid & ((brightness > near_brightness + 18.0) | white_halo | hair_light_rim | source_colored_rim)
        if int(np.count_nonzero(neighbor_mix)):
            nm = np.zeros_like(alpha, dtype=np.float32)
            nm[neighbor_mix] = 0.42
            nm[hair_light_rim] = np.maximum(nm[hair_light_rim], 0.58)
            nm[source_colored_rim] = np.maximum(nm[source_colored_rim], 0.62)
            rebuilt = rebuilt * (1.0 - nm[:, :, None]) + near_fg * nm[:, :, None]
        dark_mix = (hair_light_rim | (source_colored_rim & hair_region)) & dark_valid
        if int(np.count_nonzero(dark_mix)):
            dm = np.zeros_like(alpha, dtype=np.float32)
            dm[dark_mix] = 0.88
            dm[source_colored_rim & hair_region & dark_valid] = 0.94
            rebuilt = rebuilt * (1.0 - dm[:, :, None]) + dark_near * dm[:, :, None]
        leak_mix = hair_background_leak
        if int(np.count_nonzero(leak_mix)):
            lm = np.zeros_like(alpha, dtype=np.float32)
            lm[leak_mix] = 0.75
            rebuilt = rebuilt * (1.0 - lm[:, :, None]) + bg * lm[:, :, None]
        if int(np.count_nonzero(neutral_bg_sheet)):
            sm = np.zeros_like(alpha, dtype=np.float32)
            sm[neutral_bg_sheet] = 0.98
            rebuilt = rebuilt * (1.0 - sm[:, :, None]) + bg * sm[:, :, None]
        if int(np.count_nonzero(side_bg_sheet)):
            bm = np.zeros_like(alpha, dtype=np.float32)
            bm[side_bg_sheet] = 1.0
            rebuilt = rebuilt * (1.0 - bm[:, :, None]) + bg * bm[:, :, None]

        alpha_scale = np.ones_like(alpha, dtype=np.float32)
        trim_mask = low_alpha_haze & (alpha < 58)
        alpha_scale[trim_mask] = 0.36
        alpha_scale[white_halo & (alpha < 118)] = np.minimum(alpha_scale[white_halo & (alpha < 118)], 0.72)
        alpha_scale[hair_light_rim & (alpha < 70)] = np.minimum(alpha_scale[hair_light_rim & (alpha < 70)], 0.52)
        alpha_scale[hair_light_rim] = np.minimum(alpha_scale[hair_light_rim], 0.68)
        alpha_scale[hair_light_rim & gray_halo] = np.minimum(alpha_scale[hair_light_rim & gray_halo], 0.45)
        alpha_scale[hair_light_rim & white_halo] = np.minimum(alpha_scale[hair_light_rim & white_halo], 0.20)
        alpha_scale[source_colored_rim & hair_region] = np.minimum(alpha_scale[source_colored_rim & hair_region], 0.72)
        alpha_scale[source_colored_rim & hair_region & (alpha >= 150)] = np.minimum(
            alpha_scale[source_colored_rim & hair_region & (alpha >= 150)], 0.84
        )
        source_colored_low_alpha = source_colored_rim & hair_region & (alpha < 150)
        alpha_scale[source_colored_low_alpha] = np.minimum(alpha_scale[source_colored_low_alpha], 0.46)
        alpha_scale[hair_background_leak] = np.minimum(alpha_scale[hair_background_leak], 0.18)
        alpha_scale[neutral_bg_sheet] = np.minimum(alpha_scale[neutral_bg_sheet], 0.04)
        alpha_scale[side_bg_sheet] = 0.0
        trimmed = int(np.count_nonzero(alpha_scale < 0.999))

        rgb[:] = rebuilt
        alpha[:] = alpha * alpha_scale
        decontaminated = int(np.count_nonzero(strength > 0.01))

    arr[:, :, :3] = np.clip(rgb, 0, 255)
    arr[:, :, 3] = np.clip(alpha, 0, 255)
    edge_pixels = int(np.count_nonzero(edge_band))
    transition_pixels = int(np.count_nonzero(transition))
    alpha_transition_width = round(transition_pixels / float(max(1, edge_pixels)), 4)
    return Image.fromarray(arr.astype(np.uint8), "RGBA"), {
        "edgeHaloPixelsCleaned": cleaned,
        "decontaminatedPixels": decontaminated,
        "trimmedLowAlphaHaloPixels": trimmed,
        "whiteHaloCandidatePixels": int(np.count_nonzero(white_halo)),
        "grayHaloCandidatePixels": int(np.count_nonzero(gray_halo)),
        "hairLightRimCandidatePixels": int(np.count_nonzero(hair_light_rim)),
        "sourceColoredRimCandidatePixels": int(np.count_nonzero(source_colored_rim)),
        "hairBackgroundLeakPixels": int(np.count_nonzero(hair_background_leak)),
        "neutralBackgroundSheetPixels": int(np.count_nonzero(neutral_bg_sheet)),
        "sideBackgroundSheetPixels": int(np.count_nonzero(side_bg_sheet)),
        "alphaTransitionPixels": transition_pixels,
        "alphaTransitionWidth": alpha_transition_width,
        "estimatedSourceBackgroundRgb": [round(float(v), 2) for v in old_bg.tolist()],
        "estimatedSourceBackgroundSamples": old_bg_samples,
    }


def _remove_composed_side_residue(image, bg_rgb, face_box, old_bg_rgb=None):
    """Paint visible old-background side pockets back to the selected ID color."""
    if image is None or not face_box:
        return image, {"composedSideResiduePixels": 0, "composedSideResidueMaxComponent": 0}

    arr = np.asarray(image.convert("RGB")).astype(np.float32).copy()
    h, w = arr.shape[:2]
    fx = float(face_box.get("x") or w * 0.30)
    fy = float(face_box.get("y") or h * 0.16)
    fw = max(1.0, float(face_box.get("width") or w * 0.40))
    fh = max(1.0, float(face_box.get("height") or h * 0.28))
    yy, xx = np.indices((h, w))
    cx = fx + fw * 0.5
    lateral = np.abs(xx - cx)

    rgb = arr
    maxc = rgb.max(axis=2)
    minc = rgb.min(axis=2)
    chroma = maxc - minc
    brightness = rgb.mean(axis=2)
    bg = np.array(bg_rgb, dtype=np.float32)
    if isinstance(old_bg_rgb, (list, tuple)) and len(old_bg_rgb) == 3:
        old_bg = np.array(old_bg_rgb, dtype=np.float32)
    else:
        old_bg = bg
    bg_dist = np.linalg.norm(rgb - bg, axis=2)
    old_bg_dist = np.linalg.norm(rgb - old_bg, axis=2)
    old_bg_chroma = float(old_bg.max() - old_bg.min())
    old_bg_blueish = bool(old_bg_chroma >= 48.0 and old_bg[2] > old_bg[0] + 28.0 and old_bg[2] > old_bg[1] + 12.0)
    old_bg_reddish = bool(old_bg_chroma >= 48.0 and old_bg[0] > old_bg[1] + 24.0 and old_bg[0] > old_bg[2] + 24.0)
    old_bg_colored = old_bg_blueish or old_bg_reddish or old_bg_chroma >= 70.0

    side_pocket = (
        (yy >= fy + fh * 0.16)
        & (yy <= fy + fh * 1.56)
        & (lateral >= fw * 0.34)
        & (lateral <= fw * 1.52)
    )
    neck_inner_pocket = (
        (yy >= fy + fh * 0.58)
        & (yy <= fy + fh * 1.48)
        & (lateral >= fw * 0.18)
        & (lateral <= fw * 0.78)
    )
    pocket = side_pocket | neck_inner_pocket

    skin_like = (
        (rgb[:, :, 0] > 92)
        & (rgb[:, :, 1] > 48)
        & (rgb[:, :, 2] > 34)
        & (rgb[:, :, 0] >= rgb[:, :, 1] - 8)
        & (rgb[:, :, 1] >= rgb[:, :, 2] - 6)
        & (rgb[:, :, 0] > rgb[:, :, 2] + 18)
        & (chroma > 24)
    )
    face_skin_core = (
        ((xx - cx) / (fw * 0.62)) ** 2
        + ((yy - (fy + fh * 0.56)) / (fh * 0.86)) ** 2
        <= 1.0
    )
    strong_skin_like = skin_like & (chroma > 38.0) & (rgb[:, :, 0] > rgb[:, :, 2] + 26.0)
    hair_like = (brightness < 84.0) & (chroma <= 62.0) & (yy <= fy + fh * 1.06)
    true_hair_like = hair_like & ((lateral <= fw * 0.82) | face_skin_core)
    lower_subject_zone = yy >= fy + fh * 0.98
    dark_clothing_like = lower_subject_zone & (
        ((brightness < 116.0) & (chroma <= 178.0))
        | ((brightness < 158.0) & (chroma >= 28.0) & (chroma <= 196.0))
    )
    saturated_clothing_like = lower_subject_zone & (brightness < 218.0) & (chroma > 54.0)
    light_clothing_like = (
        (yy >= fy + fh * 1.02)
        & (lateral <= fw * 0.72)
        & (brightness >= 132.0)
        & (brightness <= 250.0)
        & (chroma <= 82.0)
    )
    clothing_like = dark_clothing_like | saturated_clothing_like | light_clothing_like
    source_bg_match = (
        (old_bg_dist <= (126.0 if old_bg_colored else 92.0))
        & (chroma <= 132.0)
        & (brightness >= 42.0)
        & (brightness <= 248.0)
        & ~face_skin_core
    )
    source_color_direction = np.zeros((h, w), dtype=bool)
    if old_bg_blueish:
        source_color_direction = (
            (rgb[:, :, 2] > rgb[:, :, 0] + 8.0)
            & (rgb[:, :, 2] >= rgb[:, :, 1] - 22.0)
        )
    elif old_bg_reddish:
        source_color_direction = (
            (rgb[:, :, 0] > rgb[:, :, 1] + 10.0)
            & (rgb[:, :, 0] > rgb[:, :, 2] + 10.0)
        )
    elif old_bg_colored:
        source_color_direction = old_bg_dist <= 132.0
    face_edge_color_residue = (
        (yy >= fy + fh * 0.76)
        & (lateral >= fw * 0.24)
        & source_color_direction
        & ~skin_like
    )
    skin_protect = skin_like & (face_skin_core | strong_skin_like | ~source_bg_match)
    neutral_old_bg = (
        pocket
        & (bg_dist > 34.0)
        & ~skin_protect
        & ~face_skin_core
        & ~true_hair_like
        & ~clothing_like
        & (brightness >= 58.0)
        & (brightness <= 246.0)
        & (chroma <= 112.0)
        & (source_bg_match | (chroma <= 74.0))
    )
    colored_source_bg = (
        pocket
        & old_bg_colored
        & (yy <= fy + fh * 1.92)
        & (bg_dist > 34.0)
        & (old_bg_dist <= 190.0)
        & source_color_direction
        & ~skin_protect
        & (~face_skin_core | face_edge_color_residue)
        & (~true_hair_like | face_edge_color_residue)
        & (~clothing_like | face_edge_color_residue)
        & (
            (lateral >= fw * 0.42)
            | ((yy >= fy + fh * 0.62) & (lateral >= fw * 0.26))
        )
        & (brightness >= 34.0)
        & (brightness <= 252.0)
    )

    central_clothing_protect = (
        (lateral <= fw * 0.58)
        & (yy >= fy + fh * 0.86)
        & (yy <= fy + fh * 2.35)
    )
    hard_artifact = (
        pocket
        & (bg_dist > 34.0)
        & ~skin_protect
        & ~face_skin_core
        & ~true_hair_like
        & ~clothing_like
        & ~central_clothing_protect
        & (
            ((brightness < 26.0) & (chroma < 58.0))
            | ((brightness < 54.0) & (chroma < 96.0) & (yy <= fy + fh * 1.25) & (lateral >= fw * 0.70))
            | ((brightness > 236.0) & (chroma < 44.0))
        )
    )

    residue_u8 = cv2.morphologyEx(
        (neutral_old_bg | colored_source_bg | hard_artifact).astype("uint8"),
        cv2.MORPH_OPEN,
        np.ones((2, 2), np.uint8),
        iterations=1,
    )
    n, labels, stats, _ = cv2.connectedComponentsWithStats(residue_u8, 8)
    remove = np.zeros((h, w), dtype=bool)
    max_component = 0
    for label in range(1, n):
        comp = labels == label
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < 10:
            continue
        x, y, cw, ch, _ = stats[label]
        mean_chroma = float(np.mean(chroma[comp]))
        mean_brightness = float(np.mean(brightness[comp]))
        max_component = max(max_component, area)
        touches_side_gap = x <= max(2, int(fx - fw * 0.52)) or (x + cw) >= min(w - 2, int(fx + fw * 1.52))
        upper_neck_sheet = (y + ch) <= int(fy + fh * 1.60)
        touches_image_side = x <= 1 or (x + cw) >= (w - 1)
        elongated = cw >= max(10, ch * 3) or ch >= max(10, cw * 3)
        hard = bool(np.any(comp & hard_artifact))
        source_colored = bool(np.any(comp & colored_source_bg))
        if hard and (touches_side_gap or touches_image_side or elongated or (area <= 320 and upper_neck_sheet)):
            remove |= comp
        elif source_colored and upper_neck_sheet and (touches_side_gap or touches_image_side or area <= 1200):
            remove |= comp
        elif upper_neck_sheet and (touches_side_gap or area >= 18) and mean_chroma <= 108.0 and mean_brightness >= 58.0:
            remove |= comp

    removed = int(np.count_nonzero(remove))
    if removed:
        arr[remove] = bg
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB"), {
        "composedSideResiduePixels": removed,
        "composedSideResidueMaxComponent": max_component,
    }


def _remove_dark_back_panel(layer, face_box):
    """Remove opaque dark background islands behind the head/neck.

    Some portrait mattes keep a chair, doorway, or dark wall as an opaque
    half-oval behind the head.  This pass is deliberately geometry-bound:
    it only looks in lateral head/upper-neck background pockets and protects
    the face oval, hair envelope, central neck, and lower clothing area.
    """
    if layer is None or not face_box:
        return layer, {"darkBackPanelRemovedPixels": 0, "darkBackPanelMaxComponent": 0}

    arr = np.asarray(layer.convert("RGBA")).astype(np.float32).copy()
    alpha = arr[:, :, 3]
    if int(np.count_nonzero(alpha > 8)) < 64:
        return layer, {"darkBackPanelRemovedPixels": 0, "darkBackPanelMaxComponent": 0}

    h, w = alpha.shape
    fx = float(face_box.get("x") or w * 0.30)
    fy = float(face_box.get("y") or h * 0.18)
    fw = max(1.0, float(face_box.get("width") or w * 0.40))
    fh = max(1.0, float(face_box.get("height") or h * 0.30))
    yy, xx = np.indices((h, w))
    cx = fx + fw * 0.5
    lateral = np.abs(xx - cx)

    rgb = arr[:, :, :3]
    brightness = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)

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
    # Clothing often starts immediately below the jaw in ID-photo crops.  The
    # previous threshold allowed dark sweaters/suits near the collar and
    # shoulders to be mistaken for a "black back panel", producing blue holes.
    lower_clothing_protect = yy >= fy + fh * 1.06
    protect = face_hair_protect | central_neck_protect | lower_clothing_protect

    pocket = (
        (yy >= fy - fh * 0.22)
        & (yy <= fy + fh * 1.08)
        & (lateral >= fw * 0.30)
        & (lateral <= fw * 1.34)
        & ~protect
    )
    side_neck_panel = (
        (yy >= fy + fh * 0.55)
        & (yy <= fy + fh * 1.06)
        & (lateral >= fw * 0.26)
        & (lateral <= fw * 1.30)
        & ~central_neck_protect
        & ~lower_clothing_protect
    )
    dark_candidate = (
        (pocket | side_neck_panel)
        & (alpha > 70)
        & (brightness < 68.0)
        & (chroma < 82.0)
    )
    if int(np.count_nonzero(dark_candidate)) < 24:
        return layer, {"darkBackPanelRemovedPixels": 0, "darkBackPanelMaxComponent": 0}

    candidate = cv2.morphologyEx(dark_candidate.astype("uint8"), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8), iterations=1)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, 8)
    remove = np.zeros((h, w), dtype=bool)
    max_component = 0
    min_area = max(28, int(w * h * 0.0018))
    for label in range(1, n):
        area = int(stats[label, cv2.CC_STAT_AREA])
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        cw = int(stats[label, cv2.CC_STAT_WIDTH])
        ch = int(stats[label, cv2.CC_STAT_HEIGHT])
        max_component = max(max_component, area)
        if area < min_area or cw < max(7, int(fw * 0.07)) or ch < max(12, int(fh * 0.15)):
            continue
        touches_lower_clothes = (y + ch) >= int(fy + fh * 1.08)
        if touches_lower_clothes:
            continue
        comp = labels == label
        # If the dark region is connected downward into the person's clothing,
        # it is almost certainly a black sweater/suit rather than background.
        if np.any(comp & lower_clothing_protect):
            continue
        remove |= comp

    removed = int(np.count_nonzero(remove))
    if removed:
        trim = cv2.dilate(remove.astype("uint8"), np.ones((2, 2), np.uint8), iterations=1).astype(bool)
        alpha[trim] = 0
        arr[:, :, 3] = alpha
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA"), {
        "darkBackPanelRemovedPixels": removed,
        "darkBackPanelMaxComponent": max_component,
    }


def _repair_composed_body_holes(result, layer, bg_rgb, face_box):
    """Inpaint only small background-colored holes inside the body silhouette."""
    if result is None or layer is None or not face_box:
        return result, layer, {"composedBodyHoleRepairedPixels": 0, "composedBodyHoleMaxComponent": 0}

    rgb = np.asarray(result.convert("RGB")).astype(np.uint8).copy()
    layer_arr = np.asarray(layer.convert("RGBA")).copy()
    alpha = layer_arr[:, :, 3]
    h, w = alpha.shape[:2]

    fx = float(face_box.get("x") or w * 0.30)
    fy = float(face_box.get("y") or h * 0.16)
    fw = max(1.0, float(face_box.get("width") or w * 0.40))
    fh = max(1.0, float(face_box.get("height") or h * 0.28))
    cx = fx + fw * 0.5
    yy, xx = np.indices((h, w))
    lateral = np.abs(xx - cx)

    body_zone = (
        (yy >= fy + fh * 1.05)
        & (yy <= fy + fh * 2.48)
        & (lateral <= fw * 1.95)
    )
    fg = alpha > 48
    row_has_fg = np.any(fg, axis=1)
    left = np.argmax(fg, axis=1)
    right = w - 1 - np.argmax(fg[:, ::-1], axis=1)
    inside_foreground_span = row_has_fg[:, None] & (xx >= left[:, None]) & (xx <= right[:, None])
    # Shoulder/clothing cutouts are often open to the surrounding background,
    # so a tiny dilation only catches pinholes. Use a wider but still
    # geometry-bounded band; large background regions are filtered by connected
    # component size below.
    near_foreground = cv2.dilate(fg.astype("uint8"), np.ones((25, 25), np.uint8), iterations=1) > 0

    bg = np.asarray(bg_rgb, dtype=np.float32)
    arr_f = rgb.astype(np.float32)
    diff = np.linalg.norm(arr_f - bg, axis=2)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    mean = cv2.blur(gray.astype(np.float32), (5, 5))
    mean_sq = cv2.blur(gray.astype(np.float32) ** 2, (5, 5))
    local_std = np.sqrt(np.maximum(mean_sq - mean ** 2, 0.0))
    hole_seed = (
        body_zone
        & near_foreground
        & (inside_foreground_span | (lateral >= fw * 0.62))
        & (alpha < 104)
        & (diff <= 44.0)
        & (local_std < 10.0)
    )
    if int(np.count_nonzero(hole_seed)) <= 0:
        return result, layer, {"composedBodyHoleRepairedPixels": 0, "composedBodyHoleMaxComponent": 0}

    n, labels, stats, _ = cv2.connectedComponentsWithStats(hole_seed.astype("uint8"), 8)
    repair = np.zeros((h, w), dtype=np.uint8)
    max_component = 0
    repaired_pixels = 0
    max_area = max(160, int(w * h * 0.030))
    for label in range(1, n):
        area = int(stats[label, cv2.CC_STAT_AREA])
        max_component = max(max_component, area)
        if area < 6 or area > max_area:
            continue
        comp = labels == label
        repair[comp] = 255
        repaired_pixels += area

    if repaired_pixels <= 0:
        return result, layer, {
            "composedBodyHoleRepairedPixels": 0,
            "composedBodyHoleMaxComponent": max_component,
        }

    repair = cv2.dilate(repair, np.ones((3, 3), np.uint8), iterations=1)
    repaired_rgb = cv2.inpaint(rgb, repair, 3, cv2.INPAINT_TELEA)
    layer_arr[:, :, 3][repair > 0] = 255
    return Image.fromarray(repaired_rgb, "RGB"), Image.fromarray(layer_arr, "RGBA"), {
        "composedBodyHoleRepairedPixels": int(repaired_pixels),
        "composedBodyHoleMaxComponent": int(max_component),
    }


def _repair_composed_hair_holes(result, layer, bg_rgb, face_box):
    """Inpaint selected-background pinholes inside the dark hair envelope."""
    if result is None or layer is None or not face_box:
        return result, layer, {"composedHairHoleRepairedPixels": 0, "composedHairHoleMaxComponent": 0}

    rgb = np.asarray(result.convert("RGB")).astype(np.uint8).copy()
    layer_arr = np.asarray(layer.convert("RGBA")).copy()
    alpha = layer_arr[:, :, 3]
    h, w = alpha.shape[:2]

    fx = float(face_box.get("x") or w * 0.30)
    fy = float(face_box.get("y") or h * 0.16)
    fw = max(1.0, float(face_box.get("width") or w * 0.40))
    fh = max(1.0, float(face_box.get("height") or h * 0.28))
    cx = fx + fw * 0.5
    yy, xx = np.indices((h, w))
    lateral = np.abs(xx - cx)

    arr_f = rgb.astype(np.float32)
    brightness = arr_f.mean(axis=2)
    chroma = arr_f.max(axis=2) - arr_f.min(axis=2)
    bg = np.asarray(bg_rgb, dtype=np.float32)
    bg_dist = np.linalg.norm(arr_f - bg, axis=2)

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
        & (alpha > 42)
        & (brightness < 122.0)
        & (chroma <= 148.0)
        & (bg_dist > 52.0)
    )
    if int(np.count_nonzero(dark_hair)) < 24:
        return result, layer, {"composedHairHoleRepairedPixels": 0, "composedHairHoleMaxComponent": 0}

    row_has = np.any(dark_hair, axis=1)
    left = np.argmax(dark_hair, axis=1)
    right = w - 1 - np.argmax(dark_hair[:, ::-1], axis=1)
    inside_hair_span = row_has[:, None] & (xx >= left[:, None]) & (xx <= right[:, None])
    close_size = max(9, int(fw * 0.16) | 1)
    hair_envelope = cv2.morphologyEx(
        dark_hair.astype("uint8"),
        cv2.MORPH_CLOSE,
        np.ones((close_size, close_size), np.uint8),
        iterations=1,
    ).astype(bool)
    hair_envelope = cv2.dilate(hair_envelope.astype("uint8"), np.ones((5, 5), np.uint8), iterations=1).astype(bool)
    near_hair = cv2.dilate(dark_hair.astype("uint8"), np.ones((9, 9), np.uint8), iterations=1).astype(bool)
    hole_seed = (
        hair_zone
        & (inside_hair_span | hair_envelope)
        & near_hair
        & ~face_core
        & (bg_dist <= 56.0)
        & (alpha < 150)
    )
    if int(np.count_nonzero(hole_seed)) <= 0:
        return result, layer, {"composedHairHoleRepairedPixels": 0, "composedHairHoleMaxComponent": 0}

    n, labels, stats, _ = cv2.connectedComponentsWithStats(hole_seed.astype("uint8"), 8)
    repair = np.zeros((h, w), dtype=np.uint8)
    max_component = 0
    repaired_pixels = 0
    max_area = max(36, int(w * h * 0.012))
    for label in range(1, n):
        area = int(stats[label, cv2.CC_STAT_AREA])
        max_component = max(max_component, area)
        if area < 3 or area > max_area:
            continue
        comp = labels == label
        repair[comp] = 255
        repaired_pixels += area

    if repaired_pixels <= 0:
        return result, layer, {
            "composedHairHoleRepairedPixels": 0,
            "composedHairHoleMaxComponent": int(max_component),
        }

    repair = cv2.dilate(repair, np.ones((3, 3), np.uint8), iterations=1)
    repaired_rgb = cv2.inpaint(rgb, repair, 3, cv2.INPAINT_TELEA)
    layer_arr[:, :, 3][repair > 0] = np.maximum(layer_arr[:, :, 3][repair > 0], 220)
    return Image.fromarray(repaired_rgb, "RGB"), Image.fromarray(layer_arr, "RGBA"), {
        "composedHairHoleRepairedPixels": int(repaired_pixels),
        "composedHairHoleMaxComponent": int(max_component),
    }


def _remove_composed_hair_side_blocks(result, layer, bg_rgb, face_box):
    """Remove old-background chunks that were retained as foreground beside hair."""
    if result is None or layer is None or not face_box:
        return result, layer, {"composedHairSideBlockRemovedPixels": 0, "composedHairSideBlockMaxComponent": 0}

    rgb = np.asarray(result.convert("RGB")).astype(np.float32).copy()
    layer_arr = np.asarray(layer.convert("RGBA")).copy()
    alpha = layer_arr[:, :, 3]
    h, w = alpha.shape[:2]

    fx = float(face_box.get("x") or w * 0.30)
    fy = float(face_box.get("y") or h * 0.16)
    fw = max(1.0, float(face_box.get("width") or w * 0.40))
    fh = max(1.0, float(face_box.get("height") or h * 0.28))
    cx = fx + fw * 0.5
    yy, xx = np.indices((h, w))
    lateral = np.abs(xx - cx)

    brightness = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    bg = np.asarray(bg_rgb, dtype=np.float32)
    bg_dist = np.linalg.norm(rgb - bg, axis=2)
    face_core = (
        ((xx - cx) / (fw * 0.58)) ** 2
        + ((yy - (fy + fh * 0.58)) / (fh * 0.82)) ** 2
        <= 1.0
    )
    skin_like = (
        (rgb[:, :, 0] > 92)
        & (rgb[:, :, 1] > 48)
        & (rgb[:, :, 2] > 34)
        & (rgb[:, :, 0] >= rgb[:, :, 1] - 8)
        & (rgb[:, :, 1] >= rgb[:, :, 2] - 8)
        & (rgb[:, :, 0] > rgb[:, :, 2] + 14)
        & (chroma > 20.0)
        & (brightness < 245.0)
    )
    hair_like = (
        (brightness < 124.0)
        & (chroma <= 150.0)
        & (yy <= fy + fh * 0.72)
        & (lateral <= fw * 1.02)
        & (bg_dist > 52.0)
    )
    side_hair_zone = (
        (yy >= fy - fh * 0.12)
        & (yy <= fy + fh * 0.72)
        & (lateral >= fw * 0.42)
        & (lateral <= fw * 1.20)
    )
    block_seed = (
        side_hair_zone
        & (alpha > 18)
        & ~face_core
        & ~skin_like
        & ~hair_like
        & (
            ((brightness > 132.0) & (chroma < 112.0))
            | ((bg_dist <= 68.0) & (chroma < 150.0))
        )
    )
    if int(np.count_nonzero(block_seed)) < 4:
        return result, layer, {"composedHairSideBlockRemovedPixels": 0, "composedHairSideBlockMaxComponent": 0}

    block_seed = cv2.morphologyEx(block_seed.astype("uint8"), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8), iterations=1)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(block_seed, 8)
    remove = np.zeros((h, w), dtype=bool)
    max_component = 0
    for label in range(1, n):
        area = int(stats[label, cv2.CC_STAT_AREA])
        max_component = max(max_component, area)
        if area < 4 or area > max(1200, int(w * h * 0.018)):
            continue
        x = int(stats[label, cv2.CC_STAT_LEFT])
        cw = int(stats[label, cv2.CC_STAT_WIDTH])
        comp = labels == label
        side_anchored = x <= int(cx - fw * 0.54) or (x + cw) >= int(cx + fw * 0.54)
        if side_anchored or area <= 260:
            remove |= comp

    removed = int(np.count_nonzero(remove))
    if removed:
        trim = cv2.dilate(remove.astype("uint8"), np.ones((2, 2), np.uint8), iterations=1).astype(bool)
        layer_arr[:, :, 3][trim] = 0
        rgb[trim] = bg
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB"), Image.fromarray(layer_arr, "RGBA"), {
        "composedHairSideBlockRemovedPixels": int(removed),
        "composedHairSideBlockMaxComponent": int(max_component),
    }


def _remove_composed_dark_line_artifacts(image, bg_rgb, face_box):
    """Paint thin old-background lines in the shoulder/head side area."""
    if image is None or not face_box:
        return image, {"composedDarkLineRemovedPixels": 0, "composedDarkLineMaxComponent": 0}

    arr = np.asarray(image.convert("RGB")).astype(np.float32).copy()
    h, w = arr.shape[:2]
    fx = float(face_box.get("x") or w * 0.30)
    fy = float(face_box.get("y") or h * 0.16)
    fw = max(1.0, float(face_box.get("width") or w * 0.40))
    fh = max(1.0, float(face_box.get("height") or h * 0.28))
    cx = fx + fw * 0.5
    yy, xx = np.indices((h, w))
    lateral = np.abs(xx - cx)

    brightness = arr.mean(axis=2)
    chroma = arr.max(axis=2) - arr.min(axis=2)
    bg = np.asarray(bg_rgb, dtype=np.float32)
    bg_dist = np.linalg.norm(arr - bg, axis=2)
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
    side_upper = (
        (yy >= fy + fh * 0.78)
        & (yy <= fy + fh * 2.05)
        & (lateral >= fw * 0.58)
        & (lateral <= fw * 2.0)
    )
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
    hair_protect = (brightness < 96.0) & (chroma < 90.0) & (yy <= fy + fh * 1.08) & (lateral <= fw * 0.98)
    clothing_protect = (
        (yy >= fy + fh * 0.98)
        & (yy <= fy + fh * 2.45)
        & (lateral <= fw * 1.72)
        & (
            ((brightness < 118.0) & (chroma <= 190.0))
            | ((brightness < 170.0) & (chroma >= 20.0) & (chroma <= 210.0))
        )
    )
    near_selected_bg_wide = cv2.dilate(
        (bg_dist <= 44.0).astype("uint8"),
        np.ones((21, 21), np.uint8),
        iterations=1,
    ).astype(bool)
    boundary_line_candidate = (
        (yy >= fy + fh * 0.54)
        & (yy <= fy + fh * 1.82)
        & (lateral >= fw * 0.18)
        & (lateral <= fw * 1.90)
        & ~face_core
        & ~central_neck
        & ~skin_like
        & near_selected_bg_wide
        & (brightness < 122.0)
        & (chroma < 168.0)
        & (bg_dist > 42.0)
    )
    neck_side_line_candidate = (
        (yy >= fy + fh * 0.56)
        & (yy <= fy + fh * 1.50)
        & (lateral >= fw * 0.30)
        & (lateral <= fw * 1.10)
        & ~central_neck
        & ~skin_like
        & near_selected_bg_wide
        & (brightness < 128.0)
        & (chroma < 178.0)
        & (bg_dist > 38.0)
    )
    lower_side_artifact = (
        (yy >= fy + fh * 1.22)
        & (yy <= fy + fh * 2.12)
        & (lateral >= fw * 0.72)
        & (lateral <= fw * 1.96)
        & ~face_core
        & ~central_neck
        & ~skin_like
        & near_selected_bg_wide
        & (bg_dist > 42.0)
        & (
            ((brightness < 78.0) & (chroma < 150.0))
            | ((brightness > 196.0) & (chroma < 78.0))
            | (chroma > 88.0)
        )
    )
    candidate_core = (
        side_upper
        & ~face_core
        & ~central_neck
        & ~hair_protect
        & ~clothing_protect
        & (brightness < 86.0)
        & (chroma < 120.0)
        & (bg_dist > 45.0)
    )
    isolated_line_candidate = (
        side_upper
        & ~face_core
        & ~central_neck
        & ~hair_protect
        & (brightness < 94.0)
        & (chroma < 132.0)
        & (bg_dist > 45.0)
    )
    near_selected_bg = cv2.dilate((bg_dist <= 36.0).astype("uint8"), np.ones((5, 5), np.uint8), iterations=1).astype(bool)
    upper_side_boundary_line = (
        (yy >= fy + fh * 0.66)
        & (yy <= fy + fh * 1.24)
        & (lateral >= fw * 0.38)
        & (lateral <= fw * 1.78)
        & ~face_core
        & near_selected_bg
        & (brightness < 104.0)
        & (chroma < 150.0)
        & (bg_dist > 48.0)
    )
    candidate = (
        candidate_core
        | isolated_line_candidate
        | boundary_line_candidate
        | neck_side_line_candidate
        | lower_side_artifact
    )
    candidate = cv2.morphologyEx(candidate.astype("uint8"), cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8), iterations=1)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, 8)
    remove = np.zeros((h, w), dtype=bool)
    max_component = 0
    for label in range(1, n):
        area = int(stats[label, cv2.CC_STAT_AREA])
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        cw = int(stats[label, cv2.CC_STAT_WIDTH])
        ch = int(stats[label, cv2.CC_STAT_HEIGHT])
        max_component = max(max_component, area)
        comp = labels == label
        boundary_hit = bool(np.any(comp & (boundary_line_candidate | neck_side_line_candidate)))
        lower_side_hit = bool(np.any(comp & lower_side_artifact))
        max_allowed_area = 2400 if boundary_hit else (1500 if lower_side_hit else 900)
        if area < 4 or area > max_allowed_area:
            continue
        elongated = cw >= max(8, ch * 2.2) or ch >= max(8, cw * 2.2)
        touches_side = x <= 3 or (x + cw) >= w - 3
        density = float(area) / float(max(1, cw * ch))
        diagonal_thin_line = (
            area <= 620
            and density <= 0.42
            and cw >= max(12, int(fw * 0.20))
            and ch >= max(12, int(fh * 0.18))
        )
        side_anchored = (
            touches_side
            or x <= int(cx - fw * 0.88)
            or (x + cw) >= int(cx + fw * 0.88)
        )
        ring = cv2.dilate(comp.astype("uint8"), np.ones((7, 7), np.uint8), iterations=1).astype(bool) & ~cv2.dilate(
            comp.astype("uint8"),
            np.ones((3, 3), np.uint8),
            iterations=1,
        ).astype(bool)
        ring_count = int(np.count_nonzero(ring))
        ring_bg_ratio = 0.0
        if ring_count:
            ring_bg_ratio = float(np.count_nonzero(ring & (bg_dist <= 34.0))) / float(ring_count)
        upper_or_side_line = (y + ch) <= int(fy + fh * 2.08) and side_anchored
        if (
            (elongated or touches_side or diagonal_thin_line)
            and upper_or_side_line
            and (
                ring_bg_ratio >= 0.12
                or bool(np.any(comp & candidate_core))
                or boundary_hit
                or lower_side_hit
                or (touches_side and area <= 420)
            )
        ):
            remove |= labels == label
        elif boundary_hit and area <= 120 and density <= 0.90:
            remove |= labels == label
        elif boundary_hit and area <= 2200 and density <= 0.72 and ring_bg_ratio >= 0.045:
            remove |= labels == label
        elif lower_side_hit and area <= 120 and density <= 0.92:
            remove |= labels == label
        elif lower_side_hit and area <= 1400 and density <= 0.76 and ring_bg_ratio >= 0.055:
            remove |= labels == label

    side_boundary_line_removed = int(np.count_nonzero(upper_side_boundary_line & ~remove))
    if side_boundary_line_removed:
        remove |= upper_side_boundary_line

    line_removed = remove & (boundary_line_candidate | neck_side_line_candidate)
    if int(np.count_nonzero(line_removed)):
        remove |= cv2.dilate(line_removed.astype("uint8"), np.ones((3, 3), np.uint8), iterations=1).astype(bool)

    removed = int(np.count_nonzero(remove))
    if removed:
        arr[remove] = bg
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB"), {
        "composedDarkLineRemovedPixels": removed,
        "composedDarkLineMaxComponent": int(max_component),
        "composedSideBoundaryLineRemovedPixels": int(side_boundary_line_removed),
    }


def _repair_lower_shoulder_gaps(result, layer, bg_rgb, face_box):
    """Repair tiny selected-background gaps along the lower shoulder/chest line."""
    if result is None or layer is None or not face_box:
        return result, layer, {"lowerShoulderGapRepairedPixels": 0, "lowerShoulderGapMaxComponent": 0}

    rgb = np.asarray(result.convert("RGB")).astype(np.uint8).copy()
    layer_arr = np.asarray(layer.convert("RGBA")).copy()
    alpha = layer_arr[:, :, 3]
    h, w = alpha.shape[:2]
    fx = float(face_box.get("x") or w * 0.30)
    fy = float(face_box.get("y") or h * 0.16)
    fw = max(1.0, float(face_box.get("width") or w * 0.40))
    fh = max(1.0, float(face_box.get("height") or h * 0.28))
    cx = fx + fw * 0.5
    yy, xx = np.indices((h, w))
    lateral = np.abs(xx - cx)

    torso_zone = (
        (yy >= fy + fh * 1.22)
        & (yy <= fy + fh * 2.48)
        & (lateral <= fw * 0.78)
    )
    shoulder_zone = (
        (yy >= fy + fh * 1.30)
        & (yy <= fy + fh * 2.48)
        & (lateral >= fw * 0.36)
        & (lateral <= fw * 1.72)
    )
    body_zone = torso_zone | shoulder_zone

    fg = alpha > 48
    if int(np.count_nonzero(fg)) < 64:
        return result, layer, {"lowerShoulderGapRepairedPixels": 0, "lowerShoulderGapMaxComponent": 0}
    row_has_fg = np.any(fg, axis=1)
    left = np.argmax(fg, axis=1)
    right = w - 1 - np.argmax(fg[:, ::-1], axis=1)
    inside_foreground_span = row_has_fg[:, None] & (xx >= left[:, None]) & (xx <= right[:, None])

    bg = np.asarray(bg_rgb, dtype=np.float32)
    rgb_f = rgb.astype(np.float32)
    diff = np.linalg.norm(rgb_f - bg, axis=2)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    mean = cv2.blur(gray.astype(np.float32), (5, 5))
    mean_sq = cv2.blur(gray.astype(np.float32) ** 2, (5, 5))
    local_std = np.sqrt(np.maximum(mean_sq - mean ** 2, 0.0))
    candidate = body_zone & inside_foreground_span & (alpha < 80) & (diff <= 34.0) & (local_std < 7.5)
    if int(np.count_nonzero(candidate)) <= 0:
        return result, layer, {"lowerShoulderGapRepairedPixels": 0, "lowerShoulderGapMaxComponent": 0}

    n, labels, stats, _ = cv2.connectedComponentsWithStats(candidate.astype("uint8"), 8)
    repair = np.zeros((h, w), dtype=np.uint8)
    max_component = 0
    repaired_pixels = 0
    for label in range(1, n):
        area = int(stats[label, cv2.CC_STAT_AREA])
        max_component = max(max_component, area)
        if area < 4 or area > max(320, int(w * h * 0.004)):
            continue
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        cw = int(stats[label, cv2.CC_STAT_WIDTH])
        ch = int(stats[label, cv2.CC_STAT_HEIGHT])
        if y < int(fy + fh * 1.20):
            continue
        if cw > fw * 0.62 or ch > fh * 0.46:
            continue
        comp = labels == label
        repair[comp] = 255
        repaired_pixels += area

    if repaired_pixels <= 0:
        return result, layer, {
            "lowerShoulderGapRepairedPixels": 0,
            "lowerShoulderGapMaxComponent": int(max_component),
        }

    repair = cv2.dilate(repair, np.ones((3, 3), np.uint8), iterations=1)
    source_rgb = layer_arr[:, :, :3].astype(np.float32)
    source_diff = np.linalg.norm(source_rgb - bg, axis=2)
    source_luma = source_rgb.mean(axis=2)
    source_valid = (repair > 0) & (source_diff > 44.0) & (source_luma > 6.0)
    seeded = rgb.copy()
    if int(np.count_nonzero(source_valid)):
        seeded[source_valid] = np.clip(source_rgb[source_valid], 0, 255).astype(np.uint8)
    inpaint_mask = repair.copy()
    inpaint_mask[source_valid] = 0
    if int(np.count_nonzero(inpaint_mask)):
        seeded = cv2.inpaint(seeded, inpaint_mask, 3, cv2.INPAINT_TELEA)
    layer_arr[:, :, :3][repair > 0] = seeded[repair > 0]
    layer_arr[:, :, 3][repair > 0] = 255
    return Image.fromarray(seeded, "RGB"), Image.fromarray(layer_arr, "RGBA"), {
        "lowerShoulderGapRepairedPixels": int(repaired_pixels),
        "lowerShoulderGapMaxComponent": int(max_component),
    }


def _extend_small_lower_panel_gaps(result, layer, face_box, max_gap_ratio=0.05):
    """Continue nearby clothing texture across a tiny lower panel-side gap."""
    if result is None or layer is None or not face_box:
        return result, layer, {
            "lowerPanelContactExtendedPixels": 0,
            "lowerPanelContactMaxGapPx": 0,
        }

    result_arr = np.asarray(result.convert("RGB")).copy()
    layer_arr = np.asarray(layer.convert("RGBA")).copy()
    alpha = layer_arr[:, :, 3]
    h, w = alpha.shape[:2]
    fy = float(face_box.get("y") or h * 0.16)
    fh = max(1.0, float(face_box.get("height") or h * 0.28))
    center_x = float(face_box.get("x") or w * 0.30) + float(face_box.get("width") or w * 0.40) * 0.5
    lower_start = max(int(round(h * 0.72)), int(round(fy + fh * 1.20)))
    max_gap_px = max(1, int(round(w * float(max_gap_ratio))))
    min_body_span = max(1, int(round(w * 0.72)))
    extended_pixels = 0
    observed_max_gap = 0

    binary = alpha > 48
    for row in range(max(0, lower_start), h):
        span = _alpha_row_span(binary, row, center_x)
        if not span or span[1] - span[0] < min_body_span:
            continue
        left, right = span
        left_gap = left
        right_gap = w - right
        if 0 < left_gap <= max_gap_px and left_gap <= right - left:
            dst = np.arange(0, left, dtype=np.int32)
            src = np.clip(2 * left - 1 - dst, left, right - 1)
            result_arr[row, dst] = result_arr[row, src]
            layer_arr[row, dst] = layer_arr[row, src]
            extended_pixels += int(left_gap)
            observed_max_gap = max(observed_max_gap, int(left_gap))
        if 0 < right_gap <= max_gap_px and right_gap <= right - left:
            dst = np.arange(right, w, dtype=np.int32)
            src = np.clip(2 * right - 1 - dst, left, right - 1)
            result_arr[row, dst] = result_arr[row, src]
            layer_arr[row, dst] = layer_arr[row, src]
            extended_pixels += int(right_gap)
            observed_max_gap = max(observed_max_gap, int(right_gap))

    return Image.fromarray(result_arr, "RGB"), Image.fromarray(layer_arr, "RGBA"), {
        "lowerPanelContactExtendedPixels": int(extended_pixels),
        "lowerPanelContactMaxGapPx": int(observed_max_gap),
    }


def _alpha_row_span(binary, row, center_x):
    xs = np.flatnonzero(binary[row])
    if xs.size == 0:
        return None
    split_points = np.flatnonzero(np.diff(xs) > 1) + 1
    runs = np.split(xs, split_points)
    containing = [run for run in runs if run[0] <= center_x <= run[-1]]
    candidates = containing or runs
    run = min(
        candidates,
        key=lambda item: (0 if item[0] <= center_x <= item[-1] else min(abs(item[0] - center_x), abs(item[-1] - center_x)), -item.size),
    )
    return int(run[0]), int(run[-1]) + 1


def _solve_id_photo_layout(
    cutout,
    face_box,
    target_size,
    composition,
    composition_profile,
    measurement_calibration=None,
):
    solve_started = time.perf_counter()
    target_w, target_h = int(target_size[0]), int(target_size[1])
    image_w, image_h = cutout.size
    alpha = np.asarray(cutout.getchannel("A"))
    binary = alpha > 24
    ys, xs = np.where(binary)
    if xs.size == 0:
        raise ValueError("ID photo foreground is empty")

    fx = float(face_box["x"])
    fy = float(face_box["y"])
    fw = max(1.0, float(face_box["width"]))
    fh = max(1.0, float(face_box["height"]))
    face_cx = fx + fw / 2.0

    alpha_left = int(xs.min())
    alpha_top = int(ys.min())
    alpha_right = int(xs.max()) + 1
    alpha_bottom = int(ys.max()) + 1
    head_x1 = max(0, int(round(face_cx - fw * 1.05)))
    head_x2 = min(image_w, int(round(face_cx + fw * 1.05)))
    head_y2 = min(image_h, int(round(fy + fh * 0.30)))
    head_region = binary[:head_y2, head_x1:head_x2]
    head_rows = np.where(np.any(head_region, axis=1))[0]
    estimated_head_top = float(head_rows.min()) if head_rows.size else max(0.0, fy - fh * 0.45)
    estimated_head_top = max(estimated_head_top, fy - fh * 0.65)
    estimated_head_height = min(fh * 1.45, max(fh * 1.30, (fy + fh) - estimated_head_top))

    shoulder_y1 = max(0, int(round(fy + fh * 0.86)))
    shoulder_y2 = min(alpha_bottom, int(round(fy + fh * (1.62 if composition != "half_body" else 2.10))))
    shoulder_rows = []
    if shoulder_y2 > shoulder_y1:
        step = max(1, (shoulder_y2 - shoulder_y1) // 54)
        for row in range(shoulder_y1, shoulder_y2, step):
            span = _alpha_row_span(binary, row, face_cx)
            if span:
                shoulder_rows.append((row, span[0], span[1]))
    if shoulder_rows:
        shoulder_widths = np.asarray([right - left for _, left, right in shoulder_rows], dtype=np.float32)
        width_low, width_high = np.percentile(shoulder_widths, [10, 90])
        stable_shoulder_rows = [
            item for item in shoulder_rows if width_low <= item[2] - item[1] <= width_high
        ] or shoulder_rows
        shoulder_centers = np.asarray(
            [(left + right) / 2.0 for _, left, right in stable_shoulder_rows], dtype=np.float32
        )
        shoulder_center = float(np.median(shoulder_centers))
        shoulder_center_mad = float(np.median(np.abs(shoulder_centers - shoulder_center)))
        shoulder_left = float(np.percentile([item[1] for item in stable_shoulder_rows], 20))
        shoulder_right = float(np.percentile([item[2] for item in stable_shoulder_rows], 80))
        shoulder_box_top = float(min(item[0] for item in stable_shoulder_rows))
        shoulder_box_bottom = float(max(item[0] for item in stable_shoulder_rows) + 1)
    else:
        stable_shoulder_rows = []
        shoulder_center = face_cx
        shoulder_center_mad = fw
        shoulder_left = max(float(alpha_left), face_cx - fw * 1.35)
        shoulder_right = min(float(alpha_right), face_cx + fw * 1.35)
        shoulder_box_top = float(shoulder_y1)
        shoulder_box_bottom = float(max(shoulder_y1 + 1, shoulder_y2))

    observed_shoulder_width = max(0.0, shoulder_right - shoulder_left)
    observed_lower_body_depth = max(0.0, float(alpha_bottom) - (fy + fh))
    shoulder_observed = bool(
        len(stable_shoulder_rows) >= 6
        and observed_shoulder_width >= fw * 1.35
        and observed_lower_body_depth >= fh * 0.42
    )
    shoulder_observation_confidence = min(
        1.0,
        len(stable_shoulder_rows) / 18.0,
        observed_shoulder_width / max(1.0, fw * 1.8),
        observed_lower_body_depth / max(1.0, fh * 0.9),
    )

    # Matting sheets and lower-body fragments can span the whole source.  They
    # must not control ID-photo scale.  Clamp the observed shoulder envelope to
    # a face-relative human range, then use it (plus the detected head) as the
    # stable horizontal crop prior.
    shoulder_left = max(shoulder_left, face_cx - fw * 1.90)
    shoulder_right = min(shoulder_right, face_cx + fw * 1.90)
    if shoulder_right - shoulder_left < fw * 1.65:
        shoulder_left = face_cx - fw * 0.825
        shoulder_right = face_cx + fw * 0.825
    shoulder_width = max(fw * 1.65, shoulder_right - shoulder_left)

    head_rows = []
    head_span_y1 = max(0, int(round(estimated_head_top)))
    head_span_y2 = min(image_h, int(round(fy + fh * 0.98)))
    if head_span_y2 > head_span_y1:
        step = max(1, (head_span_y2 - head_span_y1) // 36)
        for row in range(head_span_y1, head_span_y2, step):
            span = _alpha_row_span(binary, row, face_cx)
            if span:
                head_rows.append((row, span[0], span[1]))
    if head_rows:
        head_widths = np.asarray([right - left for _, left, right in head_rows], dtype=np.float32)
        width_low, width_high = np.percentile(head_widths, [10, 90])
        stable_head_rows = [item for item in head_rows if width_low <= item[2] - item[1] <= width_high] or head_rows
        head_center = float(np.median([(left + right) / 2.0 for _, left, right in stable_head_rows]))
        head_left = float(np.percentile([item[1] for item in stable_head_rows], 8))
        head_right = float(np.percentile([item[2] for item in stable_head_rows], 92))
        head_box_top = float(min(item[0] for item in stable_head_rows))
        head_box_bottom = float(max(item[0] for item in stable_head_rows) + 1)
    else:
        stable_head_rows = []
        head_center = face_cx
        head_left = face_cx - fw * 0.88
        head_right = face_cx + fw * 0.88
        head_box_top = estimated_head_top
        head_box_bottom = fy + fh

    left_reach = max(1.0, face_cx - shoulder_left)
    right_reach = max(1.0, shoulder_right - face_cx)
    reach_ratio = max(left_reach, right_reach) / min(left_reach, right_reach)
    source_edge_tolerance = max(2, int(round(image_w * 0.01)))
    left_edge_touch_ratio = (
        sum(1 for _, left, _ in stable_shoulder_rows if left <= source_edge_tolerance)
        / float(max(1, len(stable_shoulder_rows)))
    )
    right_edge_touch_ratio = (
        sum(1 for _, _, right in stable_shoulder_rows if right >= image_w - 1 - source_edge_tolerance)
        / float(max(1, len(stable_shoulder_rows)))
    )
    # A shoulder that is already cut by the source boundary has no measurable
    # outer contour.  In that case face/head anchors remain enforceable, while
    # shoulder-margin symmetry is explicitly marked as not observable.
    shoulder_source_clipped = max(left_edge_touch_ratio, right_edge_touch_ratio) >= 0.25
    shoulder_symmetry_applicable = bool(
        len(stable_shoulder_rows) >= 12
        and shoulder_center_mad <= fw * 0.12
        and reach_ratio <= 1.75
        and not shoulder_source_clipped
    )
    if shoulder_symmetry_applicable:
        center_weights = {"face": 0.55, "head": 0.15, "shoulder": 0.30}
    else:
        center_weights = {"face": 0.68, "head": 0.22, "shoulder": 0.10}
    visual_center = (
        center_weights["face"] * face_cx
        + center_weights["head"] * head_center
        + center_weights["shoulder"] * shoulder_center
    )
    # Outer shoulders may be cropped symmetrically in a valid head-and-shoulder
    # photo. Keep the central 80% as the non-negotiable upper-shoulder core;
    # full shoulder bounds remain available for symmetry and diagnostics.
    shoulder_core_half = shoulder_width * (0.36 if shoulder_source_clipped else 0.40)
    important_shoulder_left = max(shoulder_left, shoulder_center - shoulder_core_half)
    important_shoulder_right = min(shoulder_right, shoulder_center + shoulder_core_half)

    horizontal_pad = max(fw * 0.10, shoulder_width * 0.035)
    content_left = min(head_left, shoulder_left, face_cx - fw * 0.92) - horizontal_pad
    content_right = max(head_right, shoulder_right, face_cx + fw * 0.92) + horizontal_pad
    crop_left = max(0, int(np.floor(content_left)))
    crop_top = max(0, min(alpha_top, int(round(estimated_head_top - fh * 0.05))))
    crop_right = min(image_w, int(np.ceil(content_right)))
    lower_limit = image_h if composition == "half_body" else int(round(fy + fh * 2.35))
    crop_bottom = min(image_h, max(int(round(fy + fh * 1.75)), min(alpha_bottom, lower_limit)))
    if crop_right <= crop_left or crop_bottom <= crop_top:
        crop_left, crop_top, crop_right, crop_bottom = 0, 0, image_w, image_h

    crop_alpha = binary[crop_top:crop_bottom, crop_left:crop_right]
    crop_ys, crop_xs = np.where(crop_alpha)
    if crop_xs.size == 0:
        raise ValueError("ID photo crop does not contain the subject")
    subject_left = float(crop_xs.min())
    subject_top = float(crop_ys.min())
    subject_right = float(crop_xs.max() + 1)
    subject_bottom = float(crop_ys.max() + 1)
    face_cx_crop = face_cx - crop_left
    head_top_crop = estimated_head_top - crop_top
    layout_left = max(0.0, min(head_left, shoulder_left) - crop_left)
    layout_right = min(float(crop_right - crop_left), max(head_right, shoulder_right) - crop_left)

    lower_body_rows = []
    lower_body_y1 = max(shoulder_y1, int(round(fy + fh * 1.08)))
    for row in range(lower_body_y1, crop_bottom):
        span = _alpha_row_span(binary, row, face_cx)
        if span and span[1] - span[0] >= fw * 1.25:
            lower_body_rows.append((row, span[0], span[1], span[1] - span[0]))
    if lower_body_rows:
        width_floor = float(np.percentile([item[3] for item in lower_body_rows], 70))
        widest_lower_rows = [item for item in lower_body_rows if item[3] >= width_floor]
        lower_body_left_crop = float(np.percentile([item[1] for item in widest_lower_rows], 8)) - crop_left
        lower_body_right_crop = float(np.percentile([item[2] for item in widest_lower_rows], 92)) - crop_left
    else:
        lower_body_left_crop = subject_left
        lower_body_right_crop = subject_right

    profile = dict(composition_profile or {})
    calibration = dict(measurement_calibration or {})
    head_height_calibration = min(
        1.35,
        max(0.75, float(calibration.get("headHeightFactor") or 1.0)),
    )
    head_width_calibration = min(
        1.35,
        max(0.75, float(calibration.get("headWidthFactor") or 1.0)),
    )
    head_width_min = profile.get("headWidthRatioMin")
    head_width_max = profile.get("headWidthRatioMax")
    head_width_min = float(head_width_min) if head_width_min is not None else None
    head_width_max = float(head_width_max) if head_width_max is not None else None
    head_min = float(profile.get("headHeightRatioMin") or 0.58)
    head_max = float(
        profile.get("headHeightRatioMax")
        or profile.get("operationalHeadHeightRatioMax")
        or 0.70
    )
    ratio_rounding_epsilon = 1e-6
    solve_head_min = max(
        0.0,
        head_min - 2.0 / float(max(1, target_h)) - ratio_rounding_epsilon,
    )
    solve_head_max = (
        head_max + 2.0 / float(max(1, target_h)) + ratio_rounding_epsilon
    )
    shoulder_min = float(profile.get("shoulderWidthRatioMin") or 0.75)
    shoulder_max = float(profile.get("shoulderWidthRatioMax") or 1.0)
    top_min = float(profile.get("topMarginRatioMin") or 0.066)
    top_max = float(profile.get("topMarginRatioMax") or 0.123)
    side_safety = max(0, int(np.ceil(target_w * float(profile.get("sideSafetyRatio") or 0.0))))
    bottom_safety = max(0, int(np.ceil(target_h * float(profile.get("bottomSafetyRatio") or 0.0))))
    target_top_ratio = float(profile.get("topMarginRatioTarget") or ((top_min + top_max) / 2.0))
    target_top_ratio = min(top_max, max(top_min, target_top_ratio))
    target_top = target_h * target_top_ratio
    target_head_ratio = float(profile.get("headHeightRatioTarget") or ((head_min + head_max) / 2.0))
    target_head_ratio = min(head_max, max(head_min, target_head_ratio))
    target_shoulder_ratio = float(
        profile.get("shoulderWidthRatioTarget")
        or min(shoulder_max - 0.02, max(shoulder_min + 0.02, (shoulder_min + shoulder_max) / 2.0))
    )
    target_shoulder_ratio = min(shoulder_max, max(shoulder_min, target_shoulder_ratio))

    calibrated_head_height = estimated_head_height * head_height_calibration
    head_scale = target_h * target_head_ratio / max(1.0, calibrated_head_height)
    shoulder_scale = target_w * target_shoulder_ratio / max(1.0, shoulder_width)
    desired_scale = head_scale * 0.74 + shoulder_scale * 0.26

    has_official_head_box = bool(
        profile.get("sourceType") == "official"
        and head_width_min is not None
        and head_width_max is not None
        and profile.get("headHeightRatioMin") is not None
        and profile.get("headHeightRatioMax") is not None
    )
    head_measurement_guard = (
        min(0.015, max(0.0, (head_max - head_min) * 0.15))
        if has_official_head_box
        else min(0.035, max(0.0, (head_max - head_min) * 0.30))
    )
    base_head_scale_min = target_h * solve_head_min / max(1.0, calibrated_head_height)
    head_scale_min = (
        target_h * min(head_max, head_min + head_measurement_guard)
        / max(1.0, calibrated_head_height)
    )
    head_scale_max = target_h * solve_head_max / max(1.0, calibrated_head_height)
    source_observed_head_width = (
        fw * 1.08
        if has_official_head_box
        else min(
            max(fw * 1.18, head_right - head_left),
            fw * 1.28,
        )
    )
    observed_head_width = source_observed_head_width * head_width_calibration
    solve_head_width_min = (
        max(
            0.0,
            head_width_min - 1.0 / float(max(1, target_w)) - ratio_rounding_epsilon,
        )
        if head_width_min is not None
        else None
    )
    solve_head_width_max = (
        head_width_max + 1.0 / float(max(1, target_w)) + ratio_rounding_epsilon
        if head_width_max is not None
        else None
    )
    width_scale_min = (
        target_w * solve_head_width_min / observed_head_width
        if solve_head_width_min is not None
        else 0.0
    )
    width_scale_max = (
        target_w * solve_head_width_max / observed_head_width
        if solve_head_width_max is not None
        else float("inf")
    )
    bottom_contact_required = bool(profile.get("foregroundBottomContact", composition == "head_shoulder"))
    shoulder_side_contact_required = bool(profile.get("shoulderSideContact", composition == "head_shoulder"))
    lower_body_width = max(1.0, lower_body_right_crop - lower_body_left_crop)
    side_contact_scale_min = (
        (target_w + 2.0) / lower_body_width
        if shoulder_side_contact_required
        else 0.0
    )
    subject_height = max(1.0, subject_bottom - subject_top)
    bottom_contact_scale_min = (
        (target_h * (1.0 - top_max) + 1.0) / subject_height
        if bottom_contact_required
        else 0.0
    )
    base_feasible_scale_min = max(
        base_head_scale_min,
        width_scale_min,
        side_contact_scale_min,
        bottom_contact_scale_min,
    )
    feasible_scale_min = max(
        head_scale_min,
        width_scale_min,
        side_contact_scale_min,
        bottom_contact_scale_min,
    )
    feasible_scale_max = min(head_scale_max, width_scale_max)
    geometry_constraints_compatible = feasible_scale_min <= feasible_scale_max
    if feasible_scale_min > feasible_scale_max:
        if base_feasible_scale_min <= feasible_scale_max:
            feasible_scale_min = base_feasible_scale_min
        else:
            feasible_scale_min = base_head_scale_min
            feasible_scale_max = head_scale_max
    chin_bottom_min = profile.get("chinBottomRatioMin")
    chin_bottom_max = profile.get("chinBottomRatioMax")
    chin_bottom_target = profile.get("chinBottomRatioTarget")
    if chin_bottom_target is not None:
        chin_bottom_target = float(chin_bottom_target)
        if chin_bottom_min is not None:
            chin_bottom_target = max(float(chin_bottom_min), chin_bottom_target)
        if chin_bottom_max is not None:
            chin_bottom_target = min(float(chin_bottom_max), chin_bottom_target)
    face_bottom_crop = (fy + fh) - crop_top
    face_bottom_from_head = max(1.0, (fy + fh) - estimated_head_top)
    chin_scale_min = 0.0
    if chin_bottom_max is not None:
        chin_scale_min = (
            target_h * (1.0 - float(chin_bottom_max)) - target_top
        ) / face_bottom_from_head
    # Official head size and chin placement take precedence over irrelevant
    # lower-body width.  Shoulders may naturally meet the lower side edges of
    # an ID-photo crop, while the head must never be shrunk to fit a half-body
    # source in full.
    initial_scale = min(max(desired_scale, feasible_scale_min, chin_scale_min), feasible_scale_max)
    initial_scale = max(0.02, initial_scale)

    crop_w = crop_right - crop_left
    crop_h = crop_bottom - crop_top
    head_left_crop = head_left - crop_left
    head_right_crop = head_right - crop_left
    head_box_top_crop = head_box_top - crop_top
    head_box_bottom_crop = head_box_bottom - crop_top
    shoulder_left_crop = shoulder_left - crop_left
    shoulder_right_crop = shoulder_right - crop_left
    important_shoulder_left_crop = important_shoulder_left - crop_left
    important_shoulder_right_crop = important_shoulder_right - crop_left
    shoulder_box_top_crop = shoulder_box_top - crop_top
    shoulder_box_bottom_crop = shoulder_box_bottom - crop_top
    head_center_crop = head_center - crop_left
    shoulder_center_crop = shoulder_center - crop_left
    visual_center_crop = visual_center - crop_left

    def candidate_score(candidate_scale, candidate_x, candidate_y):
        face_center_out = candidate_x + face_cx_crop * candidate_scale
        head_center_out = candidate_x + head_center_crop * candidate_scale
        shoulder_center_out = candidate_x + shoulder_center_crop * candidate_scale
        visual_center_out = candidate_x + visual_center_crop * candidate_scale
        important_left = candidate_x + min(head_left_crop, important_shoulder_left_crop) * candidate_scale
        important_right = candidate_x + max(head_right_crop, important_shoulder_right_crop) * candidate_scale
        important_top = candidate_y + min(head_box_top_crop, shoulder_box_top_crop) * candidate_scale
        important_bottom = candidate_y + max(head_box_bottom_crop, shoulder_box_bottom_crop) * candidate_scale
        overflow = (
            max(0.0, -important_left)
            + max(0.0, important_right - target_w)
            + max(0.0, -important_top)
        )
        left_margin = max(0.0, important_left)
        right_margin = max(0.0, target_w - important_right)
        margin_difference = abs(left_margin - right_margin)
        face_error = abs(face_center_out - target_w / 2.0)
        head_error = abs(head_center_out - target_w / 2.0)
        shoulder_error = abs(shoulder_center_out - target_w / 2.0)
        visual_error = abs(visual_center_out - target_w / 2.0)
        head_ratio = calibrated_head_height * candidate_scale / float(target_h)
        head_width_ratio = observed_head_width * candidate_scale / float(target_w)
        top_ratio = (candidate_y + head_top_crop * candidate_scale) / float(target_h)
        chin_ratio = (
            target_h - (candidate_y + face_bottom_crop * candidate_scale)
        ) / float(target_h)
        top_target_error = abs(top_ratio - target_top_ratio)
        chin_target_error = (
            abs(chin_ratio - chin_bottom_target)
            if chin_bottom_target is not None
            else 0.0
        )
        foreground_bottom = candidate_y + subject_bottom * candidate_scale
        bottom_contact_gap = max(0.0, target_h - foreground_bottom)
        lower_body_left = candidate_x + lower_body_left_crop * candidate_scale
        lower_body_right = candidate_x + lower_body_right_crop * candidate_scale
        left_shoulder_panel_gap = max(0.0, lower_body_left)
        right_shoulder_panel_gap = max(0.0, target_w - lower_body_right)
        score = (
            visual_error * visual_error * 8.0
            + face_error * face_error * 3.0
            + head_error * head_error
            + shoulder_error * shoulder_error * (1.5 if shoulder_symmetry_applicable else 0.35)
            + (margin_difference * margin_difference * 2.0 if shoulder_symmetry_applicable else 0.0)
            + abs(candidate_scale - initial_scale) / max(initial_scale, 1e-6) * 15.0
            + top_target_error * top_target_error * 18000.0
            + chin_target_error * chin_target_error * 22000.0
        )
        score += max(0.0, face_error - target_w * 0.015) ** 2 * 1500.0
        score += max(0.0, visual_error - target_w * 0.010) ** 2 * 2200.0
        if shoulder_symmetry_applicable:
            score += max(0.0, margin_difference - target_w * 0.025) ** 2 * 1800.0
        score += max(0.0, solve_head_min - head_ratio) ** 2 * 300000.0
        score += max(0.0, head_ratio - solve_head_max) ** 2 * 300000.0
        if solve_head_width_min is not None:
            score += max(0.0, solve_head_width_min - head_width_ratio) ** 2 * 300000.0
        if solve_head_width_max is not None:
            score += max(0.0, head_width_ratio - solve_head_width_max) ** 2 * 300000.0
        score += max(0.0, top_min - top_ratio) ** 2 * 240000.0
        score += max(0.0, top_ratio - top_max) ** 2 * 240000.0
        if chin_bottom_min is not None:
            score += max(0.0, float(chin_bottom_min) - chin_ratio) ** 2 * 180000.0
        if chin_bottom_max is not None:
            score += max(0.0, chin_ratio - float(chin_bottom_max)) ** 2 * 180000.0
        if bottom_contact_required:
            score += bottom_contact_gap * bottom_contact_gap * 600.0
        if shoulder_side_contact_required:
            score += (
                left_shoulder_panel_gap * left_shoulder_panel_gap
                + right_shoulder_panel_gap * right_shoulder_panel_gap
            ) * 800.0
        score += overflow * overflow * 1000000.0
        return score

    def search(scales, x_radius, y_radius, x_steps, y_steps, seed=None):
        best = seed
        for candidate_scale in scales:
            base_x = target_w / 2.0 - visual_center_crop * candidate_scale
            base_y = target_top - head_top_crop * candidate_scale
            if chin_bottom_target is not None:
                chin_target_y = (
                    target_h * (1.0 - chin_bottom_target)
                    - face_bottom_crop * candidate_scale
                )
                base_y = base_y * 0.55 + chin_target_y * 0.45
            if chin_bottom_max is not None:
                base_y = max(
                    base_y,
                    target_h * (1.0 - float(chin_bottom_max)) - face_bottom_crop * candidate_scale,
                )
            if chin_bottom_min is not None:
                base_y = min(
                    base_y,
                    target_h * (1.0 - float(chin_bottom_min)) - face_bottom_crop * candidate_scale,
                )
            for x_offset in np.linspace(-x_radius, x_radius, x_steps):
                for y_offset in np.linspace(-y_radius, y_radius, y_steps):
                    candidate_x = base_x + float(x_offset)
                    candidate_y = base_y + float(y_offset)
                    score = candidate_score(candidate_scale, candidate_x, candidate_y)
                    item = (score, candidate_scale, candidate_x, candidate_y)
                    if best is None or item[0] < best[0]:
                        best = item
        return best

    coarse_scales = sorted(set(
        max(feasible_scale_min, min(feasible_scale_max, initial_scale * (1.0 + delta)))
        for delta in np.linspace(-0.08, 0.08, 9)
    ))
    best = search(coarse_scales, target_w * 0.08, target_h * 0.06, 13, 9)
    fine_scales = sorted(set(
        max(feasible_scale_min, min(feasible_scale_max, best[1] * (1.0 + delta)))
        for delta in np.linspace(-0.015, 0.015, 7)
    ))
    best = search(fine_scales, target_w * 0.02, target_h * 0.015, 11, 7, best)
    _, scale, preferred_x, preferred_y = best
    
    # --- STRICT PROFILE OVERRIDE FOR ONE-INCH ---
    strict_head_ratio = profile.get('headHeightRatioTarget')
    strict_top_gap = profile.get('topGapRatioTarget')
    if strict_head_ratio is not None:
        strict_head_height = target_h * float(strict_head_ratio)
        scale = strict_head_height / max(1.0, float(calibrated_head_height))
        preferred_x = target_w / 2.0 - head_center_crop * scale
    if strict_top_gap is not None:
        target_top_gap = target_h * float(strict_top_gap)
        preferred_y = target_top_gap - head_box_top_crop * scale
    # --------------------------------------------
    if shoulder_side_contact_required:
        cover_x_min = target_w + 0.5 - lower_body_right_crop * scale
        cover_x_max = -0.5 - lower_body_left_crop * scale
        if cover_x_min <= cover_x_max:
            preferred_x = min(cover_x_max, max(cover_x_min, preferred_x))
    if bottom_contact_required:
        contact_y_min = target_h + 0.5 - subject_bottom * scale
        preferred_y = max(contact_y_min, preferred_y)
    px = int(round(preferred_x))
    py = int(round(preferred_y))
    new_w = max(1, int(round(crop_w * scale)))
    new_h = max(1, int(round(crop_h * scale)))
    person = cutout.crop((crop_left, crop_top, crop_right, crop_bottom)).resize((new_w, new_h), Image.LANCZOS)
    layer = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    layer.paste(person, (px, py), person)

    expected_foreground = {
        "left": px + subject_left * scale,
        "top": py + subject_top * scale,
        "right": px + subject_right * scale,
        "bottom": py + subject_bottom * scale,
    }
    important_foreground = {
        # The cranial envelope must stay fully inside the panel.  The lower
        # shoulder/chest silhouette is intentionally allowed to meet and be
        # clipped by the panel sides, which is required for a zero-gap
        # head-and-shoulder composition.
        "left": px + head_left_crop * scale,
        "top": py + head_box_top_crop * scale,
        "right": px + head_right_crop * scale,
        "bottom": py + max(head_box_bottom_crop, shoulder_box_bottom_crop) * scale,
    }
    foreground_overflow = {
        "left": max(0.0, -expected_foreground["left"]),
        "right": max(0.0, expected_foreground["right"] - target_w),
        "top": max(0.0, -expected_foreground["top"]),
        "bottom": max(0.0, expected_foreground["bottom"] - target_h),
    }
    important_overflow = {
        "left": max(0.0, -important_foreground["left"]),
        "right": max(0.0, important_foreground["right"] - target_w),
        "top": max(0.0, -important_foreground["top"]),
        "bottom": max(0.0, important_foreground["bottom"] - target_h),
    }

    return {
        "person": person,
        "layer": layer,
        "crop": (crop_left, crop_top, crop_right, crop_bottom),
        "scale": scale,
        "translate": (px, py),
        "estimatedHeadTop": estimated_head_top,
        "estimatedHeadHeight": calibrated_head_height,
        "sourceEstimatedHeadHeight": estimated_head_height,
        "observedHeadWidth": observed_head_width,
        "sourceObservedHeadWidth": source_observed_head_width,
        "measurementCalibration": {
            "headHeightFactor": round(head_height_calibration, 6),
            "headWidthFactor": round(head_width_calibration, 6),
        },
        "geometryConstraintsCompatible": bool(geometry_constraints_compatible),
        "shoulderWidth": shoulder_width,
        "shoulderObserved": shoulder_observed,
        "shoulderObservationConfidence": round(shoulder_observation_confidence, 6),
        "faceCenter": face_cx,
        "headCenter": head_center,
        "shoulderCenter": shoulder_center,
        "visualCenter": visual_center,
        "centerWeights": center_weights,
        "headBounds": (head_left, head_box_top, head_right, head_box_bottom),
        "shoulderBounds": (shoulder_left, shoulder_box_top, shoulder_right, shoulder_box_bottom),
        "shoulderSymmetryApplicable": shoulder_symmetry_applicable,
        "shoulderSourceClipped": shoulder_source_clipped,
        "shoulderSourceEdgeTouchRatio": round(max(left_edge_touch_ratio, right_edge_touch_ratio), 6),
        "shoulderCenterMad": shoulder_center_mad,
        "expectedForeground": expected_foreground,
        "importantForeground": important_foreground,
        "foregroundOverflow": foreground_overflow,
        "importantForegroundOverflow": important_overflow,
        "layoutSolveMs": round((time.perf_counter() - solve_started) * 1000.0, 3),
        "sideSafetyPx": side_safety,
        "bottomSafetyPx": bottom_safety,
        "foregroundBottomContactRequired": bottom_contact_required,
        "shoulderSideContactRequired": shoulder_side_contact_required,
        "lowerBodyBoundsCrop": (lower_body_left_crop, lower_body_right_crop),
        "cropRetryCount": 1,
        "targetRange": {
            "headHeightRatioMin": head_min,
            "headHeightRatioMax": head_max,
            "headMeasurementGuard": round(head_measurement_guard, 6),
            "headWidthRatioMin": head_width_min,
            "headWidthRatioMax": head_width_max,
            "topMarginRatioMin": top_min,
            "topMarginRatioMax": top_max,
            "shoulderWidthRatioMin": shoulder_min,
            "shoulderWidthRatioMax": shoulder_max,
            "sideSafetyRatioMin": round(side_safety / float(target_w), 6),
            "bottomSafetyRatioMin": round(bottom_safety / float(target_h), 6),
            "chinBottomRatioMin": float(chin_bottom_min) if chin_bottom_min is not None else None,
            "chinBottomRatioMax": float(chin_bottom_max) if chin_bottom_max is not None else None,
        },
    }


def compose_id_photo(
    foreground_path,
    face_box,
    target_size,
    bg_color,
    composition="head_shoulder",
    source_background_rgb=None,
    preserve_detail=False,
    composition_profile=None,
    measurement_calibration=None,
    foreground_only=False,
):
    target_w, target_h = int(target_size[0]), int(target_size[1])
    composition_profile = dict(composition_profile or {})
    cutout = Image.open(foreground_path).convert("RGBA")
    bg_rgb = _hex_to_rgb(bg_color)
    bg = Image.new("RGBA", (target_w, target_h), bg_rgb + (255,))

    fx = float(face_box["x"])
    fy = float(face_box["y"])
    fw = float(face_box["width"])
    fh = float(face_box["height"])
    face_cx = fx + fw / 2.0

    solution = _solve_id_photo_layout(
        cutout,
        face_box,
        (target_w, target_h),
        composition,
        composition_profile,
        measurement_calibration=measurement_calibration,
    )
    crop_left, crop_top, crop_right, crop_bottom = solution["crop"]
    crop_w = crop_right - crop_left
    crop_h = crop_bottom - crop_top
    head_height_min = float(composition_profile.get("headHeightRatioMin") or 0.58)
    head_height_max = float(
        composition_profile.get("headHeightRatioMax")
        or composition_profile.get("operationalHeadHeightRatioMax")
        or 0.70
    )
    head_width_min = composition_profile.get("headWidthRatioMin")
    head_width_max = composition_profile.get("headWidthRatioMax")
    head_width_min = float(head_width_min) if head_width_min is not None else None
    head_width_max = float(head_width_max) if head_width_max is not None else None
    shoulder_min = float(composition_profile.get("shoulderWidthRatioMin") or 0.75)
    shoulder_max = float(composition_profile.get("shoulderWidthRatioMax") or 1.0)
    top_min = float(composition_profile.get("topMarginRatioMin") or 0.066)
    top_max = float(composition_profile.get("topMarginRatioMax") or 0.123)
    target_head_height = (head_height_min + head_height_max) / 2.0
    scale = solution["scale"]
    person = solution["person"]
    layer = solution["layer"]
    px, py = solution["translate"]
    new_w, new_h = person.size
    crop_retry_count = int(solution["cropRetryCount"])
    measured_before = {}
    target_range = {
        **solution["targetRange"],
        "headWidthRatioMin": head_width_min,
        "headWidthRatioMax": head_width_max,
    }
    bbox = layer.getbbox()
    measured_before = {
        "headHeightRatio": round((solution["estimatedHeadHeight"] * scale) / float(target_h), 6),
        "headWidthRatio": round((solution["observedHeadWidth"] * scale) / float(target_w), 6),
        "shoulderWidthRatio": round((solution["shoulderWidth"] * scale) / float(target_w), 6),
        "bottomPaddingRatio": round((target_h - (bbox[3] if bbox else target_h)) / float(target_h), 6),
    }

    bbox = layer.getbbox()
    if bbox:
        desired_top = target_h * ((top_min + top_max) / 2.0)
        min_top = target_h * top_min
        max_top = target_h * top_max
        bottom_contact_required = bool(solution["foregroundBottomContactRequired"])
        desired_bottom = 0.0 if bottom_contact_required else float(solution["bottomSafetyPx"])
        min_bottom = 0.0 if bottom_contact_required else float(solution["bottomSafetyPx"])
        max_bottom = 1.0 if bottom_contact_required else target_h * 0.25
        dx = 0
        dy = 0
        face_left_out = px + (fx - crop_left) * scale
        current_face_center = face_left_out + fw * scale / 2.0
        current_visual_center = px + (solution["visualCenter"] - crop_left) * scale
        dx = int(round(target_w / 2.0 - current_visual_center))
        max_face_error = target_w * 0.015
        min_face_dx = target_w / 2.0 - max_face_error - current_face_center
        max_face_dx = target_w / 2.0 + max_face_error - current_face_center
        dx = int(round(min(max(float(dx), min_face_dx), max_face_dx)))
        important_box = solution["importantForeground"]
        min_important_dx = -float(important_box["left"])
        max_important_dx = target_w - float(important_box["right"])
        if min_important_dx <= max_important_dx:
            min_important_dx_int = int(np.ceil(min_important_dx - 1e-9))
            max_important_dx_int = int(np.floor(max_important_dx + 1e-9))
            if min_important_dx_int <= max_important_dx_int:
                dx = min(max(dx, min_important_dx_int), max_important_dx_int)
        if solution["shoulderSideContactRequired"]:
            lower_left_crop, lower_right_crop = solution["lowerBodyBoundsCrop"]
            lower_left_out = px + lower_left_crop * scale
            lower_right_out = px + lower_right_crop * scale
            min_side_dx = int(np.ceil(target_w - lower_right_out - 1e-9))
            max_side_dx = int(np.floor(-lower_left_out + 1e-9))
            if min_side_dx <= max_side_dx:
                dx = min(max(dx, min_side_dx), max_side_dx)
        side_safety_px = int(solution["sideSafetyPx"])
        expected_box = solution["expectedForeground"]
        expected_width = float(expected_box["right"]) - float(expected_box["left"])
        if (
            not solution["shoulderSourceClipped"]
            and expected_width < target_w - side_safety_px * 2
        ):
            if float(expected_box["left"]) + dx < side_safety_px:
                dx += int(round(side_safety_px - (float(expected_box["left"]) + dx)))
            if float(expected_box["right"]) + dx > target_w - side_safety_px:
                dx -= int(round((float(expected_box["right"]) + dx) - (target_w - side_safety_px)))
        if bbox[1] < min_top:
            dy += int(round(desired_top - bbox[1]))
        elif bbox[1] > max_top:
            dy -= int(round(bbox[1] - desired_top))
        current_bottom = target_h - bbox[3]
        if current_bottom > max_bottom and (bbox[1] + dy) < max_top:
            dy += int(round(min(current_bottom - desired_bottom, max_top - (bbox[1] + dy))))
        elif current_bottom < min_bottom and (bbox[1] + dy) > min_top:
            dy -= int(round(min(desired_bottom - current_bottom, (bbox[1] + dy) - min_top)))
        if dx or dy:
            shifted = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            shifted.paste(person, (px + dx, py + dy), person)
            layer = shifted
            px += dx
            py += dy

    pre_clean_face_box = {
        "x": px + (fx - crop_left) * scale,
        "y": py + (fy - crop_top) * scale,
        "width": fw * scale,
        "height": fh * scale,
    }
    if preserve_detail:
        edge_cleanup = {
            "trustedAlphaCompositionPath": True,
            "edgeHaloPixelsCleaned": 0,
            "decontaminatedPixels": 0,
            "trimmedLowAlphaHaloPixels": 0,
        }
        dark_panel_cleanup = {"darkBackPanelRemovedPixels": 0, "darkBackPanelMaxComponent": 0}
    else:
        layer, edge_cleanup = _clean_edge_halo(layer, bg_rgb, pre_clean_face_box, source_background_rgb)
        layer, dark_panel_cleanup = _remove_dark_back_panel(layer, pre_clean_face_box)
    clean_bbox = layer.getbbox()
    if clean_bbox and clean_bbox[1] < int(round(target_h * top_min)):
        dy = int(round(target_h * ((top_min + top_max) / 2.0) - clean_bbox[1]))
        if dy > 0:
            shifted = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            shifted.paste(layer, (0, dy), layer)
            layer = shifted
            py += dy
    face_top_out = py + (fy - crop_top) * scale
    face_h_out = fh * scale
    face_left_out = px + (fx - crop_left) * scale
    
    if foreground_only:
        result = layer.copy()
    else:
        result = Image.alpha_composite(bg, layer).convert("RGB")
    cleanup_face_box = {
        "x": face_left_out,
        "y": face_top_out,
        "width": fw * scale,
        "height": face_h_out,
    }
    if preserve_detail:
        composed_residue_cleanup = {"composedSideResiduePixels": 0, "composedSideResidueMaxComponent": 0}
        body_hole_repair = {"composedBodyHoleRepairedPixels": 0, "composedBodyHoleMaxComponent": 0}
        hair_hole_repair = {"composedHairHoleRepairedPixels": 0, "composedHairHoleMaxComponent": 0}
        hair_side_block_cleanup = {"composedHairSideBlockRemovedPixels": 0, "composedHairSideBlockMaxComponent": 0}
        late_hair_hole_repair = {"composedHairHoleRepairedPixels": 0, "composedHairHoleMaxComponent": 0}
    else:
        result, composed_residue_cleanup = _remove_composed_side_residue(
            result, bg_rgb, cleanup_face_box, source_background_rgb or edge_cleanup.get("estimatedSourceBackgroundRgb")
        )
        result, layer, body_hole_repair = _repair_composed_body_holes(result, layer, bg_rgb, cleanup_face_box)
        result, layer, hair_hole_repair = _repair_composed_hair_holes(result, layer, bg_rgb, cleanup_face_box)
        result, layer, hair_side_block_cleanup = _remove_composed_hair_side_blocks(result, layer, bg_rgb, cleanup_face_box)
        result, layer, late_hair_hole_repair = _repair_composed_hair_holes(result, layer, bg_rgb, cleanup_face_box)
    hair_hole_repair = {
        "composedHairHoleRepairedPixels": int(hair_hole_repair.get("composedHairHoleRepairedPixels") or 0)
        + int(late_hair_hole_repair.get("composedHairHoleRepairedPixels") or 0),
        "composedHairHoleMaxComponent": max(
            int(hair_hole_repair.get("composedHairHoleMaxComponent") or 0),
            int(late_hair_hole_repair.get("composedHairHoleMaxComponent") or 0),
        ),
        "composedLateHairHoleRepairedPixels": int(late_hair_hole_repair.get("composedHairHoleRepairedPixels") or 0),
    }
    if preserve_detail:
        dark_line_cleanup = {"composedDarkLineRemovedPixels": 0, "composedDarkLineMaxComponent": 0, "composedSideBoundaryLineRemovedPixels": 0}
        lower_shoulder_gap_repair = {"lowerShoulderGapRepairedPixels": 0, "lowerShoulderGapMaxComponent": 0}
        late_dark_line_cleanup = dark_line_cleanup.copy()
        late_side_residue_cleanup = composed_residue_cleanup.copy()
    else:
        result, dark_line_cleanup = _remove_composed_dark_line_artifacts(result, bg_rgb, cleanup_face_box)
        result, layer, lower_shoulder_gap_repair = _repair_lower_shoulder_gaps(result, layer, bg_rgb, cleanup_face_box)
        result, late_dark_line_cleanup = _remove_composed_dark_line_artifacts(result, bg_rgb, cleanup_face_box)
        result, late_side_residue_cleanup = _remove_composed_side_residue(
            result, bg_rgb, cleanup_face_box, source_background_rgb or edge_cleanup.get("estimatedSourceBackgroundRgb")
        )
    composed_residue_cleanup = {
        "composedSideResiduePixels": int(composed_residue_cleanup.get("composedSideResiduePixels") or 0)
        + int(late_side_residue_cleanup.get("composedSideResiduePixels") or 0),
        "composedSideResidueMaxComponent": max(
            int(composed_residue_cleanup.get("composedSideResidueMaxComponent") or 0),
            int(late_side_residue_cleanup.get("composedSideResidueMaxComponent") or 0),
        ),
        "composedLateSideResiduePixels": int(late_side_residue_cleanup.get("composedSideResiduePixels") or 0),
    }
    dark_line_cleanup = {
        "composedDarkLineRemovedPixels": int(dark_line_cleanup.get("composedDarkLineRemovedPixels") or 0)
        + int(late_dark_line_cleanup.get("composedDarkLineRemovedPixels") or 0),
        "composedDarkLineMaxComponent": max(
            int(dark_line_cleanup.get("composedDarkLineMaxComponent") or 0),
            int(late_dark_line_cleanup.get("composedDarkLineMaxComponent") or 0),
        ),
        "composedSideBoundaryLineRemovedPixels": int(dark_line_cleanup.get("composedSideBoundaryLineRemovedPixels") or 0)
        + int(late_dark_line_cleanup.get("composedSideBoundaryLineRemovedPixels") or 0),
        "composedLateDarkLineRemovedPixels": int(late_dark_line_cleanup.get("composedDarkLineRemovedPixels") or 0),
    }
    if solution["shoulderSideContactRequired"]:
        result, layer, lower_panel_contact = _extend_small_lower_panel_gaps(
            result,
            layer,
            cleanup_face_box,
        )
    else:
        lower_panel_contact = {
            "lowerPanelContactExtendedPixels": 0,
            "lowerPanelContactMaxGapPx": 0,
        }

    # Save the composed mask after all output repairs so quality checking uses
    # the exact alpha shape represented by the downloadable image.
    import tempfile
    composed_mask_path = ""
    try:
        mask_tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        layer.getchannel("A").save(mask_tmp.name)
        composed_mask_path = mask_tmp.name
    except Exception:
        pass

    bbox = layer.getbbox()
    fg_w = (bbox[2] - bbox[0]) if bbox else 0
    fg_h = (bbox[3] - bbox[1]) if bbox else 0
    head_h_ratio = (solution["estimatedHeadHeight"] * scale) / float(target_h)
    head_w_ratio = (fw * scale * 1.45) / float(target_w)
    profile_head_w_ratio = (solution["observedHeadWidth"] * scale) / float(target_w)
    chin_bottom_ratio = max(0.0, (target_h - (face_top_out + face_h_out)) / float(target_h))
    face_center_out = face_left_out + fw * scale / 2.0
    head_center_out = px + (solution["headCenter"] - crop_left) * scale
    shoulder_center_out = px + (solution["shoulderCenter"] - crop_left) * scale
    visual_center_out = px + (solution["visualCenter"] - crop_left) * scale
    shoulder_left, shoulder_top, shoulder_right, shoulder_bottom = solution["shoulderBounds"]
    shoulder_left_out = px + (shoulder_left - crop_left) * scale
    shoulder_right_out = px + (shoulder_right - crop_left) * scale
    shoulder_top_out = py + (shoulder_top - crop_top) * scale
    shoulder_bottom_out = py + (shoulder_bottom - crop_top) * scale
    head_left, head_top, head_right, head_bottom = solution["headBounds"]
    head_left_out = px + (head_left - crop_left) * scale
    head_right_out = px + (head_right - crop_left) * scale
    head_top_out = py + (head_top - crop_top) * scale
    head_bottom_out = py + (head_bottom - crop_top) * scale
    left_shoulder_margin = max(0.0, min(float(target_w), shoulder_left_out))
    right_shoulder_margin = max(0.0, min(float(target_w), target_w - shoulder_right_out))
    shoulder_margin_difference = abs(left_shoulder_margin - right_shoulder_margin)
    foreground_bottom_gap_px = max(0, target_h - (bbox[3] if bbox else 0))
    foreground_bottom_contact = foreground_bottom_gap_px == 0
    translate_dx = px - int(solution["translate"][0])
    translate_dy = py - int(solution["translate"][1])

    def shifted_box(source_box):
        return {
            "left": float(source_box["left"]) + translate_dx,
            "top": float(source_box["top"]) + translate_dy,
            "right": float(source_box["right"]) + translate_dx,
            "bottom": float(source_box["bottom"]) + translate_dy,
        }

    expected_foreground = shifted_box(solution["expectedForeground"])
    important_foreground = shifted_box(solution["importantForeground"])
    foreground_overflow = {
        "left": max(0.0, -expected_foreground["left"]),
        "right": max(0.0, expected_foreground["right"] - target_w),
        "top": max(0.0, -expected_foreground["top"]),
        "bottom": max(0.0, expected_foreground["bottom"] - target_h),
    }
    important_overflow = {
        "left": max(0.0, -important_foreground["left"]),
        "right": max(0.0, important_foreground["right"] - target_w),
        "top": max(0.0, -important_foreground["top"]),
        "bottom": max(0.0, important_foreground["bottom"] - target_h),
    }
    # The lower torso is expected to continue below a head-and-shoulder panel.
    # Only left/right/top loss means important person content left the canvas.
    important_overflow_pixels = sum(
        important_overflow[key] for key in ("left", "right", "top")
    )
    expected_shoulder_width_ratio = max(0.0, shoulder_right_out - shoulder_left_out) / float(target_w)
    visible_shoulder_left = max(0.0, shoulder_left_out)
    visible_shoulder_right = min(float(target_w), shoulder_right_out)
    shoulder_width_ratio = max(0.0, visible_shoulder_right - visible_shoulder_left) / float(target_w)
    measured_after = {
        "headHeightRatio": round(head_h_ratio, 6),
        "headWidthRatio": round(profile_head_w_ratio, 6),
        "topMarginRatio": round((bbox[1] if bbox else 0) / float(target_h), 6),
        "chinBottomRatio": round(chin_bottom_ratio, 6),
        "shoulderWidthRatio": round(shoulder_width_ratio, 6),
        "expectedShoulderWidthRatio": round(expected_shoulder_width_ratio, 6),
        "faceCenterOffset": round(abs(face_center_out - target_w / 2.0) / float(target_w), 6),
        "visualCenterErrorRatio": round(abs(visual_center_out - target_w / 2.0) / float(target_w), 6),
        "shoulderMarginDifferenceRatio": round(shoulder_margin_difference / float(target_w), 6),
        "subjectWithinCanvas": important_overflow_pixels < 0.5,
        "sideSafetyRatio": round(min((bbox[0] if bbox else 0), target_w - (bbox[2] if bbox else target_w)) / float(target_w), 6),
        "bottomSafetyRatio": round((target_h - (bbox[3] if bbox else target_h)) / float(target_h), 6),
        "foregroundBottomGapPx": int(foreground_bottom_gap_px),
        "foregroundBottomContact": bool(foreground_bottom_contact),
    }
    quality = {
        "composedMaskPath": composed_mask_path,
        "outputFaceBox": {
            "x": round(face_left_out, 3),
            "y": round(face_top_out, 3),
            "width": round(fw * scale, 3),
            "height": round(face_h_out, 3),
        },
        "outputForegroundBox": {
            "x": bbox[0] if bbox else 0,
            "y": bbox[1] if bbox else 0,
            "width": fg_w,
            "height": fg_h,
        },
        "faceHeightRatio": round(face_h_out / float(target_h), 6),
        "headRatio": round(head_h_ratio, 6),
        "headHeightRatio": round(head_h_ratio, 6),
        "headWidthRatio": round(head_w_ratio, 6),
        "profileHeadWidthRatio": round(profile_head_w_ratio, 6),
        "chinBottomRatio": round(chin_bottom_ratio, 6),
        "topPaddingRatio": round((bbox[1] if bbox else 0) / float(target_h), 6),
        "bottomPaddingRatio": round((target_h - (bbox[3] if bbox else target_h)) / float(target_h), 6),
        "bottomSafetyRatio": round((target_h - (bbox[3] if bbox else target_h)) / float(target_h), 6),
        "foregroundBottomGapPx": int(foreground_bottom_gap_px),
        "foregroundBottomContact": bool(foreground_bottom_contact),
        "foregroundBottomContactRequired": bool(solution["foregroundBottomContactRequired"]),
        "sideSafetyRatio": round(min((bbox[0] if bbox else 0), target_w - (bbox[2] if bbox else target_w)) / float(target_w), 6),
        "subjectWithinCanvas": important_overflow_pixels < 0.5,
        "foregroundWidthRatio": round(fg_w / float(target_w), 6),
        "foregroundHeightRatio": round(fg_h / float(target_h), 6),
        "shoulderWidthRatio": round(shoulder_width_ratio, 6),
        "expectedShoulderWidthRatio": round(expected_shoulder_width_ratio, 6),
        "faceCenterOffset": round(abs(face_center_out - target_w / 2.0) / float(target_w), 6),
        "faceCenterErrorPx": round(abs(face_center_out - target_w / 2.0), 3),
        "headCenterErrorPx": round(abs(head_center_out - target_w / 2.0), 3),
        "shoulderCenterErrorPx": round(abs(shoulder_center_out - target_w / 2.0), 3),
        "visualCenterErrorPx": round(abs(visual_center_out - target_w / 2.0), 3),
        "visualCenterErrorRatio": round(abs(visual_center_out - target_w / 2.0) / float(target_w), 6),
        "leftShoulderMarginPx": round(left_shoulder_margin, 3),
        "rightShoulderMarginPx": round(right_shoulder_margin, 3),
        "shoulderMarginDifferencePx": round(shoulder_margin_difference, 3),
        "shoulderMarginDifferenceRatio": round(shoulder_margin_difference / float(target_w), 6),
        "shoulderSymmetryApplicable": bool(solution["shoulderSymmetryApplicable"]),
        "shoulderObserved": bool(solution["shoulderObserved"]),
        "shoulderObservationConfidence": float(solution["shoulderObservationConfidence"]),
        "shoulderSourceClipped": bool(solution["shoulderSourceClipped"]),
        "shoulderSourceEdgeTouchRatio": float(solution["shoulderSourceEdgeTouchRatio"]),
        "expectedForegroundBBox": {key: round(value, 3) for key, value in expected_foreground.items()},
        "importantForegroundBBox": {key: round(value, 3) for key, value in important_foreground.items()},
        "headBBox": {
            "left": round(head_left_out, 3),
            "top": round(head_top_out, 3),
            "right": round(head_right_out, 3),
            "bottom": round(head_bottom_out, 3),
        },
        "shoulderBBox": {
            "left": round(shoulder_left_out, 3),
            "top": round(shoulder_top_out, 3),
            "right": round(shoulder_right_out, 3),
            "bottom": round(shoulder_bottom_out, 3),
        },
        "foregroundOverflowLeft": round(foreground_overflow["left"], 3),
        "foregroundOverflowRight": round(foreground_overflow["right"], 3),
        "foregroundOverflowTop": round(foreground_overflow["top"], 3),
        "foregroundOverflowBottom": round(foreground_overflow["bottom"], 3),
        "importantForegroundOverflowLeft": round(important_overflow["left"], 3),
        "importantForegroundOverflowRight": round(important_overflow["right"], 3),
        "importantForegroundOverflowTop": round(important_overflow["top"], 3),
        "importantForegroundOverflowBottom": round(important_overflow["bottom"], 3),
        "importantForegroundOverflowPixels": round(important_overflow_pixels, 3),
        "compositionProfile": composition_profile,
        "measuredBefore": measured_before,
        "targetRange": target_range,
        "measuredAfter": measured_after,
        "cropRetryCount": crop_retry_count,
        "compositionSolver": {
            "version": "person-panel-constraint-v7-final-calibrated",
            "estimatedHeadTop": round(solution["estimatedHeadTop"], 3),
            "estimatedHeadHeight": round(solution["estimatedHeadHeight"], 3),
            "sourceEstimatedHeadHeight": round(solution["sourceEstimatedHeadHeight"], 3),
            "observedHeadWidth": round(solution["observedHeadWidth"], 3),
            "sourceObservedHeadWidth": round(solution["sourceObservedHeadWidth"], 3),
            "measurementCalibration": solution["measurementCalibration"],
            "geometryConstraintsCompatible": bool(solution["geometryConstraintsCompatible"]),
            "estimatedShoulderWidth": round(solution["shoulderWidth"], 3),
            "faceCenterX": round(face_center_out, 3),
            "headCenterX": round(head_center_out, 3),
            "shoulderCenterX": round(shoulder_center_out, 3),
            "visualCenterX": round(visual_center_out, 3),
            "centerWeights": solution["centerWeights"],
            "shoulderSymmetryApplicable": bool(solution["shoulderSymmetryApplicable"]),
            "shoulderObserved": bool(solution["shoulderObserved"]),
            "shoulderObservationConfidence": float(solution["shoulderObservationConfidence"]),
            "shoulderSourceClipped": bool(solution["shoulderSourceClipped"]),
            "shoulderSourceEdgeTouchRatio": float(solution["shoulderSourceEdgeTouchRatio"]),
            "shoulderCenterMad": round(solution["shoulderCenterMad"], 3),
            "sideSafetyPx": int(solution["sideSafetyPx"]),
            "bottomSafetyPx": int(solution["bottomSafetyPx"]),
            "foregroundBottomContactRequired": bool(solution["foregroundBottomContactRequired"]),
            "shoulderSideContactRequired": bool(solution["shoulderSideContactRequired"]),
            "deterministicRetries": crop_retry_count,
            "layoutSolveMs": float(solution["layoutSolveMs"]),
        },
        "cropBox": {
            "x": crop_left,
            "y": crop_top,
            "width": crop_right - crop_left,
            "height": crop_bottom - crop_top,
        },
        "edgeCleanup": {
            **edge_cleanup,
            **dark_panel_cleanup,
            **composed_residue_cleanup,
            **body_hole_repair,
            **hair_hole_repair,
            **hair_side_block_cleanup,
            **dark_line_cleanup,
            **lower_shoulder_gap_repair,
            **lower_panel_contact,
        },
        "cropParams": {
            "cropX": crop_left,
            "cropY": crop_top,
            "cropW": crop_right - crop_left,
            "cropH": crop_bottom - crop_top,
            "scale": round(scale, 6),
            "translateX": int(px),
            "translateY": int(py),
            "faceCenterX": round(face_left_out + fw * scale / 2.0, 3),
            "headCenterX": round(head_center_out, 3),
            "shoulderCenterX": round(shoulder_center_out, 3),
            "visualCenterX": round(visual_center_out, 3),
            "faceCenterY": round(face_top_out + face_h_out / 2.0, 3),
            "topPaddingRatio": round((bbox[1] if bbox else 0) / float(target_h), 6),
            "headHeightRatio": round(head_h_ratio, 6),
            "shoulderWidthRatio": round(fg_w / float(target_w), 6),
            "expectedShoulderWidthRatio": round(expected_shoulder_width_ratio, 6),
            "bottomSafetyRatio": round((target_h - (bbox[3] if bbox else target_h)) / float(target_h), 6),
            "sideSafetyRatio": round(min((bbox[0] if bbox else 0), target_w - (bbox[2] if bbox else target_w)) / float(target_w), 6),
            "cropRetryCount": crop_retry_count,
        },
    }
    return result, quality



