from __future__ import annotations

import base64
import gc
import json
import os
import platform
import subprocess
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response


ROOT = Path(__file__).resolve().parents[3]
SOURCE_HIVISION_ROOT = ROOT / "third_party" / "HivisionIDPhotos"
HIVISION_ROOT = SOURCE_HIVISION_ROOT
if platform.system() == "Windows":
    ascii_base = Path(tempfile.gettempdir()) / "idphoto_hivision_worker"
    ascii_base.mkdir(parents=True, exist_ok=True)
    ascii_root = ascii_base / "HivisionIDPhotos"
    if not ascii_root.exists():
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(ascii_root), str(SOURCE_HIVISION_ROOT)],
            cwd=str(ascii_base),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
        )
    if ascii_root.exists():
        HIVISION_ROOT = ascii_root
if str(HIVISION_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(HIVISION_ROOT))

os.environ["RUN_MODE"] = "beast"

from hivision.creator import human_matting as hm  # noqa: E402


FAST_MODEL = os.environ.get("ID_PHOTO_HIVISION_STANDARD_MODEL", "hivision_modnet").strip()
FAST_B_MODEL = os.environ.get(
    "ID_PHOTO_HIVISION_FAST_B_MODEL",
    "modnet_photographic_portrait_matting",
).strip()
FAST_RESIDENT_MODELS = (FAST_MODEL, FAST_B_MODEL)
SUPPORTED_MODELS = {
    "hivision_modnet",
    "modnet_photographic_portrait_matting",
    "rmbg-1.4",
    "birefnet-v1-lite",
}
MODEL_SESSIONS = {
    "hivision_modnet": "HIVISION_MODNET_SESS",
    "modnet_photographic_portrait_matting": "MODNET_PHOTOGRAPHIC_PORTRAIT_MATTING_SESS",
    "rmbg-1.4": "RMBG_SESS",
    "birefnet-v1-lite": "BIREFNET_V1_LITE_SESS",
}
_INFERENCE_LOCK = threading.Lock()
_CURRENT_MODEL = ""
_STARTUP_DEBUG: dict[str, object] = {}


def _resource_metrics() -> dict[str, object]:
    try:
        import psutil

        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        process = psutil.Process()
        return {
            "freeMemoryMb": round(memory.available / 1024 / 1024, 1),
            "swapUsedMb": round(swap.used / 1024 / 1024, 1),
            "processRssMb": round(process.memory_info().rss / 1024 / 1024, 1),
            "cpuPercent": psutil.cpu_percent(interval=None),
        }
    except Exception:
        try:
            meminfo = {}
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                key, value = line.split(":", 1)
                meminfo[key] = int(value.strip().split()[0])
            status = Path("/proc/self/status").read_text(encoding="ascii")
            rss_kb = 0
            for line in status.splitlines():
                if line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
                    break
            return {
                "freeMemoryMb": round(meminfo.get("MemAvailable", 0) / 1024, 1),
                "swapUsedMb": round(
                    (meminfo.get("SwapTotal", 0) - meminfo.get("SwapFree", 0)) / 1024,
                    1,
                ),
                "processRssMb": round(rss_kb / 1024, 1),
                "loadAverage1m": round(os.getloadavg()[0], 3),
            }
        except Exception:
            return {}


def _release_other_sessions(model: str) -> None:
    global _CURRENT_MODEL
    keep = set(FAST_RESIDENT_MODELS) if model in FAST_RESIDENT_MODELS else {model}
    for candidate, session_name in MODEL_SESSIONS.items():
        if candidate not in keep and getattr(hm, session_name, None) is not None:
            setattr(hm, session_name, None)
    if _CURRENT_MODEL and _CURRENT_MODEL != model and model not in FAST_RESIDENT_MODELS:
        gc.collect()
    _CURRENT_MODEL = model


def _release_all_sessions() -> dict[str, object]:
    global _CURRENT_MODEL
    released = []
    for model, session_name in MODEL_SESSIONS.items():
        if getattr(hm, session_name, None) is not None:
            setattr(hm, session_name, None)
            released.append(model)
    _CURRENT_MODEL = ""
    gc.collect()
    return {"releasedModels": released, **_resource_metrics()}


def _session_loaded(model: str) -> bool:
    return getattr(hm, MODEL_SESSIONS[model], None) is not None


def _ensure_session(model: str) -> int:
    if _session_loaded(model):
        return 0
    started = time.perf_counter()
    session = hm.load_onnx_model(hm.WEIGHTS[model], set_cpu=True)
    setattr(hm, MODEL_SESSIONS[model], session)
    return int((time.perf_counter() - started) * 1000)


def _resize_for_model(image: np.ndarray, model: str) -> tuple[np.ndarray, tuple[int, int], dict[str, object]]:
    height, width = image.shape[:2]
    original_size = (width, height)
    max_side = 768 if model in FAST_RESIDENT_MODELS else 1600
    if max(width, height) <= max_side:
        return image, original_size, {
            "inputOriginalSize": f"{width}x{height}",
            "inputInferenceSize": f"{width}x{height}",
            "inputScale": 1.0,
        }
    scale = max_side / float(max(width, height))
    target = (max(1, round(width * scale)), max(1, round(height * scale)))
    resized = cv2.resize(image, target, interpolation=cv2.INTER_AREA)
    return resized, original_size, {
        "inputOriginalSize": f"{width}x{height}",
        "inputInferenceSize": f"{target[0]}x{target[1]}",
        "inputScale": round(scale, 6),
    }


def _infer(image: np.ndarray, model: str) -> tuple[np.ndarray, dict[str, object]]:
    global _CURRENT_MODEL
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"unsupported model: {model}")

    image_for_model, original_size, resize_debug = _resize_for_model(image, model)
    _release_other_sessions(model)
    loaded_before = _session_loaded(model)
    model_load_ms = _ensure_session(model)
    started = time.perf_counter()
    if model == "hivision_modnet":
        rgba = hm.get_modnet_matting(image_for_model, hm.WEIGHTS[model])
    elif model == "modnet_photographic_portrait_matting":
        rgba = hm.get_modnet_matting_photographic_portrait_matting(
            image_for_model,
            hm.WEIGHTS[model],
        )
    elif model == "rmbg-1.4":
        rgba = hm.get_rmbg_matting(image_for_model, hm.WEIGHTS[model])
    else:
        rgba = hm.get_birefnet_portrait_matting(image_for_model, hm.WEIGHTS[model])
    total_ms = int((time.perf_counter() - started) * 1000)
    if rgba is None:
        raise RuntimeError(f"model returned no image: {model}")
    if rgba.shape[1::-1] != original_size:
        rgb = cv2.resize(rgba[:, :, :3], original_size, interpolation=cv2.INTER_LANCZOS4)
        alpha = cv2.resize(rgba[:, :, 3], original_size, interpolation=cv2.INTER_LINEAR)
        rgba = np.dstack((rgb, alpha))
    _CURRENT_MODEL = model
    return rgba, {
        "model": model,
        "modelLoadMs": model_load_ms,
        "inferenceMs": max(0, total_ms - model_load_ms),
        "sessionReused": loaded_before,
        "onnxRuntime": hm.onnx_runtime_config(),
        **resize_debug,
        **_resource_metrics(),
    }


def _warmup() -> dict[str, object]:
    started = time.perf_counter()
    sample = np.full((640, 480, 3), 224, dtype=np.uint8)
    cv2.ellipse(sample, (240, 255), (92, 132), 0, 0, 360, (92, 116, 150), -1)
    cv2.rectangle(sample, (100, 350), (380, 639), (65, 82, 112), -1)
    try:
        models = {}
        for model in FAST_RESIDENT_MODELS:
            _, debug = _infer(sample, model)
            models[model] = debug
        return {
            "ready": True,
            "warmupMs": int((time.perf_counter() - started) * 1000),
            "models": models,
            "loadedSessions": [model for model in FAST_RESIDENT_MODELS if _session_loaded(model)],
            "onnxRuntime": hm.onnx_runtime_config(),
            **_resource_metrics(),
        }
    except Exception as exc:
        return {"ready": False, "warmupMs": int((time.perf_counter() - started) * 1000), "error": repr(exc)}


def _metrics_header(metrics: dict[str, object]) -> str:
    raw = json.dumps(metrics, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _STARTUP_DEBUG
    _STARTUP_DEBUG = _warmup()
    yield


app = FastAPI(title="Hivision resident worker", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ready": bool(_STARTUP_DEBUG.get("ready")),
        "currentModel": _CURRENT_MODEL,
        "loadedSessions": [model for model in MODEL_SESSIONS if _session_loaded(model)],
        "startup": _STARTUP_DEBUG,
        "resources": _resource_metrics(),
    }


@app.post("/release")
def release() -> dict[str, object]:
    acquired = _INFERENCE_LOCK.acquire(timeout=30)
    if not acquired:
        raise HTTPException(status_code=503, detail="worker queue timeout")
    try:
        return {"success": True, **_release_all_sessions()}
    finally:
        _INFERENCE_LOCK.release()


@app.post("/warmup")
def warmup(model: str = Query(default=FAST_MODEL)) -> dict[str, object]:
    if model not in FAST_RESIDENT_MODELS:
        raise HTTPException(status_code=400, detail="only FAST resident models may be restored")
    acquired = _INFERENCE_LOCK.acquire(timeout=30)
    if not acquired:
        raise HTTPException(status_code=503, detail="worker queue timeout")
    try:
        result = _warmup()
        if not result.get("ready"):
            raise HTTPException(status_code=500, detail=result)
        return {"success": True, **result}
    finally:
        _INFERENCE_LOCK.release()


@app.post("/matting")
async def matting(request: Request, model: str = Query(default=FAST_MODEL)) -> Response:
    if model not in SUPPORTED_MODELS:
        raise HTTPException(status_code=400, detail="unsupported model")
    payload = await request.body()
    image_arr = np.frombuffer(payload, dtype=np.uint8)
    image = cv2.imdecode(image_arr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="invalid image")

    queue_started = time.perf_counter()
    acquired = _INFERENCE_LOCK.acquire(timeout=240)
    queue_wait_ms = int((time.perf_counter() - queue_started) * 1000)
    if not acquired:
        raise HTTPException(status_code=503, detail="worker queue timeout")
    try:
        rgba, metrics = _infer(image, model)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=repr(exc)) from exc
    finally:
        _INFERENCE_LOCK.release()
    metrics["queueWaitMs"] = queue_wait_ms
    ok, encoded = cv2.imencode(".png", rgba)
    if not ok:
        raise HTTPException(status_code=500, detail="failed to encode result")
    return Response(
        encoded.tobytes(),
        media_type="image/png",
        headers={"X-Hivision-Metrics": _metrics_header(metrics)},
    )
