"""Run the current spec-cleanup verification chain and assemble final reports."""
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
SPEC_FINAL = ROOT / "reports" / "spec-cleanup" / "final"
ALL_FORMAT_FINAL = ROOT / "reports" / "id-photo-all-formats" / "final"
GLOBAL_FINAL = ROOT / "reports" / "final"

SOURCE_CANDIDATES = [
    Path(r"C:\Users\zyu33\Desktop\b9fcfc995c64135f4be13197c85a96f0.jpg"),
    Path(r"C:\Users\zyu33\Desktop\cs.jpeg"),
    Path(r"C:\Users\zyu33\Desktop\444.jpg"),
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
            "stdout": completed.stdout[-10000:],
            "stderr": completed.stderr[-10000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "returncode": -1,
            "passed": False,
            "durationMs": int((time.perf_counter() - started) * 1000),
            "stdout": (exc.stdout or "")[-10000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-10000:] if isinstance(exc.stderr, str) else "",
            "error": f"timeout after {timeout}s",
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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_report(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def request_json(url: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        res = requests.get(url, timeout=20)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:1000]}
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


def first_source() -> Path:
    for path in SOURCE_CANDIDATES:
        if path.exists():
            return path
    return ROOT / "reports" / "id-photo-all-formats" / "samples" / "real_source_1.jpg"


def cloud_report_paths(run_id: str) -> tuple[Path, Path]:
    base = ROOT / "reports" / "cloud-deploy-e2e" / run_id / "cloud-tests"
    return base / "cloud-real-business-flow-basic.json", base / "cloud-real-business-flow-basic.md"


def assemble_cloud_deployment_report(cloud_url: str, local_vs_cloud: dict[str, Any], cloud_flow: dict[str, Any], cloud_step: dict[str, Any]) -> dict[str, Any]:
    cloud_health = request_json(cloud_url.rstrip("/") + "/api/health")
    status = "PASS" if local_vs_cloud.get("status") == "PASS" and cloud_flow.get("status") == "PASS" else "FAIL"
    blocked = local_vs_cloud.get("status") in {"PASS_WITH_CLOUD_BLOCKED", "PASS_WITH_CLOUD_DEPLOYMENT_BLOCKED"} or cloud_step.get("passed") is not True
    payload = {
        "status": status,
        "generatedAt": now(),
        "cloudUrl": cloud_url,
        "cloudHealth": cloud_health,
        "localVsCloudStatus": local_vs_cloud.get("status"),
        "cloudBusinessFlowStatus": cloud_flow.get("status"),
        "cloudBlocked": bool(local_vs_cloud.get("cloudBlocked")),
        "cloudDeploymentBlocked": bool(local_vs_cloud.get("cloudDeploymentBlocked")) or blocked,
        "deploymentAction": "verified_existing_cloud_release" if status == "PASS" else "remote_release_not_confirmed",
        "note": "This report only marks PASS when the live cloud host itself passes. Localhost is not used as a substitute.",
    }
    write_json(SPEC_FINAL / "cloud-deployment-report.json", payload)
    lines = [
        "# Cloud Deployment Report",
        "",
        f"- Status: {status}",
        f"- Cloud URL: `{cloud_url}`",
        f"- Cloud health: {'PASS' if cloud_health.get('ok') else 'FAIL'}",
        f"- Local-vs-cloud status: `{payload['localVsCloudStatus']}`",
        f"- Cloud business flow status: `{payload['cloudBusinessFlowStatus']}`",
        f"- Deployment action: `{payload['deploymentAction']}`",
        f"- Cloud deployment blocked: `{payload['cloudDeploymentBlocked']}`",
        "",
        "Localhost was not used as the cloud target.",
    ]
    write_md(SPEC_FINAL / "cloud-deployment-report.md", lines)
    return payload


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cloud-url", default="https://tupzjianzhao.chat")
    args = parser.parse_args(argv)

    SPEC_FINAL.mkdir(parents=True, exist_ok=True)
    GLOBAL_FINAL.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    cloud = args.cloud_url.rstrip("/")
    run_id = "spec-cleanup-" + time.strftime("%Y%m%d-%H%M%S")
    source = first_source()

    chain: dict[str, dict[str, Any]] = {}
    chain["specCatalog"] = run(py("verify_id_photo_spec_catalog.py"), timeout=120)
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
        "allFormatMd": copy_report(ALL_FORMAT_FINAL / "spec-format-validation-report.md", SPEC_FINAL / "all-format-validation-report.md"),
        "allFormatJson": copy_report(ALL_FORMAT_FINAL / "spec-format-validation-report.json", SPEC_FINAL / "all-format-validation-report.json"),
        "localBusinessMd": copy_report(ALL_FORMAT_FINAL / "full-business-flow-regression.md", SPEC_FINAL / "local-business-flow-report.md"),
        "localBusinessJson": copy_report(ALL_FORMAT_FINAL / "full-business-flow-regression.json", SPEC_FINAL / "local-business-flow-report.json"),
        "cloudBusinessMd": copy_report(cloud_md, SPEC_FINAL / "cloud-business-flow-report.md"),
        "cloudBusinessJson": copy_report(cloud_json, SPEC_FINAL / "cloud-business-flow-report.json"),
    }

    reports = {
        "specCatalog": load_json(SPEC_FINAL / "spec-catalog-report.json"),
        "specUi": load_json(SPEC_FINAL / "spec-ui-report.json"),
        "allFormats": load_json(SPEC_FINAL / "all-format-validation-report.json"),
        "qualityRegression": load_json(ALL_FORMAT_FINAL / "quality-threshold-fix-report.json"),
        "localVsCloud": load_json(ALL_FORMAT_FINAL / "local-vs-cloud-report.json"),
        "localBusinessFlow": load_json(SPEC_FINAL / "local-business-flow-report.json"),
        "cloudBusinessFlow": load_json(SPEC_FINAL / "cloud-business-flow-report.json"),
    }
    cloud_deploy = assemble_cloud_deployment_report(cloud, reports["localVsCloud"], reports["cloudBusinessFlow"], chain["cloudBusinessFlow"])
    reports["cloudDeployment"] = cloud_deploy

    package_scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8")).get("scripts", {})
    required_scripts = [
        "verify:id-photo-spec-catalog",
        "verify:id-photo-spec-ui",
        "verify:id-photo-all-formats",
        "verify:id-photo-quality-regression",
        "verify:full-business-flow",
        "verify:all",
    ]
    conditions = {
        "requiredNpmScriptsPresent": all(name in package_scripts for name in required_scripts),
        "specCatalogPass": reports["specCatalog"].get("status") == "PASS",
        "specUiPass": reports["specUi"].get("status") == "PASS",
        "allFormatsPass": reports["allFormats"].get("status") == "PASS",
        "qualityRegressionPass": reports["qualityRegression"].get("status") == "PASS",
        "localVsCloudPass": reports["localVsCloud"].get("status") == "PASS",
        "localBusinessFlowPass": reports["localBusinessFlow"].get("status") == "PASS",
        "cloudBusinessFlowPass": reports["cloudBusinessFlow"].get("status") == "PASS",
        "cloudDeploymentPass": reports["cloudDeployment"].get("status") == "PASS",
        "requiredReportsGenerated": all(copies.values())
        and all((SPEC_FINAL / name).exists() for name in [
            "spec-catalog-report.md",
            "spec-diff-before-after.md",
            "spec-ui-report.md",
            "all-format-validation-report.md",
            "local-business-flow-report.md",
            "cloud-business-flow-report.md",
            "cloud-deployment-report.md",
            "fixed-files.md",
        ]),
    }
    status = "PASS" if all(conditions.values()) else "FAIL"
    payload = {
        "status": status,
        "generatedAt": now(),
        "baseUrl": base,
        "cloudUrl": cloud,
        "runId": run_id,
        "sourceFile": str(source),
        "chain": chain,
        "reports": reports,
        "conditions": conditions,
        "copies": copies,
    }
    write_json(SPEC_FINAL / "final-summary.json", payload)
    write_json(GLOBAL_FINAL / "verify-all-report.json", payload)
    lines = [
        "# Verify All Report",
        "",
        f"- Status: {status}",
        f"- Base URL: `{base}`",
        f"- Cloud URL: `{cloud}`",
        f"- Run ID: `{run_id}`",
        "",
        "## Commands",
    ]
    lines.extend([f"- {name}: {'PASS' if item.get('passed') else 'FAIL'} ({item.get('durationMs')}ms)" for name, item in chain.items()])
    lines.extend(["", "## Conditions"])
    lines.extend([f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in conditions.items()])
    lines.extend(["", "## Reports"])
    for name, item in reports.items():
        lines.append(f"- {name}: status=`{item.get('status')}` path=`{item.get('path', '')}`")
    write_md(SPEC_FINAL / "verify-all-report.md", lines)
    write_md(GLOBAL_FINAL / "verify-all-report.md", lines)
    print(f"[verify-spec-cleanup-all] {status} report={SPEC_FINAL / 'final-summary.json'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
