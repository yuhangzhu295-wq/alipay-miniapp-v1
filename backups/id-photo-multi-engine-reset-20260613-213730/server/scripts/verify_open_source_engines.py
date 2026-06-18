"""Audit open-source image engines used by the current repair scope."""
from __future__ import annotations

import argparse
import importlib.util
import json
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
FINAL = ROOT / "reports" / "final"


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _request_json(url: str, timeout: float = 5.0) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        res = requests.get(url, timeout=timeout)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:500]}
        return {
            "passed": 200 <= res.status_code < 300,
            "statusCode": res.status_code,
            "durationMs": int((time.perf_counter() - started) * 1000),
            "data": data,
        }
    except Exception as exc:
        return {
            "passed": False,
            "durationMs": int((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    base_url = args.base_url.rstrip("/")
    FINAL.mkdir(parents=True, exist_ok=True)

    hd_source = _read(SERVER / "services" / "hd_inpaint.py")
    manual_source = _read(SERVER / "services" / "manual_inpaint.py")
    main_source = _read(SERVER / "main.py")
    id_photo_sources = "\n".join(
        _read(path)
        for path in [
            SERVER / "services" / "face_detector.py",
            SERVER / "services" / "portrait_matting.py",
            SERVER / "services" / "id_photo_composer.py",
            SERVER / "services" / "id_photo_quality.py",
            SERVER / "services" / "id_photo_v2.py",
        ]
        if path.exists()
    )

    watermark_health = _request_json(base_url + "/api/watermark/health")
    iopaint_health = _request_json("http://127.0.0.1:8081/api/v1/model", timeout=2.5)
    health_data = watermark_health.get("data") or {}

    module_checks = {
        "Pillow": _module_available("PIL"),
        "OpenCV": _module_available("cv2"),
        "FastAPI": _module_available("fastapi"),
        "uvicorn": _module_available("uvicorn"),
        "rembgInstalled": _module_available("rembg"),
        "mediapipeInstalled": _module_available("mediapipe"),
        "iopaintInstalled": _module_available("iopaint"),
    }
    source_checks = {
        "manualUsesOpenCV": "cv2." in manual_source and "do_manual_inpaint" in manual_source,
        "quickUsesOpenCV": "do_quick_inpaint" in manual_source and "opencv_quick" in manual_source,
        "hdRouteExists": "/api/watermark/hd-remove" in main_source and "do_hd_inpaint" in main_source,
        "hdIopaintProbeExists": "_call_iopaint" in hd_source and "IOPAINT_URL" in hd_source,
        "hdFallbackExplicit": "opencv_hd_fallback" in hd_source and "fallbackUsed" in hd_source,
        "hdNoRembg": "rembg" not in hd_source.lower(),
        "hdNoMediapipe": "mediapipe" not in hd_source.lower(),
        "idPhotoMayUseVisionOnlyInIdPhotoScope": "mediapipe" in id_photo_sources.lower() or "cv2." in id_photo_sources,
    }
    fallback_truthful = (
        health_data.get("hdRealModelLoaded") is True
        and health_data.get("fallbackUsed") is False
        and health_data.get("hdAvailable") is True
    )
    gateway_checks = {
        "watermarkHealthOk": watermark_health.get("passed") is True
        and bool(health_data.get("ok") or health_data.get("success")),
        "hdGatewayTruthful": fallback_truthful,
        "iopaintDetected": iopaint_health.get("passed") is True,
        "realIopaintLamaReady": iopaint_health.get("passed") is True
        and str(((iopaint_health.get("data") or {}).get("name") or "")).lower() == "lama",
    }

    required_pass = {
        "Pillow": module_checks["Pillow"],
        "OpenCV": module_checks["OpenCV"],
        "FastAPI": module_checks["FastAPI"],
        "uvicorn": module_checks["uvicorn"],
        **source_checks,
        "watermarkHealthOk": gateway_checks["watermarkHealthOk"],
        "hdGatewayTruthful": gateway_checks["hdGatewayTruthful"],
        "realIopaintLamaReady": gateway_checks["realIopaintLamaReady"],
    }
    passed = all(required_pass.values())
    payload = {
        "status": "PASS" if passed else "FAIL",
        "baseUrl": base_url,
        "modules": module_checks,
        "sourceChecks": source_checks,
        "gatewayChecks": gateway_checks,
        "watermarkHealth": watermark_health,
        "iopaintHealth": iopaint_health,
        "notes": [
            "OpenCV/Pillow are used for manual, quick, and explicit HD fallback repair.",
            "IOPaint/LaMa is probed through the gateway. HD is PASS only when the real LaMa model is reachable.",
            "rembg/MediaPipe are not used for HD watermark removal.",
        ],
    }

    json_path = FINAL / "open-source-engine-audit.json"
    md_path = FINAL / "open-source-engine-audit.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    md = [
        "# Open-source Engine Audit",
        "",
        f"- Status: {payload['status']}",
        f"- Base URL: `{base_url}`",
        "",
        "## Module Availability",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in module_checks.items()],
        "",
        "## Source Boundaries",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in source_checks.items()],
        "",
        "## Gateway",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in gateway_checks.items()],
        "",
        "## Notes",
        *[f"- {item}" for item in payload["notes"]],
        "",
    ]
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"[verify-open-source-engines] {payload['status']} report={md_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
