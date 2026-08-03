from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = ROOT / "reports" / "id-photo-multi-engine-reset"
HIVISION_ROOT = ROOT / "third_party" / "HivisionIDPhotos"
import sys
import platform

if platform.system() == "Windows":
    _hivision_python = HIVISION_ROOT / ".venv" / "Scripts" / "python.exe"
    VENV_PYTHON = _hivision_python if _hivision_python.exists() else Path(sys.executable)
else:
    VENV_PYTHON = Path(sys.executable)
ASCII_BASE = Path(tempfile.gettempdir()) / "idphoto_hivision_ascii"
ASCII_ROOT = ASCII_BASE / "HivisionIDPhotos"
ASCII_RUNTIME_DIR = ASCII_BASE / "runtime"
MODEL_ORDER = [
    "hivision_modnet",
    "birefnet-v1-lite",
    "modnet_photographic_portrait_matting",
    "rmbg-1.4",
]
_INFERENCE_LOCK = threading.Lock()


def _ready_marker() -> Path:
    return REPORT_DIR / "hivision-standalone-ready.json"


def production_ready() -> tuple[bool, str]:
    if os.environ.get("ID_PHOTO_DISABLE_HIVISION", "").strip().lower() in {"1", "true", "yes"}:
        return False, "disabled by ID_PHOTO_DISABLE_HIVISION"
    if not (HIVISION_ROOT / "inference.py").exists():
        return False, "Hivision inference.py not found"
    if not Path(VENV_PYTHON).exists():
        return False, "Hivision Python runtime not found"
    if os.environ.get("ID_PHOTO_FORCE_HIVISION", "").strip().lower() in {"1", "true", "yes"}:
        return True, "forced by ID_PHOTO_FORCE_HIVISION"
    if _ready_marker().exists():
        return True, f"standalone verification marker found: {_ready_marker()}"
    return False, "Hivision standalone verification has not passed"


def available_models() -> list[str]:
    weights = HIVISION_ROOT / "hivision" / "creator" / "weights"
    return [model for model in MODEL_ORDER if (weights / f"{model}.onnx").exists()]


def _ensure_ascii_root() -> dict[str, Any]:
    ASCII_BASE.mkdir(parents=True, exist_ok=True)
    if ASCII_ROOT.exists():
        return {"path": str(ASCII_ROOT), "created": False, "returncode": 0, "outputTail": "existing"}
    if platform.system() == "Windows":
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(ASCII_ROOT), str(HIVISION_ROOT)],
            cwd=str(ASCII_BASE),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
        )
    else:
        proc = subprocess.run(
            ["ln", "-s", str(HIVISION_ROOT), str(ASCII_ROOT)],
            cwd=str(ASCII_BASE),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
        )
    return {
        "path": str(ASCII_ROOT),
        "created": proc.returncode == 0,
        "returncode": proc.returncode,
        "outputTail": (proc.stdout or "")[-4000:],
    }


def get_model_routing() -> dict[str, Any]:
    installed = available_models()
    standard_requested = os.environ.get("ID_PHOTO_HIVISION_STANDARD_MODEL", "birefnet-v1-lite").strip()
    detail_requested = os.environ.get("ID_PHOTO_HIVISION_DETAIL_MODEL", "birefnet-v1-lite").strip()

    def resolve(requested: str) -> str:
        if requested in installed:
            return requested
        return installed[0] if installed else ""

    return {
        "standard": resolve(standard_requested),
        "detail": resolve(detail_requested),
        "standardRequested": standard_requested,
        "detailRequested": detail_requested,
        "installed": installed,
    }


def _model_order(preferred_model: str = "") -> list[str]:
    installed = available_models()
    requested = preferred_model or get_model_routing().get("standard") or os.environ.get("ID_PHOTO_HIVISION_MODEL", "").strip()
    ordered = []
    if requested:
        ordered.append(requested)
    ordered.extend(model for model in MODEL_ORDER if model not in ordered)
    return [model for model in ordered if not installed or model in installed]


def _alpha_metrics(alpha: Image.Image) -> dict[str, Any]:
    histogram = alpha.histogram()
    total = max(1, sum(histogram))
    transparent = sum(histogram[:8])
    transition = sum(histogram[8:248])
    foreground = sum(histogram[13:])
    return {
        "alphaExtrema": alpha.getextrema(),
        "transparentRatio": round(transparent / total, 6),
        "transitionRatio": round(transition / total, 6),
        "foregroundRatio": round(foreground / total, 6),
    }


def run_human_matting(image: Image.Image, model: str = None, request_id: str = "", timeout: int = 180) -> dict[str, Any]:
    ready, reason = production_ready()
    debug: dict[str, Any] = {
        "ready": ready,
        "readyReason": reason,
        "hivisionRoot": str(HIVISION_ROOT),
        "venvPython": str(VENV_PYTHON),
        "asciiRoot": str(ASCII_ROOT),
        "requestedModel": model or "",
        "modelRouting": get_model_routing(),
        "attempts": [],
    }
    if not ready:
        return {"success": False, "code": "HIVISION_NOT_READY", "message": reason, "debug": debug}

    ascii_state = _ensure_ascii_root()
    debug["asciiRootState"] = ascii_state
    if not ASCII_ROOT.exists():
        return {
            "success": False,
            "code": "HIVISION_ASCII_ROOT_FAILED",
            "message": "Unable to prepare ASCII Hivision runtime path",
            "debug": debug,
        }

    ASCII_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    token = f"{request_id or 'request'}-{int(time.time() * 1000)}"
    safe_token = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in token)
    input_path = ASCII_RUNTIME_DIR / f"{safe_token}-input.png"
    image.convert("RGB").save(input_path, format="PNG")

    models = _model_order(model or "")
    
    if not models:
        return {
            "success": False,
            "code": "HIVISION_NO_MODEL",
            "message": "No Hivision matting model weights are available",
            "debug": debug,
        }

    deadline = time.monotonic() + max(10, int(timeout))
    for model in models:
        remaining = int(deadline - time.monotonic())
        if remaining < 5:
            debug["timeoutBudgetExhausted"] = True
            break
        output_path = ASCII_RUNTIME_DIR / f"{safe_token}-{model}.png"
        if output_path.exists():
            output_path.unlink()
        cmd = [
            str(VENV_PYTHON),
            "inference.py",
            "-t",
            "human_matting",
            "-i",
            str(input_path),
            "-o",
            str(output_path),
            "--matting_model",
            model,
        ]
        started = time.time()
        queue_started = time.time()
        acquired = _INFERENCE_LOCK.acquire(timeout=max(5, remaining))
        queue_wait_seconds = round(time.time() - queue_started, 3)
        if not acquired:
            debug["attempts"].append({
                "model": model,
                "returncode": -1,
                "seconds": 0,
                "queueWaitSeconds": queue_wait_seconds,
                "outputPath": str(output_path),
                "outputExists": False,
                "outputTail": "Timed out waiting for the serialized Hivision inference slot",
            })
            debug["timeoutBudgetExhausted"] = True
            break
        try:
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(ASCII_ROOT),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=max(5, int(deadline - time.monotonic())),
                    shell=False,
                )
                attempt = {
                    "model": model,
                    "cmd": cmd,
                    "returncode": proc.returncode,
                    "seconds": round(time.time() - started, 2),
                    "queueWaitSeconds": queue_wait_seconds,
                    "outputPath": str(output_path),
                    "outputExists": output_path.exists(),
                    "outputTail": (proc.stdout or "")[-4000:],
                }
            except Exception as exc:
                attempt = {
                    "model": model,
                    "cmd": cmd,
                    "returncode": -1,
                    "seconds": round(time.time() - started, 2),
                    "queueWaitSeconds": queue_wait_seconds,
                    "outputPath": str(output_path),
                    "outputExists": False,
                    "outputTail": repr(exc),
                }
        finally:
            _INFERENCE_LOCK.release()
        debug["attempts"].append(attempt)
        if attempt["returncode"] != 0 or not output_path.exists():
            continue
        try:
            rgba = Image.open(output_path).convert("RGBA")
            alpha = rgba.getchannel("A")
            alpha_metrics = _alpha_metrics(alpha)
            attempt.update(alpha_metrics)
            if alpha_metrics["alphaExtrema"][1] <= 4:
                attempt["rejected"] = "empty alpha"
                continue
            if alpha_metrics["transparentRatio"] < 0.005 or alpha_metrics["foregroundRatio"] > 0.96:
                attempt["rejected"] = "opaque output without a usable transparency mask"
                continue
            return {
                "success": True,
                "engine": "hivision",
                "model": model,
                "rgba": rgba,
                "debug": {
                    **debug,
                    "selectedModel": model,
                    "selectedOutputPath": str(output_path),
                    **alpha_metrics,
                    "trustedAlpha": True,
                    "fallbackWithinHivision": model != models[0],
                    "modelRoute": "detail" if model == get_model_routing().get("detail") else "standard",
                },
            }
        except Exception as exc:
            attempt["decodeError"] = repr(exc)

    return {
        "success": False,
        "code": "HIVISION_MATTING_FAILED",
        "message": "All Hivision matting models failed",
        "debug": debug,
    }


def copy_debug_output(path: str | Path, target_dir: str | Path, name: str) -> str:
    source = Path(path)
    target = Path(target_dir) / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        shutil.copy2(source, target)
        return str(target)
    return ""
