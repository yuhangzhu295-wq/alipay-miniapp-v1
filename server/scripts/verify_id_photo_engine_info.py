from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "id-photo-multi-engine-reset"
REPORT_JSON = REPORT_DIR / "engine-adapter-report.json"
REPORT_MD = REPORT_DIR / "engine-adapter-report.md"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def get_json(base_url: str, path: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} returned non-object JSON")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    result: dict[str, Any] = {
        "baseUrl": args.base_url,
        "passed": False,
        "checks": [],
        "errors": [],
    }

    def check(name: str, passed: bool, detail: Any = None) -> None:
        result["checks"].append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed:
            result["errors"].append({"name": name, "detail": detail})

    try:
        health = get_json(args.base_url, "/api/health")
        id_health = get_json(args.base_url, "/api/id-photo/health")
        engine = get_json(args.base_url, "/api/id-photo/engine-info")

        result["health"] = health
        result["idPhotoHealth"] = id_health
        result["engineInfo"] = engine

        check("backend health ok", bool(health.get("success")), health)
        check("id-photo health exposes engineInfo", isinstance(id_health.get("engineInfo"), dict), id_health.get("engineInfo"))
        check("engine endpoint ok", bool(engine.get("success")), engine)
        check("engine present", engine.get("engine") in {"hivision", "rembg", "modnet", "birefnet", "none"}, engine.get("engine"))
        check("engineVersion present", str(engine.get("engineVersion", "")).startswith("multi-engine-reset-"), engine.get("engineVersion"))
        check("selected model present when engine loaded", (not engine.get("loaded")) or bool(engine.get("selectedModel")), engine.get("selectedModel"))

        files = engine.get("currentRuntimeFiles") or {}
        required_files = ["manager", "hivisionAdapter", "hivisionRunner", "legacyPrepareCompose", "matting", "compose", "quality"]
        for key in required_files:
            path = files.get(key)
            check(f"runtime file exists: {key}", bool(path) and Path(path).exists(), path)

        candidates = engine.get("candidates") or {}
        for key in ["hivision", "rembg", "modnet", "birefnet"]:
            check(f"candidate reported: {key}", key in candidates, candidates.get(key))

        hivision = candidates.get("hivision") or {}
        if hivision.get("available") and hivision.get("readyForRuntime"):
            check("hivision is selected when ready", engine.get("engine") == "hivision", engine.get("engine"))
            check("legacy rembg matting disabled for selected engine", bool(engine.get("legacyDisabled")), engine.get("legacyDisabled"))

        result["passed"] = not result["errors"]
    except Exception as exc:
        result["errors"].append({"name": "exception", "detail": repr(exc)})
        result["passed"] = False

    write_json(REPORT_JSON, result)
    lines = [
        "# ID Photo Engine Adapter Verification",
        "",
        f"- Base URL: `{args.base_url}`",
        f"- Result: {'PASS' if result['passed'] else 'FAIL'}",
        "",
        "## Engine",
    ]
    engine = result.get("engineInfo") or {}
    if engine:
        lines.extend([
            f"- Current engine: `{engine.get('engine')}`",
            f"- Version: `{engine.get('engineVersion')}`",
            f"- Model: `{engine.get('selectedModel')}`",
            f"- Loaded: `{engine.get('loaded')}`",
            f"- Selection reason: {engine.get('selectionReason')}",
            f"- Legacy disabled: `{engine.get('legacyDisabled')}`",
        ])
    lines.extend(["", "## Checks"])
    for item in result["checks"]:
        lines.append(f"- [{'x' if item['passed'] else ' '}] {item['name']}: `{item.get('detail')}`")
    if result["errors"]:
        lines.extend(["", "## Errors"])
        for item in result["errors"]:
            lines.append(f"- {item['name']}: `{item.get('detail')}`")

    write_md(REPORT_MD, lines)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
