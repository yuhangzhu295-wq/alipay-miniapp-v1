"""Current local ID-photo fail-fix verification.

This verifier is intentionally scoped to the local ID-photo main chain.  It
records the previous PASS as invalid, audits the real runtime, compares
Hivision internal matting models, creates zoom artifacts, and writes the
reports required by the current repair round.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from services.face_detector import detect_face  # noqa: E402
from services.id_photo_composer import compose_id_photo  # noqa: E402
from services.id_photo_quality import build_quality_report  # noqa: E402
from services.id_photo_specs import BG_COLORS  # noqa: E402
from services.portrait_matting import matte_person, matting_status  # noqa: E402
from services.portrait_quality import classify_image_type  # noqa: E402


REPORT_ROOT = ROOT / "reports" / "id-photo-final-fix"
ARTIFACT_DIR = REPORT_ROOT / "artifacts"
ALPHA_DEBUG_DIR = REPORT_ROOT / "alpha-debug"
MODEL_AB_DIR = REPORT_ROOT / "hivision-model-ab"
MODEL_AB_ARTIFACT_DIR = MODEL_AB_DIR / "artifacts"
EXTERNAL_AB_DIR = REPORT_ROOT / "external-engine-ab"
WECHAT_DIR = REPORT_ROOT / "wechat-devtools-real-preview"
DEBUG_DIR = REPORT_ROOT / "debug-json"
LEGACY_REPORT_DIR = ROOT / "reports" / "id-photo-multi-engine-reset"
RUNTIME_DIR = Path(os.environ.get("ID_PHOTO_RUNTIME_DIR", Path(tempfile.gettempdir()) / "id_photo_server"))
VERIFY_USER_ID = "verify-id-photo-user"
VERIFY_OPENID = "openid-verify-id-photo"

HIVISION_MODELS = [
    "rmbg-1.4",
    "birefnet-v1-lite",
    "modnet_photographic_portrait_matting",
    "hivision_modnet",
]

COLORS = {
    "blue": BG_COLORS["blue"],
    "white": BG_COLORS["white"],
    "red": BG_COLORS["red"],
    "lightBlue": BG_COLORS["lightBlue"],
    "gray": BG_COLORS["gray"],
}

CORRECT_SAMPLES = [
    Path(r"C:\Users\zyu33\Desktop\556e65a63ebc385b4d7c951ee3f29e39.jpg"),
    Path(r"C:\Users\zyu33\Desktop\be0dc3ea8bff5e60d5bd6cb788dc2e44.jpg"),
    Path(r"C:\Users\zyu33\Desktop\5de8bbf4436236e3cb5f395db4687582.jpg"),
]

DESKTOP_SAMPLES = []

ERROR_SCREENSHOTS = [
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 202641.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225511.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225513.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225524.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225526.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225541.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225544.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225550.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-11 225552.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-12 213441.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-13 145141.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-14 112625.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-14 112658.png"),
    Path(r"C:\Users\zyu33\Pictures\Screenshots\屏幕截图 2026-06-14 112737.png"),
]


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _utc_iso(epoch: float | None = None) -> str:
    value = time.time() if epoch is None else epoch
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def _auth_secret() -> str:
    configured = os.environ.get("ID_PHOTO_AUTH_SECRET")
    if configured:
        return configured
    return hashlib.sha256(("id-photo-auth:" + str(RUNTIME_DIR)).encode("utf-8")).hexdigest()


def _b64url_encode(data: str) -> str:
    return base64.urlsafe_b64encode(data.encode("utf-8")).decode("ascii").rstrip("=")


def _issue_verify_token() -> str:
    payload = {
        "userId": VERIFY_USER_ID,
        "openid": VERIFY_OPENID,
        "provider": "id-photo-verifier",
        "iat": int(time.time()),
        "profile": {"nickName": "id photo verifier"},
    }
    payload_text = _b64url_encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    signature = hmac.new(_auth_secret().encode("utf-8"), payload_text.encode("utf-8"), hashlib.sha256).hexdigest()
    return payload_text + "." + signature


def _auth_headers() -> dict[str, str]:
    token = _issue_verify_token()
    return {
        "Authorization": "Bearer " + token,
        "X-User-Token": token,
    }


def seed_passed_content_safety(image_path: Path, purpose: str = "id_photo") -> dict[str, Any]:
    now_epoch = time.time()
    image_bytes = image_path.read_bytes()
    sha = hashlib.sha256(image_bytes).hexdigest()
    check_id = "verify_id_photo_" + hashlib.sha256((str(image_path) + sha + str(now_epoch)).encode("utf-8")).hexdigest()[:24]
    registry_path = RUNTIME_DIR / "content_security_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(registry_path.read_text(encoding="utf-8"))
        records = existing.get("records") if isinstance(existing, dict) else existing
        if not isinstance(records, list):
            records = []
    except Exception:
        records = []
    records.append({
        "securityCheckId": check_id,
        "safeAssetId": check_id,
        "imageId": "verify_" + sha[:16],
        "userId": VERIFY_USER_ID,
        "userOpenId": VERIFY_OPENID,
        "sha256": sha,
        "imageBytes": len(image_bytes),
        "purpose": purpose,
        "mediaUrl": "local-verifier://id-photo/" + image_path.name,
        "stagingPath": "",
        "status": "PASS",
        "traceId": "local-verifier-" + check_id,
        "statusReason": "LOCAL_ID_PHOTO_VERIFIER_PASS",
        "createdAt": _utc_iso(now_epoch),
        "createdAtEpoch": now_epoch,
        "updatedAt": _utc_iso(now_epoch),
        "updatedAtEpoch": now_epoch,
        "expiresAtEpoch": now_epoch + 1800,
    })
    registry_path.write_text(json.dumps({"records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"securityCheckId": check_id, "sha256": sha, "imageBytes": len(image_bytes), "registryPath": str(registry_path)}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)[:96]


def full_url(base_url: str, path_or_url: str) -> str:
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    return urljoin(base_url.rstrip("/") + "/", path_or_url.lstrip("/"))


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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def reset_report_dir() -> None:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    for child in [ARTIFACT_DIR, ALPHA_DEBUG_DIR, MODEL_AB_DIR, EXTERNAL_AB_DIR, WECHAT_DIR, DEBUG_DIR]:
        if child.exists():
            shutil.rmtree(child)
        child.mkdir(parents=True, exist_ok=True)
    MODEL_AB_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def update_legacy_fail_summary() -> dict[str, Any]:
    payload = {
        "status": "FAIL",
        "generatedAt": now(),
        "reason": "微信开发者工具真实预览仍存在肉眼可见背景残留、头发边缘异常、肩膀断层、衣服缺口",
        "conclusion": [
            "主链路已切换到 HivisionIDPhotos。",
            "当前 hivision_modnet 模型不满足用户真实预览质量。",
            "旧 rembg 不允许冒充主链路通过。",
            "上一轮质量 PASS 无效，本轮必须重跑。",
            "当前验证脚本过宽，必须增加局部放大质量检查。",
        ],
    }
    write_json(LEGACY_REPORT_DIR / "final-summary.json", payload)
    write_md(LEGACY_REPORT_DIR / "final-summary.md", [
        "# ID-photo Multi-engine Reset Final Summary",
        "",
        "- Status: `FAIL`",
        f"- Generated at: `{payload['generatedAt']}`",
        f"- Reason: {payload['reason']}",
        "",
        "## Current Conclusion",
        *[f"- {item}" for item in payload["conclusion"]],
    ])
    write_json(REPORT_ROOT / "final-summary.json", payload)
    write_md(REPORT_ROOT / "final-summary.md", [
        "# Current ID-photo Fail Fix Summary",
        "",
        "- Status: `FAIL`",
        f"- Generated at: `{payload['generatedAt']}`",
        f"- Reason: {payload['reason']}",
        "",
        "This is an intentional reset: no PASS will be recorded until the stricter local preview, zoom, sample, and business-flow checks complete.",
    ])
    return payload


def port8000_process_info() -> str:
    cmd = (
        "$c=Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue;"
        "$c | Select-Object LocalAddress,LocalPort,State,OwningProcess | ConvertTo-Json -Compress;"
        "foreach($owner in ($c|Select-Object -ExpandProperty OwningProcess -Unique)){"
        "Get-CimInstance Win32_Process -Filter \"ProcessId=$owner\" | "
        "Select-Object ProcessId,Name,ExecutablePath,CommandLine,CreationDate | ConvertTo-Json -Compress}"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=12,
    )
    return proc.stdout.strip()


def runtime_audit(base_url: str) -> dict[str, Any]:
    import id_photo_engines.engine_manager as engine_manager
    import id_photo_engines.hivision.adapter as hivision_adapter
    import id_photo_engines.hivision.runner as hivision_runner
    import main
    import services.id_photo_composer as id_photo_composer
    import services.id_photo_quality as id_photo_quality
    import services.id_photo_v2 as id_photo_v2
    import services.portrait_matting as portrait_matting

    api = ROOT / "utils" / "aiImageApi.js"
    page = ROOT / "pages" / "generate" / "generate.js"
    api_text = api.read_text(encoding="utf-8", errors="ignore") if api.exists() else ""
    page_text = page.read_text(encoding="utf-8", errors="ignore") if page.exists() else ""
    health = request_json("GET", full_url(base_url, "/api/health"), timeout=10)
    engine = request_json("GET", full_url(base_url, "/api/id-photo/engine-info"), timeout=20)
    payload = {
        "generatedAt": now(),
        "projectRoot": str(ROOT),
        "python": sys.executable,
        "port8000Process": port8000_process_info(),
        "health": health,
        "engineInfo": engine,
        "imports": {
            "main": str(Path(main.__file__).resolve()),
            "idPhotoApi": str(Path(main.__file__).resolve()),
            "engineManager": str(Path(engine_manager.__file__).resolve()),
            "hivisionAdapter": str(Path(hivision_adapter.__file__).resolve()),
            "hivisionRunner": str(Path(hivision_runner.__file__).resolve()),
            "prepareCompose": str(Path(id_photo_v2.__file__).resolve()),
            "matting": str(Path(portrait_matting.__file__).resolve()),
            "compose": str(Path(id_photo_composer.__file__).resolve()),
            "quality": str(Path(id_photo_quality.__file__).resolve()),
        },
        "frontend": {
            "aiImageApi": str(api),
            "generatePage": str(page),
            "cacheBustHelper": "_withCacheBust" in api_text,
            "requestIdLogged": "requestId" in api_text and "requestId" in page_text,
            "previewUrlLogged": "previewUrl" in api_text and "previewUrl" in page_text,
            "downloadUrlLogged": "downloadUrl" in api_text and "downloadUrl" in page_text,
            "engineLogged": "engineModel" in api_text and "engineModel" in page_text,
        },
        "mattingStatus": matting_status(),
    }
    write_json(DEBUG_DIR / "runtime-chain-audit.json", payload)
    lines = [
        "# Runtime Chain Audit",
        "",
        f"- Generated at: `{payload['generatedAt']}`",
        f"- Project root: `{payload['projectRoot']}`",
        f"- Python: `{payload['python']}`",
        "- 8000 process:",
        "```text",
        payload["port8000Process"],
        "```",
        f"- `/api/health`: status={health.get('statusCode')} ok={health.get('ok')}",
        f"- `/api/id-photo/engine-info`: status={engine.get('statusCode')} ok={engine.get('ok')}",
        f"- Current engine: `{(engine.get('data') or {}).get('engine')}`",
        f"- Current model: `{(engine.get('data') or {}).get('selectedModel')}`",
        "",
        "## Runtime Files",
        *[f"- {key}: `{value}`" for key, value in payload["imports"].items()],
        "",
        "## Frontend Cache / Debug Contract",
        *[f"- {key}: `{value}`" for key, value in payload["frontend"].items() if key not in {"aiImageApi", "generatePage"}],
    ]
    write_md(REPORT_ROOT / "runtime-chain-audit.md", lines)
    return payload


def cache_clean_report(before_note: str = "") -> dict[str, Any]:
    cleared: list[dict[str, Any]] = []
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("outputs", "uploads"):
        target = RUNTIME_DIR / name
        before_files = list(target.rglob("*")) if target.exists() else []
        before_count = sum(1 for item in before_files if item.is_file())
        before_bytes = sum(item.stat().st_size for item in before_files if item.is_file())
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
            "afterFileCount": sum(1 for item in target.rglob("*") if item.is_file()),
        })
    for registry in ("asset_registry.json",):
        path = RUNTIME_DIR / registry
        existed = path.exists()
        if existed:
            path.unlink()
        cleared.append({"path": str(path), "existed": existed, "removed": existed})
    payload = {
        "status": "PASS",
        "generatedAt": now(),
        "runtimeDir": str(RUNTIME_DIR),
        "beforeNote": before_note,
        "cleared": cleared,
        "wechatDevtoolsCache": "No direct DevTools cache API is available in this script; backend URLs are regenerated with requestId/cacheBust and old outputs/uploads were removed.",
    }
    write_json(DEBUG_DIR / "cache-clean-report.json", payload)
    write_md(REPORT_ROOT / "cache-clean-report.md", [
        "# Cache Clean Report",
        "",
        f"- Status: `{payload['status']}`",
        f"- Generated at: `{payload['generatedAt']}`",
        f"- Runtime dir: `{payload['runtimeDir']}`",
        f"- Backend restart note: {before_note or 'handled by outer service restart step'}",
        f"- WeChat DevTools cache note: {payload['wechatDevtoolsCache']}",
        "",
        "| path | before files | before bytes | after files |",
        "| --- | ---: | ---: | ---: |",
        *[
            f"| `{row['path']}` | {row.get('beforeFileCount', '')} | {row.get('beforeBytes', '')} | {row.get('afterFileCount', '')} |"
            for row in cleared
        ],
    ])
    return payload


def collect_existing(paths: list[Path], limit: int = 0) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        if path.is_dir():
            candidates = []
            for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                candidates.extend(sorted(path.glob(ext)))
        else:
            candidates = [path]
        for candidate in candidates:
            if not candidate.exists():
                continue
            key = str(candidate.resolve())
            if key in seen:
                continue
            seen.add(key)
            out.append(candidate)
            if limit and len(out) >= limit:
                return out
    return out


def select_single_face_sources(paths: list[Path], limit: int) -> tuple[list[Path], list[dict[str, Any]]]:
    selected: list[Path] = []
    skipped: list[dict[str, Any]] = []
    for path in collect_existing(paths, limit=0):
        try:
            face = detect_face(path)
            image_type = classify_image_type(path.read_bytes())
        except Exception as exc:
            face = {"success": False, "message": str(exc)}
            image_type = {"imageType": "unknown", "realPerson": False, "error": str(exc)}
        if (
            face.get("success")
            and int(face.get("faceCount") or 0) == 1
            and image_type.get("imageType") == "real_person"
            and image_type.get("realPerson") is True
        ):
            selected.append(path)
            if limit and len(selected) >= limit:
                break
        else:
            skipped.append({
                "path": str(path),
                "reason": "visual-reference-or-not-real-single-face-source",
                "face": face,
                "imageType": image_type,
            })
    return selected, skipped


def copy_source_sample(path: Path, target_dir: Path, label: str) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
    target = target_dir / f"{safe_name(label)}.jpg"
    image.save(target, quality=94)
    return target


def _checkerboard(size: tuple[int, int], cell: int = 16) -> Image.Image:
    w, h = size
    board = Image.new("RGBA", size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(board)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            fill = (226, 232, 240, 255) if ((x // cell) + (y // cell)) % 2 else (248, 250, 252, 255)
            draw.rectangle([x, y, min(w, x + cell), min(h, y + cell)], fill=fill)
    return board


def _composite_foreground(foreground: Image.Image, bg: tuple[int, int, int]) -> Image.Image:
    base = Image.new("RGBA", foreground.size, bg + (255,))
    base.alpha_composite(foreground)
    return base.convert("RGB")


def save_alpha_debug_artifacts(
    base_url: str,
    label: str,
    source: Path,
    prepare_data: dict[str, Any],
) -> dict[str, Any]:
    debug = prepare_data.get("debug") or {}
    quality = prepare_data.get("quality") or {}
    foreground_raw = debug.get("foregroundPath") or quality.get("foregroundPath") or ""
    mask_raw = debug.get("maskPath") or quality.get("maskPath") or ""
    foreground_path = Path(foreground_raw) if foreground_raw else None
    mask_path = Path(mask_raw) if mask_raw else None
    request_id = prepare_data.get("requestId") or debug.get("requestId") or ""
    out_dir = ALPHA_DEBUG_DIR / safe_name(label)
    out_dir.mkdir(parents=True, exist_ok=True)
    row: dict[str, Any] = {
        "label": label,
        "requestId": request_id,
        "source": str(source),
        "foregroundPath": str(foreground_path) if foreground_path else "",
        "maskPath": str(mask_path) if mask_path else "",
        "artifacts": {},
    }

    try:
        src = ImageOps.exif_transpose(Image.open(source)).convert("RGB")
        src_path = out_dir / "source.jpg"
        src.save(src_path, quality=94)
        row["artifacts"]["source"] = str(src_path)
    except Exception as exc:
        row["sourceError"] = str(exc)

    if not foreground_path or not foreground_path.exists():
        row["status"] = "FAIL"
        row["reason"] = "foregroundPath missing after prepare"
        return row

    fg = Image.open(foreground_path).convert("RGBA")
    transparent = out_dir / "transparent_png.png"
    fg.save(transparent)
    row["artifacts"]["transparent_png"] = str(transparent)

    alpha = fg.getchannel("A")
    alpha_path = out_dir / "alpha_channel.png"
    alpha.save(alpha_path)
    row["artifacts"]["alpha_channel"] = str(alpha_path)

    alpha_vis = Image.merge("RGBA", (alpha, alpha, alpha, Image.new("L", alpha.size, 255)))
    alpha_vis_path = out_dir / "alpha_visualization.png"
    alpha_vis.save(alpha_vis_path)
    row["artifacts"]["alpha_visualization"] = str(alpha_vis_path)

    for name, bg in {
        "foreground_on_checkerboard": None,
        "foreground_on_black": (0, 0, 0),
        "foreground_on_white": (255, 255, 255),
        "foreground_on_blue": tuple(int(BG_COLORS["blue"][i:i + 2], 16) for i in (1, 3, 5)),
    }.items():
        if bg is None:
            canvas = _checkerboard(fg.size)
            canvas.alpha_composite(fg)
            image = canvas.convert("RGB")
        else:
            image = _composite_foreground(fg, bg)
        path = out_dir / f"{name}.jpg"
        image.save(path, quality=94)
        row["artifacts"][name] = str(path)

    try:
        face = (quality.get("faceBox") or debug.get("faceBox") or {})
        alpha_metrics = shoulder_alpha_metrics(alpha, face)
        row["alphaMetrics"] = alpha_metrics
        row["status"] = "PASS" if max(
            float(alpha_metrics.get("shoulderAlphaMissingRatio") or 0),
            float(alpha_metrics.get("clothingAlphaMissingRatio") or 0),
            float(alpha_metrics.get("torsoCutoutRatio") or 0),
        ) < 0.20 else "FAIL"
    except Exception as exc:
        row["status"] = "FAIL"
        row["metricError"] = str(exc)
    return row


def draw_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str) -> None:
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
    draw.text(xy, text, fill=(15, 23, 42), font=font)


def save_zoom(image_path: Path, target: Path, box: tuple[int, int, int, int], label: str, passed: bool, reason: str) -> dict[str, Any]:
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    left, top, right, bottom = box
    left = max(0, min(w - 1, int(left)))
    top = max(0, min(h - 1, int(top)))
    right = max(left + 1, min(w, int(right)))
    bottom = max(top + 1, min(h, int(bottom)))
    crop = img.crop((left, top, right, bottom))
    crop = crop.resize((max(160, crop.width * 4), max(160, crop.height * 4)), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (crop.width, crop.height + 42), "white")
    canvas.paste(crop, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, crop.height, canvas.width - 1, canvas.height - 1], fill=(240, 253, 244) if passed else (254, 242, 242))
    draw_label(draw, (8, crop.height + 5), f"{label}: {'PASS' if passed else 'FAIL'}")
    draw_label(draw, (8, crop.height + 22), reason[:70])
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, quality=94)
    return {"path": str(target), "box": [left, top, right, bottom], "passed": passed, "reason": reason}


def zoom_boxes(metrics: dict[str, Any], image_size: tuple[int, int]) -> dict[str, tuple[int, int, int, int]]:
    w, h = image_size
    face = metrics.get("outputFaceBox") or {}
    fg = metrics.get("outputForegroundBox") or {}
    fx = float(face.get("x") or w * 0.30)
    fy = float(face.get("y") or h * 0.17)
    fw = float(face.get("width") or w * 0.40)
    fh = float(face.get("height") or h * 0.28)
    fgx = float(fg.get("x") or 0)
    fgy = float(fg.get("y") or 0)
    fgw = float(fg.get("width") or w)
    fgh = float(fg.get("height") or h)
    return {
        "hair-zoom": (fx - fw * 0.35, max(0, fy - fh * 0.75), fx + fw * 1.35, fy + fh * 0.28),
        "left-ear-zoom": (fx - fw * 0.62, fy + fh * 0.15, fx + fw * 0.08, fy + fh * 0.92),
        "right-ear-zoom": (fx + fw * 0.92, fy + fh * 0.15, fx + fw * 1.62, fy + fh * 0.92),
        "left-neck-zoom": (fx - fw * 0.38, fy + fh * 0.82, fx + fw * 0.22, fy + fh * 1.62),
        "right-neck-zoom": (fx + fw * 0.78, fy + fh * 0.82, fx + fw * 1.38, fy + fh * 1.62),
        "left-shoulder-zoom": (fgx, fy + fh * 1.25, fgx + fgw * 0.35, min(h, fgy + fgh)),
        "right-shoulder-zoom": (fgx + fgw * 0.65, fy + fh * 1.25, fgx + fgw, min(h, fgy + fgh)),
        "bottom-left-zoom": (0, h * 0.72, w * 0.35, h),
        "bottom-left-zoom": (0, h * 0.72, w * 0.35, h),
        "bottom-right-zoom": (w * 0.65, h * 0.72, w, h),
    }


def shoulder_alpha_metrics(alpha_image: Image.Image, face_box: dict[str, Any] | None) -> dict[str, float]:
    empty_metrics = {
        "shoulderAlphaMissingRatio": 0.0,
        "clothingAlphaMissingRatio": 0.0,
        "bodyRegionBackgroundHoleRatio": 0.0,
        "torsoCutoutRatio": 0.0,
        "leftShoulderCutoutRatio": 0.0,
        "rightShoulderCutoutRatio": 0.0,
    }
    if not face_box:
        return empty_metrics
    arr = np.asarray(alpha_image.convert("L"))
    h, w = arr.shape[:2]
    binary = arr > 12
    fx = int(float(face_box.get("x") or 0))
    fy = int(float(face_box.get("y") or 0))
    fw = int(float(face_box.get("width") or 0))
    fh = int(float(face_box.get("height") or 0))
    cx = fx + fw * 0.5
    
    yy, xx = np.indices((h, w))
    
    body_zone = (
        (yy >= fy + fh * 0.95)
        & (xx >= cx - fw * 1.2)
        & (xx <= cx + fw * 1.2)
    )
    left_shoulder_zone = (
        (yy >= fy + fh * 1.2)
        & (xx <= cx - fw * 0.5)
        & (xx >= cx - fw * 1.5)
    )
    right_shoulder_zone = (
        (yy >= fy + fh * 1.2)
        & (xx >= cx + fw * 0.5)
        & (xx <= cx + fw * 1.5)
    )
    
    holes = body_zone & (binary == 0)
    body_area = np.count_nonzero(body_zone)
    hole_ratio = float(np.count_nonzero(holes)) / max(1, body_area)
    
    l_holes = left_shoulder_zone & (binary == 0)
    r_holes = right_shoulder_zone & (binary == 0)
    l_area = np.count_nonzero(left_shoulder_zone)
    r_area = np.count_nonzero(right_shoulder_zone)
    l_ratio = float(np.count_nonzero(l_holes)) / max(1, l_area)
    r_ratio = float(np.count_nonzero(r_holes)) / max(1, r_area)
    
    # Find internal holes inside the main body
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary.astype("uint8"), 8)
    internal_hole_ratio = 0.0
    if n > 1:
        largest = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        main_body = labels == largest
        padded = cv2.copyMakeBorder(main_body.astype("uint8"), 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
        ff_mask = np.zeros((h + 4, w + 4), np.uint8)
        cv2.floodFill(padded, ff_mask, (0, 0), 255)
        filled = cv2.bitwise_not(padded)[1:-1, 1:-1]
        internal_holes = (filled > 0) & (main_body == 0)
        internal_hole_ratio = float(np.count_nonzero(internal_holes)) / max(1, int(stats[largest, cv2.CC_STAT_AREA]))
        
    return {
        "shoulderAlphaMissingRatio": max(l_ratio, r_ratio),
        "clothingAlphaMissingRatio": hole_ratio,
        "bodyRegionBackgroundHoleRatio": internal_hole_ratio,
        "torsoCutoutRatio": hole_ratio,
        "leftShoulderCutoutRatio": l_ratio,
        "rightShoulderCutoutRatio": r_ratio,
    }


def quality_strict_pass(quality: dict[str, Any], color: str, force_fail_current: bool = False) -> tuple[bool, list[str]]:
    report = quality.get("qualityReport") or {}
    checks = report.get("checks") or {}
    metrics = report.get("metrics") or {}
    merged = {**metrics, **checks}
    reasons: list[str] = []
    if force_fail_current:
        reasons.append("hivision_modnet is forced FAIL by user-provided real-preview evidence")
    if report.get("passed") is not True:
        reasons.extend(report.get("failReasons") or ["qualityReport.passed is not true"])
    if color != "white":
        strict_limits = {
            "edgeWhiteHaloRatio": 0.010,
            "hairEdgeHaloRatio": 0.018,
            "foregroundLeakRatio": 0.015,
            "backgroundContaminationScore": 0.020,
            "shoulderAlphaMissingRatio": 0.015,
            "clothingAlphaMissingRatio": 0.020,
            "bodyRegionBackgroundHoleRatio": 0.005,
            "torsoCutoutRatio": 0.020,
            "leftShoulderCutoutRatio": 0.015,
            "rightShoulderCutoutRatio": 0.015,
        }
        for key, limit in strict_limits.items():
            value = float(merged.get(key) or 0)
            if value > limit:
                reasons.append(f"{key}={value:.6f} > {limit:.6f}")
        background_sheet_signal = float(merged.get("remainingBackgroundSheetRatio") or 0) > 0.006
        head_side_signal = float(merged.get("remainingHeadSideBackgroundRatio") or 0) > 0.003
        if int(merged.get("sideBoundaryLineMaxComponentPixels") or 0) > 520 and head_side_signal:
            reasons.append("sideBoundaryLineMaxComponentPixels above 520 with head-side background signal")
        if int(merged.get("sideResidualArtifactMaxComponentPixels") or 0) > 260 and background_sheet_signal:
            reasons.append("sideResidualArtifactMaxComponentPixels above 260 with background-sheet signal")
        if int(merged.get("sideResidualArtifactPixels") or 0) > 900 and (background_sheet_signal or head_side_signal):
            reasons.append("sideResidualArtifactPixels above 900 with matting leak signal")
    if float(merged.get("remainingHeadSideBackgroundRatio") or 0) > 0.006:
        reasons.append("remainingHeadSideBackgroundRatio above 0.006")
    if float(merged.get("remainingBackgroundSheetRatio") or 0) > 0.018:
        reasons.append("remainingBackgroundSheetRatio above 0.018")
    if int(merged.get("hairBackgroundHoleMaxComponentPixels") or 0) > 18:
        reasons.append("hairBackgroundHoleMaxComponentPixels above 18")
    if int(merged.get("hairBackgroundHolePixels") or 0) > 64:
        reasons.append("hairBackgroundHolePixels above 64")
    if int(merged.get("sideBoundaryLineMaxComponentPixels") or 0) > 760:
        reasons.append("sideBoundaryLineMaxComponentPixels above 760")
    if int(merged.get("sideResidualArtifactMaxComponentPixels") or 0) > 520:
        reasons.append("sideResidualArtifactMaxComponentPixels above 520")
    return not reasons, reasons


def run_direct_sample(sample: Path, label: str, model: str, out_dir: Path, force_fail_model: bool = False) -> dict[str, Any]:
    previous = os.environ.get("ID_PHOTO_HIVISION_MODEL")
    os.environ["ID_PHOTO_HIVISION_MODEL"] = model
    try:
        source = copy_source_sample(sample, out_dir / "source", label)
        face = detect_face(source)
        if not face.get("success"):
            return {"sample": label, "model": model, "status": "FAIL", "reason": "face detection failed", "face": face}
        matting = matte_person(source, face.get("faceBox"))
        row: dict[str, Any] = {
            "sample": label,
            "source": str(source),
            "requestedModel": model,
            "actualModel": matting.get("model"),
            "engine": matting.get("engine"),
            "face": face,
            "mattingQuality": matting.get("quality"),
            "colors": {},
            "status": "PASS",
            "failReasons": [],
        }
        if not matting.get("success"):
            row["status"] = "FAIL"
            row["failReasons"].append(matting.get("message") or matting.get("code") or "matting failed")
            return row
        fg = Path(matting["foregroundPath"])
        transparent = out_dir / "transparent" / f"{label}__{safe_name(model)}.png"
        transparent.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fg, transparent)
        row["transparent"] = str(transparent)
        alpha = Image.open(transparent).convert("RGBA").getchannel("A")
        alpha_path = out_dir / "transparent" / f"{label}__{safe_name(model)}_alpha.png"
        alpha.save(alpha_path)
        row["alphaMask"] = str(alpha_path)
        alpha_metrics = shoulder_alpha_metrics(alpha, face.get("faceBox"))
        for color, hex_color in COLORS.items():
            result, metrics = compose_id_photo(fg, face.get("faceBox"), (295, 413), hex_color, source_background_rgb=((matting.get("quality") or {}).get("mattingRefine") or {}).get("sourceBackgroundRgb"))
            img_path = out_dir / color / f"{label}__{safe_name(model)}__{color}.jpg"
            img_path.parent.mkdir(parents=True, exist_ok=True)
            result.save(img_path, quality=95)
            debug = {"usedForegroundPng": True, "usedOriginalImageDirectly": False}
            quality_report = build_quality_report(str(img_path), 295, 413, hex_color, {**(matting.get("quality") or {}), **metrics}, debug)
            quality = {"qualityReport": quality_report, **{**metrics, **alpha_metrics}}
            passed, reasons = quality_strict_pass(quality, color, force_fail_current=force_fail_model)
            zdir = out_dir / "zooms" / label / safe_name(model) / color
            zooms = {}
            boxes = zoom_boxes(metrics, result.size)
            for zlabel, box in boxes.items():
                zooms[zlabel] = save_zoom(
                    img_path,
                    zdir / f"{zlabel}.jpg",
                    box,
                    zlabel,
                    passed,
                    "; ".join(reasons) if reasons else "strict local zoom metrics clean",
                )
            row["colors"][color] = {
                "path": str(img_path),
                "qualityReport": quality_report,
                "metrics": metrics,
                "passed": passed,
                "failReasons": reasons,
                "zooms": zooms,
            }
            if not passed:
                row["status"] = "FAIL"
                row["failReasons"].extend([f"{color}: {reason}" for reason in reasons])
        return row
    finally:
        if previous is None:
            os.environ.pop("ID_PHOTO_HIVISION_MODEL", None)
        else:
            os.environ["ID_PHOTO_HIVISION_MODEL"] = previous


def make_contact_sheet(rows: list[dict[str, Any]], target: Path) -> str:
    cells: list[tuple[str, Path]] = []
    for row in rows:
        source = row.get("source")
        if source:
            cells.append((f"{row['sample']} source", Path(source)))
        for color in COLORS:
            path = ((row.get("colors") or {}).get(color) or {}).get("path")
            if path:
                cells.append((f"{row['sample']} {row.get('actualModel')} {color}", Path(path)))
    if not cells:
        return ""
    cell_w, cell_h = 170, 250
    cols = min(6, len(cells))
    rows_n = (len(cells) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows_n * cell_h), (248, 250, 252))
    draw = ImageDraw.Draw(sheet)
    for idx, (caption, path) in enumerate(cells):
        x = (idx % cols) * cell_w
        y = (idx // cols) * cell_h
        try:
            img = Image.open(path).convert("RGB")
            img.thumbnail((cell_w - 16, cell_h - 44), Image.Resampling.LANCZOS)
            sheet.paste(img, (x + (cell_w - img.width) // 2, y + 8))
        except Exception:
            pass
        draw_label(draw, (x + 6, y + cell_h - 32), caption[:28])
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, quality=92)
    return str(target)


def run_model_ab(sample_limit: int) -> dict[str, Any]:
    sources, skipped_sources = select_single_face_sources(CORRECT_SAMPLES + DESKTOP_SAMPLES, sample_limit)
    model_rows: dict[str, list[dict[str, Any]]] = {}
    model_summary: dict[str, dict[str, Any]] = {}
    for model in HIVISION_MODELS:
        rows = []
        for idx, sample in enumerate(sources, 1):
            rows.append(run_direct_sample(sample, f"sample_{idx:02d}", model, MODEL_AB_ARTIFACT_DIR, force_fail_model=(model == "hivision_modnet")))
        model_rows[model] = rows
        checks = [color for row in rows for color in (row.get("colors") or {}).values()]
        passed = sum(1 for item in checks if item.get("passed"))
        total = len(checks)
        expected_total = len(sources) * len(COLORS)
        failed_samples = [row for row in rows if row.get("status") != "PASS"]
        forced_reason = "user real-preview evidence invalidates this model in current round" if model == "hivision_modnet" else ""
        complete = total == expected_total and not failed_samples
        model_summary[model] = {
            "status": "PASS" if total and passed == total and complete and not forced_reason else "FAIL",
            "requestedModel": model,
            "passedColorChecks": passed,
            "totalColorChecks": total,
            "expectedColorChecks": expected_total,
            "failedSampleCount": len(failed_samples),
            "reason": forced_reason or ("all strict zoom/color checks passed" if total and passed == total and complete else "one or more samples/colors failed or did not complete"),
        }
    candidates = [name for name, item in model_summary.items() if item["status"] == "PASS"]
    selected = candidates[0] if candidates else ""
    payload = {
        "status": "PASS" if selected else "FAIL",
        "generatedAt": now(),
        "samples": [str(path) for path in sources],
        "visualReferenceSkippedAsUploadSource": skipped_sources,
        "modelSummary": model_summary,
        "selectedModel": selected,
        "selectionReason": "first Hivision internal model with all strict zoom/color checks passing and not invalidated by user evidence" if selected else "all Hivision internal models failed strict local checks",
        "rows": model_rows,
    }
    contact = make_contact_sheet([row for rows in model_rows.values() for row in rows], MODEL_AB_DIR / "model-switch-contact-sheet.jpg")
    payload["contactSheet"] = contact
    write_json(MODEL_AB_DIR / "model-switch-report.json", payload)
    lines = [
        "# Hivision Model Switch Report",
        "",
        f"- Status: `{payload['status']}`",
        f"- Generated at: `{payload['generatedAt']}`",
        f"- Contact sheet: `{contact}`",
        f"- Final selected model: `{selected or 'NONE'}`",
        f"- Selection reason: {payload['selectionReason']}",
        "",
        "| model | status | checks | reason |",
        "| --- | --- | ---: | --- |",
    ]
    for model, item in model_summary.items():
        lines.append(f"| {model} | {item['status']} | {item['passedColorChecks']}/{item['totalColorChecks']} | {item['reason']} |")
    write_md(MODEL_AB_DIR / "model-switch-report.md", lines)
    return payload


def external_engine_report(model_ab: dict[str, Any]) -> dict[str, Any]:
    skipped = bool(model_ab.get("selectedModel"))
    payload = {
        "status": "SKIPPED" if skipped else "BLOCKED",
        "generatedAt": now(),
        "reason": "Hivision internal model passed strict local A/B; external engines were not mixed into the main chain." if skipped else "Hivision internal models did not pass; external engine installation must be reviewed before changing main chain.",
        "engines": [
            {"engine": "rembg", "model": "u2net_human_seg", "status": "available-adapter"},
            {"engine": "rembg", "model": "isnet-general-use", "status": "available-adapter"},
            {"engine": "MODNet", "model": "external", "status": "adapter-present-not-installed"},
            {"engine": "BiRefNet", "model": "external", "status": "adapter-present-not-installed"},
        ],
    }
    write_json(EXTERNAL_AB_DIR / "external-engine-report.json", payload)
    write_md(EXTERNAL_AB_DIR / "external-engine-report.md", [
        "# External Engine Report",
        "",
        f"- Status: `{payload['status']}`",
        f"- Generated at: `{payload['generatedAt']}`",
        f"- Reason: {payload['reason']}",
        "",
        "| engine | model | status |",
        "| --- | --- | --- |",
        *[f"| {row['engine']} | {row['model']} | {row['status']} |" for row in payload["engines"]],
    ])
    return payload


def screenshot_evidence() -> dict[str, Any]:
    rows = []
    evidence_dir = ARTIFACT_DIR / "error-screenshots"
    for idx, path in enumerate(ERROR_SCREENSHOTS, 1):
        row = {
            "label": f"error_screenshot_{idx:02d}",
            "path": str(path),
            "exists": path.exists(),
            "failureTypes": [
                "ear-side old background",
                "neck-side gray block",
                "hair edge blue/gray/white halo",
                "shoulder or clothing edge defect",
                "script PASS but visual FAIL evidence",
            ],
        }
        if path.exists():
            img = Image.open(path).convert("RGB")
            row["size"] = list(img.size)
            target = evidence_dir / f"{row['label']}_overview.jpg"
            target.parent.mkdir(parents=True, exist_ok=True)
            overview = img.copy()
            overview.thumbnail((900, 900), Image.Resampling.LANCZOS)
            overview.save(target, quality=92)
            row["overview"] = str(target)
            w, h = img.size
            row["zooms"] = {
                "left-edge": save_zoom(path, evidence_dir / f"{row['label']}_left_edge.jpg", (0, h * 0.25, w * 0.35, h * 0.85), "left-edge evidence", False, "historical visual failure evidence"),
                "right-edge": save_zoom(path, evidence_dir / f"{row['label']}_right_edge.jpg", (w * 0.65, h * 0.25, w, h * 0.85), "right-edge evidence", False, "historical visual failure evidence"),
                "bottom": save_zoom(path, evidence_dir / f"{row['label']}_bottom.jpg", (0, h * 0.70, w, h), "bottom evidence", False, "historical visual failure evidence"),
            }
        rows.append(row)
    payload = {
        "status": "FAIL_EVIDENCE_RECORDED",
        "generatedAt": now(),
        "total": len(rows),
        "existing": sum(1 for row in rows if row["exists"]),
        "samples": rows,
    }
    write_json(DEBUG_DIR / "error-samples-report.json", payload)
    write_md(REPORT_ROOT / "error-samples-report.md", [
        "# Error Samples Report",
        "",
        f"- Status: `{payload['status']}`",
        f"- Existing screenshots: {payload['existing']}/{payload['total']}",
        "- These screenshots are treated as visual failure evidence, not raw upload sources.",
        "",
        *[f"- {row['label']}: exists={row['exists']} path=`{row['path']}` failures={', '.join(row['failureTypes'])}" for row in rows],
    ])
    return payload


def run_backend_sample(base_url: str, sample: Path, label: str) -> dict[str, Any]:
    safety = seed_passed_content_safety(sample, "id_photo")
    with sample.open("rb") as fh:
        prep = request_json(
            "POST",
            full_url(base_url, "/api/id-photo/prepare"),
            files={"image": (sample.name, fh, "image/jpeg")},
            data={
                "purpose": "official_id_photo",
                "specId": "one-inch",
                "widthPx": "295",
                "heightPx": "413",
                "mode": "official",
                "composition": "head_shoulder",
                "outfit": "preserve_original",
                "securityCheckId": safety["securityCheckId"],
            },
            headers=_auth_headers(),
            timeout=180,
        )
    row: dict[str, Any] = {"label": label, "source": str(sample), "prepare": prep, "colors": {}, "status": "FAIL"}
    prepared_id = (prep.get("data") or {}).get("preparedId")
    if not prep.get("ok") or not prepared_id:
        return row
    prepare_data = prep.get("data") or {}
    row["alphaDebug"] = save_alpha_debug_artifacts(base_url, label, sample, prepare_data)
    request_ids: set[str] = set()
    for color, hex_color in COLORS.items():
        comp = request_json(
            "POST",
            full_url(base_url, "/api/id-photo/compose"),
            data={"preparedId": prepared_id, "bgColor": color, "bgColorName": color, "outputType": "jpg"},
            headers=_auth_headers(),
            timeout=180,
        )
        data = comp.get("data") or {}
        image_url = data.get("previewUrl") or data.get("finalImageUrl") or data.get("imageUrl") or ""
        request_ids.add(data.get("requestId") or "")
        out_path = ARTIFACT_DIR / "backend" / label / f"{color}.jpg"
        dl = {"ok": False}
        if image_url:
            try:
                response = requests.get(full_url(base_url, image_url), timeout=60)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(response.content)
                dl = {
                    "ok": response.status_code == 200,
                    "statusCode": response.status_code,
                    "path": str(out_path),
                    "size": list(Image.open(out_path).size),
                    "sha256": sha256_file(out_path),
                }
            except Exception as exc:
                dl = {"ok": False, "error": str(exc), "path": str(out_path)}
        quality_report = ((data.get("quality") or {}).get("qualityReport") or {})
        passed, reasons = quality_strict_pass({"qualityReport": quality_report}, color)
        zooms = {}
        if dl.get("ok") and out_path.exists():
            metrics = quality_report.get("metrics") or {}
            try:
                output_size = Image.open(out_path).size
                boxes = zoom_boxes(metrics, output_size)
                zdir = ARTIFACT_DIR / "backend" / label / "zooms" / color
                for zlabel, box in boxes.items():
                    zooms[zlabel] = save_zoom(
                        out_path,
                        zdir / f"{zlabel}.jpg",
                        box,
                        f"{label} {color} {zlabel}",
                        passed,
                        "; ".join(reasons) if reasons else "strict local zoom metrics clean",
                    )
            except Exception as exc:
                zooms["error"] = {"error": str(exc)}
        parsed = urlparse(image_url)
        row["colors"][color] = {
            "compose": comp,
            "download": dl,
            "previewUrl": image_url,
            "downloadUrl": data.get("downloadUrl") or "",
            "requestId": data.get("requestId") or "",
            "hasCacheBust": bool(parsed.query),
            "previewEqualsDownload": bool(image_url and image_url == (data.get("downloadUrl") or image_url)),
            "strictPass": passed,
            "strictReasons": reasons,
            "zooms": zooms,
        }
    row["requestIds"] = sorted(x for x in request_ids if x)
    row["status"] = "PASS" if row["colors"] and all(item["download"].get("ok") and item["strictPass"] and item["hasCacheBust"] for item in row["colors"].values()) else "FAIL"
    return row


def user_samples_report(base_url: str, limit: int) -> dict[str, Any]:
    samples, skipped = select_single_face_sources(CORRECT_SAMPLES + DESKTOP_SAMPLES, limit)
    rows = [run_backend_sample(base_url, sample, f"user_sample_{idx:02d}") for idx, sample in enumerate(samples, 1)]
    contact = make_contact_sheet([
        {"sample": row["label"], "source": row["source"], "actualModel": "backend", "colors": {c: {"path": item["download"].get("path")} for c, item in row["colors"].items()}}
        for row in rows
    ], REPORT_ROOT / "user-correct-samples-contact-sheet.jpg")
    payload = {
        "status": "PASS" if rows and all(row["status"] == "PASS" for row in rows) else "FAIL",
        "generatedAt": now(),
        "baseUrl": base_url,
        "sampleCount": len(rows),
        "visualReferenceSkippedAsUploadSource": skipped,
        "contactSheet": contact,
        "samples": rows,
    }
    write_json(DEBUG_DIR / "user-correct-samples-report.json", payload)
    write_md(REPORT_ROOT / "user-correct-samples-report.md", [
        "# User Correct Samples Report",
        "",
        f"- Status: `{payload['status']}`",
        f"- Samples: {len(rows)}",
        f"- Contact sheet: `{contact}`",
        "",
        *[f"- {row['label']}: {row['status']} requestIds={row.get('requestIds')}" for row in rows],
    ])
    return payload


def download_random_samples(count: int) -> tuple[list[Path], bool, list[dict[str, Any]]]:
    target_dir = ARTIFACT_DIR / "random-source"
    target_dir.mkdir(parents=True, exist_ok=True)
    skipped: list[dict[str, Any]] = []
    selected: list[Path] = []
    network_used = False
    headers = {
        "User-Agent": "Mozilla/5.0 id-photo-final-fix-verifier/1.0",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    def accept_candidate(path: Path, source_url: str, gender: str = "unknown", source_kind: str = "network") -> bool:
        try:
            face = detect_face(path)
            image_type = classify_image_type(path.read_bytes())
            img = Image.open(path)
            w, h = img.size
            box = face.get("faceBox") or {}
            fh = float(box.get("height") or 0)
            fw = float(box.get("width") or 0)
            fx = float(box.get("x") or 0)
            fy = float(box.get("y") or 0)
            face_h_ratio = fh / max(1, h)
            face_w_ratio = fw / max(1, w)
            face_center_y = (fy + fh * 0.5) / max(1, h)
            face_center_x = (fx + fw * 0.5) / max(1, w)
            below_face_ratio = (h - (fy + fh)) / max(1, h)
            top_margin_ratio = fy / max(1, h)
            rgb_small = np.asarray(img.convert("RGB").resize((160, 160), Image.Resampling.BILINEAR), dtype=np.uint8)
            hsv = cv2.cvtColor(rgb_small, cv2.COLOR_RGB2HSV)
            sat_mean = float(np.mean(hsv[:, :, 1]))
            rg = np.abs(rgb_small[:, :, 0].astype("float32") - rgb_small[:, :, 1].astype("float32"))
            yb = np.abs(0.5 * (rgb_small[:, :, 0].astype("float32") + rgb_small[:, :, 1].astype("float32")) - rgb_small[:, :, 2].astype("float32"))
            colorfulness = float(np.sqrt(np.var(rg) + np.var(yb)) + 0.3 * np.sqrt(np.mean(rg) ** 2 + np.mean(yb) ** 2))
            landmarks = face.get("landmarks") or {}
            right_eye = landmarks.get("rightEye") or {}
            left_eye = landmarks.get("leftEye") or {}
            nose = landmarks.get("nose") or {}
            mouth = landmarks.get("mouth") or {}
            eye_span = abs(float(left_eye.get("x") or 0) - float(right_eye.get("x") or 0))
            eye_y_delta = abs(float(left_eye.get("y") or 0) - float(right_eye.get("y") or 0)) / max(1.0, fw)
            eye_span_ratio = eye_span / max(1.0, fw)
            eye_mid_x = (float(left_eye.get("x") or 0) + float(right_eye.get("x") or 0)) * 0.5
            nose_offset = abs(float(nose.get("x") or 0) - eye_mid_x) / max(1.0, eye_span)
            mouth_offset = abs(float(mouth.get("x") or 0) - eye_mid_x) / max(1.0, eye_span)
            front_face_ok = (
                eye_span > 0
                and 0.22 <= eye_span_ratio <= 0.62
                and eye_y_delta <= 0.10
                and nose_offset <= 0.42
                and mouth_offset <= 0.48
            )
            geometry_reasons: list[str] = []
            if w < 360 or h < 480:
                geometry_reasons.append("image-too-small-for-id-photo-positive-sample")
            if sat_mean < 22.0 and colorfulness < 24.0:
                geometry_reasons.append("not-natural-color-real-person-photo")
            if not front_face_ok:
                geometry_reasons.append("face-landmarks-not-front-facing")
            if not (0.14 <= face_h_ratio <= 0.52):
                geometry_reasons.append("face-height-not-head-shoulder-framing")
            if not (0.12 <= face_w_ratio <= 0.54):
                geometry_reasons.append("face-width-not-head-shoulder-framing")
            if not (0.22 <= face_center_y <= 0.62):
                geometry_reasons.append("face-center-y-not-front-id-photo-range")
            if not (0.24 <= face_center_x <= 0.76):
                geometry_reasons.append("face-center-x-not-front-id-photo-range")
            if below_face_ratio < 0.20:
                geometry_reasons.append("no-visible-neck-shoulder-chest-below-face")
            if not (0.02 <= top_margin_ratio <= 0.45):
                geometry_reasons.append("top-margin-not-id-photo-source-range")
            geometry_ok = not geometry_reasons
            geometry = {
                "width": w,
                "height": h,
                "faceHeightRatio": round(face_h_ratio, 4),
                "faceWidthRatio": round(face_w_ratio, 4),
                "faceCenterY": round(face_center_y, 4),
                "faceCenterX": round(face_center_x, 4),
                "belowFaceRatio": round(below_face_ratio, 4),
                "topMarginRatio": round(top_margin_ratio, 4),
                "saturationMean": round(sat_mean, 4),
                "colorfulness": round(colorfulness, 4),
                "eyeSpanRatio": round(eye_span_ratio, 4),
                "eyeYDeltaRatio": round(eye_y_delta, 4),
                "noseOffsetRatio": round(nose_offset, 4),
                "mouthOffsetRatio": round(mouth_offset, 4),
                "frontFaceOk": front_face_ok,
                "geometryOk": geometry_ok,
                "geometryReasons": geometry_reasons,
            }
            ok = (
                face.get("success")
                and int(face.get("faceCount") or 0) == 1
                and float(face.get("confidence") or 0) >= 0.60
                and image_type.get("imageType") == "real_person"
                and image_type.get("realPerson") is True
                and geometry_ok
            )
            if ok:
                selected.append(path)
                return True
            skipped.append({
                "url": source_url,
                "path": str(path),
                "gender": gender,
                "sourceKind": source_kind,
                "reason": "candidate-not-single-front-real-person-with-visible-neck-shoulder",
                "face": face,
                "imageType": image_type,
                "geometry": geometry,
                "geometryOk": geometry_ok,
                "size": [w, h],
            })
            return False
        except Exception as exc:
            skipped.append({"url": source_url, "path": str(path), "sourceKind": source_kind, "reason": "candidate-error", "error": str(exc)})
            return False

    def save_candidate(content: bytes, suffix: str, index: int, source_name: str) -> Path:
        path = target_dir / f"random_{index:03d}_{source_name}{suffix}"
        try:
            image = ImageOps.exif_transpose(Image.open(BytesIO(content))).convert("RGB")
            image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
            path = path.with_suffix(".jpg")
            image.save(path, quality=94)
        except Exception:
            path.write_bytes(content)
        return path

    attempts = 0
    for index in range(max(count * 3, 18)):
        if len(selected) >= count:
            break
        attempts += 1
        url = f"https://thispersondoesnotexist.com/?id_photo_verify={int(time.time() * 1000)}_{index}"
        try:
            response = requests.get(url, headers=headers, timeout=18)
            if response.status_code == 200 and len(response.content) > 5000:
                network_used = True
                path = save_candidate(response.content, ".jpg", index, "tpdne")
                accept_candidate(path, url)
        except Exception as exc:
            skipped.append({"url": url, "reason": "network-fetch-error", "error": str(exc)})
        time.sleep(0.08)

    while len(selected) < count and attempts < count * 6 + 30:
        attempts += 1
        try:
            api_url = "https://randomuser.me/api/?results=1&inc=gender,picture&noinfo"
            response = requests.get(api_url, headers=headers, timeout=18)
            data = response.json()
            item = (data.get("results") or [{}])[0]
            pic_url = ((item.get("picture") or {}).get("large") or "")
            if not pic_url:
                skipped.append({"url": api_url, "reason": "randomuser-no-picture"})
                continue
            pic = requests.get(pic_url, headers=headers, timeout=18)
            if pic.status_code == 200 and len(pic.content) > 1000:
                network_used = True
                path = save_candidate(pic.content, ".jpg", attempts, "randomuser")
                accept_candidate(path, pic_url, item.get("gender") or "unknown")
        except Exception as exc:
            skipped.append({"url": "https://randomuser.me/api/", "reason": "network-fetch-error", "error": str(exc)})

    if len(selected) < count:
        fallback_roots = [
            *CORRECT_SAMPLES,
            *DESKTOP_SAMPLES,
            ROOT / "reports" / "id-photo-current-fail-fix" / "artifacts" / "random-source",
            ROOT / "reports" / "antigravity-id-photo-takeover" / "artifacts" / "random-source",
            ROOT / "reports" / "id-photo-samples" / "source",
        ]
        skipped.append({
            "reason": "NETWORK_ELIGIBLE_RANDOM_UNDER_REQUESTED_COUNT",
            "requested": count,
            "networkSelected": len(selected),
            "fallbackRoots": [str(item) for item in fallback_roots],
        })
        selected_keys = {str(item.resolve()) for item in selected if item.exists()}
        fallback_index = 0
        for candidate in collect_existing(fallback_roots, limit=0):
            if len(selected) >= count:
                break
            try:
                key = str(candidate.resolve())
            except Exception:
                key = str(candidate)
            if key in selected_keys:
                continue
            fallback_index += 1
            copied = copy_source_sample(candidate, target_dir, f"fallback_{fallback_index:03d}_{candidate.stem}")
            if accept_candidate(copied, f"fallback:{candidate}", source_kind="NETWORK_FALLBACK"):
                selected_keys.add(str(copied.resolve()))

    if selected:
        return selected[:count], network_used, skipped

    fallback = collect_existing([
        ROOT / "reports" / "id-photo-samples" / "source",
        ROOT / "reports" / "id-photo-current-fail-fix" / "artifacts" / "random-source",
        ROOT / "reports" / "antigravity-id-photo-takeover" / "artifacts" / "random-source",
    ], limit=count)
    skipped.append({"reason": "NETWORK_FALLBACK", "fallbackCount": len(fallback)})
    return fallback, False, skipped


def generalization_report(base_url: str, count: int) -> dict[str, Any]:
    samples, network, skipped = download_random_samples(count)
    rows = [run_backend_sample(base_url, sample, f"random_{idx:02d}") for idx, sample in enumerate(samples, 1)]
    passed = sum(1 for row in rows if row["status"] == "PASS")
    rate = round(passed / max(1, len(rows)) * 100, 2)
    contact = make_contact_sheet([
        {"sample": row["label"], "source": row["source"], "actualModel": "backend", "colors": {c: {"path": item["download"].get("path")} for c, item in row["colors"].items()}}
        for row in rows
    ], REPORT_ROOT / "generalization-contact-sheet.jpg")
    complete_count = len(rows) >= count
    payload = {
        "status": "PASS" if rows and complete_count and rate >= 95.0 else "FAIL",
        "generatedAt": now(),
        "baseUrl": base_url,
        "networkAccess": network,
        "requestedSampleCount": count,
        "sampleCount": len(rows),
        "completeRequestedCount": complete_count,
        "passed": passed,
        "passRate": rate,
        "contactSheet": contact,
        "skippedRandomCandidates": skipped,
        "samples": rows,
    }
    write_json(DEBUG_DIR / "generalization-report.json", payload)
    write_md(REPORT_ROOT / "generalization-report.md", [
        "# Generalization Report",
        "",
        f"- Status: `{payload['status']}`",
        f"- Network access: `{network}`",
        f"- Requested samples: `{count}`",
        f"- Samples: {passed}/{len(rows)} pass ({rate}%)",
        f"- Complete requested count: `{complete_count}`",
        f"- Contact sheet: `{contact}`",
        f"- Skipped random candidates: `{len(skipped)}`",
    ])
    return payload


def negative_samples_report(base_url: str) -> dict[str, Any]:
    cmd = ["node", "server/scripts/run_python.js", "server/scripts/verify_id_photo_negative_samples.py", "--base-url", base_url]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    source = LEGACY_REPORT_DIR / "negative-samples-report.json"
    payload = json.loads(source.read_text(encoding="utf-8")) if source.exists() else {"status": "FAIL", "reason": "missing negative source report"}
    payload["command"] = " ".join(cmd)
    payload["returncode"] = proc.returncode
    payload["outputTail"] = (proc.stdout or "")[-4000:]
    write_json(DEBUG_DIR / "negative-samples-report.json", payload)
    write_md(REPORT_ROOT / "negative-samples-report.md", [
        "# Negative Samples Report",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- False pass: `{payload.get('falsePass')}`",
        f"- Command return code: `{proc.returncode}`",
        "",
        "```text",
        payload["outputTail"],
        "```",
    ])
    return payload


def full_business_flow_report(base_url: str, run_command: bool) -> dict[str, Any]:
    if not run_command:
        payload = {"status": "SKIPPED", "reason": "caller disabled full command"}
    else:
        cmd = ["node", "server/scripts/run_python.js", "server/scripts/verify_id_photo_full_business_flow.py", "--base-url", base_url]
        proc = subprocess.run(cmd, cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3600)
        source = ROOT / "reports" / "final" / "full-business-flow-report.json"
        payload = json.loads(source.read_text(encoding="utf-8")) if source.exists() else {"status": "FAIL", "reason": "missing full business source report"}
        payload["command"] = " ".join(cmd)
        payload["returncode"] = proc.returncode
        payload["outputTail"] = (proc.stdout or "")[-5000:]
    write_json(DEBUG_DIR / "full-business-flow-regression.json", payload)
    write_md(REPORT_ROOT / "full-business-flow-regression.md", [
        "# Full Business Flow Regression",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Return code: `{payload.get('returncode')}`",
        "- Scope note: this command checks existing business flows; this script does not modify non-ID-photo pages.",
    ])
    return payload


def wechat_real_preview_report(browser: dict[str, Any] | None = None, chrome: dict[str, Any] | None = None, computer: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "status": "BLOCKED",
        "generatedAt": now(),
        "browser": browser or {"status": "NOT_RUN"},
        "chrome": chrome or {"status": "NOT_RUN"},
        "computerUse": computer or {"status": "NOT_RUN"},
        "reason": "WeChat DevTools UI automation requires an available plugin/browser surface and the DevTools window. Backend and file-based dynamic previews are still generated under artifacts.",
    }
    write_json(REPORT_ROOT / "wechat-real-preview-report.json", payload)
    write_md(REPORT_ROOT / "wechat-real-preview-report.md", [
        "# WeChat Real Preview Report",
        "",
        f"- Status: `{payload['status']}`",
        f"- Generated at: `{payload['generatedAt']}`",
        f"- Reason: {payload['reason']}",
        f"- Browser: `{payload['browser'].get('status')}`",
        f"- Chrome: `{payload['chrome'].get('status')}`",
        f"- Computer Use: `{payload['computerUse'].get('status')}`",
    ])
    return payload


def final_summary(parts: dict[str, Any]) -> dict[str, Any]:
    selected = ((parts.get("modelAb") or {}).get("selectedModel") or "")
    pass_conditions = {
        "legacyFailRecorded": (parts.get("legacyFail") or {}).get("status") == "FAIL",
        "runtimeAuditOk": bool((parts.get("runtime") or {}).get("health", {}).get("ok")),
        "cacheCleaned": (parts.get("cacheClean") or {}).get("status") == "PASS",
        "modelSelected": bool(selected),
        "userSamplesPass": (parts.get("userSamples") or {}).get("status") == "PASS",
        "generalizationPass": (parts.get("generalization") or {}).get("status") == "PASS",
        "negativePass": (parts.get("negative") or {}).get("status") == "PASS",
        "fullBusinessPass": (parts.get("fullBusiness") or {}).get("status") == "PASS",
        "wechatPreviewPass": (parts.get("wechat") or {}).get("status") == "PASS",
    }
    status = "PASS" if all(pass_conditions.values()) else "FAIL"
    blockers = [key for key, value in pass_conditions.items() if not value]
    payload = {
        "status": status,
        "generatedAt": now(),
        "selectedModel": selected,
        "passConditions": pass_conditions,
        "blockers": blockers,
        "parts": {key: value for key, value in parts.items() if key != "modelRows"},
    }
    write_json(REPORT_ROOT / "final-summary.json", payload)
    write_md(REPORT_ROOT / "final-summary.md", [
        "# Current ID-photo Fail Fix Final Summary",
        "",
        f"- Status: `{status}`",
        f"- Generated at: `{payload['generatedAt']}`",
        f"- Selected model: `{selected or 'NONE'}`",
        f"- Blockers: `{', '.join(blockers) if blockers else 'none'}`",
        "",
        "## Stop Conditions",
        *[f"- {key}: `{value}`" for key, value in pass_conditions.items()],
        "",
        "## Required Reports",
        f"- Runtime audit: `{REPORT_ROOT / 'runtime-chain-audit.md'}`",
        f"- Cache clean: `{REPORT_ROOT / 'cache-clean-report.md'}`",
        f"- Model A/B: `{MODEL_AB_DIR / 'model-switch-report.md'}`",
        f"- User samples: `{REPORT_ROOT / 'user-correct-samples-report.md'}`",
        f"- Error samples: `{REPORT_ROOT / 'error-samples-report.md'}`",
        f"- Zoom artifacts: `{ARTIFACT_DIR}`",
        f"- WeChat preview: `{REPORT_ROOT / 'wechat-real-preview-report.md'}`",
        f"- Generalization: `{REPORT_ROOT / 'generalization-report.md'}`",
        f"- Negative samples: `{REPORT_ROOT / 'negative-samples-report.md'}`",
        f"- Full business flow: `{REPORT_ROOT / 'full-business-flow-regression.md'}`",
    ])
    return payload


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", default="all", choices=["all", "fail-audit", "cache-clean", "model-ab", "user-samples", "error-samples", "generalization", "negative", "full-business", "finalize"])
    parser.add_argument("--sample-limit", type=int, default=3)
    parser.add_argument("--user-sample-limit", type=int, default=6)
    parser.add_argument("--random-count", type=int, default=30)
    parser.add_argument("--skip-full-business", action="store_true")
    args = parser.parse_args()

    if args.mode == "all":
        reset_report_dir()
    else:
        REPORT_ROOT.mkdir(parents=True, exist_ok=True)
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        ALPHA_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        MODEL_AB_DIR.mkdir(parents=True, exist_ok=True)
        MODEL_AB_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        EXTERNAL_AB_DIR.mkdir(parents=True, exist_ok=True)

    parts: dict[str, Any] = {}

    if args.mode in {"all", "fail-audit"}:
        parts["legacyFail"] = update_legacy_fail_summary()
        parts["runtime"] = runtime_audit(args.base_url)
    if args.mode in {"all", "cache-clean"}:
        parts["cacheClean"] = cache_clean_report()
    if args.mode in {"all", "model-ab"}:
        parts["modelAb"] = run_model_ab(args.sample_limit)
        parts["external"] = external_engine_report(parts["modelAb"])
    if args.mode in {"all", "error-samples"}:
        parts["errors"] = screenshot_evidence()
    if args.mode in {"all", "user-samples"}:
        parts["userSamples"] = user_samples_report(args.base_url, args.user_sample_limit)
    if args.mode in {"all", "generalization"}:
        parts["generalization"] = generalization_report(args.base_url, args.random_count)
    if args.mode in {"all", "negative"}:
        parts["negative"] = negative_samples_report(args.base_url)
    if args.mode in {"all", "full-business"}:
        parts["fullBusiness"] = full_business_flow_report(args.base_url, not args.skip_full_business)
    if args.mode in {"all", "finalize"}:
        parts["wechat"] = wechat_real_preview_report()
        summary = final_summary(parts)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary.get("status") == "PASS" else 1

    print(json.dumps(parts, ensure_ascii=False, indent=2)[:12000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
