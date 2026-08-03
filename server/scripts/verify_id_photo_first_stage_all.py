"""Run the complete first-stage ID-photo repair verification chain."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "server" / "scripts"
RUN_PYTHON = SCRIPTS / "run_python.js"
REPORT_ROOT = ROOT / "reports" / "id-photo-all-formats"
FINAL = REPORT_ROOT / "final"
GLOBAL_FINAL = ROOT / "reports" / "final"


def run(cmd: list[str], timeout: int) -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    started = time.perf_counter()
    completed = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )
    return {
        "cmd": cmd,
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "durationMs": int((time.perf_counter() - started) * 1000),
        "stdout": completed.stdout[-8000:],
        "stderr": completed.stderr[-8000:],
    }


def py(script: str, *args: str) -> list[str]:
    return ["node", str(RUN_PYTHON), f"server/scripts/{script}", *args]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "FAIL", "missing": True, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["path"] = str(path)
        return data
    except Exception as exc:
        return {"status": "FAIL", "error": str(exc), "path": str(path)}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cloud-url", default=os.environ.get("ID_PHOTO_CLOUD_URL", "https://tupzjianzhao.chat"))
    args = parser.parse_args(argv)
    FINAL.mkdir(parents=True, exist_ok=True)
    GLOBAL_FINAL.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")

    chain = {
        "idPhotoAllFormats": run(py("verify_id_photo_all_formats.py", "--base-url", base), timeout=3600),
        "idPhotoQualityRegression": run(py("verify_id_photo_quality_regression.py", "--base-url", base), timeout=3600),
        "idPhotoLocalVsCloud": run(py("verify_id_photo_local_vs_cloud.py", "--base-url", base, "--cloud-url", args.cloud_url), timeout=900),
        "frontendBackendSync": run(py("verify_frontend_backend_sync.py", "--base-url", base), timeout=300),
        "idPhotoMainFlow": run(py("verify_id_photo_main_flow.py", "--base-url", base), timeout=420),
    }
    chain["fullBusinessFlow"] = run(py("verify_id_photo_full_business_flow.py", "--base-url", base), timeout=300)

    reports = {
        "specFormat": load_json(FINAL / "spec-format-validation-report.json"),
        "qualityRegression": load_json(FINAL / "quality-threshold-fix-report.json"),
        "localVsCloud": load_json(FINAL / "local-vs-cloud-report.json"),
        "fullBusinessFlow": load_json(FINAL / "full-business-flow-regression.json"),
    }
    conditions = {
        "allCommandsRan": all(item.get("returncode") is not None for item in chain.values()),
        "allFormatCommandPass": chain["idPhotoAllFormats"].get("passed") is True,
        "qualityRegressionCommandPass": chain["idPhotoQualityRegression"].get("passed") is True,
        "localVsCloudCommandPass": chain["idPhotoLocalVsCloud"].get("passed") is True,
        "frontendBackendSyncCommandPass": chain["frontendBackendSync"].get("passed") is True,
        "idPhotoMainFlowCommandPass": chain["idPhotoMainFlow"].get("passed") is True,
        "fullBusinessFlowCommandPass": chain["fullBusinessFlow"].get("passed") is True,
        "specFormatReportPass": reports["specFormat"].get("status") == "PASS",
        "qualityRegressionReportPass": reports["qualityRegression"].get("status") == "PASS",
        "localVsCloudReportNotFailed": reports["localVsCloud"].get("status") in {"PASS", "PASS_WITH_CLOUD_BLOCKED", "PASS_WITH_CLOUD_DEPLOYMENT_BLOCKED"},
        "fullBusinessFlowReportPass": reports["fullBusinessFlow"].get("status") == "PASS",
        "requiredReportsGenerated": all(
            path.exists()
            for path in [
                FINAL / "root-cause.md",
                FINAL / "spec-format-validation-report.md",
                FINAL / "local-vs-cloud-report.md",
                FINAL / "quality-threshold-fix-report.md",
                FINAL / "fixed-files.md",
                FINAL / "full-business-flow-regression.md",
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
        "cloudUrl": args.cloud_url,
        "chain": chain,
        "reports": reports,
        "conditions": conditions,
        "summary": {
            "specCount": reports["specFormat"].get("specCount"),
            "validatedSpecCount": reports["specFormat"].get("validatedSpecCount"),
            "colorChecks": reports["specFormat"].get("colorChecks"),
            "qualityChecks": reports["qualityRegression"].get("qualityChecks"),
            "cloudStatus": reports["localVsCloud"].get("status"),
        },
    }
    write_json(FINAL / "final-summary.json", payload)
    write_json(GLOBAL_FINAL / "verify-all-report.json", payload)
    lines = [
        "# Verify All Report",
        "",
        f"- Status: {status}",
        f"- Base URL: `{base}`",
        f"- Cloud URL: `{args.cloud_url}`",
        f"- Specs verified: {payload['summary']['validatedSpecCount']}/{payload['summary']['specCount']}",
        f"- Color checks: {payload['summary']['colorChecks']}",
        f"- Quality checks: {payload['summary']['qualityChecks']}",
        f"- Cloud status: `{payload['summary']['cloudStatus']}`",
        "",
        "## Commands",
        *[f"- {name}: {'PASS' if item.get('passed') else 'FAIL'} ({item.get('durationMs')}ms)" for name, item in chain.items()],
        "",
        "## Conditions",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in conditions.items()],
        "",
        "## Reports",
        *[f"- {name}: `{item.get('path', '')}` status={item.get('status')}" for name, item in reports.items()],
    ]
    write_md(GLOBAL_FINAL / "verify-all-report.md", lines)
    write_md(FINAL / "verify-all-report.md", lines)
    print(f"[verify-id-photo-first-stage-all] {status} report={GLOBAL_FINAL / 'verify-all-report.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
