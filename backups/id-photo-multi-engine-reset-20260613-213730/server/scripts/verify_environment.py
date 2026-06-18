"""Backend, gateway, and network checkpoint verifier."""
from __future__ import annotations

import argparse
import importlib.util
import json
import socket
import sys
import time
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
CHECKPOINTS = REPORTS / "checkpoints"
FINAL = REPORTS / "final"

NETWORK_URLS = [
    "https://randomuser.me/api/?results=2",
    "https://thispersondoesnotexist.com/",
    "https://picsum.photos/300/400",
]


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _request_json(url: str) -> dict:
    started = time.perf_counter()
    try:
        res = requests.get(url, timeout=8)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:300]}
        return {
            "passed": res.status_code == 200,
            "statusCode": res.status_code,
            "durationMs": int((time.perf_counter() - started) * 1000),
            "data": data,
        }
    except Exception as exc:
        return {"passed": False, "durationMs": int((time.perf_counter() - started) * 1000), "error": str(exc)}


def backend_check(base_url: str) -> dict:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    package_path = ROOT / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    scripts = package.get("scripts", {})
    api_health = _request_json(base_url.rstrip("/") + "/api/health")
    wm_health = _request_json(base_url.rstrip("/") + "/api/watermark/health")
    payload = {
        "status": "PASS" if api_health["passed"] and (api_health.get("data") or {}).get("success") is True else "FAIL",
        "baseUrl": base_url,
        "workingDirectory": str(ROOT),
        "port8000Open": _port_open("127.0.0.1", 8000),
        "pythonExecutable": sys.executable,
        "pythonVersion": sys.version,
        "mainPyExists": (ROOT / "server" / "main.py").exists(),
        "fastapiInstalled": _module_available("fastapi"),
        "uvicornInstalled": _module_available("uvicorn"),
        "packageScripts": {
            "dev:watermark": scripts.get("dev:watermark", ""),
            "verify:id-photo": scripts.get("verify:id-photo", ""),
            "verify:watermark": scripts.get("verify:watermark", ""),
            "verify:frontend-ui": scripts.get("verify:frontend-ui", ""),
            "verify:open-source-engines": scripts.get("verify:open-source-engines", ""),
            "verify:all": scripts.get("verify:all", ""),
        },
        "apiHealth": api_health,
        "watermarkGatewayHealth": wm_health,
    }
    report_json = json.dumps(payload, ensure_ascii=True, indent=2)
    (CHECKPOINTS / "backend-start-check.json").write_text(report_json, encoding="utf-8")
    (FINAL / "backend-start-check.json").write_text(report_json, encoding="utf-8")
    md = [
        "# Backend Start Check",
        "",
        f"- Status: {payload['status']}",
        f"- Base URL: `{base_url}`",
        f"- Working directory: `{ROOT}`",
        f"- Port 8000 open: {payload['port8000Open']}",
        f"- `/api/health`: {'PASS' if api_health.get('passed') and (api_health.get('data') or {}).get('success') is True else 'FAIL'}",
        f"- `/api/watermark/health` gateway: {'PASS' if wm_health.get('passed') else 'FAIL'}",
        f"- Python: `{sys.executable}`",
        f"- `server/main.py` exists: {payload['mainPyExists']}",
        f"- FastAPI installed: {payload['fastapiInstalled']}",
        f"- uvicorn installed: {payload['uvicornInstalled']}",
        "",
        "## Scripts",
        *[f"- `{key}`: `{value}`" for key, value in payload["packageScripts"].items()],
        "",
    ]
    report_md = "\n".join(md)
    (CHECKPOINTS / "backend-start-check.md").write_text(report_md, encoding="utf-8")
    (FINAL / "backend-start-check.md").write_text(report_md, encoding="utf-8")
    return payload


def network_check() -> dict:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    results = []
    for url in NETWORK_URLS:
        started = time.perf_counter()
        try:
            res = requests.get(url, timeout=12, headers={"User-Agent": "id-photo-verifier/1.0"})
            ok = res.status_code in (200, 302) and bool(res.content or res.headers.get("location"))
            results.append({
                "url": url,
                "passed": ok,
                "statusCode": res.status_code,
                "contentType": res.headers.get("content-type", ""),
                "bytes": len(res.content or b""),
                "durationMs": int((time.perf_counter() - started) * 1000),
            })
        except Exception as exc:
            results.append({
                "url": url,
                "passed": False,
                "error": str(exc),
                "durationMs": int((time.perf_counter() - started) * 1000),
            })
    network_access = any(item.get("passed") for item in results)
    payload = {
        "status": "PASS" if network_access else "FAIL",
        "NETWORK_ACCESS": network_access,
        "NETWORK_FALLBACK": not network_access,
        "results": results,
    }
    report_json = json.dumps(payload, ensure_ascii=True, indent=2)
    (CHECKPOINTS / "network-check.json").write_text(report_json, encoding="utf-8")
    (FINAL / "network-check.json").write_text(report_json, encoding="utf-8")
    md = [
        "# Network Check",
        "",
        f"NETWORK_ACCESS={'true' if network_access else 'false'}",
        f"NETWORK_FALLBACK={'true' if not network_access else 'false'}",
        "",
        "## URL Results",
        *[f"- `{item['url']}`: {'PASS' if item.get('passed') else 'FAIL'} status={item.get('statusCode', 'n/a')} durationMs={item.get('durationMs')}" for item in results],
        "",
    ]
    report_md = "\n".join(md)
    (CHECKPOINTS / "network-check.md").write_text(report_md, encoding="utf-8")
    (FINAL / "network-check.md").write_text(report_md, encoding="utf-8")
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--backend", action="store_true")
    parser.add_argument("--network", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    REPORTS.mkdir(exist_ok=True)
    FINAL.mkdir(parents=True, exist_ok=True)
    run_backend = args.backend or not args.network
    run_network = args.network or not args.backend
    backend = backend_check(args.base_url) if run_backend else {"status": "SKIPPED"}
    network = network_check() if run_network else {"NETWORK_ACCESS": None}
    passed = backend.get("status") in {"PASS", "SKIPPED"}
    print(f"[verify-environment] backend={backend.get('status')} network={network.get('NETWORK_ACCESS')}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
