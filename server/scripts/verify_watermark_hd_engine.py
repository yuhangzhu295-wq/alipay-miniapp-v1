"""Verify the HD watermark engine contract.

HD is only considered available when the real IOPaint/LaMa service is reachable.
OpenCV fallback is allowed as a separate compatibility path, but it must not be
reported as HD success.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "reports" / "final"
CHECKPOINTS = ROOT / "reports" / "checkpoints"


def _get_json(url: str, timeout: float = 5.0) -> dict[str, Any]:
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


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _start_iopaint_if_needed(port: int = 8081) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}/api/v1/model"
    first = _get_json(url, timeout=2.0)
    if first.get("passed"):
        return {"attempted": False, "alreadyRunning": True, "health": first}

    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    stdout = CHECKPOINTS / "verify-iopaint-8081.out.log"
    stderr = CHECKPOINTS / "verify-iopaint-8081.err.log"
    cmd = [
        sys.executable,
        "-m",
        "iopaint",
        "start",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--model",
        "lama",
        "--device",
        "cpu",
        "--no-inbrowser",
        "--quality",
        "100",
    ]
    started: dict[str, Any] = {
        "attempted": True,
        "alreadyRunning": False,
        "cmd": cmd,
        "stdout": str(stdout),
        "stderr": str(stderr),
    }
    try:
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        with stdout.open("ab") as out_fh, stderr.open("ab") as err_fh:
            process = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdout=out_fh,
                stderr=err_fh,
                creationflags=flags,
            )
        started["pid"] = process.pid
    except Exception as exc:
        started["error"] = str(exc)
        started["health"] = first
        return started

    deadline = time.time() + 60
    last = first
    while time.time() < deadline:
        time.sleep(2)
        last = _get_json(url, timeout=4.0)
        if last.get("passed"):
            break
    started["health"] = last
    return started


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    base_url = args.base_url.rstrip("/")
    FINAL.mkdir(parents=True, exist_ok=True)

    iopaint_start = _start_iopaint_if_needed(8081)
    iopaint_health = _get_json("http://127.0.0.1:8081/api/v1/model", timeout=5.0)
    gateway = _get_json(base_url + "/api/watermark/health", timeout=8.0)
    health = gateway.get("data") or {}

    checks = {
        "iopaintModuleInstalled": _module_available("iopaint"),
        "torchInstalled": _module_available("torch"),
        "opencvInstalled": _module_available("cv2"),
        "pillowInstalled": _module_available("PIL"),
        "iopaintHttpReachable": iopaint_health.get("passed") is True,
        "iopaintModelIsLama": str(((iopaint_health.get("data") or {}).get("name") or "")).lower() == "lama",
        "gatewayReachable": gateway.get("passed") is True and bool(health.get("ok") or health.get("success")),
        "gatewayHdAvailableTrue": health.get("hdAvailable") is True,
        "gatewayRealModelLoaded": health.get("hdRealModelLoaded") is True,
        "gatewayFallbackNotUsed": health.get("fallbackUsed") is False,
        "gatewayEngineNotFallback": health.get("hdEngine") not in {"opencv_hd_fallback", "not_ready", "", None},
        "gatewayHasFallbackFields": "fallbackAvailable" in health and "fallbackEngine" in health,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "status": status,
        "baseUrl": base_url,
        "checks": checks,
        "iopaintStart": iopaint_start,
        "iopaintHealth": iopaint_health,
        "watermarkHealth": gateway,
    }

    json_path = FINAL / "watermark-hd-engine-audit.json"
    md_path = FINAL / "watermark-hd-engine-audit.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    md = [
        "# Watermark HD Engine Audit",
        "",
        f"- Status: {status}",
        f"- Base URL: `{base_url}`",
        f"- IOPaint start attempted: `{iopaint_start.get('attempted')}`",
        f"- IOPaint model: `{((iopaint_health.get('data') or {}).get('name'))}`",
        f"- Gateway hdEngine: `{health.get('hdEngine')}`",
        f"- Gateway hdRealModelLoaded: `{health.get('hdRealModelLoaded')}`",
        f"- Gateway fallbackUsed: `{health.get('fallbackUsed')}`",
        "",
        "## Checks",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in checks.items()],
        "",
    ]
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"[verify-watermark-hd-engine] {status} report={md_path}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
