from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .common.diagnostics import module_path, python_path
from .hivision.adapter import hivision_available, hivision_root, hivision_runtime_ready
from .rembg.adapter import rembg_available
from .modnet.adapter import modnet_available
from .birefnet.adapter import birefnet_available


ENGINE_VERSION = os.environ.get("ID_PHOTO_ENGINE_VERSION", "multi-engine-reset-20260613-local")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _hivision_ready_marker() -> Path:
    return _project_root() / "reports" / "id-photo-multi-engine-reset" / "hivision-standalone-ready.json"


def _hivision_runtime_ready() -> tuple[bool, str]:
    if os.environ.get("ID_PHOTO_FORCE_HIVISION", "").strip().lower() in {"1", "true", "yes"}:
        return True, "forced by ID_PHOTO_FORCE_HIVISION"
    marker = _hivision_ready_marker()
    if marker.exists():
        return True, f"verified marker found: {marker}"
    ready, reason = hivision_runtime_ready()
    if ready:
        return True, reason
    return False, reason


def _runtime_files() -> dict[str, str]:
    import services.id_photo_v2 as id_photo_v2
    import id_photo_engines.hivision.runner as hivision_runner

    return {
        "manager": str(Path(__file__).resolve()),
        "hivisionRunner": module_path(hivision_runner),
        "legacyPrepareCompose": module_path(id_photo_v2),
    }


def get_engine_info() -> dict[str, Any]:
    hivision_ok, hivision_reason = hivision_available()
    hivision_ready, hivision_ready_reason = _hivision_runtime_ready()
    rembg_ok, rembg_model, rembg_reason = rembg_available()
    modnet_ok, modnet_reason = modnet_available()
    birefnet_ok, birefnet_reason = birefnet_available()

    requested = os.environ.get("ID_PHOTO_ENGINE", "auto").strip().lower() or "auto"
    from .hivision.runner import get_model_routing

    model_routing = get_model_routing()
    if requested in {"hivision", "auto"} and hivision_ok and hivision_ready:
        selected = {
            "engine": "hivision",
            "selectedModel": model_routing.get("standard") or "",
            "loaded": True,
            "selectionReason": hivision_ready_reason,
        }
    elif rembg_ok:
        selected = {
            "engine": "rembg",
            "selectedModel": rembg_model,
            "loaded": True,
            "selectionReason": "HivisionIDPhotos not yet verified; using stable local rembg chain",
        }
    else:
        selected = {
            "engine": "none",
            "selectedModel": "",
            "loaded": False,
            "selectionReason": "No local ID-photo engine is available",
        }

    return {
        "success": True,
        "engine": selected["engine"],
        "engineVersion": ENGINE_VERSION,
        "selectedModel": selected["selectedModel"],
        "loaded": selected["loaded"],
        "selectionReason": selected["selectionReason"],
        "modelRouting": model_routing,
        "availableEngines": ["hivision", "rembg", "modnet", "birefnet"],
        "candidates": {
            "hivision": {
                "available": hivision_ok,
                "reason": hivision_reason,
                "readyForRuntime": hivision_ready,
                "runtimeReadyReason": hivision_ready_reason,
                "readyMarker": str(_hivision_ready_marker()),
                "path": str(hivision_root()),
            },
            "rembg": {
                "available": rembg_ok,
                "model": rembg_model,
                "reason": rembg_reason,
            },
            "modnet": {"available": modnet_ok, "reason": modnet_reason},
            "birefnet": {"available": birefnet_ok, "reason": birefnet_reason},
        },
        "python": python_path(),
        "legacyDisabled": False,
        "legacyNote": "Legacy compose and quality modules remain active; Hivision supplies the routed foreground mask.",
        "currentRuntimeFiles": _runtime_files(),
    }


def get_engine_runtime_tags() -> dict[str, Any]:
    info = get_engine_info()
    return {
        "engine": info.get("engine"),
        "engineVersion": info.get("engineVersion"),
        "engineModel": info.get("selectedModel"),
        "engineLoaded": info.get("loaded"),
        "engineSelectionReason": info.get("selectionReason"),
    }
