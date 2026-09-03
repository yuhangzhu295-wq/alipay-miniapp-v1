"""Aggregate first-stage ID-photo business-flow verification."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "id-photo-all-formats"
FINAL = REPORT_ROOT / "final"
GLOBAL_FINAL = ROOT / "reports" / "final"
SPEC_DISPLAY = ROOT / "reports" / "spec-display-cleanup"
MAX_AGE_SECONDS = 4 * 60 * 60
STEP_TIMEOUT_SECONDS = int(os.environ.get("ID_PHOTO_VERIFY_STEP_TIMEOUT_SECONDS", str(45 * 60)))


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "FAIL", "missing": True, "path": str(path), "fresh": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["path"] = str(path)
        data["fresh"] = time.time() - path.stat().st_mtime <= MAX_AGE_SECONDS
        return data
    except Exception as exc:
        return {"status": "FAIL", "error": str(exc), "path": str(path), "fresh": False}


def health(base_url: str, path: str) -> dict[str, Any]:
    try:
        res = requests.get(base_url.rstrip("/") + path, timeout=10)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:500]}
        return {
            "statusCode": res.status_code,
            "data": data,
            "passed": res.status_code == 200 and bool(data.get("success") or data.get("message") == "server running" or data.get("templates")),
        }
    except Exception as exc:
        return {"statusCode": 0, "error": str(exc), "passed": False}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_step(name: str, cmd: list[str]) -> dict[str, Any]:
    started = time.time()
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=STEP_TIMEOUT_SECONDS,
        )
        return {
            "name": name,
            "cmd": cmd,
            "returncode": completed.returncode,
            "passed": completed.returncode == 0,
            "durationSeconds": round(time.time() - started, 2),
            "stdoutTail": (completed.stdout or "")[-2000:],
            "stderrTail": (completed.stderr or "")[-2000:],
        }
    except Exception as exc:
        return {
            "name": name,
            "cmd": cmd,
            "returncode": 1,
            "passed": False,
            "durationSeconds": round(time.time() - started, 2),
            "error": str(exc),
        }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    base = args.base_url.rstrip("/")
    FINAL.mkdir(parents=True, exist_ok=True)
    GLOBAL_FINAL.mkdir(parents=True, exist_ok=True)

    runner = ["node", str(ROOT / "server" / "scripts" / "run_python.js")]
    preflight_runs = [
        run_step("all-formats", runner + ["server/scripts/verify_id_photo_all_formats.py", "--base-url", base]),
        run_step("quality-regression", runner + ["server/scripts/verify_id_photo_quality_regression.py", "--base-url", base]),
        run_step("local-vs-cloud", runner + ["server/scripts/verify_id_photo_local_vs_cloud.py", "--base-url", base]),
        run_step("frontend-backend-sync", runner + ["server/scripts/verify_frontend_backend_sync.py", "--base-url", base]),
        run_step("id-photo-main-flow", runner + ["server/scripts/verify_id_photo_main_flow.py", "--base-url", base]),
    ]

    reports = {
        "allFormats": load_json(FINAL / "spec-format-validation-report.json"),
        "qualityRegression": load_json(FINAL / "quality-threshold-fix-report.json"),
        "localVsCloud": load_json(FINAL / "local-vs-cloud-report.json"),
        "frontendBackendSync": load_json(SPEC_DISPLAY / "frontend-backend-sync-report.json"),
        "idPhotoMainFlow": load_json(SPEC_DISPLAY / "id-photo-main-flow-report.json"),
    }
    api_health = {
        "api": health(base, "/api/health"),
        "capabilities": health(base, "/api/id-photo/capabilities"),
    }
    all_formats = reports["allFormats"]
    quality = reports["qualityRegression"]
    local_cloud = reports["localVsCloud"]
    conditions = {
        "apiHealthPass": api_health["api"].get("passed") is True,
        "capabilitiesPass": api_health["capabilities"].get("passed") is True,
        "subVerificationsRan": all(item.get("passed") is True for item in preflight_runs),
        "allFormatsFreshPass": all_formats.get("status") == "PASS" and all_formats.get("fresh") is True,
        "allFrontendSpecsVerified": int(all_formats.get("validatedSpecCount") or 0) == int(all_formats.get("specCount") or -1),
        "allColorChecksPass": int(all_formats.get("failedColorChecks") or 0) == 0 and int(all_formats.get("colorChecks") or 0) > 0,
        "negativeRejected": ((all_formats.get("negative") or {}).get("passed") is True),
        "qualityRegressionFreshPass": quality.get("status") == "PASS" and quality.get("fresh") is True,
        "qualitySamplesCovered": int(quality.get("sampleCount") or 0) >= 4,
        "qualityFailuresZero": int(quality.get("failedQualityChecks") or 0) == 0,
        "qualityNegativeRejected": all(row.get("rejected") for row in (quality.get("negative") or [])),
        "localVsCloudRan": local_cloud.get("status") in {"PASS", "PASS_WITH_CLOUD_BLOCKED", "PASS_WITH_CLOUD_DEPLOYMENT_BLOCKED"} and local_cloud.get("fresh") is True,
        "cloudBlockedDocumentedOrPass": local_cloud.get("status") == "PASS" or local_cloud.get("cloudBlocked") is True or local_cloud.get("cloudDeploymentBlocked") is True,
        "frontendBackendSyncPass": reports["frontendBackendSync"].get("status") == "PASS" and reports["frontendBackendSync"].get("fresh") is True,
        "idPhotoMainFlowPass": reports["idPhotoMainFlow"].get("status") == "PASS" and reports["idPhotoMainFlow"].get("fresh") is True,
        "requiredFinalReportsGenerated": all(
            p.exists()
            for p in [
                FINAL / "root-cause.md",
                FINAL / "spec-format-validation-report.md",
                FINAL / "local-vs-cloud-report.md",
                FINAL / "quality-threshold-fix-report.md",
                FINAL / "fixed-files.md",
                FINAL / "spec-format-sample-comparison.jpg",
            ]
        ),
    }
    status = "PASS" if all(conditions.values()) else "FAIL"
    payload = {
        "status": status,
        "passed": status == "PASS",
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "baseUrl": base,
        "health": api_health,
        "preflightRuns": preflight_runs,
        "conditions": conditions,
        "reports": reports,
        "summary": {
            "specCount": int(all_formats.get("specCount") or 0),
            "validatedSpecCount": int(all_formats.get("validatedSpecCount") or 0),
            "colorChecks": int(all_formats.get("colorChecks") or 0),
            "qualityChecks": int(quality.get("qualityChecks") or 0),
            "cloudStatus": local_cloud.get("status"),
            "cloudBlocked": local_cloud.get("cloudBlocked"),
        },
    }
    write_json(FINAL / "full-business-flow-regression.json", payload)
    write_json(GLOBAL_FINAL / "full-business-flow-report.json", payload)
    lines = [
        "# Full Business Flow Regression",
        "",
        f"- Status: {status}",
        f"- Base URL: `{base}`",
        f"- Specs verified: {payload['summary']['validatedSpecCount']}/{payload['summary']['specCount']}",
        f"- Color checks: {payload['summary']['colorChecks']}",
        f"- Quality checks: {payload['summary']['qualityChecks']}",
        f"- Cloud status: `{payload['summary']['cloudStatus']}`",
        "",
        "## Conditions",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in conditions.items()],
        "",
        "## Sub Verification Commands",
        *[f"- {item.get('name')}: {'PASS' if item.get('passed') else 'FAIL'} ({item.get('durationSeconds')}s)" for item in preflight_runs],
        "",
        "## Report Files",
        *[f"- {name}: `{item.get('path', '')}` status={item.get('status')}" for name, item in reports.items()],
    ]
    write_md(FINAL / "full-business-flow-regression.md", lines)
    write_md(GLOBAL_FINAL / "full-business-flow-report.md", lines)
    print(f"[verify-id-photo-full-business-flow] {status} report={FINAL / 'full-business-flow-regression.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
