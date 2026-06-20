from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
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
    VENV_PYTHON = HIVISION_ROOT / ".venv" / "Scripts" / "python.exe"
else:
    VENV_PYTHON = Path(sys.executable)
ASCII_BASE = Path(tempfile.gettempdir()) / "idphoto_hivision_ascii"
ASCII_ROOT = ASCII_BASE / "HivisionIDPhotos"
ASCII_RUNTIME_DIR = ASCII_BASE / "runtime"
MODEL_ORDER = [
    "birefnet-v1-lite",
    "hivision_modnet",
    "modnet_photographic_portrait_matting",
    "rmbg-1.4",
]


def _ready_marker() -> Path:
    return REPORT_DIR / "hivision-standalone-ready.json"


def production_ready() -> tuple[bool, str]:
    if os.environ.get("ID_PHOTO_DISABLE_HIVISION", "").strip().lower() in {"1", "true", "yes"}:
        return False, "disabled by ID_PHOTO_DISABLE_HIVISION"
    if not (HIVISION_ROOT / "inference.py").exists():
        return False, "Hivision inference.py not found"
    if platform.system() == "Windows" and not Path(VENV_PYTHON).exists():
        return False, "Hivision venv python not found"
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


def _model_order() -> list[str]:
    requested = os.environ.get("ID_PHOTO_HIVISION_MODEL", "").strip()
    installed = available_models()
    ordered = []
    if requested:
        ordered.append(requested)
    ordered.extend(model for model in MODEL_ORDER if model not in ordered)
    return [model for model in ordered if not installed or model in installed]


def run_human_matting(image: Image.Image, model: str = None, request_id: str = "", timeout: int = 180) -> dict[str, Any]:
    ready, reason = production_ready()
    debug: dict[str, Any] = {
        "ready": ready,
        "readyReason": reason,
        "hivisionRoot": str(HIVISION_ROOT),
        "venvPython": str(VENV_PYTHON),
        "asciiRoot": str(ASCII_ROOT),
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

    if model:
        models = [model]
    else:
        models = _model_order()
    
    if not models:
        return {
            "success": False,
            "code": "HIVISION_NO_MODEL",
            "message": "No Hivision matting model weights are available",
            "debug": debug,
        }

    for model in models:
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
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(ASCII_ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                shell=False,
            )
            attempt = {
                "model": model,
                "cmd": cmd,
                "returncode": proc.returncode,
                "seconds": round(time.time() - started, 2),
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
                "outputPath": str(output_path),
                "outputExists": False,
                "outputTail": repr(exc),
            }
        debug["attempts"].append(attempt)
        if attempt["returncode"] != 0 or not output_path.exists():
            continue
        try:
            rgba = Image.open(output_path).convert("RGBA")
            alpha = rgba.getchannel("A")
            extrema = alpha.getextrema()
            if extrema[1] <= 4:
                attempt["alphaExtrema"] = extrema
                attempt["rejected"] = "empty alpha"
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
                    "alphaExtrema": extrema,
                    "fallbackWithinHivision": model != models[0],
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
