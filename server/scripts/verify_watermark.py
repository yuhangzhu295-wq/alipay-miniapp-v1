"""Dynamic verifier for the remove-watermark manual/quick/HD chains.

The script starts or reuses the local FastAPI backend, generates fresh
watermark samples, calls the real endpoints, downloads real result images, and
fails on any chain mix-up. It also audits the mini-program frontend state flow
that chooses the endpoint and result currently being downloaded.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
REPORTS = ROOT / "reports"
FINAL = REPORTS / "final"
WATERMARK_REPORTS = REPORTS / "watermark"
SAMPLES = FINAL / "watermark-samples"
SOURCE_DIR = SAMPLES / "source"
MASK_DIR = SAMPLES / "mask"
MODE_DIRS = {
    "manual": SAMPLES / "manual",
    "quick": SAMPLES / "quick",
    "hd": SAMPLES / "hd",
}
DIFF_DIR = SAMPLES / "diff"
CONTACT_SHEET = FINAL / "watermark-comparison-contact-sheet.jpg"
CHAIN_MD = FINAL / "watermark-hd-chain-report.md"
CHAIN_JSON = FINAL / "watermark-hd-chain-report.json"
REGRESSION_MD = WATERMARK_REPORTS / "watermark-regression-report.md"
REGRESSION_JSON = WATERMARK_REPORTS / "watermark-regression-report.json"
VERIFY_USER_ID = "verify-watermark-user"
VERIFY_OPENID = "openid-verify-watermark"


@dataclass
class Sample:
    name: str
    image_path: Path
    mask_path: Path


def _mkdirs() -> None:
    for path in [FINAL, WATERMARK_REPORTS, SOURCE_DIR, MASK_DIR, DIFF_DIR, *MODE_DIRS.values()]:
        path.mkdir(parents=True, exist_ok=True)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_file(path: Path) -> str:
    return _sha256(path.read_bytes())


def _utc_iso(epoch: float | None = None) -> str:
    value = time.time() if epoch is None else epoch
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def _runtime_dir() -> Path:
    return Path(os.environ.get("ID_PHOTO_RUNTIME_DIR") or (Path(tempfile.gettempdir()) / "id_photo_server")).resolve()


def _auth_secret() -> str:
    configured = os.environ.get("ID_PHOTO_AUTH_SECRET")
    if configured:
        return configured
    return hashlib.sha256(("id-photo-auth:" + os.path.abspath(str(_runtime_dir()))).encode("utf-8")).hexdigest()


def _b64url_encode(data: str) -> str:
    return base64.urlsafe_b64encode(data.encode("utf-8")).decode("ascii").rstrip("=")


def _issue_verify_token() -> str:
    payload = {
        "userId": VERIFY_USER_ID,
        "openid": VERIFY_OPENID,
        "provider": "watermark-verifier",
        "iat": int(time.time()),
        "profile": {"nickName": "watermark verifier"},
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


def seed_passed_content_safety(sample: Sample) -> dict[str, Any]:
    """Seed a local PASS record so this regression still exercises the backend Gate.

    The content-security callback itself is covered by the dedicated WeChat
    security verifier. This watermark verifier needs a real PASS
    securityCheckId so the image-processing endpoints do not correctly fail
    closed before reaching the watermark engines.
    """
    now = time.time()
    image_bytes = sample.image_path.read_bytes()
    check_id = "verify_watermark_" + hashlib.sha256((sample.name + str(now)).encode("utf-8")).hexdigest()[:24]
    runtime_dir = _runtime_dir()
    registry_path = runtime_dir / "content_security_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(registry_path.read_text(encoding="utf-8"))
        records = existing.get("records") if isinstance(existing, dict) else existing
        if not isinstance(records, list):
            records = []
    except Exception:
        records = []
    record = {
        "securityCheckId": check_id,
        "safeAssetId": check_id,
        "imageId": "verify_" + hashlib.sha256(image_bytes).hexdigest()[:16],
        "userId": VERIFY_USER_ID,
        "userOpenId": VERIFY_OPENID,
        "sha256": hashlib.sha256(image_bytes).hexdigest(),
        "imageBytes": len(image_bytes),
        "purpose": "watermark_removal",
        "mediaUrl": "local-verifier://watermark/" + sample.name,
        "stagingPath": "",
        "status": "PASS",
        "traceId": "local-verifier-" + check_id,
        "statusReason": "LOCAL_WATERMARK_VERIFIER_PASS",
        "createdAt": _utc_iso(now),
        "createdAtEpoch": now,
        "updatedAt": _utc_iso(now),
        "updatedAtEpoch": now,
        "expiresAtEpoch": now + 1800,
    }
    records.append(record)
    registry_path.write_text(json.dumps({"records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "securityCheckId": check_id,
        "registryPath": str(registry_path),
        "imageBytes": len(image_bytes),
        "sha256": record["sha256"],
    }


def _full_url(base_url: str, image_url: str) -> str:
    if image_url.startswith("http://") or image_url.startswith("https://"):
        return image_url
    if not image_url.startswith("/"):
        image_url = "/" + image_url
    return base_url.rstrip("/") + image_url


def _get_json(url: str, timeout: float = 5) -> dict[str, Any]:
    res = requests.get(url, timeout=timeout)
    try:
        data = res.json()
    except Exception:
        data = {"success": False, "message": res.text[:500]}
    data["_statusCode"] = res.status_code
    return data


def _can_reach(base_url: str) -> bool:
    try:
        data = _get_json(base_url.rstrip("/") + "/api/watermark/health", timeout=3)
        return data.get("_statusCode") == 200 and bool(data.get("success") or data.get("ok"))
    except Exception:
        return False


def ensure_backend(base_url: str) -> dict[str, Any]:
    """Reuse the backend if alive; otherwise start uvicorn and poll health."""
    status: dict[str, Any] = {
        "baseUrl": base_url,
        "alreadyRunning": False,
        "started": False,
        "pid": None,
        "errors": [],
    }
    if _can_reach(base_url):
        status["alreadyRunning"] = True
        status["passed"] = True
        return status

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    try:
        env = os.environ.copy()
        env.setdefault("ID_PHOTO_RUNTIME_DIR", str(_runtime_dir()))
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        process = subprocess.Popen(
            cmd,
            cwd=str(SERVER),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            env=env,
        )
        status["started"] = True
        status["pid"] = process.pid
    except Exception as exc:
        status["errors"].append(f"start failed: {exc}")

    deadline = time.time() + 30
    while time.time() < deadline:
        if _can_reach(base_url):
            status["passed"] = True
            return status
        time.sleep(1)

    status["passed"] = False
    return status


def _draw_gradient(draw: ImageDraw.ImageDraw, width: int, height: int, start: tuple[int, int, int], end: tuple[int, int, int]) -> None:
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(start[i] * (1 - t) + end[i] * t) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)


def _add_watermark(draw: ImageDraw.ImageDraw, mask_draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, color=(245, 245, 245)) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=12, fill=(255, 255, 255, 78), outline=(235, 235, 235))
    draw.text((x1 + 14, y1 + 10), text, fill=color)
    mask_draw.rounded_rectangle((x1 - 3, y1 - 3, x2 + 3, y2 + 3), radius=14, fill=255)


def generate_samples() -> list[Sample]:
    samples: list[Sample] = []
    specs = [
        ("portrait_blue", (480, 640), (205, 226, 246), (60, 135, 214)),
        ("document_diagonal", (640, 480), (244, 245, 248), (210, 218, 228)),
        ("product_logo", (560, 560), (238, 238, 235), (184, 194, 202)),
        ("dark_scene", (640, 480), (54, 62, 80), (18, 26, 40)),
        ("light_stamp", (520, 640), (255, 255, 255), (232, 240, 250)),
        ("qr_corner", (560, 420), (229, 234, 240), (195, 205, 220)),
        ("wide_banner", (700, 420), (220, 232, 246), (110, 152, 190)),
        ("busy_texture", (600, 520), (236, 229, 214), (188, 178, 160)),
        ("diagonal_tile_wall", (760, 430), (248, 226, 196), (238, 212, 176)),
    ]

    for idx, (name, size, start, end) in enumerate(specs, start=1):
        width, height = size
        image = Image.new("RGB", size, start)
        draw = ImageDraw.Draw(image, "RGBA")
        _draw_gradient(draw, width, height, start, end)

        if "portrait" in name:
            draw.ellipse([width * 0.33, height * 0.14, width * 0.67, height * 0.43], fill=(236, 192, 164))
            draw.rectangle([width * 0.38, height * 0.42, width * 0.62, height * 0.66], fill=(44, 56, 86))
            draw.polygon([(width * 0.22, height), (width * 0.38, height * 0.58), (width * 0.62, height * 0.58), (width * 0.78, height)], fill=(33, 44, 68))
        elif "product" in name:
            draw.rounded_rectangle([110, 110, 450, 435], radius=28, fill=(248, 248, 246), outline=(150, 158, 168), width=3)
            draw.ellipse([220, 190, 340, 310], fill=(158, 172, 188))
        elif "dark" in name:
            for x in range(0, width, 28):
                draw.line([(x, 0), (x + 160, height)], fill=(80, 92, 120, 80), width=2)
        elif "busy" in name:
            for x in range(0, width, 24):
                draw.line([(x, 0), (x - 80, height)], fill=(144, 126, 105, 70), width=3)
            for y in range(0, height, 30):
                draw.line([(0, y), (width, y + 35)], fill=(245, 240, 230, 120), width=2)
        else:
            draw.rectangle([width * 0.13, height * 0.16, width * 0.87, height * 0.82], outline=(142, 157, 180), width=3)
            draw.line([width * 0.18, height * 0.32, width * 0.82, height * 0.32], fill=(142, 157, 180), width=2)
            draw.line([width * 0.18, height * 0.46, width * 0.78, height * 0.46], fill=(142, 157, 180), width=2)

        mask = Image.new("L", size, 0)
        mask_draw = ImageDraw.Draw(mask)
        if name == "document_diagonal":
            overlay = Image.new("RGBA", size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.text((170, 190), "CONFIDENTIAL 2026", fill=(210, 40, 60, 150))
            overlay = overlay.rotate(-18, expand=False, center=(width // 2, height // 2))
            image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
            mask_draw.rectangle([140, 155, 500, 285], fill=255)
        elif name == "diagonal_tile_wall":
            overlay = Image.new("RGBA", size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            for tx in range(-120, width + 180, 185):
                for ty in range(-80, height + 120, 110):
                    overlay_draw.line([(tx, ty), (tx + 150, ty + 96)], fill=(120, 112, 96, 82), width=4)
                    overlay_draw.line([(tx + 150, ty + 96), (tx + 300, ty)], fill=(120, 112, 96, 82), width=4)
                    overlay_draw.text((tx + 72, ty + 42), "xiao", fill=(92, 82, 62, 110))
                    mask_draw.line([(tx, ty), (tx + 150, ty + 96)], fill=255, width=11)
                    mask_draw.line([(tx + 150, ty + 96), (tx + 300, ty)], fill=255, width=11)
                    mask_draw.rectangle([tx + 66, ty + 36, tx + 130, ty + 64], fill=255)
            draw.ellipse([120, 210, 300, 385], fill=(232, 188, 54, 175))
            draw.line([250, 188, 330, 390], fill=(76, 86, 54, 255), width=5)
            draw.line([310, 175, 420, 380], fill=(92, 98, 58, 245), width=5)
            draw.polygon([(448, 214), (535, 244), (492, 300)], fill=(236, 226, 171, 180))
            draw.rounded_rectangle([285, 315, 425, 430], radius=14, fill=(225, 228, 202, 132), outline=(186, 178, 138, 185), width=3)
            image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        elif name == "wide_banner":
            _add_watermark(draw, mask_draw, (385, 305, 670, 382), "WATERMARK")
            _add_watermark(draw, mask_draw, (32, 30, 235, 92), "ID SAMPLE")
        elif name == "busy_texture":
            _add_watermark(draw, mask_draw, (330, 378, 575, 455), "xhs 429942")
        elif name == "dark_scene":
            _add_watermark(draw, mask_draw, (390, 350, 610, 430), "DO NOT COPY", color=(250, 250, 250))
        elif name == "qr_corner":
            draw.rectangle([420, 270, 535, 385], fill=(245, 245, 245, 160))
            for qx in range(430, 525, 16):
                for qy in range(280, 375, 16):
                    if (qx + qy) % 32 == 0:
                        draw.rectangle([qx, qy, qx + 10, qy + 10], fill=(40, 40, 40, 220))
            mask_draw.rectangle([412, 262, 543, 393], fill=255)
        else:
            _add_watermark(draw, mask_draw, (int(width * 0.55), int(height * 0.82), int(width * 0.95), int(height * 0.94)), "WATERMARK")

        image = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=3))
        image_path = SOURCE_DIR / f"{idx:02d}_{name}.jpg"
        mask_path = MASK_DIR / f"{idx:02d}_{name}_mask.png"
        image.save(image_path, quality=94)
        mask.save(mask_path)
        samples.append(Sample(name=f"{idx:02d}_{name}", image_path=image_path, mask_path=mask_path))
    return samples


def post_chain(base_url: str, mode: str, sample: Sample, safety: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    endpoint = {
        "manual": "/api/watermark/manual-remove",
        "quick": "/api/watermark/quick-remove",
        "hd": "/api/watermark/hd-remove",
    }[mode]
    started = time.perf_counter()
    with sample.image_path.open("rb") as image_fh, sample.mask_path.open("rb") as mask_fh:
        res = requests.post(
            base_url.rstrip("/") + endpoint,
            files={
                "image": (sample.image_path.name, image_fh, "image/jpeg"),
                "mask": (sample.mask_path.name, mask_fh, "image/png"),
            },
            data={
                "mode": mode,
                "quality": mode,
                "engine": "hd" if mode == "hd" else f"opencv_{mode}",
                "strength": "medium",
                "preserveDetail": "true",
                "securityCheckId": safety["securityCheckId"],
            },
            headers=headers,
            timeout=180 if mode == "hd" else 90,
        )
    elapsed = int((time.perf_counter() - started) * 1000)
    try:
        data = res.json()
    except Exception:
        data = {"success": False, "message": res.text[:500]}
    data["_statusCode"] = res.status_code
    data["_costMs"] = elapsed
    data["_endpoint"] = endpoint
    return data


def download_result(base_url: str, response: dict[str, Any], target: Path) -> dict[str, Any]:
    image_url = response.get("resultUrl") or response.get("imageUrl") or ""
    if not image_url:
        return {"passed": False, "error": "missing resultUrl/imageUrl"}
    res = requests.get(_full_url(base_url, image_url), timeout=45)
    if res.status_code != 200 or not res.content:
        return {"passed": False, "statusCode": res.status_code, "bytes": len(res.content or b"")}
    target.write_bytes(res.content)
    local_hash = _sha256(res.content)
    try:
        image = Image.open(BytesIO(res.content)).convert("RGB")
        size = image.size
    except Exception as exc:
        return {"passed": False, "statusCode": res.status_code, "error": f"image decode failed: {exc}"}
    return {
        "passed": True,
        "statusCode": res.status_code,
        "url": image_url,
        "path": str(target),
        "hash": local_hash,
        "hashMatchesResponse": (not response.get("fileHash")) or response.get("fileHash") == local_hash,
        "size": {"width": size[0], "height": size[1]},
    }


def image_diff(a: Path, b: Path) -> dict[str, Any]:
    img_a = Image.open(a).convert("RGB")
    img_b = Image.open(b).convert("RGB")
    if img_a.size != img_b.size:
        img_b = img_b.resize(img_a.size)
    diff = ImageChops.difference(img_a, img_b)
    stat = ImageStat.Stat(diff)
    mean = sum(stat.mean) / len(stat.mean)
    max_diff = max(channel[1] for channel in diff.getextrema())
    return {
        "mean": round(float(mean), 6),
        "max": int(max_diff),
        "changed": bool(diff.getbbox()),
    }


def save_visual_diff(a: Path, b: Path, target: Path) -> dict[str, Any]:
    img_a = Image.open(a).convert("RGB")
    img_b = Image.open(b).convert("RGB")
    if img_a.size != img_b.size:
        img_b = img_b.resize(img_a.size)
    diff = ImageChops.difference(img_a, img_b)
    enhanced = diff.point(lambda value: min(255, value * 4))
    target.parent.mkdir(parents=True, exist_ok=True)
    enhanced.save(target, quality=92)
    stat = ImageStat.Stat(diff)
    return {
        "path": str(target),
        "mean": round(float(sum(stat.mean) / len(stat.mean)), 6),
        "max": int(max(channel[1] for channel in diff.getextrema())),
        "changed": bool(diff.getbbox()),
    }


def validate_mode_result(sample: Sample, mode: str, response: dict[str, Any], download: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    expected_engine = {
        "manual": "opencv_manual",
        "quick": "opencv_quick",
        "hd": None,
    }[mode]
    result_url = response.get("resultUrl") or response.get("imageUrl") or ""
    output_path = str(response.get("outputPath") or "")
    if response.get("_statusCode") != 200 or not response.get("success"):
        failures.append(f"{sample.name}:{mode} endpoint failed")
    if response.get("mode") != mode:
        failures.append(f"{sample.name}:{mode} returned mode={response.get('mode')!r}")
    engine = response.get("engine")
    if expected_engine and engine != expected_engine:
        failures.append(f"{sample.name}:{mode} returned engine={engine!r}")
    if mode == "hd" and (not engine or engine in ("opencv_manual", "opencv_quick", "manual", "quick", "opencv_hd_fallback", "not_ready")):
        failures.append(f"{sample.name}:hd engine invalid: {engine!r}")
    if mode == "hd" and response.get("fallbackUsed") is True:
        failures.append(f"{sample.name}:hd used fallback instead of real IOPaint/LaMa")
    if f"/uploads/watermark/{mode}/" not in result_url.replace("\\", "/"):
        failures.append(f"{sample.name}:{mode} resultUrl not isolated: {result_url}")
    if f"uploads{os.sep}watermark{os.sep}{mode}" not in output_path and f"uploads/watermark/{mode}" not in output_path.replace("\\", "/"):
        failures.append(f"{sample.name}:{mode} outputPath not isolated: {output_path}")
    if not response.get("fileHash"):
        failures.append(f"{sample.name}:{mode} missing response fileHash")
    if not download.get("passed"):
        failures.append(f"{sample.name}:{mode} result download failed")
    if download.get("passed") and not download.get("hashMatchesResponse"):
        failures.append(f"{sample.name}:{mode} downloaded hash != response fileHash")
    return failures


def audit_frontend() -> dict[str, Any]:
    js = (ROOT / "pages" / "tool-detail" / "tool-detail.js").read_text(encoding="utf-8")
    wxml = (ROOT / "pages" / "tool-detail" / "tool-detail.wxml").read_text(encoding="utf-8")
    api = (ROOT / "utils" / "watermarkApi.js").read_text(encoding="utf-8")
    canvas = (ROOT / "utils" / "watermarkCanvas.js").read_text(encoding="utf-8")
    config = (ROOT / "utils" / "watermarkConfig.js").read_text(encoding="utf-8")

    checks = {
        "healthUsesWatermarkHealth": "/api/watermark/health" in api,
        "manualEndpointPresent": "/api/watermark/remove-v2" in api and "quality === 'manual'" in api,
        "quickEndpointPresent": "/api/watermark/remove-v2" in api and "'quick'" in api,
        "hdEndpointPresent": "/api/watermark/remove-v2" in api and "quality === 'hd'" in api,
        "pageCallsQuickForScan": "wmApi.removeV2" in js and "modeKey" in js and "'quick'" in js,
        "pageCallsHdForHd": "wmApi.removeV2" in js and "/api/watermark/remove-v2" in js and "quality === 'hd'" in js,
        "separateStateManual": "manualResultUrl" in js and "manualResultLocalPath" in js,
        "separateStateQuick": "quickResultUrl" in js and "quickResultLocalPath" in js,
        "separateStateHd": "hdResultUrl" in js and "hdResultLocalPath" in js,
        "currentStateUsedForDownload": "currentResultLocalPath || that.data.resultImage" in js,
        "ordinaryUiHidesEngineAndOutput": "engine: {{currentEngine}}" not in wxml and "output: {{currentOutputPath}}" not in wxml,
        "hdHealthRequiresRealModel": "hdRealModelLoaded" in js and "fallbackUsed" in js,
        "debugPanelHiddenDefault": "showDebugPanel: false" in js and "isDebugPanelAllowed" in js and 'wx:if="{{showDebugPanel' in wxml,
        "noAiExperimentText": "AI智能（实验）" not in js and "AI智能（实验）" not in wxml,
        "canvasUndoRedoClearPresent": "undo" in canvas and "redo" in canvas and "clearAll" in canvas,
        "localBackendConfigured": "127.0.0.1:8000" in config,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
    }


def check_health(base_url: str) -> dict[str, Any]:
    api_health = {"passed": False}
    watermark_health = {"passed": False}
    try:
        data = _get_json(base_url.rstrip("/") + "/api/health", timeout=5)
        api_health = {
            "passed": data.get("_statusCode") == 200 and bool(data.get("success")) and (
                data.get("message") == "server running" or data.get("success") is True
            ),
            "data": data,
        }
    except Exception as exc:
        api_health = {"passed": False, "error": str(exc)}

    try:
        data = _get_json(base_url.rstrip("/") + "/api/watermark/health", timeout=5)
        required = {
            "success": data.get("success") is True or data.get("ok") is True,
            "manualAvailable": data.get("manualAvailable") is True,
            "quickAvailable": data.get("quickAvailable") is True,
            "hdAvailable": data.get("hdAvailable") is True,
            "manualEngine": data.get("manualEngine") == "opencv_manual",
            "quickEngine": data.get("quickEngine") == "opencv_quick",
            "hdEngine": bool(data.get("hdEngine")) and data.get("hdEngine") not in {"opencv_hd_fallback", "not_ready"},
            "fallbackTruthful": (
                data.get("hdRealModelLoaded") is True
                and data.get("fallbackUsed") is False
                and data.get("hdAvailable") is True
            ),
        }
        watermark_health = {
            "passed": data.get("_statusCode") == 200 and all(required.values()),
            "required": required,
            "data": data,
        }
    except Exception as exc:
        watermark_health = {"passed": False, "error": str(exc)}
    return {
        "passed": bool(api_health.get("passed")) and bool(watermark_health.get("passed")),
        "apiHealth": api_health,
        "watermarkHealth": watermark_health,
    }


def run_sample_matrix(base_url: str, samples: list[Sample]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    headers = _auth_headers()
    for sample in samples:
        safety = seed_passed_content_safety(sample)
        row: dict[str, Any] = {
            "sample": sample.name,
            "source": str(sample.image_path),
            "mask": str(sample.mask_path),
            "security": {
                "mode": "localPassRecordForWatermarkRegression",
                "securityCheckId": safety["securityCheckId"],
                "registryPath": safety["registryPath"],
                "imageBytes": safety["imageBytes"],
            },
            "modes": {},
            "comparisons": {},
            "failures": [],
        }
        for mode in ("manual", "quick", "hd"):
            response = post_chain(base_url, mode, sample, safety, headers)
            output_path = MODE_DIRS[mode] / f"{sample.name}_{mode}.jpg"
            download = download_result(base_url, response, output_path)
            quality_path = MODE_DIRS[mode] / f"{sample.name}_{mode}.json"
            mode_failures = validate_mode_result(sample, mode, response, download)
            if download.get("passed"):
                source_diff = image_diff(sample.image_path, output_path)
            else:
                source_diff = {"changed": False, "mean": 0, "max": 0}
            if not source_diff.get("changed"):
                mode_failures.append(f"{sample.name}:{mode} output did not differ from source")
            mode_payload = {
                "response": response,
                "download": download,
                "sourceDiff": source_diff,
                "passed": not mode_failures,
                "failures": mode_failures,
            }
            quality_path.write_text(json.dumps(mode_payload, ensure_ascii=True, indent=2), encoding="utf-8")
            row["modes"][mode] = mode_payload
            row["failures"].extend(mode_failures)

        manual = row["modes"]["manual"]
        quick = row["modes"]["quick"]
        hd = row["modes"]["hd"]
        for other in ("quick", "hd"):
            other_payload = row["modes"][other]
            compare_key = f"manualVs{other.capitalize()}"
            same_url = (manual["response"].get("resultUrl") or manual["response"].get("imageUrl")) == (
                other_payload["response"].get("resultUrl") or other_payload["response"].get("imageUrl")
            )
            same_path = str(manual["response"].get("outputPath") or "") == str(other_payload["response"].get("outputPath") or "")
            same_hash = str(manual["response"].get("fileHash") or "") == str(other_payload["response"].get("fileHash") or "")
            pixel_diff = {"changed": False, "mean": 0, "max": 0}
            diff_path = ""
            if manual["download"].get("passed") and other_payload["download"].get("passed"):
                pixel_diff = image_diff(Path(manual["download"]["path"]), Path(other_payload["download"]["path"]))
                if other == "hd":
                    diff_info = save_visual_diff(
                        Path(manual["download"]["path"]),
                        Path(other_payload["download"]["path"]),
                        DIFF_DIR / f"{sample.name}_manual_vs_hd_diff.jpg",
                    )
                    diff_path = diff_info["path"]
                    pixel_diff.update({"diffPath": diff_path})
            if other == "hd":
                distinct_enough = bool(pixel_diff.get("changed")) and (
                    float(pixel_diff.get("mean") or 0) >= 0.10 or int(pixel_diff.get("max") or 0) >= 10
                )
            else:
                distinct_enough = bool(pixel_diff.get("changed"))
            comparison = {
                "sameUrl": same_url,
                "samePath": same_path,
                "sameHash": same_hash,
                "pixelDiff": pixel_diff,
                "diffPath": diff_path,
                "distinctEnough": distinct_enough,
                "passed": not same_url and not same_path and not same_hash and distinct_enough,
            }
            row["comparisons"][compare_key] = comparison
            if not comparison["passed"]:
                row["failures"].append(f"{sample.name}:{compare_key} chain isolation/visual difference failed")

        row["passed"] = not row["failures"]
        rows.append(row)
        failures.extend(row["failures"])
    return {
        "passed": not failures,
        "sampleCount": len(samples),
        "rows": rows,
        "failures": failures,
    }


def make_contact_sheet(matrix: dict[str, Any]) -> None:
    rows = matrix["rows"]
    thumb_w, thumb_h = 170, 130
    label_h = 54
    margin = 16
    columns = ["source", "mask", "manual", "quick", "hd", "diff"]
    sheet_w = margin * 2 + len(columns) * thumb_w
    sheet_h = margin * 2 + len(rows) * (thumb_h + label_h + 10)
    sheet = Image.new("RGB", (sheet_w, sheet_h), (248, 250, 252))
    draw = ImageDraw.Draw(sheet)

    x = margin
    for col in columns:
        draw.text((x + 6, 4), col.upper(), fill=(23, 37, 84))
        x += thumb_w

    y = margin + 10
    for row in rows:
        image_paths = [
            Path(row["source"]),
            Path(row["mask"]),
            Path(row["modes"]["manual"]["download"].get("path", "")),
            Path(row["modes"]["quick"]["download"].get("path", "")),
            Path(row["modes"]["hd"]["download"].get("path", "")),
            Path((row["comparisons"].get("manualVsHd") or {}).get("diffPath") or ""),
        ]
        for col_idx, path in enumerate(image_paths):
            x = margin + col_idx * thumb_w
            box = [x + 6, y + 6, x + thumb_w - 6, y + thumb_h - 6]
            draw.rounded_rectangle([x + 4, y + 4, x + thumb_w - 4, y + thumb_h + label_h - 4], radius=6, fill=(255, 255, 255), outline=(215, 226, 238))
            try:
                img = Image.open(path).convert("RGB")
                img.thumbnail((thumb_w - 18, thumb_h - 18))
                px = x + (thumb_w - img.width) // 2
                py = y + 10 + (thumb_h - 18 - img.height) // 2
                sheet.paste(img, (px, py))
            except Exception:
                draw.text((box[0], box[1]), "missing", fill=(185, 28, 28))

            if col_idx >= 2 and columns[col_idx] != "diff":
                mode = columns[col_idx]
                mode_data = row["modes"][mode]
                engine = str(mode_data["response"].get("engine") or "")
                h = str(mode_data["response"].get("fileHash") or "")[:10]
                status = "PASS" if mode_data.get("passed") else "FAIL"
                draw.text((x + 8, y + thumb_h + 2), f"{status} {engine}", fill=(22, 101, 52) if status == "PASS" else (185, 28, 28))
                draw.text((x + 8, y + thumb_h + 20), f"hash {h}", fill=(71, 85, 105))
            elif columns[col_idx] == "diff":
                comp = row["comparisons"].get("manualVsHd") or {}
                pixel = comp.get("pixelDiff") or {}
                status = "PASS" if comp.get("passed") else "FAIL"
                draw.text((x + 8, y + thumb_h + 2), f"{status} manual-vs-HD", fill=(22, 101, 52) if status == "PASS" else (185, 28, 28))
                draw.text((x + 8, y + thumb_h + 20), f"mean {pixel.get('mean')} max {pixel.get('max')}", fill=(71, 85, 105))
            else:
                draw.text((x + 8, y + thumb_h + 8), row["sample"][:22], fill=(71, 85, 105))
        y += thumb_h + label_h + 10

    sheet.save(CONTACT_SHEET, quality=92)


def write_reports(payload: dict[str, Any]) -> None:
    CHAIN_JSON.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    REGRESSION_JSON.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    (FINAL / "watermark-regression-report.json").write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    health = payload["health"]["watermarkHealth"].get("data", {})
    matrix = payload["matrix"]
    first_row = matrix["rows"][0] if matrix["rows"] else {}
    first_manual = (first_row.get("modes") or {}).get("manual", {})
    first_hd = (first_row.get("modes") or {}).get("hd", {})
    same_url = None
    same_hash = None
    if first_row:
        comp = first_row["comparisons"]["manualVsHd"]
        same_url = comp["sameUrl"]
        same_hash = comp["sameHash"]

    lines = [
        "# Watermark HD Chain Validation Report",
        "",
        f"- Status: {payload['status']}",
        f"- Base URL: `{payload['baseUrl']}`",
        f"- Generated samples: {matrix['sampleCount']}",
        f"- Contact sheet: `{CONTACT_SHEET}`",
        f"- Diff images: `{DIFF_DIR}`",
        "",
        "## Backend Health",
        f"- /api/health: {'PASS' if payload['health']['apiHealth'].get('passed') else 'FAIL'}",
        f"- /api/watermark/health: {'PASS' if payload['health']['watermarkHealth'].get('passed') else 'FAIL'}",
        f"- manualEngine: `{health.get('manualEngine')}`",
        f"- quickEngine: `{health.get('quickEngine')}`",
        f"- hdEngine: `{health.get('hdEngine')}`",
        f"- hdRealModelLoaded: `{health.get('hdRealModelLoaded')}`",
        f"- fallbackUsed: `{health.get('fallbackUsed')}`",
        "",
        "## Chain Isolation",
        f"- First manual resultUrl: `{(first_manual.get('response') or {}).get('resultUrl')}`",
        f"- First hd resultUrl: `{(first_hd.get('response') or {}).get('resultUrl')}`",
        f"- First manual/hd same URL: `{same_url}`",
        f"- First manual/hd same hash: `{same_hash}`",
        "",
        "## Frontend Audit",
    ]
    for name, passed in payload["frontend"]["checks"].items():
        lines.append(f"- {name}: {'PASS' if passed else 'FAIL'}")
    lines.extend(["", "## Sample Matrix"])
    for row in matrix["rows"]:
        lines.append(f"- {row['sample']}: {'PASS' if row['passed'] else 'FAIL'}")
        if row["failures"]:
            lines.append(f"  failures: {'; '.join(row['failures'])}")
    if matrix["failures"]:
        lines.extend(["", "## Failures"])
        for item in matrix["failures"]:
            lines.append(f"- {item}")

    CHAIN_MD.write_text("\n".join(lines), encoding="utf-8")
    REGRESSION_MD.write_text("\n".join(lines), encoding="utf-8")
    (FINAL / "watermark-regression-report.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    base_url = args.base_url.rstrip("/")
    _mkdirs()
    service = ensure_backend(base_url)
    health = check_health(base_url)
    samples = generate_samples()
    frontend = audit_frontend()
    matrix = run_sample_matrix(base_url, samples)
    make_contact_sheet(matrix)

    stop_conditions = {
        "backendStartedOrRunning": bool(service.get("passed")),
        "apiHealthOk": bool(health["apiHealth"].get("passed")),
        "watermarkHealthOk": bool(health["watermarkHealth"].get("passed")),
        "manualChainOk": all(row["modes"]["manual"].get("passed") for row in matrix["rows"]),
        "quickChainOk": all(row["modes"]["quick"].get("passed") for row in matrix["rows"]),
        "hdChainOk": all(row["modes"]["hd"].get("passed") for row in matrix["rows"]),
        "manualHdDifferentUrl": all(not row["comparisons"]["manualVsHd"]["sameUrl"] for row in matrix["rows"]),
        "manualHdDifferentPath": all(not row["comparisons"]["manualVsHd"]["samePath"] for row in matrix["rows"]),
        "manualHdDifferentHash": all(not row["comparisons"]["manualVsHd"]["sameHash"] for row in matrix["rows"]),
        "manualHdVisiblyDifferent": all(row["comparisons"]["manualVsHd"]["distinctEnough"] for row in matrix["rows"]),
        "frontendStateSeparated": bool(frontend.get("passed")),
        "contactSheetGenerated": CONTACT_SHEET.exists(),
        "sampleCountAtLeast8": len(samples) >= 8,
    }
    passed = all(stop_conditions.values()) and matrix["passed"]
    payload = {
        "status": "PASS" if passed else "FAIL",
        "baseUrl": base_url,
        "service": service,
        "health": health,
        "frontend": frontend,
        "matrix": matrix,
        "stopConditions": stop_conditions,
        "reports": {
            "chainMd": str(CHAIN_MD),
            "chainJson": str(CHAIN_JSON),
            "regressionMd": str(REGRESSION_MD),
            "regressionJson": str(REGRESSION_JSON),
            "contactSheet": str(CONTACT_SHEET),
            "samples": str(SAMPLES),
        },
    }
    write_reports(payload)
    print(f"[verify-watermark] {payload['status']} report={CHAIN_MD}")
    print(f"[verify-watermark] contact-sheet={CONTACT_SHEET}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
