"""Real-preview breakpoint verification for the local ID-photo chain.

This script is intentionally narrower than the random 40-sample validation:
it checks the exact local backend/API/frontend preview contract, cache busting,
fresh physical output files, and zoomed local residue regions.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from services.face_detector import detect_face  # noqa: E402
from services.id_photo_specs import BG_COLORS  # noqa: E402
from services.portrait_matting import (  # noqa: E402
    _get_rembg_session,
    clean_refined_foreground_rgba,
    matting_status,
    postprocess_alpha,
)


MULTI_ENGINE_REPORT_DIR = ROOT / "reports" / "id-photo-multi-engine-reset"
REPORT_DIR = MULTI_ENGINE_REPORT_DIR / "real-preview"
ARTIFACT_DIR = MULTI_ENGINE_REPORT_DIR / "artifacts"
COLORS = {
    "blue": BG_COLORS["blue"],
    "white": BG_COLORS["white"],
    "red": BG_COLORS["red"],
    "lightBlue": BG_COLORS["lightBlue"],
    "gray": BG_COLORS["gray"],
}
FORCED_SAMPLES = [
    ("current-male", Path(r"C:\Users\zyu33\Desktop\b9fcfc995c64135f4be13197c85a96f0.jpg"), True),
    ("current-female", Path(r"C:\Users\zyu33\Desktop\cs.jpeg"), True),
    ("reference-visual-only", Path(r"C:\Users\zyu33\Desktop\4755783172013fb27a507a42c99868ee.jpg"), False),
    ("problem-contact-sheet", Path(r"C:\Users\zyu33\Desktop\63315937095ac2f3253351b0d7a95340.png"), False),
]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)[:80]


def full_url(base_url: str, path_or_url: str) -> str:
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    return urljoin(base_url.rstrip("/") + "/", path_or_url.lstrip("/"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def request_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = requests.request(method, url, **kwargs)
        try:
            data = response.json()
        except Exception:
            data = {"text": response.text[:1200]}
        return {
            "ok": 200 <= response.status_code < 300,
            "statusCode": response.status_code,
            "elapsedMs": int((time.perf_counter() - started) * 1000),
            "data": data,
        }
    except Exception as exc:
        return {
            "ok": False,
            "statusCode": 0,
            "elapsedMs": int((time.perf_counter() - started) * 1000),
            "data": {"success": False, "message": str(exc)},
        }


def reset_report_dir() -> None:
    if REPORT_DIR.exists():
        for child in REPORT_DIR.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except PermissionError:
                # Windows keeps backend logs locked while uvicorn is running.
                # Keep the live log file, but still regenerate every report/artifact.
                continue
    if ARTIFACT_DIR.exists():
        shutil.rmtree(ARTIFACT_DIR)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def clear_runtime_cache() -> dict[str, Any]:
    runtime = Path(os.environ.get("ID_PHOTO_RUNTIME_DIR", Path(tempfile.gettempdir()) / "id_photo_server"))
    cleared: list[dict[str, Any]] = []
    runtime.mkdir(parents=True, exist_ok=True)
    for name in ("outputs", "uploads"):
        target = runtime / name
        before_files = list(target.rglob("*")) if target.exists() else []
        before_count = sum(1 for p in before_files if p.is_file())
        before_bytes = sum(p.stat().st_size for p in before_files if p.is_file())
        if target.exists():
            for child in target.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink(missing_ok=True)
        target.mkdir(parents=True, exist_ok=True)
        cleared.append({
            "path": str(target),
            "beforeFileCount": before_count,
            "beforeBytes": before_bytes,
            "afterFileCount": sum(1 for p in target.rglob("*") if p.is_file()),
        })
    for registry in ("asset_registry.json",):
        path = runtime / registry
        existed = path.exists()
        if existed:
            path.unlink()
        cleared.append({"path": str(path), "existed": existed, "removed": existed})
    user_registry = runtime / "user_photo_registry.json"
    cleared.append({
        "path": str(user_registry),
        "existed": user_registry.exists(),
        "removed": False,
        "reason": "preserve my-electronic-photo user records during scoped ID-photo validation",
    })
    return {"runtimeDir": str(runtime), "cleared": cleared, "clearedAt": time.strftime("%Y-%m-%d %H:%M:%S")}


def port_process_info() -> str:
    cmd = (
        "$c=Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue;"
        "$c | Select-Object LocalAddress,LocalPort,OwningProcess | ConvertTo-Json -Compress;"
        "foreach($p in ($c|Select-Object -ExpandProperty OwningProcess -Unique)){"
        "Get-CimInstance Win32_Process -Filter \"ProcessId=$p\" | "
        "Select-Object ProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Compress}"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
    )
    return result.stdout.strip()


def write_runtime_import_map() -> dict[str, Any]:
    modules = [
        "main",
        "services.id_photo_v2",
        "services.portrait_matting",
        "services.id_photo_composer",
        "services.id_photo_quality",
        "services.face_detector",
    ]
    imported = {}
    for name in modules:
        module = importlib.import_module(name)
        imported[name] = str(Path(module.__file__).resolve())
    status = matting_status()
    session = _get_rembg_session()
    payload = {
        "projectRoot": str(ROOT),
        "serverDir": str(SERVER),
        "port8000": port_process_info(),
        "imports": imported,
        "mattingStatus": status,
        "rembgSessionType": type(session).__name__ if session is not None else "",
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    lines = [
        "# Runtime Import Map",
        "",
        f"- Project root: `{payload['projectRoot']}`",
        f"- Server dir: `{payload['serverDir']}`",
        "- 8000 process:",
        "```text",
        payload["port8000"],
        "```",
        "",
        "## Imported Files",
    ]
    for key, value in imported.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend([
        "",
        "## Matting",
        f"- status: `{status}`",
        f"- rembg session type: `{payload['rembgSessionType']}`",
    ])
    write_md(REPORT_DIR / "runtime-import-map.md", lines)
    write_json(REPORT_DIR / "runtime-import-map.json", payload)
    return payload


def normalize_source(source: Path, out: Path) -> bytes:
    image = ImageOps.exif_transpose(Image.open(source)).convert("RGB")
    image.save(out, quality=96)
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=96)
    return buf.getvalue()


def make_raw_and_refined_artifacts(sample_dir: Path, img_bytes: bytes) -> dict[str, Any]:
    image = ImageOps.exif_transpose(Image.open(BytesIO(img_bytes))).convert("RGBA")
    face = detect_face(img_bytes)
    raw_rgba = None
    try:
        from rembg import remove

        session = _get_rembg_session()
        raw_rgba = Image.open(BytesIO(remove(img_bytes, session=session))).convert("RGBA")
    except Exception:
        raw_rgba = image.copy()
        raw_rgba.putalpha(0)
    raw_rgba.save(sample_dir / "foreground-before-clean.png")
    raw_rgba.getchannel("A").save(sample_dir / "raw-mask.png")
    refined_alpha, _, refine_debug = postprocess_alpha(
        raw_rgba.getchannel("A"),
        face.get("faceBox") if face.get("success") else None,
        image=image,
        return_debug=True,
    )
    refined_rgba = raw_rgba.copy()
    refined_rgba.putalpha(refined_alpha)
    refined_rgba, fg_debug = clean_refined_foreground_rgba(refined_rgba, face.get("faceBox") if face.get("success") else None)
    refined_rgba.save(sample_dir / "foreground-after-clean.png")
    refined_rgba.getchannel("A").save(sample_dir / "refined-mask.png")
    return {
        "face": face,
        "refineDebug": {**refine_debug, **fg_debug},
        "rawAlphaRatio": round(np.count_nonzero(np.asarray(raw_rgba.getchannel("A")) > 8) / float(raw_rgba.width * raw_rgba.height), 6),
        "refinedAlphaRatio": round(np.count_nonzero(np.asarray(refined_rgba.getchannel("A")) > 8) / float(refined_rgba.width * refined_rgba.height), 6),
    }


def prepare(base_url: str, sample: Path) -> dict[str, Any]:
    with sample.open("rb") as f:
        files = {"image": (sample.name, f, "image/jpeg")}
        data = {"purpose": "official_id_photo", "specId": "one-inch", "composition": "head_shoulder", "mode": "official"}
        return request_json("POST", full_url(base_url, "/api/id-photo/prepare"), files=files, data=data, timeout=40)


def compose(base_url: str, prepared_id: str, color: str) -> dict[str, Any]:
    data = {"preparedId": prepared_id, "bgColor": color, "bgColorName": color, "outputType": "jpg"}
    return request_json("POST", full_url(base_url, "/api/id-photo/compose"), data=data, timeout=30)


def download_to(base_url: str, url: str, out: Path) -> dict[str, Any]:
    response = requests.get(full_url(base_url, url), timeout=30)
    out.write_bytes(response.content)
    return {"statusCode": response.status_code, "bytes": len(response.content), "sha256": sha256_file(out) if out.exists() else ""}


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip()
    if value in BG_COLORS:
        value = BG_COLORS[value]
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def crop_box(cx: int, cy: int, half_w: int, half_h: int, width: int, height: int) -> tuple[int, int, int, int]:
    left = max(0, cx - half_w)
    top = max(0, cy - half_h)
    right = min(width, cx + half_w)
    bottom = min(height, cy + half_h)
    return left, top, right, bottom


def roi_definitions(face_box: dict[str, Any], width: int, height: int) -> dict[str, tuple[int, int, int, int]]:
    fx = float(face_box.get("x") or width * 0.32)
    fy = float(face_box.get("y") or height * 0.16)
    fw = max(1.0, float(face_box.get("width") or width * 0.36))
    fh = max(1.0, float(face_box.get("height") or height * 0.28))
    cx = fx + fw * 0.5
    return {
        "right-ear-zoom": crop_box(int(fx + fw * 1.02), int(fy + fh * 0.58), int(fw * 0.34), int(fh * 0.48), width, height),
        "left-ear-zoom": crop_box(int(fx - fw * 0.02), int(fy + fh * 0.58), int(fw * 0.34), int(fh * 0.48), width, height),
        "right-neck-zoom": crop_box(int(fx + fw * 0.86), int(fy + fh * 1.18), int(fw * 0.42), int(fh * 0.42), width, height),
        "left-neck-zoom": crop_box(int(fx + fw * 0.14), int(fy + fh * 1.18), int(fw * 0.42), int(fh * 0.42), width, height),
        "right-shoulder-zoom": crop_box(int(fx + fw * 1.05), int(fy + fh * 1.92), int(fw * 0.62), int(fh * 0.46), width, height),
        "left-shoulder-zoom": crop_box(int(fx - fw * 0.05), int(fy + fh * 1.92), int(fw * 0.62), int(fh * 0.46), width, height),
        "bottom-left-zoom": (0, max(0, height - int(fh * 0.72)), min(width, int(cx)), height),
        "bottom-right-zoom": (max(0, int(cx)), max(0, height - int(fh * 0.72)), width, height),
        "hair-edge-zoom": crop_box(int(cx), int(fy + fh * 0.05), int(fw * 0.78), int(fh * 0.36), width, height),
    }


def residue_check(image_path: Path, bg_hex: str, face_box: dict[str, Any]) -> dict[str, Any]:
    image = Image.open(image_path).convert("RGB")
    arr = np.asarray(image).astype(np.float32)
    h, w = arr.shape[:2]
    bg = np.array(hex_to_rgb(bg_hex), dtype=np.float32)
    yy, xx = np.indices((h, w))
    fx = float(face_box.get("x") or w * 0.32)
    fy = float(face_box.get("y") or h * 0.16)
    fw = max(1.0, float(face_box.get("width") or w * 0.36))
    fh = max(1.0, float(face_box.get("height") or h * 0.28))
    cx = fx + fw * 0.5
    lateral = np.abs(xx - cx)

    rgb = arr
    maxc = rgb.max(axis=2)
    minc = rgb.min(axis=2)
    chroma = maxc - minc
    brightness = rgb.mean(axis=2)
    bg_dist = np.linalg.norm(rgb - bg, axis=2)
    pocket = (
        (yy >= fy + fh * 0.10)
        & (yy <= fy + fh * 2.12)
        & (lateral >= fw * 0.20)
        & (lateral <= fw * 1.52)
    )
    face_core = ((xx - cx) / (fw * 0.62)) ** 2 + ((yy - (fy + fh * 0.58)) / (fh * 0.88)) ** 2 <= 1.0
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
    neutral_old_bg = (
        pocket
        & ~face_core
        & ~skin_like
        & ~hair_like
        & ~clothing_like
        & (bg_dist > 38.0)
        & (brightness >= 55.0)
        & (brightness <= 248.0)
        & (chroma <= 116.0)
    )
    residue_u8 = cv2.morphologyEx(
        neutral_old_bg.astype("uint8"),
        cv2.MORPH_OPEN,
        np.ones((2, 2), np.uint8),
        iterations=1,
    )
    n, labels, stats, _ = cv2.connectedComponentsWithStats(residue_u8, 8)
    max_area = 0
    components = 0
    for label in range(1, n):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area >= 8:
            components += 1
            max_area = max(max_area, area)
    pixels = int(np.count_nonzero(residue_u8))
    # A tiny neutral area around shirt seams is tolerable; connected old-background
    # sheets next to ears/neck/shoulders are not.
    # A few dozen antialiased dark hair/clothing pixels at the white-background
    # boundary are acceptable; connected old-background sheets are still blocked
    # by the max-component and component-count gates.
    passed = pixels <= 120 and max_area <= 38 and components <= 6
    return {
        "foreignBackgroundPixels": pixels,
        "foreignBackgroundMaxComponent": max_area,
        "foreignBackgroundComponents": components,
        "passed": passed,
    }


def background_hole_check(image_path: Path, bg_hex: str, face_box: dict[str, Any]) -> dict[str, Any]:
    """Detect foreground body areas that were cut through to the selected background."""
    bg = np.array(hex_to_rgb(bg_hex), dtype=np.float32)
    bg_chroma = float(bg.max() - bg.min())
    bg_brightness = float(bg.mean())
    if bg_brightness > 244.0 and bg_chroma < 8.0:
        return {
            "checked": False,
            "backgroundHolePixels": 0,
            "backgroundHoleMaxComponent": 0,
            "backgroundHoleComponents": 0,
            "passed": True,
            "reason": "white_background_not_distinguishable_from_white_clothing",
        }

    image = Image.open(image_path).convert("RGB")
    arr = np.asarray(image).astype(np.float32)
    h, w = arr.shape[:2]
    yy, xx = np.indices((h, w))
    fx = float(face_box.get("x") or w * 0.32)
    fy = float(face_box.get("y") or h * 0.16)
    fw = max(1.0, float(face_box.get("width") or w * 0.36))
    fh = max(1.0, float(face_box.get("height") or h * 0.28))
    cx = fx + fw * 0.5
    lateral = np.abs(xx - cx)
    maxc = arr.max(axis=2)
    minc = arr.min(axis=2)
    chroma = maxc - minc
    bg_dist = np.linalg.norm(arr - bg, axis=2)

    central_chest = (
        (yy >= fy + fh * 1.22)
        & (yy <= min(h - 2, fy + fh * 2.08))
        & (lateral <= fw * 0.76)
    )
    inner_neck = (
        (yy >= fy + fh * 0.96)
        & (yy <= fy + fh * 1.45)
        & (lateral <= fw * 0.46)
    )
    body_core = central_chest | inner_neck
    bg_like = bg_dist <= 18.0
    if bg_chroma < 40.0:
        bg_like &= chroma <= bg_chroma + 26.0
        bg_like &= bg_dist <= 14.0
    bg_hole = body_core & bg_like
    body_u8 = body_core.astype("uint8")
    eroded_body = cv2.erode(body_u8, np.ones((3, 3), np.uint8), iterations=1) > 0
    body_boundary = body_core & ~eroded_body

    n, labels, stats, _ = cv2.connectedComponentsWithStats(bg_hole.astype("uint8"), 8)
    enclosed = np.zeros_like(bg_hole, dtype=bool)
    max_area = 0
    components = 0
    for label in range(1, n):
        comp = labels == label
        if np.any(comp & body_boundary):
            continue
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area >= 10:
            components += 1
            max_area = max(max_area, area)
            enclosed |= comp
    pixels = int(np.count_nonzero(enclosed))
    passed = pixels <= 220 and max_area <= 64 and components <= 8
    return {
        "checked": True,
        "backgroundHolePixels": pixels,
        "backgroundHoleMaxComponent": max_area,
        "backgroundHoleComponents": components,
        "passed": passed,
    }


def save_zooms(image_path: Path, sample_dir: Path, color: str, face_box: dict[str, Any]) -> list[dict[str, Any]]:
    image = Image.open(image_path).convert("RGB")
    rois = roi_definitions(face_box, image.width, image.height)
    rows = []
    thumbs = []
    for name, box in rois.items():
        crop = image.crop(box)
        zoom = crop.resize((max(1, crop.width * 4), max(1, crop.height * 4)), Image.Resampling.NEAREST)
        out = sample_dir / f"{color}-{name}.jpg"
        zoom.save(out, quality=95)
        rows.append({"name": name, "box": box, "path": str(out)})
        thumbs.append((name, zoom))
    if thumbs:
        tw = max(t.width for _, t in thumbs)
        th = max(t.height for _, t in thumbs) + 22
        sheet = Image.new("RGB", (tw * 3, th * 3), (246, 248, 252))
        draw = ImageDraw.Draw(sheet)
        for idx, (name, thumb) in enumerate(thumbs):
            x = (idx % 3) * tw
            y = (idx // 3) * th
            sheet.paste(thumb, (x, y))
            draw.text((x + 4, y + thumb.height + 3), f"{color}-{name}", fill=(20, 28, 44))
        sheet.save(sample_dir / f"{color}-zoom-sheet.jpg", quality=94)
    return rows


def extract_problem_contact_sheet(contact_sheet: Path) -> list[tuple[str, Path]]:
    if not contact_sheet.exists():
        return []
    image = Image.open(contact_sheet).convert("RGB")
    out_dir = ARTIFACT_DIR / "problem-contact-sheet-extracts"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Extract two visible input thumbnails from the generated contact sheet.
    boxes = {
        "contact-female-input": (10, 38, 96, 136),
        "contact-male-input": (552, 38, 635, 136),
    }
    rows = []
    for label, box in boxes.items():
        crop = image.crop(box).resize((max(1, (box[2] - box[0]) * 4), max(1, (box[3] - box[1]) * 4)), Image.Resampling.LANCZOS)
        path = out_dir / f"{label}.jpg"
        crop.save(path, quality=95)
        rows.append((label, path))
    return rows


def verify_sample(base_url: str, label: str, source: Path, required: bool, started_at: float) -> dict[str, Any]:
    sample_dir = ARTIFACT_DIR / safe_name(label)
    sample_dir.mkdir(parents=True, exist_ok=True)
    row: dict[str, Any] = {"label": label, "sourcePath": str(source), "required": required, "success": False}
    if not source.exists():
        row.update({"error": "missing_source"})
        return row

    img_bytes = normalize_source(source, sample_dir / "source.jpg")
    shutil.copy2(sample_dir / "source.jpg", sample_dir / "normalized.jpg")
    row["intermediates"] = make_raw_and_refined_artifacts(sample_dir, img_bytes)

    prep = prepare(base_url, sample_dir / "normalized.jpg")
    row["prepare"] = prep
    if not prep["ok"] or not (prep["data"].get("success") and prep["data"].get("preparedId")):
        row["error"] = "prepare_failed"
        return row
    prepared_id = prep["data"]["preparedId"]
    row["preparedId"] = prepared_id
    color_rows = []
    preview_download_ok = True
    quality_ok = True
    url_ok = True
    for color, hex_value in COLORS.items():
        comp = compose(base_url, prepared_id, color)
        color_row: dict[str, Any] = {"color": color, "compose": comp}
        if not comp["ok"] or not comp["data"].get("success"):
            color_row["error"] = "compose_failed"
            color_rows.append(color_row)
            quality_ok = False
            continue
        data = comp["data"]
        preview_url = data.get("previewUrl") or data.get("finalImageUrl") or data.get("imageUrl") or ""
        download_url = data.get("downloadUrl") or preview_url
        request_id = data.get("requestId") or ""
        preview_file_path = Path(data.get("previewFilePath") or "")
        download_file_path = Path(data.get("downloadFilePath") or "")
        image_out = sample_dir / f"{color}-compose.jpg"
        dl = download_to(base_url, preview_url, image_out)
        shutil.copy2(image_out, sample_dir / f"{color}-preview-image.jpg")
        shutil.copy2(image_out, sample_dir / f"{color}-download-image.jpg")
        quality = data.get("quality") or {}
        face_box = quality.get("outputFaceBox") or ((quality.get("qualityReport") or {}).get("metrics") or {}).get("outputFaceBox") or {}
        if not face_box:
            face_box = {"x": 86, "y": 68, "width": 122, "height": 122}
        residue = residue_check(image_out, hex_value, face_box)
        holes = background_hole_check(image_out, hex_value, face_box)
        zooms = save_zooms(image_out, sample_dir, color, face_box)
        preview_hash = sha256_file(sample_dir / f"{color}-preview-image.jpg")
        download_hash = sha256_file(sample_dir / f"{color}-download-image.jpg")
        mtime_ok = preview_file_path.exists() and preview_file_path.stat().st_mtime >= started_at - 2
        request_in_url = bool(request_id and request_id in preview_url)
        has_version = "?v=" in preview_url or "&v=" in preview_url
        same_physical = preview_file_path == download_file_path and preview_file_path.exists()
        preview_download_same = preview_hash == download_hash
        url_match = request_in_url and has_version and mtime_ok and same_physical
        preview_download_ok = preview_download_ok and preview_download_same
        quality_ok = quality_ok and residue["passed"] and holes["passed"]
        url_ok = url_ok and url_match
        color_row.update({
            "requestId": request_id,
            "previewUrl": preview_url,
            "downloadUrl": download_url,
            "previewFilePath": str(preview_file_path),
            "downloadFilePath": str(download_file_path),
            "requestIdInPreviewUrl": request_in_url,
            "hasCacheBust": has_version,
            "physicalFileFresh": mtime_ok,
            "previewDownloadSame": preview_download_same,
            "samePhysicalPath": same_physical,
            "download": dl,
            "residue": residue,
            "backgroundHoles": holes,
            "zooms": zooms,
        })
        color_rows.append(color_row)
    row["colors"] = color_rows
    row["previewDownloadOk"] = preview_download_ok
    row["urlMatchOk"] = url_ok
    row["zoomQualityOk"] = quality_ok
    row["success"] = preview_download_ok and url_ok and quality_ok
    return row


def frontend_binding_check() -> dict[str, Any]:
    js = (ROOT / "pages" / "generate" / "generate.js").read_text(encoding="utf-8")
    wxml = (ROOT / "pages" / "generate" / "generate.wxml").read_text(encoding="utf-8")
    api = (ROOT / "utils" / "aiImageApi.js").read_text(encoding="utf-8")
    return {
        "resultPreviewSrcData": "resultPreviewSrc" in js,
        "previewUsesRemoteVersionedUrl": "resultPreviewSrc || resultImage" in wxml,
        "cacheBustHelper": "_withCacheBust" in api,
        "previewFilePathLogged": "previewFilePath" in api and "previewFilePath" in js,
        "downloadFilePathLogged": "downloadFilePath" in api and "downloadFilePath" in js,
    }


def write_reports(payload: dict[str, Any]) -> None:
    write_json(REPORT_DIR / "final-summary.json", payload)
    write_json(MULTI_ENGINE_REPORT_DIR / "wechat-real-preview-report.json", payload)
    cache = payload["cacheClear"]
    write_md(REPORT_DIR / "cache-clear-check.md", [
        "# Cache Clear Check",
        "",
        f"- Runtime dir: `{cache['runtimeDir']}`",
        f"- Cleared at: `{cache['clearedAt']}`",
        "",
        "| path | before files | before bytes | after files |",
        "|---|---:|---:|---:|",
        *[
            f"| `{item['path']}` | {item.get('beforeFileCount', '')} | {item.get('beforeBytes', '')} | {item.get('afterFileCount', '')} |"
            for item in cache["cleared"]
        ],
    ])

    fb = payload["frontendBinding"]
    write_md(REPORT_DIR / "frontend-backend-url-match.md", [
        "# Frontend / Backend URL Match",
        "",
        f"- Frontend uses `resultPreviewSrc || resultImage`: `{fb['previewUsesRemoteVersionedUrl']}`",
        f"- API adds cache bust: `{fb['cacheBustHelper']}`",
        f"- API logs previewFilePath/downloadFilePath: `{fb['previewFilePathLogged'] and fb['downloadFilePathLogged']}`",
        "",
        "| sample | color | requestId | cache-bust URL | fresh physical file | preview/download same | path |",
        "|---|---|---|---:|---:|---:|---|",
        *[
            f"| {sample['label']} | {color['color']} | `{color.get('requestId','')}` | {color.get('hasCacheBust')} | {color.get('physicalFileFresh')} | {color.get('previewDownloadSame')} | `{color.get('previewFilePath','')}` |"
            for sample in payload["samples"]
            for color in sample.get("colors", [])
        ],
    ])

    write_md(REPORT_DIR / "local-artifact-comparison.md", [
        "# Local Artifact Comparison",
        "",
        "Each sample directory contains: `source`, `normalized`, `raw-mask`, `refined-mask`, `foreground-before-clean`, `foreground-after-clean`, five `*-compose`, `*-preview-image`, and `*-download-image` files.",
        "",
        "| sample | success | preparedId | preview/download | url match | zoom quality |",
        "|---|---:|---|---:|---:|---:|",
        *[
            f"| {sample['label']} | {sample.get('success')} | `{sample.get('preparedId','')}` | {sample.get('previewDownloadOk')} | {sample.get('urlMatchOk')} | {sample.get('zoomQualityOk')} |"
            for sample in payload["samples"]
        ],
    ])

    write_md(REPORT_DIR / "zoom-quality-check.md", [
        "# Zoom Quality Check",
        "",
        "The local ROI gate checks ears, neck, shoulders, bottom corners, hair-edge zooms, and foreground core background holes. It fails on connected neutral old-background sheets or body/clothing areas cut through to the selected background.",
        "",
        "| sample | color | foreign pixels | max component | components | bg-hole pixels | bg-hole max | pass |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
        *[
            f"| {sample['label']} | {color['color']} | {color.get('residue',{}).get('foreignBackgroundPixels','')} | {color.get('residue',{}).get('foreignBackgroundMaxComponent','')} | {color.get('residue',{}).get('foreignBackgroundComponents','')} | {color.get('backgroundHoles',{}).get('backgroundHolePixels','')} | {color.get('backgroundHoles',{}).get('backgroundHoleMaxComponent','')} | {color.get('residue',{}).get('passed','') and color.get('backgroundHoles',{}).get('passed','')} |"
            for sample in payload["samples"]
            for color in sample.get("colors", [])
        ],
    ])

    why = payload.get("diagnosis", {})
    write_md(REPORT_DIR / "final-summary.md", [
        "# Real Preview Debug Final Summary",
        "",
        f"- Status: `{payload['status']}`",
        f"- Base URL: `{payload['baseUrl']}`",
        f"- Health: `{payload['health'].get('ok')}`",
        f"- Runtime imports verified: `{payload['runtimeImportsVerified']}`",
        f"- Frontend cache-bust preview binding verified: `{payload['frontendBindingOk']}`",
        f"- Required samples passed: `{payload['requiredSamplesPassed']}`",
        f"- Preview/download consistency: `{payload['previewDownloadPassed']}`",
        f"- URL/file freshness match: `{payload['urlMatchPassed']}`",
        f"- Zoom ROI quality: `{payload['zoomQualityPassed']}`",
        "",
        "## Why The Previous PASS Did Not Match DevTools",
        f"- Diagnosis: {why.get('summary')}",
        f"- Old process/cache: {why.get('oldProcessOrCache')}",
        f"- Missing frontend cache-bust: {why.get('missingCacheBust')}",
        f"- Verification gap: {why.get('verificationGap')}",
        "",
        "## Modified Scope",
        "- `server/main.py`: ID-photo compose now returns cache-busted preview/download URLs and physical paths.",
        "- `utils/aiImageApi.js`: ID-photo compose downloads cache-busted URLs and logs requestId + file paths.",
        "- `pages/generate/generate.js`: preview state stores remote versioned URL separately from local download path.",
        "- `pages/generate/generate.wxml`: preview image binds to the versioned URL first.",
        "- `server/scripts/verify_id_photo_real_preview.py`: new real-preview breakpoint verifier.",
        "",
        "## Reports",
        f"- runtime import map: `{REPORT_DIR / 'runtime-import-map.md'}`",
        f"- cache clear: `{REPORT_DIR / 'cache-clear-check.md'}`",
        f"- frontend/backend URL match: `{REPORT_DIR / 'frontend-backend-url-match.md'}`",
        f"- local artifact comparison: `{REPORT_DIR / 'local-artifact-comparison.md'}`",
        f"- zoom quality check: `{REPORT_DIR / 'zoom-quality-check.md'}`",
    ])
    write_md(MULTI_ENGINE_REPORT_DIR / "wechat-real-preview-report.md", [
        "# WeChat Real Preview Verification Report",
        "",
        f"- Status: `{payload['status']}`",
        f"- Base URL: `{payload['baseUrl']}`",
        f"- Runtime imports verified: `{payload['runtimeImportsVerified']}`",
        f"- Frontend cache-bust preview binding verified: `{payload['frontendBindingOk']}`",
        f"- Required samples passed: `{payload['requiredSamplesPassed']}`",
        f"- Preview/download consistency: `{payload['previewDownloadPassed']}`",
        f"- URL/file freshness match: `{payload['urlMatchPassed']}`",
        f"- Zoom ROI quality: `{payload['zoomQualityPassed']}`",
        f"- Artifact directory: `{ARTIFACT_DIR}`",
        f"- Detailed report: `{REPORT_DIR / 'final-summary.md'}`",
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    reset_report_dir()
    started_at = time.time()
    cache_clear = clear_runtime_cache()
    runtime = write_runtime_import_map()
    health = request_json("GET", full_url(args.base_url, "/api/health"), timeout=10)
    extracted = extract_problem_contact_sheet(Path(r"C:\Users\zyu33\Desktop\63315937095ac2f3253351b0d7a95340.png"))

    samples = []
    for label, path, required in FORCED_SAMPLES:
        samples.append(verify_sample(args.base_url, label, path, required, started_at))
    for label, path in extracted:
        samples.append(verify_sample(args.base_url, label, path, False, started_at))

    required = [s for s in samples if s.get("required")]
    frontend = frontend_binding_check()
    frontend_ok = all(frontend.values())
    required_ok = bool(required) and all(s.get("success") for s in required)
    preview_download_ok = all(s.get("previewDownloadOk", False) for s in required)
    url_ok = all(s.get("urlMatchOk", False) for s in required)
    zoom_ok = all(s.get("zoomQualityOk", False) for s in required)
    runtime_ok = all(str(ROOT) in v for v in (runtime.get("imports") or {}).values())
    status = "PASS" if health.get("ok") and runtime_ok and frontend_ok and required_ok and preview_download_ok and url_ok and zoom_ok else "FAIL"
    payload = {
        "status": status,
        "baseUrl": args.base_url,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "health": health,
        "runtimeImportsVerified": runtime_ok,
        "frontendBinding": frontend,
        "frontendBindingOk": frontend_ok,
        "cacheClear": cache_clear,
        "samples": samples,
        "requiredSamplesPassed": required_ok,
        "previewDownloadPassed": preview_download_ok,
        "urlMatchPassed": url_ok,
        "zoomQualityPassed": zoom_ok,
        "diagnosis": {
            "summary": "Previous random/report validation did not force local mini-program preview URL freshness or zoomed ROI residue gates.",
            "oldProcessOrCache": "The script records current 8000 process and clears local runtime output/upload files before generating fresh artifacts.",
            "missingCacheBust": "Before this fix, compose responses could be consumed without a requestId/hash cache-bust URL in the page preview.",
            "verificationGap": "The new verifier writes per-ROI zoom files and fails on connected old-background pockets around ears, neck, shoulders, and bottom corners.",
        },
    }
    write_reports(payload)
    if status != "PASS":
        print("[verify-id-photo-real-preview] FAIL report=" + str(REPORT_DIR / "final-summary.md"))
        return 1
    print("[verify-id-photo-real-preview] PASS report=" + str(REPORT_DIR / "final-summary.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
