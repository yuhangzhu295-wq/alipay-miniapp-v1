"""Face-driven ID-photo composition."""
from PIL import Image, ImageDraw, ImageFilter
import cv2
import numpy as np


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
    halo = white_halo | gray_halo | low_alpha_haze | hair_light_rim | hair_background_leak | neutral_bg_sheet | side_bg_sheet

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
        strength *= halo.astype(np.float32)

        rebuilt = rgb * (1.0 - strength[:, :, None]) + reconstructed * strength[:, :, None]
        neighbor_mix = halo & near_valid & ((brightness > near_brightness + 18.0) | white_halo | hair_light_rim)
        if int(np.count_nonzero(neighbor_mix)):
            nm = np.zeros_like(alpha, dtype=np.float32)
            nm[neighbor_mix] = 0.42
            nm[hair_light_rim] = np.maximum(nm[hair_light_rim], 0.58)
            rebuilt = rebuilt * (1.0 - nm[:, :, None]) + near_fg * nm[:, :, None]
        dark_mix = hair_light_rim & dark_valid
        if int(np.count_nonzero(dark_mix)):
            dm = np.zeros_like(alpha, dtype=np.float32)
            dm[dark_mix] = 0.88
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
        (old_bg_dist <= 92.0)
        & (chroma <= 132.0)
        & (brightness >= 42.0)
        & (brightness <= 248.0)
        & ~face_skin_core
    )
    skin_protect = skin_like & (face_skin_core | strong_skin_like | ~source_bg_match)
    neutral_old_bg = (
        pocket
        & (bg_dist > 34.0)
        & ~skin_protect
        & ~face_skin_core
        & ~hair_like
        & ~clothing_like
        & (brightness >= 58.0)
        & (brightness <= 246.0)
        & (chroma <= 112.0)
        & (source_bg_match | (chroma <= 74.0))
    )

    residue_u8 = cv2.morphologyEx(neutral_old_bg.astype("uint8"), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8), iterations=1)
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
        if upper_neck_sheet and (touches_side_gap or area >= 18) and mean_chroma <= 108.0 and mean_brightness >= 58.0:
            remove |= comp

    removed = int(np.count_nonzero(remove))
    if removed:
        arr[remove] = bg
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB"), {
        "composedSideResiduePixels": removed,
        "composedSideResidueMaxComponent": max_component,
    }

def compose_id_photo(foreground_path, face_box, target_size, bg_color, composition="head_shoulder", source_background_rgb=None):
    target_w, target_h = int(target_size[0]), int(target_size[1])
    cutout = Image.open(foreground_path).convert("RGBA")
    bg_rgb = _hex_to_rgb(bg_color)
    bg = Image.new("RGBA", (target_w, target_h), bg_rgb + (255,))

    fx = float(face_box["x"])
    fy = float(face_box["y"])
    fw = float(face_box["width"])
    fh = float(face_box["height"])
    face_cx = fx + fw / 2.0

    side_expand = 0.95 if composition != "half_body" else 1.7
    crop_left = max(0, int(face_cx - fw * side_expand))
    crop_top = max(0, int(fy - fh * 0.9))
    crop_right = min(cutout.width, int(face_cx + fw * side_expand))
    crop_bottom = min(cutout.height, int(fy + fh * (2.30 if composition != "half_body" else 4.2)))
    if crop_right <= crop_left or crop_bottom <= crop_top:
        crop_left, crop_top, crop_right, crop_bottom = 0, 0, cutout.width, cutout.height

    cropped_person = cutout.crop((crop_left, crop_top, crop_right, crop_bottom))
    crop_w, crop_h = cropped_person.size
    if composition != "half_body" and crop_w > 24:
        alpha = cropped_person.getchannel("A")
        draw = ImageDraw.Draw(alpha)
        trim = max(1, int(crop_w * 0.006))
        trim_bottom = max(1, int(crop_h * 0.012))
        draw.rectangle([0, 0, trim, crop_h], fill=0)
        draw.rectangle([crop_w - trim, 0, crop_w, crop_h], fill=0)
        draw.rectangle([0, crop_h - trim_bottom, crop_w, crop_h], fill=0)
        cropped_person.putalpha(alpha.filter(ImageFilter.GaussianBlur(radius=0.35)))
    face_height_ratio = 0.39 if composition != "half_body" else 0.26
    target_face_h = target_h * face_height_ratio
    scale_by_face = target_face_h / max(1.0, fh)
    scale_by_width = target_w * (1.46 if composition != "half_body" else 1.12) / max(1.0, crop_w)
    scale_by_height = target_h * (1.24 if composition != "half_body" else 1.08) / max(1.0, crop_h)
    scale = min(scale_by_face, scale_by_width, scale_by_height)

    def render_with_scale(render_scale):
        new_w = max(1, int(crop_w * render_scale))
        new_h = max(1, int(crop_h * render_scale))
        person = cropped_person.resize((new_w, new_h), Image.LANCZOS)
        face_cx_in_crop = (face_cx - crop_left) * render_scale
        estimated_head_top = (fy - fh * 0.55 - crop_top) * render_scale
        top_padding = target_h * 0.082
        px = int(target_w / 2.0 - face_cx_in_crop)
        py = int(top_padding - estimated_head_top)
        px = max(target_w - new_w, min(0, px))
        py = max(int(target_h * 0.02) - new_h, min(int(target_h * 0.12), py))
        layer = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        layer.paste(person, (px, py), person)
        return person, layer, px, py, new_w, new_h

    # Auto-repair the most common composition failures before output.  The
    # approved reference layout lets shoulders/hair approach the side edges;
    # only head size, top padding, and truly undersized subjects are corrected
    # here so the final 295x413 file does not look pasted into a smaller frame.
    for _ in range(5):
        person, layer, px, py, new_w, new_h = render_with_scale(scale)
        bbox = layer.getbbox()
        if not bbox:
            break
        fg_w_ratio = (bbox[2] - bbox[0]) / float(target_w)
        bottom_padding = (target_h - bbox[3]) / float(target_h)
        face_h_ratio = (fh * scale) / float(target_h)
        head_h_ratio = (face_h_ratio * 1.75)
        if head_h_ratio > 0.70 and scale > 0.05:
            scale *= max(0.90, 0.68 / max(0.01, head_h_ratio))
            continue
        if head_h_ratio < 0.58 and fg_w_ratio < 0.96 and bottom_padding > 0.10:
            scale *= min(1.12, 0.61 / max(0.01, head_h_ratio))
            continue
        if fg_w_ratio < 0.75 and face_h_ratio < 0.38:
            scale *= min(1.12, 0.78 / max(0.01, fg_w_ratio))
            continue
        break

    bbox = layer.getbbox()
    if bbox:
        desired_top = target_h * 0.085
        min_top = target_h * 0.07
        max_top = target_h * 0.115
        desired_bottom = target_h * 0.15
        min_bottom = target_h * 0.12
        max_bottom = target_h * 0.18
        dx = 0
        dy = 0
        face_left_out = px + (fx - crop_left) * scale
        current_face_center = face_left_out + fw * scale / 2.0
        dx += int(round(target_w / 2.0 - current_face_center))
        if bbox[0] + dx < 0:
            dx -= bbox[0] + dx
        if bbox[2] + dx > target_w:
            dx -= (bbox[2] + dx) - target_w
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
    layer, edge_cleanup = _clean_edge_halo(layer, bg_rgb, pre_clean_face_box, source_background_rgb)
    clean_bbox = layer.getbbox()
    if clean_bbox and clean_bbox[1] < int(round(target_h * 0.071)):
        dy = int(round(target_h * 0.084 - clean_bbox[1]))
        if dy > 0:
            shifted = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            shifted.paste(layer, (0, dy), layer)
            layer = shifted
            py += dy
    face_top_out = py + (fy - crop_top) * scale
    face_h_out = fh * scale
    face_left_out = px + (fx - crop_left) * scale
    result = Image.alpha_composite(bg, layer).convert("RGB")
    result, composed_residue_cleanup = _remove_composed_side_residue(
        result,
        bg_rgb,
        {
            "x": face_left_out,
            "y": face_top_out,
            "width": fw * scale,
            "height": face_h_out,
        },
        source_background_rgb or edge_cleanup.get("estimatedSourceBackgroundRgb"),
    )
    bbox = layer.getbbox()
    fg_w = (bbox[2] - bbox[0]) if bbox else 0
    fg_h = (bbox[3] - bbox[1]) if bbox else 0
    head_h_ratio = (face_h_out * 1.75) / float(target_h)
    head_w_ratio = (fw * scale * 1.45) / float(target_w)
    quality = {
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
        "topPaddingRatio": round((bbox[1] if bbox else 0) / float(target_h), 6),
        "bottomPaddingRatio": round((target_h - (bbox[3] if bbox else target_h)) / float(target_h), 6),
        "foregroundWidthRatio": round(fg_w / float(target_w), 6),
        "foregroundHeightRatio": round(fg_h / float(target_h), 6),
        "shoulderWidthRatio": round(fg_w / float(target_w), 6),
        "faceCenterOffset": round(abs((face_left_out + fw * scale / 2.0) - target_w / 2.0) / float(target_w), 6),
        "cropBox": {
            "x": crop_left,
            "y": crop_top,
            "width": crop_right - crop_left,
            "height": crop_bottom - crop_top,
        },
        "edgeCleanup": {**edge_cleanup, **composed_residue_cleanup},
        "cropParams": {
            "cropX": crop_left,
            "cropY": crop_top,
            "cropW": crop_right - crop_left,
            "cropH": crop_bottom - crop_top,
            "scale": round(scale, 6),
            "faceCenterX": round(face_left_out + fw * scale / 2.0, 3),
            "faceCenterY": round(face_top_out + face_h_out / 2.0, 3),
            "topPaddingRatio": round((bbox[1] if bbox else 0) / float(target_h), 6),
            "headHeightRatio": round(head_h_ratio, 6),
            "shoulderWidthRatio": round(fg_w / float(target_w), 6),
        },
    }
    return result, quality



