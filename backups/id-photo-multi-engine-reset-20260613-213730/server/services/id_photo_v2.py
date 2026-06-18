"""统一证件照 / 职业形象照 v2 生成服务。"""
import tempfile
import time
import uuid
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from services.id_photo_specs import BG_COLORS, get_spec
from services.outfit_templates import ADVANCED_OUTFIT_ENABLED, get_template, list_templates, normalize_outfit
from services.portrait_quality import (
    PortraitQualityError,
    classify_image_type,
    compose_headshot,
    is_illustration_like,
    segment_human_rgba,
    validate_portrait_input,
    validate_segmentation_mask,
)
from services.face_detector import detect_face
from services.id_photo_composer import compose_id_photo
from services.id_photo_quality import build_quality_report, validate_composition_metrics, validate_final_output
from services.portrait_matting import matte_person, matting_status


CREATIVE_TYPES = {"anime", "cartoon", "illustration"}
PREPARE_CACHE = {}
PREPARE_CACHE_TTL_SECONDS = 24 * 3600
COMPOSITION_VERSION = "id-head-shoulder-v3"
OUTFIT_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "outfits"
OUTFIT_ASSET_CACHE = {}


class TemplateError(ValueError):
    def __init__(self, code, message, template_id="", status_code=400):
        super().__init__(message)
        self.code = code
        self.template_id = template_id
        self.status_code = status_code


def cleanup_prepare_cache(now=None):
    now = time.time() if now is None else float(now)
    removed = 0
    deleted_files = 0
    for prepared_id, item in list(PREPARE_CACHE.items()):
        created_at = float(item.get("createdAt") or 0)
        if created_at and created_at + PREPARE_CACHE_TTL_SECONDS > now:
            continue
        PREPARE_CACHE.pop(prepared_id, None)
        removed += 1
        for key in ("foregroundPngPath", "alphaMaskPath"):
            path = item.get(key)
            try:
                if path and Path(path).exists():
                    Path(path).unlink()
                    deleted_files += 1
            except Exception:
                pass
    return {
        "removedPreparedItems": removed,
        "deletedPreparedFiles": deleted_files,
        "retentionSeconds": PREPARE_CACHE_TTL_SECONDS,
    }


def get_capabilities():
    return {"templates": list_templates()}


def _hex_to_rgb(value, fallback="#1a73e8"):
    value = (value or fallback).strip()
    if value in BG_COLORS:
        value = BG_COLORS[value]
    if not value.startswith("#") or len(value) != 7:
        value = fallback
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def _background(size, bg_color, outfit="preserve_original"):
    rgb = _hex_to_rgb(bg_color)
    if normalize_outfit(outfit) in {"business_blue", "anime_business"}:
        bg2 = (max(0, rgb[0] - 12), max(0, rgb[1] - 36), max(0, rgb[2] - 56))
        canvas = Image.new("RGBA", size, rgb + (255,))
        draw = ImageDraw.Draw(canvas)
        for y in range(size[1]):
            ratio = y / max(1, size[1])
            r = int(rgb[0] * (1 - ratio) + bg2[0] * ratio)
            g = int(rgb[1] * (1 - ratio) + bg2[1] * ratio)
            b = int(rgb[2] * (1 - ratio) + bg2[2] * ratio)
            draw.line([(0, y), (size[0], y)], fill=(r, g, b))
        return canvas
    return Image.new("RGBA", size, rgb + (255,))


def _blur_score(img_bytes):
    image = ImageOps.exif_transpose(Image.open(BytesIO(img_bytes))).convert("L")
    gray = np.asarray(image)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _reject_if_too_blurry(img_bytes, detected=None):
    score = _blur_score(img_bytes)
    if score < 18:
        raise PortraitQualityError(
            "IMAGE_TOO_BLURRY",
            {
                **(detected or {}),
                "code": "IMAGE_TOO_BLURRY",
                "message": "图片清晰度较低，建议更换更清晰的正面照片。",
                "blurScore": round(score, 2),
            },
        )
    return score


def _shade(color, factor):
    rgb = tuple(max(0, min(255, int(channel * factor))) for channel in color[:3])
    return rgb + ((color[3] if len(color) > 3 else 255),)


def _load_raster_outfit(outfit_id):
    cache_key = outfit_id
    if cache_key in OUTFIT_ASSET_CACHE:
        return OUTFIT_ASSET_CACHE[cache_key].copy()
    asset_name = "shirt-white.png" if outfit_id == "white_shirt" else "suit-black.png"
    asset_path = OUTFIT_ASSET_DIR / asset_name
    if not asset_path.exists():
        return None
    asset = Image.open(asset_path).convert("RGBA")
    bbox = asset.getchannel("A").getbbox()
    if bbox:
        asset = asset.crop(bbox)
    if outfit_id != "white_shirt":
        arr = np.asarray(asset).copy()
        rgb = arr[:, :, :3].astype(np.float32)
        alpha = arr[:, :, 3] > 12
        brightness = rgb.mean(axis=2)
        saturation = rgb.max(axis=2) - rgb.min(axis=2)
        fabric = alpha & ~((brightness > 145) & (saturation < 72))
        targets = {
            "mist_gray_suit": np.array([155, 163, 175], dtype=np.float32),
            "elegant_black_suit": np.array([35, 38, 45], dtype=np.float32),
            "deep_blue_suit": np.array([32, 56, 94], dtype=np.float32),
            "red_tie_suit": np.array([31, 33, 39], dtype=np.float32),
            "pure_black_suit": np.array([18, 19, 23], dtype=np.float32),
        }
        target = targets.get(outfit_id, targets["elegant_black_suit"])
        texture = np.clip(0.58 + brightness / 255.0 * 0.72, 0.58, 1.22)
        recolored = target[None, None, :] * texture[:, :, None]
        local_contrast = (rgb - brightness[:, :, None]) * 0.14
        recolored = np.clip(recolored + local_contrast, 0, 255)
        arr[:, :, :3][fabric] = recolored[fabric].astype(np.uint8)
        if outfit_id == "red_tie_suit":
            height, width = alpha.shape
            yy, xx = np.ogrid[:height, :width]
            tie = (
                fabric
                & (xx > width * 0.43)
                & (xx < width * 0.57)
                & (yy > height * 0.15)
                & (yy < height * 0.83)
            )
            tie_texture = np.clip(0.55 + brightness / 255.0 * 0.75, 0.55, 1.18)
            tie_rgb = np.array([178, 25, 38], dtype=np.float32)[None, None, :] * tie_texture[:, :, None]
            arr[:, :, :3][tie] = np.clip(tie_rgb, 0, 255).astype(np.uint8)[tie]
        asset = Image.fromarray(arr, "RGBA")
    OUTFIT_ASSET_CACHE[cache_key] = asset.copy()
    return asset


def _render_raster_outfit(size, outfit_id, cx, y0, shoulder_w, face_w):
    asset = _load_raster_outfit(outfit_id)
    if asset is None:
        return None
    w, h = size
    target_width = int(min(w * 1.28, max(w * 1.10, shoulder_w * 1.02)))
    scale = target_width / float(max(1, asset.width))
    target_height = max(1, int(asset.height * scale))
    asset = asset.resize((target_width, target_height), Image.Resampling.LANCZOS)
    paste_x = int(round(cx - target_width / 2.0))
    paste_y = int(round(y0 - face_w * 0.24))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer.alpha_composite(asset, (paste_x, paste_y))
    return layer


def _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, shirt_color, outline=(220, 225, 232, 255)):
    shirt_left = cx - shoulder_w * 0.25
    shirt_right = cx + shoulder_w * 0.25
    neck_left = cx - face_w * 0.28
    neck_right = cx + face_w * 0.28
    v_y = y0 + face_w * 0.30
    draw.polygon(
        [
            (neck_left, y0 + face_w * 0.08),
            (cx, v_y),
            (neck_right, y0 + face_w * 0.08),
            (shirt_right, y1),
            (shirt_left, y1),
        ],
        fill=shirt_color,
    )
    collar_h = max(face_w * 0.22, 22)
    collar = (250, 251, 253, 255)
    draw.polygon(
        [
            (cx - face_w * 0.42, y0 + face_w * 0.08),
            (cx - face_w * 0.08, y0 + collar_h),
            (cx - face_w * 0.01, v_y),
            (neck_left, y0 + face_w * 0.02),
        ],
        fill=collar,
        outline=outline,
    )
    draw.polygon(
        [
            (cx + face_w * 0.42, y0 + face_w * 0.08),
            (cx + face_w * 0.08, y0 + collar_h),
            (cx + face_w * 0.01, v_y),
            (neck_right, y0 + face_w * 0.02),
        ],
        fill=collar,
        outline=outline,
    )


def _draw_tie(draw, cx, y0, y1, face_w, color=(25, 32, 44, 255)):
    knot_w = face_w * 0.11
    knot_h = face_w * 0.10
    draw.polygon([(cx, y0 + 2), (cx - knot_w, y0 + knot_h), (cx, y0 + knot_h * 1.8), (cx + knot_w, y0 + knot_h)], fill=color)
    draw.polygon([(cx - knot_w * 0.66, y0 + knot_h * 1.55), (cx + knot_w * 0.66, y0 + knot_h * 1.55), (cx + knot_w * 0.36, y1), (cx - knot_w * 0.36, y1)], fill=color)


def _draw_bow(draw, cx, y0, face_w, color=(44, 76, 140, 255), accent=(130, 165, 220, 255)):
    w = face_w * 0.46
    h = face_w * 0.22
    draw.polygon([(cx - w, y0), (cx - w * 0.08, y0 + h * 0.34), (cx - w, y0 + h), (cx - w * 0.56, y0 + h * 0.50)], fill=color)
    draw.polygon([(cx + w, y0), (cx + w * 0.08, y0 + h * 0.34), (cx + w, y0 + h), (cx + w * 0.56, y0 + h * 0.50)], fill=color)
    draw.rounded_rectangle([cx - w * 0.11, y0 + h * 0.22, cx + w * 0.11, y0 + h * 0.78], radius=max(2, int(h * 0.12)), fill=accent)


def _draw_jacket(draw, cx, y0, shoulder_y, y1, shoulder_w, face_w, jacket, lapel=(236, 239, 244, 255), tie=None):
    left = cx - shoulder_w * 0.54
    right = cx + shoulder_w * 0.54
    neck_left = cx - face_w * 0.34
    neck_right = cx + face_w * 0.34
    center_v = y0 + face_w * 0.52
    silhouette = [
        (left, y1),
        (left, shoulder_y + face_w * 0.16),
        (left + shoulder_w * 0.08, shoulder_y - face_w * 0.04),
        (neck_left, y0 + face_w * 0.05),
        (cx, center_v),
        (neck_right, y0 + face_w * 0.05),
        (right - shoulder_w * 0.08, shoulder_y - face_w * 0.04),
        (right, shoulder_y + face_w * 0.16),
        (right, y1),
    ]
    draw.polygon(silhouette, fill=jacket)

    shade = _shade(jacket, 0.86)
    highlight = _shade(jacket, 1.10)
    draw.polygon(
        [(left, y1), (left, shoulder_y + face_w * 0.16), (cx - shoulder_w * 0.30, shoulder_y), (cx - shoulder_w * 0.22, y1)],
        fill=shade,
    )
    draw.polygon(
        [(right, y1), (right, shoulder_y + face_w * 0.16), (cx + shoulder_w * 0.30, shoulder_y), (cx + shoulder_w * 0.22, y1)],
        fill=highlight,
    )

    left_lapel = [
        (neck_left, y0 + face_w * 0.04),
        (cx - face_w * 0.05, center_v),
        (cx - face_w * 0.18, y1),
        (cx - face_w * 0.50, y0 + face_w * 0.30),
    ]
    right_lapel = [
        (neck_right, y0 + face_w * 0.04),
        (cx + face_w * 0.05, center_v),
        (cx + face_w * 0.18, y1),
        (cx + face_w * 0.50, y0 + face_w * 0.30),
    ]
    draw.polygon(left_lapel, fill=lapel)
    draw.polygon(right_lapel, fill=_shade(lapel, 0.96))
    seam = _shade(jacket, 0.72)
    seam_width = max(1, int(face_w * 0.012))
    draw.line(left_lapel[:3], fill=seam, width=seam_width)
    draw.line(right_lapel[:3], fill=seam, width=seam_width)
    if tie:
        _draw_tie(draw, cx, y0 + face_w * 0.28, min(y1, y0 + face_w * 0.98), face_w, tie)


def _apply_outfit_template(result, quality, outfit, composition="head_shoulder", image_type="real_person"):
    outfit_id = normalize_outfit(outfit)
    template = get_template(outfit_id)
    if not template:
        raise TemplateError("TEMPLATE_NOT_AVAILABLE", "当前模板暂未接入，请选择其他模板。", outfit_id)
    label = template["name"]
    if outfit_id == "preserve_original":
        quality.update({"outfitApplied": False, "outfit": outfit_id, "outfitName": label})
        return result, {"id": outfit_id, "name": label, "applied": False}
    if not ADVANCED_OUTFIT_ENABLED:
        raise TemplateError(
            "OUTFIT_TEMPLATE_DISABLED",
            "高级换装暂未开放，请使用保留原服装模式。",
            outfit_id,
        )

    base = result.convert("RGBA")
    w, h = base.size
    face = quality.get("outputFaceBox") or {}
    fg = quality.get("outputForegroundBox") or quality.get("foregroundBoundingBox") or {}
    if face.get("height"):
        fx = float(face.get("x", w * 0.38))
        fy = float(face.get("y", h * 0.16))
        fw = float(face.get("width", w * 0.24))
        fh = float(face.get("height", h * 0.28))
        cx = fx + fw / 2.0
        y0 = fy + fh * (1.04 if composition != "half_body" else 1.08)
    else:
        fx = float(fg.get("x", w * 0.18))
        fy = float(fg.get("y", h * 0.07))
        fw = float(fg.get("width", w * 0.64))
        fh = max(1.0, float(fg.get("height", h * 0.70)))
        cx = fx + fw / 2.0
        y0 = fy + fh * (0.78 if image_type in CREATIVE_TYPES else 0.48)
    face_w = max(48.0, fw)
    y0 = min(max(y0, h * 0.30), h * 0.72)
    shoulder_y = min(h * 0.86, y0 + face_w * (0.58 if composition != "half_body" else 0.78))
    y1 = h + 18
    shoulder_w = min(w * 1.22, max(w * 0.72, face_w * (3.4 if composition != "half_body" else 3.85)))

    raster_layer = _render_raster_outfit((w, h), outfit_id, cx, y0, shoulder_w, face_w)
    if raster_layer is not None:
        composed = Image.alpha_composite(base, raster_layer).convert("RGB")
        original_foreground = quality.get("outputForegroundBox") or {}
        original_top = max(0, int(float(original_foreground.get("y") or y0)))
        quality.update({
            "outfitApplied": True,
            "outfit": outfit_id,
            "outfitName": label,
            "outfitRenderer": "photorealistic_raster_template",
            "outputForegroundBox": {
                "x": 0,
                "y": original_top,
                "width": w,
                "height": h - original_top,
            },
            "foregroundWidthRatio": 1.0,
            "foregroundHeightRatio": round((h - original_top) / float(max(1, h)), 6),
            "shoulderWidthRatio": min(1.0, round(shoulder_w / float(max(1, w)), 6)),
            "outfitAnchor": {
                "neckY": round(y0, 2),
                "shoulderY": round(shoulder_y, 2),
                "shoulderWidth": round(shoulder_w, 2),
            },
        })
        return composed, {
            "id": outfit_id,
            "name": label,
            "applied": True,
            "renderer": "photorealistic_raster_template",
        }

    anchor_y0 = y0
    anchor_shoulder_y = shoulder_y
    anchor_shoulder_w = shoulder_w
    render_scale = 3
    cx *= render_scale
    y0 *= render_scale
    shoulder_y *= render_scale
    y1 *= render_scale
    shoulder_w *= render_scale
    face_w *= render_scale
    layer = Image.new("RGBA", (w * render_scale, h * render_scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    shadow = (0, 0, 0, 35)
    draw.ellipse([cx - shoulder_w * 0.52, shoulder_y - 8, cx + shoulder_w * 0.52, shoulder_y + face_w * 0.55], fill=shadow)

    if outfit_id == "white_shirt":
        shoulder_top = y0 + face_w * 0.28
        draw.polygon(
            [
                (cx - face_w * 0.42, y0 + face_w * 0.06),
                (cx + face_w * 0.42, y0 + face_w * 0.06),
                (cx + shoulder_w * 0.54, shoulder_top + face_w * 0.26),
                (cx + shoulder_w * 0.45, y1),
                (cx - shoulder_w * 0.45, y1),
                (cx - shoulder_w * 0.54, shoulder_top + face_w * 0.26),
            ],
            fill=(250, 250, 247, 255),
        )
        _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, (255, 255, 255, 255))
        seam = (224, 229, 236, 255)
        draw.line([(cx, y0 + face_w * 0.34), (cx, y1)], fill=seam, width=max(1, int(face_w * 0.012)))
        for idx in range(3):
            by = y0 + face_w * (0.58 + idx * 0.24)
            draw.ellipse([cx - 3, by - 3, cx + 3, by + 3], fill=(218, 224, 232, 255))
    elif outfit_id == "business_blue":
        _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, (255, 255, 255, 255))
        _draw_jacket(draw, cx, y0, shoulder_y, y1, shoulder_w, face_w, (34, 62, 96, 255), (236, 241, 248, 255), (34, 54, 94, 255))
    elif outfit_id == "mist_gray_suit":
        _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, (255, 255, 255, 255))
        _draw_jacket(draw, cx, y0, shoulder_y, y1, shoulder_w, face_w, (186, 193, 203, 255), (250, 251, 253, 255), (30, 35, 46, 255))
    elif outfit_id == "elegant_black_suit":
        _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, (255, 255, 255, 255))
        _draw_jacket(draw, cx, y0, shoulder_y, y1, shoulder_w, face_w, (26, 28, 35, 255), (247, 248, 251, 255), (28, 32, 44, 255))
    elif outfit_id == "deep_blue_suit":
        _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, (255, 255, 255, 255))
        _draw_jacket(draw, cx, y0, shoulder_y, y1, shoulder_w, face_w, (26, 44, 78, 255), (244, 248, 255, 255), (24, 51, 110, 255))
    elif outfit_id == "red_tie_suit":
        _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, (255, 255, 255, 255))
        _draw_jacket(draw, cx, y0, shoulder_y, y1, shoulder_w, face_w, (24, 25, 30, 255), (248, 249, 252, 255), (180, 26, 38, 255))
    elif outfit_id == "pure_black_suit":
        _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, (255, 255, 255, 255))
        _draw_jacket(draw, cx, y0, shoulder_y, y1, shoulder_w, face_w, (17, 18, 23, 255), (247, 248, 251, 255), (10, 12, 18, 255))
    elif outfit_id == "mens_black_suit":
        _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, (255, 255, 255, 255))
        _draw_jacket(draw, cx, y0, shoulder_y, y1, shoulder_w, face_w, (24, 25, 29, 255), (246, 247, 250, 255), (20, 24, 34, 255))
    elif outfit_id == "womens_black_suit":
        _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, (255, 255, 255, 255))
        _draw_jacket(draw, cx, y0, shoulder_y, y1, shoulder_w, face_w, (32, 33, 39, 255), (248, 249, 252, 255), None)
    elif outfit_id == "student_uniform":
        _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, (248, 250, 255, 255))
        _draw_jacket(draw, cx, y0, shoulder_y, y1, shoulder_w, face_w, (28, 43, 78, 255), (245, 247, 252, 255), None)
        _draw_bow(draw, cx, y0 + face_w * 0.34, face_w, (34, 63, 128, 255), (150, 185, 232, 255))
    elif outfit_id == "anime_business":
        _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, (255, 255, 255, 255), (190, 205, 230, 255))
        _draw_jacket(draw, cx, y0, shoulder_y, y1, shoulder_w, face_w, (49, 78, 132, 255), (242, 247, 255, 255), (44, 71, 132, 255))
    elif outfit_id == "anime_school_uniform":
        _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, (250, 252, 255, 255), (185, 202, 235, 255))
        _draw_jacket(draw, cx, y0, shoulder_y, y1, shoulder_w, face_w, (39, 55, 105, 255), (242, 246, 255, 255), None)
        _draw_bow(draw, cx, y0 + face_w * 0.30, face_w, (52, 91, 166, 255), (232, 148, 168, 255))
    elif outfit_id == "anime_suit":
        _draw_shirt(draw, cx, y0, y1, shoulder_w, face_w, (255, 255, 255, 255), (190, 205, 230, 255))
        _draw_jacket(draw, cx, y0, shoulder_y, y1, shoulder_w, face_w, (28, 31, 42, 255), (248, 249, 252, 255), (32, 38, 58, 255))
    else:
        raise TemplateError("TEMPLATE_NOT_AVAILABLE", "当前模板暂未接入，请选择其他模板。", outfit_id)

    layer = layer.resize((w, h), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(radius=0.18))
    composed = Image.alpha_composite(base, layer).convert("RGB")
    original_foreground = quality.get("outputForegroundBox") or {}
    original_top = max(0, int(float(original_foreground.get("y") or y0)))
    quality.update({
        "outfitApplied": True,
        "outfit": outfit_id,
        "outfitName": label,
        "outputForegroundBox": {
            "x": 0,
            "y": original_top,
            "width": w,
            "height": h - original_top,
        },
        "foregroundWidthRatio": 1.0,
        "foregroundHeightRatio": round((h - original_top) / float(max(1, h)), 6),
        "shoulderWidthRatio": min(1.0, round(anchor_shoulder_w / float(max(1, w)), 6)),
        "outfitAnchor": {
            "neckY": round(anchor_y0, 2),
            "shoulderY": round(anchor_shoulder_y, 2),
            "shoulderWidth": round(anchor_shoulder_w, 2),
        },
    })
    return composed, {"id": outfit_id, "name": label, "applied": True}


def _alpha_bbox(alpha):
    arr = np.asarray(alpha)
    ys, xs = np.where(arr > 8)
    if xs.size == 0 or ys.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _resize_input_for_prepare(img_bytes, max_side=960):
    """Normalize large phone photos before detection/segmentation.

    ID-photo output is small, so running GrabCut on 4K phone images only burns
    time and often causes the frontend timeout. A 960px working image preserves
    enough head/shoulder detail for 295x413 and 413x579 outputs.
    """
    try:
        img = Image.open(BytesIO(img_bytes))
        img = ImageOps.exif_transpose(img).convert("RGB")
        original_size = img.size
        longest = max(original_size)
        resized = False
        if longest > max_side:
            scale = max_side / float(longest)
            new_size = (
                max(1, int(round(original_size[0] * scale))),
                max(1, int(round(original_size[1] * scale))),
            )
            img = img.resize(new_size, Image.LANCZOS)
            resized = True
        out = BytesIO()
        img.save(out, format="JPEG", quality=92)
        return out.getvalue(), {
            "originalSize": f"{original_size[0]}x{original_size[1]}",
            "workingSize": f"{img.size[0]}x{img.size[1]}",
            "resized": resized,
        }
    except Exception:
        return img_bytes, {"originalSize": "unknown", "workingSize": "unknown", "resized": False}


def _segment_creative(img_bytes):
    return _fast_segment_rgba(img_bytes)


def _fast_segment_rgba(img_bytes, quality=None):
    """Fast local foreground extraction for ID-photo composition.

    This avoids blocking on first-time model downloads. It uses faceBox when
    available, then GrabCut to build an alpha foreground for background compose.
    """
    try:
        import cv2

        data = np.frombuffer(img_bytes, np.uint8)
        bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if bgr is None:
            return Image.open(BytesIO(img_bytes)).convert("RGBA")
        h, w = bgr.shape[:2]
        face = (quality or {}).get("faceBox") or {}
        if face.get("width") and face.get("height"):
            x = float(face.get("x", 0))
            y = float(face.get("y", 0))
            fw = float(face.get("width", 1))
            fh = float(face.get("height", 1))
            left = max(0, int(x - fw * 1.25))
            top = max(0, int(y - fh * 0.95))
            right = min(w - 1, int(x + fw * 2.25))
            bottom = min(h - 1, int(y + fh * 3.85))
        else:
            left = int(w * 0.08)
            top = int(h * 0.04)
            right = int(w * 0.92)
            bottom = int(h * 0.96)
        rect_w = max(2, right - left)
        rect_h = max(2, bottom - top)
        mask = np.zeros((h, w), np.uint8)
        bgd = np.zeros((1, 65), np.float64)
        fgd = np.zeros((1, 65), np.float64)
        cv2.grabCut(bgr, mask, (left, top, rect_w, rect_h), bgd, fgd, 2, cv2.GC_INIT_WITH_RECT)
        grabcut = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")

        prior = np.zeros((h, w), np.uint8)
        if face.get("width") and face.get("height"):
            fx = int(float(face.get("x", 0)))
            fy = int(float(face.get("y", 0)))
            fw = int(float(face.get("width", 1)))
            fh = int(float(face.get("height", 1)))
            cx = int(fx + fw / 2)
            face_cy = int(fy + fh / 2)
            head_rx = int(max(fw * 0.92, fw + 14))
            head_ry = int(max(fh * 1.18, fh + 18))
            cv2.ellipse(prior, (cx, face_cy), (head_rx, head_ry), 0, 0, 360, 255, -1)
            neck_top = int(fy + fh * 0.88)
            shoulder_y = int(min(h - 1, fy + fh * 2.18))
            bottom_y = int(min(h - 1, fy + fh * (3.05 if h / max(1, fh) > 3.2 else 2.72)))
            shoulder_half = int(min(w * 0.48, max(fw * 1.85, fw + 36)))
            neck_half = int(max(fw * 0.34, 18))
            torso_half = int(min(w * 0.42, max(fw * 1.35, fw + 24)))
            pts = np.array([
                [cx - neck_half, neck_top],
                [cx + neck_half, neck_top],
                [cx + shoulder_half, shoulder_y],
                [cx + torso_half, bottom_y],
                [cx - torso_half, bottom_y],
                [cx - shoulder_half, shoulder_y],
            ], dtype=np.int32)
            pts[:, 0] = np.clip(pts[:, 0], 0, w - 1)
            pts[:, 1] = np.clip(pts[:, 1], 0, h - 1)
            cv2.fillPoly(prior, [pts], 255)
        else:
            cv2.ellipse(prior, (w // 2, int(h * 0.47)), (int(w * 0.36), int(h * 0.44)), 0, 0, 360, 255, -1)

        # GrabCut gives hair edges; the face-driven prior prevents dark clothes
        # from being punched out as background.
        alpha = np.maximum(grabcut, prior)
        kernel = np.ones((7, 7), np.uint8)
        alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel, iterations=2)
        alpha = cv2.dilate(alpha, np.ones((3, 3), np.uint8), iterations=1)

        # Keep only the connected component containing the face center when
        # possible; otherwise keep the largest component. This removes blue/black
        # floating fragments before composition.
        n, labels, stats, _ = cv2.connectedComponentsWithStats((alpha > 0).astype("uint8"), 8)
        if n > 1:
            keep_label = 0
            if face.get("width") and face.get("height"):
                fc_x = int(float(face.get("x", 0)) + float(face.get("width", 1)) / 2)
                fc_y = int(float(face.get("y", 0)) + float(face.get("height", 1)) / 2)
                fc_x = int(np.clip(fc_x, 0, w - 1))
                fc_y = int(np.clip(fc_y, 0, h - 1))
                keep_label = int(labels[fc_y, fc_x])
            if keep_label <= 0:
                keep_label = int(1 + np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            min_area = max(64, int(w * h * 0.003))
            keep = np.zeros_like(alpha)
            if stats[keep_label, cv2.CC_STAT_AREA] >= min_area:
                keep[labels == keep_label] = 255
            alpha = keep

        alpha = cv2.GaussianBlur(alpha, (5, 5), 0)
        rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA)
        rgba[:, :, 3] = alpha
        return Image.fromarray(rgba, "RGBA")
    except Exception:
        return Image.open(BytesIO(img_bytes)).convert("RGBA")


def _compose_creative_subject(cutout, background, composition="head_shoulder"):
    target_w, target_h = background.size
    bbox = _alpha_bbox(cutout.getchannel("A"))
    if not bbox:
        raise PortraitQualityError(
            "SEGMENTATION_INCOMPLETE",
            {"imageType": "unknown", "message": "未检测到清晰人物主体，请重新上传头像或半身照。"},
        )

    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    pad_x = int(bw * (0.10 if composition == "square_avatar" else 0.18))
    pad_top = int(bh * 0.08)
    pad_bottom = int(bh * (0.05 if composition != "half_body" else 0.16))
    crop = (
        max(0, x1 - pad_x),
        max(0, y1 - pad_top),
        min(cutout.width, x2 + pad_x),
        min(cutout.height, y2 + pad_bottom),
    )
    subject = cutout.crop(crop)
    sw, sh = subject.size
    if composition == "half_body":
        scale = min(target_w * 1.05 / max(1, sw), target_h * 0.98 / max(1, sh))
        top_padding = int(target_h * 0.04)
    elif composition == "square_avatar":
        scale = min(target_w * 1.10 / max(1, sw), target_h * 1.06 / max(1, sh))
        top_padding = int(target_h * 0.05)
    else:
        scale = min(target_w * 1.28 / max(1, sw), target_h * 1.08 / max(1, sh))
        top_padding = int(target_h * 0.07)
    nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
    subject = subject.resize((nw, nh), Image.LANCZOS)
    px = int((target_w - nw) / 2)
    py = min(top_padding, target_h - nh)

    layer = Image.new("RGBA", background.size, (0, 0, 0, 0))
    layer.paste(subject, (px, py), subject)
    result = Image.alpha_composite(background, layer)
    out_bbox = layer.getbbox() or (0, 0, 0, 0)
    quality = {
        "foregroundBoundingBox": {"x": out_bbox[0], "y": out_bbox[1], "width": out_bbox[2] - out_bbox[0], "height": out_bbox[3] - out_bbox[1]},
        "topPaddingRatio": round(out_bbox[1] / float(max(1, target_h)), 6),
        "subjectWidthRatio": round((out_bbox[2] - out_bbox[0]) / float(max(1, target_w)), 6),
        "subjectHeightRatio": round((out_bbox[3] - out_bbox[1]) / float(max(1, target_h)), 6),
    }
    return result.convert("RGB"), quality


def _normalize_mode(requested_mode, image_type, purpose, spec):
    if image_type in CREATIVE_TYPES:
        return "anime" if purpose in {"anime_avatar", "creative_id_photo"} or spec.get("category") == "anime" else "creative"
    if requested_mode in {"creative", "anime"}:
        return requested_mode
    if spec.get("mode") in {"creative", "anime"}:
        return spec["mode"]
    return "official"


def _build_spec(spec_id="", purpose="official_id_photo", width_px=None, height_px=None, width_mm=None, height_mm=None):
    spec = get_spec(spec_id, purpose)
    if width_px and height_px:
        spec["width"] = int(width_px)
        spec["height"] = int(height_px)
        spec["id"] = spec_id or spec.get("id") or "custom"
    if width_mm:
        spec["widthMm"] = width_mm
    if height_mm:
        spec["heightMm"] = height_mm
    return spec


def _validate_basic_template(outfit, actual_image_type, purpose, composition):
    outfit_id = normalize_outfit(outfit)
    if outfit_id != "preserve_original" and not ADVANCED_OUTFIT_ENABLED:
        raise TemplateError(
            "OUTFIT_TEMPLATE_DISABLED",
            "高级换装暂未开放，请使用保留原服装模式。",
            outfit_id,
        )
    template = get_template(outfit_id)
    if template is None or not template.get("available"):
        raise TemplateError("TEMPLATE_NOT_AVAILABLE", "当前模板暂未接入，请选择其他模板。", outfit_id)
    if actual_image_type not in template.get("supportedImageTypes", []):
        raise TemplateError(
            "TEMPLATE_TYPE_MISMATCH",
            "当前模板不适合该图片类型，请切换真人模板或创意模板。",
            outfit_id,
        )
    if purpose not in template.get("supportedPurposes", []):
        raise TemplateError("TEMPLATE_NOT_AVAILABLE", "当前模板暂未接入，请选择其他模板。", outfit_id)
    if composition not in template.get("compositionSupport", []):
        raise TemplateError(
            "COMPOSITION_FAILED",
            "服装贴合失败，请切换保留原服装或重新上传正面半身照。",
            outfit_id,
        )
    return outfit_id


def _prepare_cutout(
    img_bytes,
    purpose="official_id_photo",
    spec_id="",
    image_type="",
    mode="official",
    composition="",
    outfit="preserve_original",
    width_px=None,
    height_px=None,
    width_mm=None,
    height_mm=None,
    request_id="",
):
    times = {}
    t_resize = time.perf_counter()
    img_bytes, resize_info = _resize_input_for_prepare(img_bytes)
    times["normalize_image_ms"] = int((time.perf_counter() - t_resize) * 1000)
    print(
        f"[id-photo] requestId={request_id} step=normalize_image "
        f"cost={times['normalize_image_ms']}ms info={resize_info}",
        flush=True,
    )

    spec = _build_spec(spec_id, purpose, width_px, height_px, width_mm, height_mm)
    composition = composition or spec.get("composition") or "head_shoulder"

    t0 = time.perf_counter()
    detected = classify_image_type(img_bytes)
    blur_score = _reject_if_too_blurry(img_bytes, detected)
    detected["blurScore"] = round(blur_score, 2)
    face = detect_face(img_bytes, classifier_quality=detected)
    times["detect_face_ms"] = int((time.perf_counter() - t0) * 1000)
    print(
        f"[id-photo] requestId={request_id} step=detect_face "
        f"cost={times['detect_face_ms']}ms engine={face.get('engine')}",
        flush=True,
    )

    detected_type = detected.get("imageType") or "unknown"
    if image_type:
        detected_type = image_type
    # The lightweight illustration heuristic can misclassify compressed real
    # screenshots. A confident MediaPipe real-face detection is stronger
    # evidence for the official ID-photo path, so allow it to override only
    # the heuristic image type. Images without a reliable real face are still
    # rejected below.
    face_reliable = (
        face.get("success")
        and face.get("engine") == "mediapipe"
        and float(face.get("confidence") or 0) >= 0.82
    )
    creative_override_allowed = face_reliable and not is_illustration_like(img_bytes, face.get("faceBox"))
    if detected_type in CREATIVE_TYPES and creative_override_allowed and not image_type:
        detected_type = "real_person"
        detected["imageType"] = "real_person"
        detected["inputType"] = "real_person"
        detected["realPerson"] = True
        detected["classificationOverride"] = "mediapipe_face"
    if not image_type and is_illustration_like(img_bytes, face.get("faceBox")):
        detected_type = "illustration"
        detected["imageType"] = "illustration"
        detected["inputType"] = "illustration"
        detected["realPerson"] = False
    if detected_type in CREATIVE_TYPES or detected_type in {"object", "landscape"}:
        raise PortraitQualityError(
            "INVALID_INPUT_NOT_REAL_PERSON",
            {
                **detected,
                "code": "INVALID_ID_PHOTO_INPUT",
                "message": "请上传清晰的真人正面照片。",
            },
        )
    if not face.get("success"):
        raise PortraitQualityError(
            "NO_FACE_DETECTED",
            {
                **detected,
                "code": face.get("code") or "FACE_NOT_FOUND",
                "message": face.get("message") or "请上传清晰的真人正面照片。",
                "faceDetector": face,
            },
        )

    actual_image_type = "real_person"
    final_mode = "official" if mode != "creative" else "creative"
    outfit_id = _validate_basic_template(outfit, actual_image_type, purpose, composition)

    t1 = time.perf_counter()
    matting = matte_person(img_bytes, face.get("faceBox"))
    times["remove_background_ms"] = int((time.perf_counter() - t1) * 1000)
    print(f"[id-photo] requestId={request_id} step=remove_background cost={times['remove_background_ms']}ms", flush=True)
    if not matting.get("success"):
        raise PortraitQualityError(
            "SEGMENTATION_INCOMPLETE",
            {
                "code": matting.get("code") or "MASK_QUALITY_FAILED",
                "message": matting.get("message") or "人像抠图不完整，请重新上传清晰正面照片。",
                "matting": matting,
                "faceDetector": face,
            },
        )

    prepared_id = uuid.uuid4().hex
    warnings = ["已按所选规格裁切，请以提交平台最终审核为准。"]
    quality = {
        **detected,
        **matting.get("quality", {}),
        "realPerson": True,
        "faceDetected": True,
        "singlePerson": True,
        "faceCount": face.get("faceCount", 1),
        "faceBox": face["faceBox"],
        "landmarks": face.get("landmarks", {}),
        "faceConfidence": face.get("confidence", 0),
        "faceDetector": face.get("engine", "unknown"),
        "mattingEngine": matting.get("engine"),
        "mattingModel": matting.get("model"),
    }
    debug = {
        "faceDetector": face.get("engine", "unknown"),
        "mattingEngine": matting.get("engine"),
        "rembgModel": matting.get("model"),
        "faceCount": face.get("faceCount", 1),
        "faceBox": face.get("faceBox"),
        "foregroundPath": matting.get("foregroundPath"),
        "maskPath": matting.get("maskPath"),
        "cropParams": {
            "compositionVersion": COMPOSITION_VERSION,
            "composition": composition,
            "faceBox": face.get("faceBox"),
        },
    }
    PREPARE_CACHE[prepared_id] = {
        "preparedId": prepared_id,
        "foregroundPngPath": matting["foregroundPath"],
        "alphaMaskPath": matting.get("maskPath", ""),
        "faceBox": face["faceBox"],
        "quality": quality,
        "spec": spec,
        "purpose": purpose,
        "imageType": actual_image_type,
        "mode": final_mode,
        "composition": composition,
        "outfit": outfit_id,
        "warnings": warnings,
        "createdAt": time.time(),
        "compositionVersion": COMPOSITION_VERSION,
        "debug": debug,
    }
    times["save_foreground_ms"] = int((time.perf_counter() - t1) * 1000) - times["remove_background_ms"]
    print(f"[id-photo] requestId={request_id} step=prepare_cache preparedId={prepared_id}")
    return PREPARE_CACHE[prepared_id], times


def compose_prepared_id_photo(prepared_id, bg_color="", bg_color_name="", output_type="jpg", request_id=""):
    item = PREPARE_CACHE.get(prepared_id)
    if not item:
        raise PortraitQualityError(
            "PREPARED_NOT_FOUND",
            {"code": "PREPARED_NOT_FOUND", "message": "预处理结果已失效，请重新上传照片。"},
            status_code=404,
        )
    t0 = time.perf_counter()
    spec = dict(item["spec"])
    bg_color = bg_color or spec.get("defaultBg") or "blue"
    if bg_color == "custom":
        bg_color = "#1a73e8"
    target_size = (int(spec.get("width", 413)), int(spec.get("height", 579)))
    item_quality = item.get("quality") or {}
    source_background_rgb = (
        (item_quality.get("mattingRefine") or {}).get("sourceBackgroundRgb")
        or item_quality.get("sourceBackgroundRgb")
    )
    result, quality = compose_id_photo(
        item["foregroundPngPath"],
        item.get("faceBox") or item_quality.get("faceBox"),
        target_size,
        BG_COLORS.get(bg_color, bg_color),
        composition=item["composition"],
        source_background_rgb=source_background_rgb,
    )
    quality = {
        **item_quality,
        **quality,
    }
    metrics_check = validate_composition_metrics(quality)
    if not metrics_check.get("success"):
        raise PortraitQualityError(metrics_check["code"], metrics_check)
    result, outfit_payload = _apply_outfit_template(
        result,
        quality,
        item.get("outfit", "preserve_original"),
        item["composition"],
        item["imageType"],
    )
    suffix = ".jpg" if (output_type or "jpg").lower() in {"jpg", "jpeg"} else ".png"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    result.save(tmp, format="JPEG" if suffix == ".jpg" else "PNG", quality=95)
    tmp.flush()
    spec["bgColor"] = BG_COLORS.get(bg_color, bg_color)
    debug = {
        "bgColor": spec["bgColor"],
        "outputSize": f"{target_size[0]}x{target_size[1]}",
        "backgroundPureColor": True,
        "originalBackgroundRemoved": True,
        "usedForegroundPng": True,
        "usedOriginalImageDirectly": False,
        "foregroundPath": item.get("foregroundPngPath"),
        "maskPath": item.get("alphaMaskPath"),
        "cropParams": quality.get("cropParams") or quality.get("cropBox"),
    }
    final_check = validate_final_output(tmp.name, target_size[0], target_size[1], spec["bgColor"])
    if not final_check.get("success"):
        raise PortraitQualityError(final_check["code"], final_check)
    quality_report = build_quality_report(tmp.name, target_size[0], target_size[1], spec["bgColor"], quality, debug)
    quality["qualityReport"] = quality_report
    quality["qualityPassed"] = bool(quality_report.get("passed"))
    quality["qualityScore"] = quality_report.get("score", 0)
    quality["qualityFailReasons"] = quality_report.get("failReasons", [])
    if not quality_report.get("passed"):
        raise PortraitQualityError(
            (quality_report.get("failReasons") or ["ID_PHOTO_QUALITY_FAILED"])[0],
            {
                "code": "ID_PHOTO_QUALITY_FAILED",
                "message": "证件照生成质量未达标，请重新上传清晰正面照片。",
                **quality,
            },
        )
    print(f"[id-photo] requestId={request_id} step=compose_background cost={int((time.perf_counter() - t0) * 1000)}ms")
    return {
        "path": tmp.name,
        "mode": item["mode"],
        "imageType": item["imageType"],
        "spec": spec,
        "outfit": outfit_payload,
        "warnings": item["warnings"],
        "quality": quality,
        "preparedId": prepared_id,
        "bgColor": spec["bgColor"],
        "bgColorName": bg_color_name,
        "debug": debug,
    }


def prepare_id_photo_v2(
    img_bytes,
    purpose="official_id_photo",
    spec_id="",
    image_type="",
    mode="official",
    composition="",
    outfit="preserve_original",
    width_px=None,
    height_px=None,
    width_mm=None,
    height_mm=None,
    request_id="",
):
    return _prepare_cutout(
        img_bytes,
        purpose=purpose,
        spec_id=spec_id,
        image_type=image_type,
        mode=mode,
        composition=composition,
        outfit=outfit,
        width_px=width_px,
        height_px=height_px,
        width_mm=width_mm,
        height_mm=height_mm,
        request_id=request_id,
    )


def generate_id_photo_v2(
    img_bytes,
    purpose="official_id_photo",
    spec_id="",
    bg_color="",
    image_type="",
    mode="official",
    composition="",
    outfit="preserve_original",
    enhance_level="standard",
    output_type="jpg",
    width_px=None,
    height_px=None,
    width_mm=None,
    height_mm=None,
):
    detected = classify_image_type(img_bytes)
    blur_score = _reject_if_too_blurry(img_bytes, detected)
    detected["blurScore"] = round(blur_score, 2)
    actual_image_type = image_type or detected.get("imageType") or "unknown"
    spec = get_spec(spec_id, purpose)
    if width_px and height_px:
        spec["width"] = int(width_px)
        spec["height"] = int(height_px)
        spec["id"] = spec_id or spec.get("id") or "custom"
    if width_mm:
        spec["widthMm"] = width_mm
    if height_mm:
        spec["heightMm"] = height_mm
    composition = composition or spec.get("composition") or "head_shoulder"
    bg_color = bg_color or spec.get("defaultBg") or "blue"
    if bg_color == "custom":
        bg_color = "#1a73e8"
    target_size = (int(spec.get("width", 413)), int(spec.get("height", 579)))
    final_mode = _normalize_mode(mode, actual_image_type, purpose, spec)
    outfit_id = normalize_outfit(outfit)
    if outfit_id != "preserve_original" and not ADVANCED_OUTFIT_ENABLED:
        raise TemplateError(
            "OUTFIT_TEMPLATE_DISABLED",
            "高级换装暂未开放，请使用保留原服装模式。",
            outfit_id,
        )
    template = get_template(outfit_id)
    if template is None:
        raise TemplateError("TEMPLATE_NOT_AVAILABLE", "当前模板暂未接入，请选择其他模板。", outfit_id)
    if not template.get("available"):
        raise TemplateError(
            "TEMPLATE_NOT_AVAILABLE",
            "当前模板暂未接入，请选择其他模板。",
            outfit_id,
        )
    if actual_image_type not in template.get("supportedImageTypes", []):
        raise TemplateError(
            "TEMPLATE_TYPE_MISMATCH",
            "当前模板不适合该图片类型，请切换真人模板或创意模板。",
            outfit_id,
        )
    if purpose not in template.get("supportedPurposes", []):
        raise TemplateError(
            "TEMPLATE_NOT_AVAILABLE",
            "当前模板暂未接入，请选择其他模板。",
            outfit_id,
        )
    if composition not in template.get("compositionSupport", []):
        raise TemplateError(
            "COMPOSITION_FAILED",
            "服装贴合失败，请切换保留原服装或重新上传正面半身照。",
            outfit_id,
        )
    warnings = []

    if actual_image_type in {"object", "landscape", "unknown"}:
        raise PortraitQualityError(
            "NO_FACE_DETECTED",
            {
                **detected,
                "code": "NO_SUBJECT_DETECTED",
                "message": "未检测到清晰人物主体，请重新上传头像或半身照。",
            },
        )

    if actual_image_type in CREATIVE_TYPES:
        warnings.append("当前为创意版，不保证官方审核通过")
        if purpose in {"id_card", "social_security", "passport", "teacher_exam", "civil_service_exam", "official_id_photo"}:
            warnings.append("当前为二次元/插画图片，可生成创意证件照效果，但不适合作为官方证件照提交。")
        cutout = _segment_creative(img_bytes)
        alpha = cutout.getchannel("A").filter(ImageFilter.GaussianBlur(radius=0.4))
        cutout.putalpha(alpha)
        bg = _background(target_size, bg_color, outfit_id)
        result, quality = _compose_creative_subject(cutout, bg, composition)
        quality.update(detected)
    else:
        task = "professional" if purpose in {"career_portrait", "resume"} or composition == "half_body" else "changeBg"
        input_quality = validate_portrait_input(img_bytes, task=task)
        cutout = _fast_segment_rgba(img_bytes, input_quality)
        refined_alpha, quality = validate_segmentation_mask(cutout.getchannel("A"), input_quality, task=task)
        cutout.putalpha(Image.fromarray(refined_alpha, "L"))
        bg = _background(target_size, bg_color, outfit_id)
        result, quality = compose_headshot(
            cutout,
            quality,
            bg,
            target_size=target_size,
            composition=composition,
        )
        if final_mode == "official":
            warnings.append("已按所选规格裁切，请以提交平台最终审核为准。")
        else:
            warnings.append("创意版仅适合头像、展示、简历美化等场景，不保证官方审核通过。")

    result, outfit_payload = _apply_outfit_template(result, quality, outfit_id, composition, actual_image_type)

    if enhance_level == "light":
        result = result.filter(ImageFilter.SMOOTH_MORE)

    suffix = ".jpg" if (output_type or "jpg").lower() in {"jpg", "jpeg"} else ".png"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    result.save(tmp, format="JPEG" if suffix == ".jpg" else "PNG", quality=95)
    tmp.flush()

    spec_payload = dict(spec)
    spec_payload["bgColor"] = BG_COLORS.get(bg_color, bg_color)
    return {
        "path": tmp.name,
        "mode": final_mode,
        "imageType": actual_image_type,
        "spec": spec_payload,
        "outfit": outfit_payload,
        "warnings": warnings,
        "quality": quality,
    }
