"""Run the spec-restore verification chain and assemble final reports."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "server" / "scripts"
RUN_PYTHON = SCRIPTS / "run_python.js"
FINAL = ROOT / "reports" / "spec-restore" / "final"
GLOBAL_FINAL = ROOT / "reports" / "final"
ALL_FORMAT_FINAL = ROOT / "reports" / "id-photo-all-formats" / "final"

SOURCE_CANDIDATES = [
    Path(r"C:\Users\zyu33\Desktop\b9fcfc995c64135f4be13197c85a96f0.jpg"),
    Path(r"C:\Users\zyu33\Desktop\cs.jpeg"),
    Path(r"C:\Users\zyu33\Desktop\444.jpg"),
    ROOT / "reports" / "id-photo-all-formats" / "samples" / "real_source_1.jpg",
]


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def py(script: str, *args: str) -> list[str]:
    return ["node", str(RUN_PYTHON), f"server/scripts/{script}", *args]


def run(cmd: list[str], timeout: int) -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    started = time.perf_counter()
    try:
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
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "returncode": -1,
            "passed": False,
            "durationMs": int((time.perf_counter() - started) * 1000),
            "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "",
            "error": f"timeout after {timeout}s",
        }


def request_json(url: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        res = requests.get(url, timeout=20)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:1200]}
        return {
            "ok": 200 <= res.status_code < 300,
            "statusCode": res.status_code,
            "durationMs": int((time.perf_counter() - started) * 1000),
            "data": data,
        }
    except Exception as exc:
        return {
            "ok": False,
            "statusCode": 0,
            "durationMs": int((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "FAIL", "missing": True, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data["path"] = str(path)
            return data
        return {"status": "FAIL", "error": "json root is not object", "path": str(path)}
    except Exception as exc:
        return {"status": "FAIL", "error": str(exc), "path": str(path)}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_report(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def first_source() -> Path:
    for path in SOURCE_CANDIDATES:
        if path.exists():
            return path
    return SOURCE_CANDIDATES[-1]


def cloud_report_paths(run_id: str) -> tuple[Path, Path]:
    base = ROOT / "reports" / "cloud-deploy-e2e" / run_id / "cloud-tests"
    return base / "cloud-real-business-flow-basic.json", base / "cloud-real-business-flow-basic.md"


def status_is_pass(report: dict[str, Any]) -> bool:
    return report.get("status") == "PASS"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cloud-url", default="https://tupzjianzhao.chat")
    args = parser.parse_args(argv)

    FINAL.mkdir(parents=True, exist_ok=True)
    GLOBAL_FINAL.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    cloud = args.cloud_url.rstrip("/")
    run_id = "spec-restore-" + time.strftime("%Y%m%d-%H%M%S")
    source = first_source()

    chain: dict[str, dict[str, Any]] = {}
    chain["specRestore"] = run(py("verify_id_photo_spec_restore.py", "--mode", "all"), timeout=120)
    chain["specVisibility"] = run(py("verify_id_photo_spec_visibility.py"), timeout=120)
    chain["specSearch"] = run(py("verify_id_photo_spec_search.py"), timeout=120)
    chain["specCategory"] = run(py("verify_id_photo_spec_category.py"), timeout=120)
    chain["specUi"] = run(py("verify_id_photo_spec_ui.py"), timeout=120)
    chain["allFormats"] = run(py("verify_id_photo_all_formats.py", "--base-url", base), timeout=3600)
    chain["qualityRegression"] = run(py("verify_id_photo_quality_regression.py", "--base-url", base), timeout=3600)
    chain["localVsCloud"] = run(py("verify_id_photo_local_vs_cloud.py", "--base-url", base, "--cloud-url", cloud), timeout=1200)
    chain["frontendBackendSync"] = run(py("verify_frontend_backend_sync.py", "--base-url", base), timeout=300)
    chain["idPhotoMainFlow"] = run(py("verify_id_photo_main_flow.py", "--base-url", base), timeout=420)
    chain["localBusinessFlow"] = run(py("verify_id_photo_full_business_flow.py", "--base-url", base), timeout=300)
    chain["cloudBusinessFlow"] = run(
        py("verify_cloud_real_business_flow.py", "--base-url", cloud, "--run-id", run_id, "--source-file", str(source)),
        timeout=1800,
    )

    cloud_json, cloud_md = cloud_report_paths(run_id)
    copies = {
        "allFormatMd": copy_report(ALL_FORMAT_FINAL / "spec-format-validation-report.md", FINAL / "all-format-validation-report.md"),
        "allFormatJson": copy_report(ALL_FORMAT_FINAL / "spec-format-validation-report.json", FINAL / "all-format-validation-report.json"),
        "localBusinessMd": copy_report(ALL_FORMAT_FINAL / "full-business-flow-regression.md", FINAL / "local-business-flow-report.md"),
        "localBusinessJson": copy_report(ALL_FORMAT_FINAL / "full-business-flow-regression.json", FINAL / "local-business-flow-report.json"),
        "cloudBusinessMd": copy_report(cloud_md, FINAL / "cloud-business-flow-report.md"),
        "cloudBusinessJson": copy_report(cloud_json, FINAL / "cloud-business-flow-report.json"),
    }

    local_health = request_json(base + "/api/health")
    cloud_health = request_json(cloud + "/api/health")
    cloud_retention = request_json(cloud + "/api/assets/retention-policy")
    cloud_deployment = {
        "status": "PASS" if cloud_health.get("ok") and cloud_retention.get("ok") else "FAIL",
        "generatedAt": now(),
        "cloudUrl": cloud,
        "cloudHealth": cloud_health,
        "retentionPolicy": cloud_retention,
        "retentionSeconds": ((cloud_retention.get("data") or {}).get("retentionSeconds")),
        "localhostUsedAsCloud": False,
    }
    write_json(FINAL / "cloud-deployment-report.json", cloud_deployment)
    write_md(FINAL / "cloud-deployment-report.md", [
        "# Cloud Deployment Report",
        "",
        f"- Status: {cloud_deployment['status']}",
        f"- Cloud URL: `{cloud}`",
        f"- Cloud health: {'PASS' if cloud_health.get('ok') else 'FAIL'}",
        f"- Retention policy endpoint: {'PASS' if cloud_retention.get('ok') else 'FAIL'}",
        f"- Retention seconds: `{cloud_deployment.get('retentionSeconds')}`",
        "- Localhost was not used as the cloud target.",
    ])

    reports = {
        "specRestore": load_json(FINAL / "final-summary.json"),
        "allFormats": load_json(FINAL / "all-format-validation-report.json"),
        "qualityRegression": load_json(ALL_FORMAT_FINAL / "quality-threshold-fix-report.json"),
        "localVsCloud": load_json(ALL_FORMAT_FINAL / "local-vs-cloud-report.json"),
        "localBusinessFlow": load_json(FINAL / "local-business-flow-report.json"),
        "cloudBusinessFlow": load_json(FINAL / "cloud-business-flow-report.json"),
        "cloudDeployment": cloud_deployment,
    }

    package_scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8")).get("scripts", {})
    required_scripts = [
        "verify:id-photo-spec-restore",
        "verify:id-photo-spec-visibility",
        "verify:id-photo-spec-search",
        "verify:id-photo-spec-category",
        "verify:id-photo-spec-ui",
        "verify:id-photo-all-formats",
        "verify:full-business-flow",
        "verify:all",
    ]
    required_report_names = [
        "old-vs-current-category-report.md",
        "current-visible-spec-audit.md",
        "spec-visibility-before-after.md",
        "restored-spec-list.md",
        "spec-search-report.md",
        "spec-category-report.md",
        "all-format-validation-report.md",
        "local-business-flow-report.md",
        "cloud-business-flow-report.md",
        "cloud-deployment-report.md",
        "fixed-files.md",
    ]
    conditions = {
        "localHealthPass": local_health.get("ok") is True,
        "requiredNpmScriptsPresent": all(name in package_scripts for name in required_scripts),
        "staticSpecRestorePass": all(chain[name].get("passed") for name in ["specRestore", "specVisibility", "specSearch", "specCategory", "specUi"]),
        "allFormatsPass": status_is_pass(reports["allFormats"]),
        "qualityRegressionPass": status_is_pass(reports["qualityRegression"]),
        "localVsCloudPassOrDocumented": reports["localVsCloud"].get("status") in {"PASS", "PASS_WITH_CLOUD_BLOCKED", "PASS_WITH_CLOUD_DEPLOYMENT_BLOCKED"},
        "localBusinessFlowPass": status_is_pass(reports["localBusinessFlow"]),
        "cloudBusinessFlowPass": status_is_pass(reports["cloudBusinessFlow"]),
        "cloudDeploymentPass": cloud_deployment.get("status") == "PASS",
        "cloudRetentionSeconds86400": cloud_deployment.get("retentionSeconds") == 86400,
        "requiredReportsGenerated": all(copies.values()) and all((FINAL / name).exists() for name in required_report_names),
    }
    status = "PASS" if all(conditions.values()) else "FAIL"
    payload = {
        "status": status,
        "generatedAt": now(),
        "runId": run_id,
        "baseUrl": base,
        "cloudUrl": cloud,
        "sourceFile": str(source),
        "localHealth": local_health,
        "chain": chain,
        "copies": copies,
        "reports": reports,
        "conditions": conditions,
    }
    write_json(FINAL / "final-summary.json", payload)
    write_json(GLOBAL_FINAL / "verify-all-report.json", payload)
    lines = [
        "# Spec Restore Verify All Report",
        "",
        f"- Status: {status}",
        f"- Run ID: `{run_id}`",
        f"- Base URL: `{base}`",
        f"- Cloud URL: `{cloud}`",
        "",
        "## Commands",
    ]
    lines.extend([f"- {name}: {'PASS' if item.get('passed') else 'FAIL'} ({item.get('durationMs')}ms)" for name, item in chain.items()])
    lines.extend(["", "## Conditions"])
    lines.extend([f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in conditions.items()])
    lines.extend(["", "## Reports"])
    for name, report in reports.items():
        lines.append(f"- {name}: status=`{report.get('status')}` path=`{report.get('path', '')}`")
    write_md(FINAL / "verify-all-report.md", lines)
    write_md(GLOBAL_FINAL / "verify-all-report.md", lines)
    print(f"[verify-spec-restore-all] {status} report={FINAL / 'final-summary.json'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
