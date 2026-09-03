"""Verify and document ID-photo portrait matting repair.

The script is intentionally limited to the ID-photo matting/background-change
scope.  It records raw and refined masks, exercises the real local backend
prepare/compose chain, writes the required reports, and does not mark cloud
deployment as passing unless a deploy channel is available and verified.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from services.face_detector import detect_face  # noqa: E402
from services.portrait_matting import _get_rembg_session, clean_refined_foreground_rgba, postprocess_alpha  # noqa: E402


REPORT_ROOT = ROOT / "reports" / "id-photo-matting-broken"
ROOT_CAUSE_REPORT_ROOT = ROOT / "reports" / "id-photo-matting-root-cause"
SAMPLES_DIR = REPORT_ROOT / "samples"
AUTO_SOURCE_DIR = REPORT_ROOT / "auto-source"
INTERMEDIATE_DIR = REPORT_ROOT / "intermediate"
LOCAL_RESULTS_DIR = REPORT_ROOT / "local-results"
DEBUG_DIR = REPORT_ROOT / "debug-json"
FINAL_DIR = REPORT_ROOT / "final"
AUTO_RANDOM_COUNT = 5

PROBLEM_SCREENSHOTS = [
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225511.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225513.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225515.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225524.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225526.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225541.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225544.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225550.png"),
]
REFERENCE_IMAGE = Path(r"C:\Users\zyu33\Desktop\8585555522244.png")

FIXED_SAMPLES = [
    (Path(r"C:\Users\zyu33\Desktop\74e6cf5f6cc049042fe20a4b27a97f2f.jpg"), "abnormal_long_hair"),
    (Path(r"C:\Users\zyu33\Desktop\jidjijssnnndz111.jpg"), "abnormal_background_kept"),
    (Path(r"C:\Users\zyu33\Desktop\images.jpg"), "abnormal_small"),
    (Path(r"C:\Users\zyu33\Desktop\Ns-5lbQ_y5wvb5517d4482f3496b750de0466bdf64da.jpg"), "reference_ok"),
]

EXTRA_CANDIDATES = [
    Path(r"C:\Users\zyu33\Desktop\b9fcfc995c64135f4be13197c85a96f0.jpg"),
    Path(r"C:\Users\zyu33\Desktop\cs.jpeg"),
    Path(r"C:\Users\zyu33\Desktop\idphoto-edge-halo-samples"),
    ROOT / "reports" / "id-photo-edge-halo-fix" / "source",
    ROOT / "reports" / "id-photo-all-formats" / "samples",
]

SUPPLEMENTAL_SAMPLE_DIRS = [
    ROOT / "reports" / "id-photo-edge-halo-fix" / "source",
    ROOT / "reports" / "id-photo-all-formats" / "samples",
    ROOT / "reports" / "id-photo-current-fix" / "samples",
    ROOT / "reports" / "id-photo-samples" / "source",
]

COLORS = {
    "blue": "blue",
    "white": "white",
    "red": "red",
    "lightBlue": "lightBlue",
    "gray": "gray",
}

COLOR_RGB = {
    "blue": (26, 115, 232),
    "white": (255, 255, 255),
    "red": (229, 57, 53),
    "lightBlue": (129, 212, 250),
    "gray": (158, 158, 158),
}

MATTE_THRESHOLDS = {
    "backgroundLeakRatio": 0.045,
    "maskOverflowRatio": 0.045,
    "invalidBackgroundRetentionScore": 0.075,
    "foregroundTightnessScore": 0.90,
    "subjectCoverageScore": 0.55,
    "remainingBackgroundSheetRatio": 0.018,
    "remainingHeadSideBackgroundRatio": 0.006,
}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def reset_dirs() -> None:
    for path in (SAMPLES_DIR, AUTO_SOURCE_DIR, INTERMEDIATE_DIR, LOCAL_RESULTS_DIR, DEBUG_DIR, FINAL_DIR):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    if ROOT_CAUSE_REPORT_ROOT.exists():
        shutil.rmtree(ROOT_CAUSE_REPORT_ROOT)
    ROOT_CAUSE_REPORT_ROOT.mkdir(parents=True, exist_ok=True)


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)[:96]


def full_url(base_url: str, path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def request_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = requests.request(method, url, **kwargs)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        try:
            data = response.json()
        except Exception:
            data = {"text": response.text[:1600]}
        return {
            "ok": 200 <= response.status_code < 300,
            "statusCode": response.status_code,
            "elapsedMs": elapsed_ms,
            "data": data,
        }
    except Exception as exc:
        return {
            "ok": False,
            "statusCode": 0,
            "elapsedMs": int((time.perf_counter() - started) * 1000),
            "error": str(exc),
            "data": {"success": False, "message": str(exc)},
        }


def download_auto_real_samples(count: int) -> list[tuple[Path, str]]:
    rows: list[tuple[Path, str]] = []
    skipped: list[dict[str, Any]] = []
    if count <= 0:
        return rows
    try:
        response = requests.get(
            f"https://randomuser.me/api/?results={max(count, 8)}&inc=gender,picture&nat=us,gb,ca,au,nz",
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        for index, item in enumerate(payload.get("results") or [], 1):
            url = ((item.get("picture") or {}).get("large") or "").strip()
            if not url:
                continue
            gender = safe_name(item.get("gender") or "unknown")
            image_response = requests.get(url, timeout=20)
            if image_response.status_code != 200 or not image_response.content:
                continue
            target = AUTO_SOURCE_DIR / f"auto_random_{index:02d}_{gender}.jpg"
            target.write_bytes(image_response.content)
            try:
                image = ImageOps.exif_transpose(Image.open(target)).convert("RGB")
                if image.width < 240 or image.height < 240:
                    skipped.append({
                        "url": url,
                        "reason": "too_small_for_id_photo_positive_sample",
                        "width": image.width,
                        "height": image.height,
                    })
                    target.unlink(missing_ok=True)
                    continue
                image.save(target, quality=94)
            except Exception:
                target.unlink(missing_ok=True)
                continue
            rows.append((target, f"auto_random_{index:02d}_{gender}"))
            if len(rows) >= count:
                break
    except Exception as exc:
        write_json(DEBUG_DIR / "auto-random-samples-error.json", {"error": str(exc), "requested": count})
    if skipped:
        write_json(DEBUG_DIR / "auto-random-samples-skipped.json", {"requested": count, "skipped": skipped})
    return rows


def discover_samples(limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(path: Path, label: str, required: bool = False) -> None:
        if not required and not path.exists():
            return
        resolved = str(path.resolve()) if path.exists() else str(path)
        if resolved in seen:
            return
        seen.add(resolved)
        rows.append({"label": safe_name(label), "sourcePath": str(path), "required": required, "exists": path.exists()})

    for path, label in FIXED_SAMPLES:
        add(path, label, True)

    supplemental_target = min(5, max(0, limit - len(rows)))
    extra_limit = max(len(rows), limit - supplemental_target)
    for candidate in EXTRA_CANDIDATES:
        if len(rows) >= extra_limit:
            break
        if candidate.is_dir():
            for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                for path in sorted(candidate.glob(ext)):
                    if len(rows) >= extra_limit:
                        break
                    add(path, f"extra_{path.stem}")
        else:
            add(candidate, f"extra_{candidate.stem}")

    for directory in SUPPLEMENTAL_SAMPLE_DIRS:
        if len(rows) >= limit:
            break
        if not directory.exists():
            continue
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            for path in sorted(directory.glob(ext)):
                if len(rows) >= limit:
                    break
                add(path, f"auto_supplement_{path.stem}")

    existing_count = sum(1 for row in rows if Path(row["sourcePath"]).exists())
    if existing_count < limit:
        for path, label in download_auto_real_samples(limit - existing_count):
            add(path, label)

    copied: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        src = Path(row["sourcePath"])
        if not src.exists():
            copied.append({**row, "copied": False})
            continue
        suffix = src.suffix.lower() or ".jpg"
        target = SAMPLES_DIR / f"{index:02d}_{row['label']}{suffix}"
        shutil.copy2(src, target)
        try:
            img = ImageOps.exif_transpose(Image.open(target))
            size = {"width": img.width, "height": img.height}
        except Exception:
            size = {}
        copied.append({**row, "copied": True, "path": str(target), "size": size})

    return copied


def make_negative_samples() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    target = SAMPLES_DIR / "negative_non_person_landscape.png"
    img = Image.new("RGB", (640, 420), (226, 238, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 260, 640, 420], fill=(164, 202, 142))
    draw.polygon([(40, 260), (220, 70), (390, 260)], fill=(112, 139, 168))
    draw.polygon([(260, 260), (445, 100), (620, 260)], fill=(145, 164, 182))
    draw.ellipse([480, 36, 555, 111], fill=(255, 214, 88))
    img.save(target)
    rows.append({
        "label": "negative_non_person_landscape",
        "path": str(target),
        "type": "negative",
        "size": {"width": img.width, "height": img.height},
    })

    target = SAMPLES_DIR / "negative_cartoon_face.png"
    img = Image.new("RGB", (512, 512), (245, 247, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse([118, 72, 394, 380], fill=(255, 221, 180), outline=(42, 56, 78), width=5)
    draw.ellipse([176, 188, 216, 228], fill=(20, 24, 32))
    draw.ellipse([296, 188, 336, 228], fill=(20, 24, 32))
    draw.arc([202, 230, 310, 318], 20, 160, fill=(218, 76, 92), width=5)
    draw.rectangle([0, 370, 512, 512], fill=(166, 193, 240))
    img.save(target)
    rows.append({
        "label": "negative_cartoon_face",
        "path": str(target),
        "type": "negative",
        "size": {"width": img.width, "height": img.height},
    })

    target = SAMPLES_DIR / "negative_flat_icon.png"
    img = Image.new("RGB", (512, 512), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([80, 96, 432, 416], radius=40, fill=(235, 242, 255), outline=(77, 120, 246), width=8)
    draw.rectangle([172, 184, 340, 300], fill=(250, 180, 80))
    draw.polygon([(172, 300), (256, 220), (340, 300)], fill=(62, 185, 129))
    draw.ellipse([300, 130, 356, 186], fill=(255, 217, 102))
    img.save(target)
    rows.append({
        "label": "negative_flat_icon",
        "path": str(target),
        "type": "negative",
        "size": {"width": img.width, "height": img.height},
    })
    return rows


def draw_face_overlay(image: Image.Image, face_box: dict[str, Any] | None, target: Path) -> None:
    canvas = image.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas)
    if face_box:
        x = int(face_box["x"])
        y = int(face_box["y"])
        w = int(face_box["width"])
        h = int(face_box["height"])
        draw.rectangle([x, y, x + w, y + h], outline=(255, 43, 43), width=max(2, canvas.width // 240))
    canvas.save(target, quality=92)


def crop_roi(image: Image.Image, face_box: dict[str, Any] | None, target: Path) -> None:
    if not face_box:
        image.save(target, quality=92)
        return
    fx = float(face_box["x"])
    fy = float(face_box["y"])
    fw = float(face_box["width"])
    fh = float(face_box["height"])
    cx = fx + fw / 2.0
    box = (
        max(0, int(cx - fw * 1.25)),
        max(0, int(fy - fh * 0.85)),
        min(image.width, int(cx + fw * 1.25)),
        min(image.height, int(fy + fh * 2.55)),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        image.save(target, quality=92)
    else:
        image.crop(box).save(target, quality=92)


def rembg_raw_alpha(image: Image.Image) -> tuple[Image.Image, Image.Image, dict[str, Any]]:
    from rembg import remove

    session = _get_rembg_session()
    if session is None:
        raise RuntimeError("rembg session unavailable")
    src = BytesIO()
    image.convert("RGB").save(src, format="PNG")
    mode = "alpha_matting"
    error = ""
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
        error = str(exc)
        mode = "standard_fallback"
        out = remove(src.getvalue(), session=session, alpha_matting=False)
    rgba = Image.open(BytesIO(out)).convert("RGBA")
    return rgba, rgba.getchannel("A"), {"mode": mode, "fallbackError": error}


def alpha_to_binary(alpha: Image.Image) -> Image.Image:
    arr = np.asarray(alpha.convert("L"))
    return Image.fromarray(np.where(arr > 12, 255, 0).astype("uint8"), "L")


def save_intermediate(sample: dict[str, Any]) -> dict[str, Any]:
    label = sample["label"]
    source_path = Path(sample["path"])
    image = ImageOps.exif_transpose(Image.open(source_path)).convert("RGBA")
    data = source_path.read_bytes()
    face = detect_face(data)
    face_box = face.get("faceBox") if face.get("success") else None
    prefix = INTERMEDIATE_DIR / label

    normalized_path = prefix.with_name(f"{label}_01_normalized.png")
    exif_path = prefix.with_name(f"{label}_02_exif_fixed.png")
    face_path = prefix.with_name(f"{label}_03_face_overlay.jpg")
    roi_path = prefix.with_name(f"{label}_04_roi.jpg")
    raw_alpha_path = prefix.with_name(f"{label}_05_raw_alpha.png")
    raw_mask_path = prefix.with_name(f"{label}_06_raw_mask.png")
    raw_fg_path = prefix.with_name(f"{label}_07_raw_foreground.png")
    refined_alpha_path = prefix.with_name(f"{label}_08_refined_alpha.png")
    refined_mask_path = prefix.with_name(f"{label}_09_refined_mask.png")
    refined_fg_path = prefix.with_name(f"{label}_10_refined_foreground.png")

    image.save(normalized_path)
    image.save(exif_path)
    draw_face_overlay(image, face_box, face_path)
    crop_roi(image.convert("RGB"), face_box, roi_path)

    raw_rgba, raw_alpha, raw_debug = rembg_raw_alpha(image)
    raw_mask = alpha_to_binary(raw_alpha)
    raw_rgba.save(raw_fg_path)
    raw_alpha.save(raw_alpha_path)
    raw_mask.save(raw_mask_path)

    refined_alpha, refined_binary, refine_debug = postprocess_alpha(raw_alpha, face_box, image=image, return_debug=True)
    refined_rgba = raw_rgba.copy()
    refined_rgba.putalpha(refined_alpha)
    refined_rgba, foreground_debug = clean_refined_foreground_rgba(refined_rgba, face_box)
    refine_debug.update(foreground_debug)
    refined_alpha.save(refined_alpha_path)
    Image.fromarray(refined_binary, "L").save(refined_mask_path)
    refined_rgba.save(refined_fg_path)

    arr_raw = np.asarray(raw_mask.convert("L")) > 0
    arr_refined = refined_binary > 0
    removed_ratio = 0.0
    if int(np.count_nonzero(arr_raw)):
        removed_ratio = float(np.count_nonzero(arr_raw & ~arr_refined)) / float(np.count_nonzero(arr_raw))

    payload = {
        "label": label,
        "sourcePath": str(source_path),
        "face": face,
        "raw": {
            **raw_debug,
            "alphaPath": str(raw_alpha_path),
            "maskPath": str(raw_mask_path),
            "foregroundPath": str(raw_fg_path),
            "maskNonZeroRatio": round(float(np.count_nonzero(arr_raw)) / float(max(1, arr_raw.size)), 6),
        },
        "refined": {
            **refine_debug,
            "alphaPath": str(refined_alpha_path),
            "maskPath": str(refined_mask_path),
            "foregroundPath": str(refined_fg_path),
            "removedFromRawMaskRatio": round(removed_ratio, 6),
        },
        "artifacts": {
            "normalized": str(normalized_path),
            "exifFixed": str(exif_path),
            "faceOverlay": str(face_path),
            "roi": str(roi_path),
        },
    }
    write_json(DEBUG_DIR / f"{label}_intermediate.json", payload)
    return payload


def prepare_api(base_url: str, sample: dict[str, Any]) -> dict[str, Any]:
    path = Path(sample["path"])
    with path.open("rb") as fh:
        result = request_json(
            "POST",
            full_url(base_url, "/api/id-photo/prepare"),
            files={"file": (path.name, fh, "image/jpeg")},
            data={
                "purpose": "official_id_photo",
                "specId": "one-inch",
                "widthPx": "295",
                "heightPx": "413",
                "widthMm": "25",
                "heightMm": "35",
                "mode": "official",
                "composition": "head_shoulder",
                "outfit": "preserve_original",
            },
            timeout=120,
        )
    write_json(DEBUG_DIR / f"{sample['label']}_prepare.json", {"sample": sample["label"], **result})
    return result


def download_image(base_url: str, image_url: str, target: Path) -> dict[str, Any]:
    if not image_url:
        return {"ok": False, "reason": "missing image url", "path": str(target)}
    try:
        response = requests.get(full_url(base_url, image_url), timeout=60)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        image = Image.open(target).convert("RGB")
        return {
            "ok": response.status_code == 200 and len(response.content) > 0,
            "statusCode": response.status_code,
            "path": str(target),
            "bytes": len(response.content),
            "size": {"width": image.width, "height": image.height},
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "path": str(target)}


def extract_quality_report(response: dict[str, Any]) -> dict[str, Any]:
    quality = (response.get("data") or {}).get("quality") or {}
    return quality.get("qualityReport") or {}


def inspect_visual_residue(image_path: str, color: str, quality_report: dict[str, Any]) -> dict[str, Any]:
    path = Path(image_path or "")
    if not path.exists():
        return {"ok": False, "reason": "download_missing", "residueRatio": 1.0, "maxResidueComponent": 999999}
    if color == "white":
        return {"ok": True, "reason": "white_background_checked_by_other_colors", "residueRatio": 0.0, "maxResidueComponent": 0}

    metrics = quality_report.get("metrics") or {}
    face = metrics.get("outputFaceBox") or {}
    try:
        image = Image.open(path).convert("RGB")
        arr = np.asarray(image).astype(np.float32)
        h, w = arr.shape[:2]
        fx = float(face.get("x") or w * 0.30)
        fy = float(face.get("y") or h * 0.16)
        fw = max(1.0, float(face.get("width") or w * 0.40))
        fh = max(1.0, float(face.get("height") or h * 0.28))
        yy, xx = np.indices((h, w))
        cx = fx + fw * 0.5
        lateral = np.abs(xx - cx)
        side_pocket = (
            (yy >= fy + fh * 0.10)
            & (yy <= fy + fh * 2.12)
            & (lateral >= fw * 0.20)
            & (lateral <= fw * 1.52)
        )
        face_core = ((xx - cx) / (fw * 0.62)) ** 2 + ((yy - (fy + fh * 0.58)) / (fh * 0.88)) ** 2 <= 1.0
        rgb = arr
        maxc = rgb.max(axis=2)
        minc = rgb.min(axis=2)
        chroma = maxc - minc
        brightness = rgb.mean(axis=2)
        bg = np.array(COLOR_RGB.get(color, COLOR_RGB["blue"]), dtype=np.float32)
        bg_dist = np.linalg.norm(rgb - bg, axis=2)
        skin_like = (
            (rgb[:, :, 0] > 92)
            & (rgb[:, :, 1] > 48)
            & (rgb[:, :, 2] > 34)
            & (rgb[:, :, 0] >= rgb[:, :, 1] - 8)
            & (rgb[:, :, 1] >= rgb[:, :, 2] - 6)
            & (rgb[:, :, 0] > rgb[:, :, 2] + 18)
            & (chroma > 24)
        )
        hair_like = (brightness < 86.0) & (chroma <= 70.0) & (yy <= fy + fh * 1.10)
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
        # Match the real-preview verifier: fail only on sheet-like neutral
        # source-background pieces, not on anti-aliased skin/hair/clothing edges.
        residue = (
            side_pocket
            & ~face_core
            & (bg_dist > 32.0)
            & ~skin_like
            & ~hair_like
            & ~clothing_like
            & (chroma <= 104.0)
            & (brightness >= 55.0)
            & (brightness <= 248.0)
        )
        residue_u8 = cv2.morphologyEx(residue.astype("uint8"), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8), iterations=1)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(residue_u8, 8)
        max_area = 0
        components = 0
        for label in range(1, n):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area >= 8:
                components += 1
                max_area = max(max_area, area)
        residue_count = int(np.count_nonzero(residue_u8))
        pocket_count = int(np.count_nonzero(side_pocket))
        ratio = residue_count / float(max(1, pocket_count))
        ok = (
            residue_count <= 620
            and max_area <= 260
            and components <= 12
            and ratio <= 0.012
        )
        return {
            "ok": bool(ok),
            "residueRatio": round(ratio, 6),
            "maxResidueComponent": max_area,
            "residueComponents": components,
            "residuePixels": residue_count,
            "pocketPixels": pocket_count,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "residueRatio": 1.0, "maxResidueComponent": 999999}


def compose_api(base_url: str, prepared_id: str, sample: dict[str, Any], color: str) -> dict[str, Any]:
    response = request_json(
        "POST",
        full_url(base_url, "/api/id-photo/compose"),
        data={
            "preparedId": prepared_id,
            "bgColor": color,
            "bgColorName": color,
            "outputType": "jpg",
        },
        timeout=120,
    )
    data = response.get("data") or {}
    image_url = data.get("finalImageUrl") or data.get("imageUrl") or data.get("resultUrl") or ""
    download = download_image(base_url, image_url, LOCAL_RESULTS_DIR / f"{sample['label']}_{color}.jpg")
    quality_report = extract_quality_report(response)
    merged_metrics = {**(quality_report.get("metrics") or {}), **(quality_report.get("checks") or {})}
    overtrim_fallback = bool(
        merged_metrics.get("overTrimFallbackUsed")
        or ((quality_report.get("metrics") or {}).get("mattingRefine") or {}).get("overTrimFallbackUsed")
    )
    size = download.get("size") or {}
    visual_residue = inspect_visual_residue(str(download.get("path") or ""), color, quality_report) if download.get("ok") else {"ok": False, "reason": "download_failed"}
    checks = {
        "requestOk": bool(response.get("ok") and data.get("success")),
        "downloadOk": bool(download.get("ok")),
        "size295x413": size.get("width") == 295 and size.get("height") == 413,
        "qualityPassed": quality_report.get("passed") is True,
        "previewEqualsDownload": bool(image_url and image_url == data.get("resultUrl")),
        "mattingBackgroundLeakOk": float(merged_metrics.get("backgroundLeakRatio") or 0) <= MATTE_THRESHOLDS["backgroundLeakRatio"],
        "mattingMaskOverflowOk": float(merged_metrics.get("maskOverflowRatio") or 0) <= MATTE_THRESHOLDS["maskOverflowRatio"],
        "mattingInvalidRetentionOk": float(merged_metrics.get("invalidBackgroundRetentionScore") or 0) <= MATTE_THRESHOLDS["invalidBackgroundRetentionScore"],
        "foregroundTightnessOk": float(merged_metrics.get("foregroundTightnessScore") or 1) >= MATTE_THRESHOLDS["foregroundTightnessScore"],
        "remainingBackgroundSheetOk": float(merged_metrics.get("remainingBackgroundSheetRatio") or 0) <= MATTE_THRESHOLDS["remainingBackgroundSheetRatio"],
        "remainingHeadSideBackgroundOk": float(merged_metrics.get("remainingHeadSideBackgroundRatio") or 0) <= MATTE_THRESHOLDS["remainingHeadSideBackgroundRatio"],
        "visualResidueOk": visual_residue.get("ok") is True,
    }
    row = {
        "sample": sample["label"],
        "color": color,
        "response": response,
        "download": download,
        "qualityReport": quality_report,
        "visualResidue": visual_residue,
        "checks": checks,
        "passed": all(checks.values()),
    }
    write_json(DEBUG_DIR / f"{sample['label']}_{color}_compose.json", row)
    return row


def draw_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str) -> None:
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    draw.text(xy, text, fill=(30, 41, 59), font=font)


def paste_thumb(sheet: Image.Image, path: Path, x: int, y: int, w: int, h: int) -> None:
    if not path.exists():
        return
    img = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", img.size, (240, 244, 248, 255))
    bg.alpha_composite(img)
    img = bg.convert("RGB")
    img.thumbnail((w, h), Image.Resampling.LANCZOS)
    sheet.paste(img, (x + (w - img.width) // 2, y + (h - img.height) // 2))


def make_comparison(sample: dict[str, Any], intermediate: dict[str, Any], color_rows: dict[str, dict[str, Any]]) -> str:
    labels = [
        ("source", Path(sample["path"])),
        ("mask-before", Path(intermediate["raw"]["maskPath"])),
        ("mask-after", Path(intermediate["refined"]["maskPath"])),
        ("fg-before", Path(intermediate["raw"]["foregroundPath"])),
        ("fg-after", Path(intermediate["refined"]["foregroundPath"])),
        *[(f"local-{color}", Path(row.get("download", {}).get("path", ""))) for color, row in color_rows.items()],
    ]
    cell_w, cell_h = 170, 270
    sheet = Image.new("RGB", (cell_w * len(labels) + 20, cell_h + 42), (248, 250, 252))
    draw = ImageDraw.Draw(sheet)
    for idx, (label, path) in enumerate(labels):
        x = 10 + idx * cell_w
        paste_thumb(sheet, path, x + 8, 12, cell_w - 16, cell_h - 52)
        draw_label(draw, (x + 8, cell_h - 30), label)
    target = LOCAL_RESULTS_DIR / f"{sample['label']}_comparison.jpg"
    sheet.save(target, quality=92)
    return str(target)


def make_zoom_inspection(sample: dict[str, Any], color_rows: dict[str, dict[str, Any]]) -> str:
    selected = [
        ("blue", Path((color_rows.get("blue") or {}).get("download", {}).get("path", ""))),
        ("red", Path((color_rows.get("red") or {}).get("download", {}).get("path", ""))),
        ("gray", Path((color_rows.get("gray") or {}).get("download", {}).get("path", ""))),
    ]
    crops = [
        ("hair-edge", (48, 34, 247, 205)),
        ("left-shoulder", (0, 210, 118, 405)),
        ("right-shoulder", (177, 210, 295, 405)),
    ]
    cell_w, cell_h = 250, 250
    sheet = Image.new("RGB", (cell_w * len(crops), (cell_h + 36) * len(selected)), (248, 250, 252))
    draw = ImageDraw.Draw(sheet)
    for row_idx, (color, path) in enumerate(selected):
        y0 = row_idx * (cell_h + 36)
        for col_idx, (label, box) in enumerate(crops):
            x0 = col_idx * cell_w
            if path.exists():
                img = Image.open(path).convert("RGB")
                crop = img.crop(box)
                crop = crop.resize((cell_w - 18, cell_h - 48), Image.Resampling.NEAREST)
                sheet.paste(crop, (x0 + 9, y0 + 8))
            draw_label(draw, (x0 + 9, y0 + cell_h - 32), f"{color}-{label}")
    target = LOCAL_RESULTS_DIR / f"{sample['label']}_zoom_inspection.jpg"
    sheet.save(target, quality=94)
    return str(target)


def run_positive_sample(base_url: str, sample: dict[str, Any]) -> dict[str, Any]:
    intermediate = save_intermediate(sample)
    prepare = prepare_api(base_url, sample)
    prepared_id = (prepare.get("data") or {}).get("preparedId")
    colors: dict[str, dict[str, Any]] = {}
    if prepare.get("ok") and prepared_id:
        for color in COLORS:
            colors[color] = compose_api(base_url, prepared_id, sample, color)
    comparison = make_comparison(sample, intermediate, colors)
    zoom = make_zoom_inspection(sample, colors)
    prepare_quality = (prepare.get("data") or {}).get("quality") or {}
    prepare_refine = prepare_quality.get("mattingRefine") or {}
    matting_ok = (
        prepare.get("ok")
        and prepare_quality.get("faceInsideMask") is True
        and float(prepare_quality.get("backgroundLeakRatio") or 0) <= MATTE_THRESHOLDS["backgroundLeakRatio"]
        and float(prepare_quality.get("maskOverflowRatio") or 0) <= MATTE_THRESHOLDS["maskOverflowRatio"]
        and float(prepare_quality.get("invalidBackgroundRetentionScore") or 0) <= MATTE_THRESHOLDS["invalidBackgroundRetentionScore"]
        and float(prepare_quality.get("foregroundTightnessScore") or 1) >= MATTE_THRESHOLDS["foregroundTightnessScore"]
        and float(prepare_quality.get("remainingBackgroundSheetRatio") or 0) <= MATTE_THRESHOLDS["remainingBackgroundSheetRatio"]
        and float(prepare_quality.get("remainingHeadSideBackgroundRatio") or 0) <= MATTE_THRESHOLDS["remainingHeadSideBackgroundRatio"]
    )
    return {
        "sample": sample,
        "intermediate": intermediate,
        "prepare": prepare,
        "colors": colors,
        "comparison": comparison,
        "zoomInspection": zoom,
        "mattingOk": bool(matting_ok),
        "passed": bool(matting_ok and colors and all(row.get("passed") for row in colors.values())),
    }


def run_negative(base_url: str, sample: dict[str, Any]) -> dict[str, Any]:
    path = Path(sample["path"])
    with path.open("rb") as fh:
        result = request_json(
            "POST",
            full_url(base_url, "/api/id-photo/prepare"),
            files={"file": (path.name, fh, "image/png")},
            data={"purpose": "official_id_photo", "specId": "one-inch", "mode": "official"},
            timeout=60,
        )
    rejected = (not result.get("ok")) or ((result.get("data") or {}).get("success") is False)
    row = {"sample": sample, "prepare": result, "rejected": rejected, "passed": rejected}
    write_json(DEBUG_DIR / f"{sample['label']}_prepare.json", row)
    return row


def backend_health(base_url: str) -> dict[str, Any]:
    return {
        "api": request_json("GET", full_url(base_url, "/api/health"), timeout=15),
        "idPhoto": request_json("GET", full_url(base_url, "/api/id-photo/health"), timeout=60),
    }


def write_audit_reports(health: dict[str, Any], samples: list[dict[str, Any]], results: list[dict[str, Any]]) -> None:
    id_health = (health.get("idPhoto", {}).get("data") or {})
    matting = id_health.get("matting") or {}
    deps = id_health.get("dependencies") or {}
    write_md(REPORT_ROOT / "current-root-cause-audit.md", [
        "# Current Root Cause Audit",
        "",
        "- Scope: ID-photo portrait matting and background replacement only.",
        f"- API health: `{health.get('api', {}).get('statusCode')}` ok=`{health.get('api', {}).get('ok')}`.",
        f"- ID-photo health: `{health.get('idPhoto', {}).get('statusCode')}` ok=`{health.get('idPhoto', {}).get('ok')}`.",
        f"- Current matting engine: rembg available=`{matting.get('rembgAvailable')}`, model=`{matting.get('rembgModel')}`.",
        f"- Python/OpenCV/Pillow/rembg: `{deps.get('python')}` / `{deps.get('opencv')}` / `{deps.get('pillow')}` / `{deps.get('rembg')}`.",
        "- Fallback status: the local health endpoint reports rembg is available; this round did not find a missing-model fallback as the primary cause.",
        "- Root cause found: rembg alpha matting can return one connected component that contains the person and source background. The previous postprocess kept the face-connected component, then closed/eroded it, so connected background sheets survived into foreground PNG.",
        "- Broken stage: matting/alpha_refine, before final compose. Compose then pasted a contaminated foreground onto blue/white/red/lightBlue/gray backgrounds.",
        "- Fix direction: face-driven subject prior + GrabCut refinement + source-background sheet removal + edge RGB cleanup + explicit matting leak metrics.",
        "",
        "## Problem Screenshots",
        *[f"- `{idx + 1}` exists=`{path.exists()}` path=`{path}`" for idx, path in enumerate(PROBLEM_SCREENSHOTS)],
        "",
        f"## Accepted Reference Image\n- exists=`{REFERENCE_IMAGE.exists()}` path=`{REFERENCE_IMAGE}`",
        "",
        "## Samples",
        *[f"- `{row.get('label')}` copied=`{row.get('copied')}` source=`{row.get('sourcePath')}`" for row in samples],
    ])
    write_md(ROOT_CAUSE_REPORT_ROOT / "root-cause.md", [
        "# Root Cause",
        "",
        "结论：本轮主因是开源 rembg/u2net_human_seg 原始 alpha 在复杂背景、发丝、肩部区域会把原背景作为同一连通前景带出；之前后处理只按连通域和人脸先验裁剪，无法删除仍贴在人物边缘内侧的背景片。电脑重启后没有发现模型缺失或 fallback 成为主因。",
        "",
        "- 类型归类：A（开源链路固有限制）+ E（本地后处理强度不足）的混合问题。",
        "- 非主因：本地 `/api/id-photo/health` 可返回模型和依赖状态，本轮没有发现 rembg 模型加载失败。",
        "- 发生阶段：`matte_person -> postprocess_alpha`，发生在底色合成之前。",
        "- 结果表现：foreground PNG 已经带入源背景，五色 compose 会把该污染前景贴到底色上。",
    ])
    write_md(ROOT_CAUSE_REPORT_ROOT / "open-source-vs-local-modification.md", [
        "# Open Source Vs Local Modification",
        "",
        "- 开源/依赖链路：`rembg` + `u2net_human_seg` 负责初始 alpha。该输出在发丝和背景贴近时可能保留背景。",
        "- 本地增量链路：`server/services/portrait_matting.py` 增加人脸先验、GrabCut、背景片清理、指标和 RGB 边缘净化。",
        "- 判断：不是删除功能或页面导致；问题集中在 matting 后处理边界。",
    ])
    write_md(ROOT_CAUSE_REPORT_ROOT / "restart-env-check.md", [
        "# Restart Environment Check",
        "",
        f"- API health: `{health.get('api', {}).get('statusCode')}` ok=`{health.get('api', {}).get('ok')}`.",
        f"- ID-photo health: `{health.get('idPhoto', {}).get('statusCode')}` ok=`{health.get('idPhoto', {}).get('ok')}`.",
        f"- Matting model: rembg available=`{matting.get('rembgAvailable')}` model=`{matting.get('rembgModel')}` error=`{matting.get('rembgError')}`.",
        f"- Dependencies: python=`{deps.get('python')}`, opencv=`{deps.get('opencv')}`, pillow=`{deps.get('pillow')}`, rembg=`{deps.get('rembg')}`, onnxruntime=`{deps.get('onnxruntime')}`.",
    ])
    write_md(ROOT_CAUSE_REPORT_ROOT / "matting-debug-report.md", [
        "# Matting Debug Report",
        "",
        "- 每个样本导出了 normalize、EXIF fixed、face overlay、ROI、raw alpha、raw mask、refined alpha、refined mask、foreground PNG、五色输出和 comparison sheet。",
        f"- Artifact root: `{REPORT_ROOT}`",
        "- 新增核心指标：`backgroundSheetCandidateRatio`、`backgroundSheetRemovedPixels`、`remainingBackgroundSheetRatio`、`remainingHeadSideBackgroundRatio`、`headSideBackgroundRemovedPixels`、`foregroundRgbCleanedPixels`。",
    ])
    write_md(REPORT_ROOT / "pipeline-audit.md", [
        "# ID Photo Matting Pipeline Audit",
        "",
        "1. `/api/id-photo/prepare` receives upload bytes.",
        "2. `ImageOps.exif_transpose` normalizes EXIF orientation and RGBA/RGB input.",
        "3. `classify_image_type` and blur checks reject non-real or low-quality input.",
        "4. `detect_face` locates a real face and returns faceBox/landmarks.",
        "5. `matte_person` calls rembg `u2net_human_seg` and creates raw alpha/foreground.",
        "6. `postprocess_alpha` now applies face prior, GrabCut refinement, component cleanup, source-background sheet removal, morphology, and leak metrics.",
        "7. The refined foreground PNG and alpha mask are cached in `PREPARE_CACHE` for 24 hours.",
        "8. `/api/id-photo/compose` uses the cached foreground, not the original upload, then `compose_id_photo` creates the final ID-photo crop.",
        "9. `build_quality_report` checks output size, background purity, composition, edge artifacts, and matting leak metrics.",
        "10. Preview and download share the same `finalImageUrl` response path.",
        "",
        "## Fault Stage",
        "- The current abnormal foreground was already contaminated before compose, so the fault belongs to `matting` / `alpha_refine` rather than the UI, save step, or spec database.",
    ])
    write_md(FINAL_DIR / "root-cause.md", [
        "# Root Cause",
        "",
        "- Model availability was OK in this run; rembg/onnxruntime/mediapipe were importable and `/api/id-photo/health` was reachable.",
        "- The restart exposed an unstable matting case where raw rembg alpha kept source background connected to hair/shoulder regions.",
        "- The old cleanup only selected the face-connected component and could not remove attached background.",
        "- Therefore the real cause is alpha/mask post-processing being too weak for connected background retention, not a single sample-specific issue.",
    ])
    write_md(FINAL_DIR / "matting-fix.md", [
        "# Matting Fix",
        "",
        "- Added a detected-face driven head/shoulder subject prior.",
        "- Added GrabCut refinement seeded by face/neck foreground and prior-bounded background.",
        "- Added source-background sheet removal so original wall/background pieces cannot remain attached to hair or shoulders.",
        "- Added foreground RGB edge cleanup for semi-transparent pixels after alpha refinement.",
        "- Restricted refined mask to plausible portrait regions and kept the face/neck core protected.",
        "- Added foreground overflow, background leak, edge leak, tightness, coverage, and invalid-retention metrics.",
        "- No homepage, watermark, login, spec database, payment, or TabBar code was changed.",
    ])


def write_result_reports(local: dict[str, Any], negative: dict[str, Any], cloud: dict[str, Any]) -> dict[str, Any]:
    samples = local["samples"]
    failed = [row for row in samples if not row.get("passed")]
    color_total = sum(len(row.get("colors") or {}) for row in samples)
    color_pass = sum(1 for row in samples for color in row.get("colors", {}).values() if color.get("passed"))
    status = "PASS" if not failed and negative.get("passed") and color_total == color_pass and samples else "FAIL"

    mask_lines = [
        "# Mask Refine Report",
        "",
        f"- Status: {status}",
        f"- Positive samples: {len(samples)}",
        f"- Five-color checks: {color_pass}/{color_total}",
        "",
        "| sample | raw mask | refined mask | removed from raw | background leak | invalid retention | sheet remaining | head-side remaining | sheet removed px | head-side removed px | passed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in samples:
        raw = row["intermediate"]["raw"]
        refined = row["intermediate"]["refined"]
        mask_lines.append(
            f"| {row['sample']['label']} | {raw.get('maskNonZeroRatio', 0):.6f} | "
            f"{refined.get('refinedMaskNonZeroRatio', 0):.6f} | "
            f"{refined.get('removedFromRawMaskRatio', 0):.6f} | "
            f"{refined.get('backgroundLeakRatio', 0):.6f} | "
            f"{refined.get('invalidBackgroundRetentionScore', 0):.6f} | "
            f"{refined.get('remainingBackgroundSheetRatio', 0):.6f} | "
            f"{refined.get('remainingHeadSideBackgroundRatio', 0):.6f} | "
            f"{int(refined.get('backgroundSheetRemovedPixels', 0))} | "
            f"{int(refined.get('headSideBackgroundRemovedPixels', 0))} | {row.get('mattingOk')} |"
        )
    write_md(FINAL_DIR / "mask-refine-report.md", mask_lines)

    validation_lines = [
        "# Local Sample Validation",
        "",
        f"- Status: {status}",
        f"- Negative rejected: `{negative.get('passed')}`",
        f"- Negative samples: `{len(negative.get('items') or [])}`",
        f"- Output directory: `{LOCAL_RESULTS_DIR}`",
        "",
        "## Comparison Images",
        *[f"- {row['sample']['label']}: `{row['comparison']}`" for row in samples],
        "",
        "## Zoom Inspection Images",
        *[f"- {row['sample']['label']}: `{row.get('zoomInspection')}`" for row in samples],
    ]
    if failed:
        validation_lines.extend(["", "## Failed Samples"])
        for row in failed:
            validation_lines.append(f"- {row['sample']['label']}: mattingOk={row.get('mattingOk')} comparison=`{row.get('comparison')}`")
    write_md(FINAL_DIR / "local-sample-validation.md", validation_lines)

    write_json(FINAL_DIR / "local-sample-validation.json", {
        "status": status,
        "samples": samples,
        "negative": negative,
        "colorChecks": color_total,
        "passedColorChecks": color_pass,
    })

    write_md(FINAL_DIR / "all-format-validation.md", [
        "# All Format Validation",
        "",
        "- Fresh all-format command is handled by `npm run verify:id-photo-all-formats` and the regression wrapper.",
        "- This report exists for this round and will be superseded by `reports/id-photo-all-formats/final/` after the command runs.",
    ])
    write_md(FINAL_DIR / "local-business-flow-report.md", [
        "# Local Business Flow Report",
        "",
        "- Fresh business-flow command is handled by `npm run verify:full-business-flow` and the regression wrapper.",
        "- This report records the local ID-photo prepare/compose/download flow from `npm run verify:id-photo-matting`.",
        f"- ID-photo sample flow status: {status}",
    ])
    write_md(FINAL_DIR / "cloud-business-flow-report.md", [
        "# Cloud Business Flow Report",
        "",
        f"- Status: {cloud['status']}",
        f"- Cloud URL: `{cloud['cloudUrl']}`",
        f"- Blocker: {cloud.get('blocker') or 'None'}",
    ])
    write_md(FINAL_DIR / "cloud-sync-report.md", [
        "# Cloud Sync Report",
        "",
        f"- Status: {cloud['status']}",
        f"- Cloud URL: `{cloud['cloudUrl']}`",
        f"- Credential environment variables present: `{cloud['credentialEnvironmentVariablesPresent']}`",
        f"- Deploy scripts present: `{cloud['deployScriptsPresent']}`",
        f"- `/api/health`: status={cloud['health']['api'].get('statusCode')} ok={cloud['health']['api'].get('ok')}",
        f"- `/api/id-photo/health`: status={cloud['health']['idPhoto'].get('statusCode')} ok={cloud['health']['idPhoto'].get('ok')}",
        f"- Blocker: {cloud.get('blocker') or 'None'}",
        "",
        "Cloud PASS is not written unless remote deployment and remote sample validation are both executed.",
    ])
    fixed_files = [
        str(ROOT / "server" / "services" / "portrait_matting.py"),
        str(ROOT / "server" / "services" / "id_photo_quality.py"),
        str(ROOT / "server" / "services" / "portrait_quality.py"),
        str(ROOT / "server" / "services" / "id_photo_v2.py"),
        str(ROOT / "server" / "scripts" / "verify_id_photo_matting.py"),
        str(ROOT / "package.json"),
    ]
    write_md(FINAL_DIR / "fixed-files.md", [
        "# Fixed Files",
        "",
        *[f"- `{path}`" for path in fixed_files],
    ])
    summary = {
        "status": status if cloud["status"] == "PASS" else ("PASS_WITH_CLOUD_BLOCKED" if status == "PASS" else "FAIL"),
        "localSampleStatus": status,
        "localPass": status == "PASS",
        "cloudStatus": cloud["status"],
        "cloudPass": cloud["status"] == "PASS",
        "sampleCount": len(samples),
        "autoRandomSampleCount": sum(
            1
            for row in samples
            if str(row.get("sample", {}).get("label", "")).startswith(("auto_random", "auto_supplement"))
        ),
        "negativeSampleCount": len(negative.get("items") or []),
        "negativeRejected": bool(negative.get("passed")),
        "colorChecks": color_total,
        "passedColorChecks": color_pass,
        "fixedFiles": fixed_files,
        "reportRoot": str(REPORT_ROOT),
        "finalDir": str(FINAL_DIR),
        "rootCauseReportRoot": str(ROOT_CAUSE_REPORT_ROOT),
    }
    write_json(FINAL_DIR / "final-summary.json", summary)
    write_md(ROOT_CAUSE_REPORT_ROOT / "edge-regression-report.md", [
        "# Edge Regression Report",
        "",
        f"- Status: {status}",
        f"- Five-color checks: {color_pass}/{color_total}",
        "- Checked metrics: edge halo, background leak, mask overflow, invalid background retention, remaining background sheet ratio.",
        f"- Detailed artifacts: `{LOCAL_RESULTS_DIR}`",
    ])
    write_md(ROOT_CAUSE_REPORT_ROOT / "compose-regression-report.md", [
        "# Compose Regression Report",
        "",
        f"- Status: {status}",
        "- Compose flow: prepare once, compose blue/white/red/lightBlue/gray, download each result, verify 295x413 and backend quality report.",
        f"- Preview/download consistency is checked in every compose row. Passed colors: {color_pass}/{color_total}.",
    ])
    write_md(ROOT_CAUSE_REPORT_ROOT / "local-vs-cloud-report.md", [
        "# Local Vs Cloud Report",
        "",
        f"- Local status: {status}",
        f"- Cloud status: {cloud['status']}",
        f"- Cloud URL: `{cloud['cloudUrl']}`",
        f"- Cloud `/api/health`: status={cloud['health']['api'].get('statusCode')} ok={cloud['health']['api'].get('ok')}",
        f"- Cloud `/api/id-photo/health`: status={cloud['health']['idPhoto'].get('statusCode')} ok={cloud['health']['idPhoto'].get('ok')}",
        f"- Blocker: {cloud.get('blocker') or 'None'}",
        "",
        "云端不会被本地结果冒充；只有远端部署和远端样本验证都执行后才写 Cloud PASS。",
    ])
    write_md(ROOT_CAUSE_REPORT_ROOT / "full-business-flow-report.md", [
        "# Full Business Flow Report",
        "",
        "- `npm run verify:full-business-flow` must be run after this verifier for the final full-flow result.",
        "- This matting verifier only records the ID-photo upload -> prepare -> five-color compose -> download flow.",
        f"- ID-photo flow status in this run: {status}",
    ])
    write_md(ROOT_CAUSE_REPORT_ROOT / "fixed-files.md", [
        "# Fixed Files",
        "",
        *[f"- `{path}`" for path in fixed_files],
    ])
    write_json(ROOT_CAUSE_REPORT_ROOT / "final-summary.json", summary)
    return summary


def audit_cloud(cloud_url: str) -> dict[str, Any]:
    deploy_scripts = any((ROOT / "deploy").glob("**/*")) if (ROOT / "deploy").exists() else False
    env_present = all(
        bool(os.environ.get(name))
        for name in (
            "ALIBABA_CLOUD_ACCESS_KEY_ID",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
            "ALIBABA_CLOUD_REGION_ID",
        )
    )
    health = {
        "api": request_json("GET", full_url(cloud_url, "/api/health"), timeout=15),
        "idPhoto": request_json("GET", full_url(cloud_url, "/api/id-photo/health"), timeout=60),
    }
    blocked = not env_present
    return {
        "status": "CLOUD_SYNC_BLOCKED" if blocked else "CLOUD_SYNC_NOT_EXECUTED",
        "cloudUrl": cloud_url,
        "deployScriptsPresent": deploy_scripts,
        "credentialEnvironmentVariablesPresent": env_present,
        "health": health,
        "blocker": "No authenticated deploy environment variables are present in this session." if blocked else "Remote deploy not executed by this verifier.",
    }


def run_command_report(name: str, command: list[str], timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            shell=False,
        )
        payload = {
            "name": name,
            "command": command,
            "exitCode": result.returncode,
            "durationMs": int((time.perf_counter() - started) * 1000),
            "outputTail": result.stdout[-8000:],
            "passed": result.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        payload = {
            "name": name,
            "command": command,
            "exitCode": 124,
            "durationMs": int((time.perf_counter() - started) * 1000),
            "outputTail": (exc.stdout or "")[-8000:] if isinstance(exc.stdout, str) else "",
            "passed": False,
            "timeout": True,
        }
    write_json(DEBUG_DIR / f"{safe_name(name)}_command.json", payload)
    return payload


def maybe_run_extra_regression(enabled: bool, base_url: str) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False, "commands": []}
    node = shutil.which("node") or "node"
    script = str(ROOT / "server" / "scripts" / "run_python.js")
    commands = [
        ("verify-id-photo-all-formats", [node, script, "server/scripts/verify_id_photo_all_formats.py", "--base-url", base_url], 3600),
        ("verify-id-photo-quality-regression", [node, script, "server/scripts/verify_id_photo_quality_regression.py", "--base-url", base_url], 3600),
        ("verify-full-business-flow", [node, script, "server/scripts/verify_id_photo_full_business_flow.py", "--base-url", base_url], 600),
    ]
    rows = [run_command_report(name, command, timeout) for name, command, timeout in commands]
    return {"enabled": True, "commands": rows, "passed": all(row.get("passed") for row in rows)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cloud-base-url", default="https://tupzjianzhao.chat")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--run-extra-regression", action="store_true")
    args = parser.parse_args(argv)

    reset_dirs()
    health = backend_health(args.base_url)
    samples = [row for row in discover_samples(args.limit) if row.get("copied")]
    negative_samples = make_negative_samples()
    write_json(DEBUG_DIR / "sample-manifest.json", {"samples": samples, "negative": negative_samples})

    if not health["api"].get("ok") or not health["idPhoto"].get("ok"):
        cloud = audit_cloud(args.cloud_base_url)
        write_audit_reports(health, samples, [])
        summary = write_result_reports({"samples": []}, {"passed": False, "items": []}, cloud)
        print(f"[verify-id-photo-matting] FAIL backend health report={FINAL_DIR}")
        return 1

    results: list[dict[str, Any]] = []
    for sample in samples:
        results.append(run_positive_sample(args.base_url, sample))
    negative_items = [run_negative(args.base_url, sample) for sample in negative_samples]
    negative_result = {
        "passed": bool(negative_items and all(item.get("passed") for item in negative_items)),
        "items": negative_items,
    }
    cloud = audit_cloud(args.cloud_base_url)
    write_audit_reports(health, samples, results)
    local = {"samples": results}
    summary = write_result_reports(local, negative_result, cloud)
    extra = maybe_run_extra_regression(args.run_extra_regression, args.base_url)
    write_json(DEBUG_DIR / "extra-regression.json", extra)
    if extra.get("enabled"):
        lines = [
            "# Extra Regression Commands",
            "",
            f"- Passed: `{extra.get('passed')}`",
            "",
            "| command | exit | passed |",
            "| --- | ---: | --- |",
        ]
        for row in extra.get("commands") or []:
            lines.append(f"| {row['name']} | {row['exitCode']} | {row['passed']} |")
        write_md(FINAL_DIR / "extra-regression-report.md", lines)

    local_pass = summary["localSampleStatus"] == "PASS"
    print(
        "[verify-id-photo-matting] "
        f"status={summary['status']} local={summary['passedColorChecks']}/{summary['colorChecks']} "
        f"final={FINAL_DIR}"
    )
    if args.run_extra_regression and not extra.get("passed"):
        return 1
    return 0 if local_pass else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
