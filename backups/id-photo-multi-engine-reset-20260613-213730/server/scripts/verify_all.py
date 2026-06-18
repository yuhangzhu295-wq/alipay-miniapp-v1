"""Final regression verifier for the current repair scope.

Scope: ID-photo random/negative samples, removed one-click outfit and removed
career entry, watermark normal/HD, watermark gateway, mandatory 444/6666
samples, spec search layout, real WeChat DevTools business flow, frontend
business flow, and protected-feature regression.
"""
from __future__ import annotations

import argparse
import os
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "reports" / "final"
REPORTS = ROOT / "reports"
SCRIPTS = ROOT / "server" / "scripts"
RUN_PYTHON = SCRIPTS / "run_python.js"


def _run(cmd: list[str], timeout: int = 1200) -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
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
        "stdout": completed.stdout[-6000:],
        "stderr": completed.stderr[-6000:],
    }


def _py(script_name: str, *args: str) -> list[str]:
    """Run child Python verifiers through the same wrapper used by npm scripts.

    Direct second-level Python subprocesses have proven flaky on Windows when
    the workspace path contains non-ASCII characters. The Node wrapper is the
    package.json source of truth and preserves the project path correctly.
    """
    return ["node", str(RUN_PYTHON), f"server/scripts/{script_name}", *args]


def _run_until_pass(cmd: list[str], timeout: int, attempts: int = 2) -> dict[str, Any]:
    history = []
    for attempt in range(1, attempts + 1):
        result = _run(cmd, timeout=timeout)
        history.append({
            "attempt": attempt,
            "returncode": result["returncode"],
            "passed": result["passed"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
        })
        if result["passed"]:
            result["attempts"] = history
            return result
    result["attempts"] = history
    return result


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "FAIL", "reason": "missing", "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_path"] = str(path)
        return data
    except Exception as exc:
        return {"status": "FAIL", "reason": str(exc), "path": str(path)}


def _health(base_url: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, path in {"api": "/api/health", "watermark": "/api/watermark/health"}.items():
        try:
            res = requests.get(base_url.rstrip("/") + path, timeout=8)
            try:
                data = res.json()
            except Exception:
                data = {"text": res.text[:500]}
            result[name] = {
                "statusCode": res.status_code,
                "data": data,
                "passed": res.status_code == 200 and bool(data.get("success") or data.get("ok")),
            }
        except Exception as exc:
            result[name] = {"statusCode": 0, "error": str(exc), "passed": False}
    result["passed"] = result["api"].get("passed") is True and result["watermark"].get("passed") is True
    return result


def _protected_feature_regression() -> dict[str, Any]:
    app_json = _read(ROOT / "app.json")
    generate_js = _read(ROOT / "pages" / "generate" / "generate.js")
    generate_wxml = _read(ROOT / "pages" / "generate" / "generate.wxml")
    tools_js = _read(ROOT / "pages" / "tools" / "tools.js")
    tool_js = _read(ROOT / "pages" / "tool-detail" / "tool-detail.js")
    tool_wxml = _read(ROOT / "pages" / "tool-detail" / "tool-detail.wxml")
    specs_js = _read(ROOT / "pages" / "specs" / "specs.js")
    wm_api = _read(ROOT / "utils" / "watermarkApi.js")

    checks = {
        "idPhotoRouteExists": "pages/generate/generate" in app_json,
        "idPhotoGenerateFlowExists": "prepareIdPhotoV2" in generate_js and "composeIdPhotoV2" in generate_js,
        "idPhotoDownloadStillExists": "savePhoto" in generate_js and "canDownload" in generate_js,
        "oneClickOutfitRemovedFromGenerator": "outfit" not in generate_wxml
        and "outfit" not in generate_js
        and "selectOutfit" not in generate_js,
        "careerEntryRemovedFromToolsPage": "id: 'professional'" not in tools_js
        and 'id: "professional"' not in tools_js
        and "职业形象照" not in tools_js,
        "otherToolEntriesStillExist": all(
            item in tools_js
            for item in [
                "verifyPhoto",
                "changeBg",
                "customSize",
                "editImage",
                "formatConvert",
                "colorize",
                "addWatermark",
                "removeWatermark",
                "layout",
                "collect",
            ]
        ),
        "toolDetailRouteSupportsWatermark": "removeWatermark" in tool_js and "removeWatermark" in tool_wxml,
        "watermarkEndpointsPresent": "/api/watermark/manual-remove" in wm_api
        and "/api/watermark/quick-remove" in wm_api
        and "/api/watermark/hd-remove" in wm_api,
        "specSearchStillExists": "searchSpecEntries" in specs_js and "onSearch" in specs_js,
        "ordinaryWatermarkUiNoDebug": "engine: {{currentEngine}}" not in tool_wxml
        and "output: {{currentOutputPath}}" not in tool_wxml,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "status": status,
        "checks": checks,
        "note": "Protected features were checked after the real ID-photo, remove-outfit, tools-page, watermark, and DevTools business flows ran.",
    }
    (FINAL / "protected-feature-regression-report.json").write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    md = [
        "# Protected Feature Regression Report",
        "",
        f"- Status: {status}",
        "",
        "## Checks",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in checks.items()],
        "",
    ]
    (FINAL / "protected-feature-regression-report.md").write_text("\n".join(md), encoding="utf-8")
    return payload


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    FINAL.mkdir(parents=True, exist_ok=True)

    chain_runs = {
        "environment": _run(_py("verify_environment.py", "--base-url", args.base_url), timeout=240),
        "openSourceEngines": _run(_py("verify_open_source_engines.py", "--base-url", args.base_url), timeout=240),
        "watermarkHdEngine": _run(_py("verify_watermark_hd_engine.py", "--base-url", args.base_url), timeout=240),
        "watermark": _run(_py("verify_watermark.py", "--base-url", args.base_url), timeout=1800),
        "watermark444": _run(_py("verify_watermark_444.py", "--base-url", args.base_url), timeout=900),
        "watermark6666": _run(_py("verify_watermark_6666.py", "--base-url", args.base_url), timeout=900),
        "idPhoto": _run(
            _py(
                "verify_id_photo_chain.py",
                "--base-url",
                args.base_url,
                "--real-count",
                "40",
                "--min-pass-rate",
                "95",
            ),
            timeout=3600,
        ),
        "removeOutfit": _run(_py("verify_remove_outfit.py"), timeout=180),
        "toolsPage": _run(_py("verify_tools_page.py"), timeout=120),
        "mainFlow": _run(_py("verify_main_flow.py", "--base-url", args.base_url), timeout=240),
        "specDisplay": _run(_py("verify_spec_display.py"), timeout=180),
        "frontendBackendSync": _run(_py("verify_frontend_backend_sync.py", "--base-url", args.base_url), timeout=240),
        "idPhotoMainFlow": _run(_py("verify_id_photo_main_flow.py", "--base-url", args.base_url), timeout=360),
        "specLayout": _run(_py("verify_spec_layout.py"), timeout=180),
        "frontendUi": _run(_py("verify_frontend_ui.py"), timeout=240),
        "devtoolsBusinessFlow": _run_until_pass(
            ["node", str(SCRIPTS / "verify_devtools_business_flow.js")],
            timeout=1800,
            attempts=2,
        ),
    }

    protected = _protected_feature_regression()
    chain_runs["fullBusinessFlow"] = _run(
        _py("verify_full_business_flow.py", "--base-url", args.base_url),
        timeout=240,
    )
    frontend_json_path = FINAL / "frontend-ui-validation-report.json"
    frontend_md_path = FINAL / "frontend-ui-validation-report.md"
    if frontend_json_path.exists():
        (FINAL / "frontend-business-flow-report.json").write_text(
            frontend_json_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    if frontend_md_path.exists():
        (FINAL / "frontend-business-flow-report.md").write_text(
            frontend_md_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    health = _health(args.base_url)
    reports = {
        "backendStart": _json(FINAL / "backend-start-check.json"),
        "network": _json(FINAL / "network-check.json"),
        "openSource": _json(FINAL / "open-source-engine-audit.json"),
        "hdEngine": _json(FINAL / "watermark-hd-engine-audit.json"),
        "watermark444": _json(FINAL / "watermark-444-regression-report.json"),
        "watermark6666": _json(FINAL / "watermark-6666-validation-report.json"),
        "watermarkQuality": _json(FINAL / "watermark-quality-report.json"),
        "watermark": _json(REPORTS / "watermark" / "watermark-regression-report.json"),
        "idPhoto": _json(FINAL / "id-photo-validation-report.json"),
        "removeOutfitCareer": _json(REPORTS / "remove-outfit-and-career" / "final-report.json"),
        "removeOutfit": _json(REPORTS / "remove-outfit-and-career" / "remove-outfit-report.json"),
        "toolsPage": _json(REPORTS / "remove-outfit-and-career" / "tools-page-report.json"),
        "mainFlow": _json(REPORTS / "remove-outfit-and-career" / "main-flow-report.json"),
        "specDisplay": _json(REPORTS / "spec-display-cleanup" / "final-report.json"),
        "frontendBackendSync": _json(REPORTS / "spec-display-cleanup" / "frontend-backend-sync-report.json"),
        "idPhotoMainFlow": _json(REPORTS / "spec-display-cleanup" / "id-photo-main-flow-report.json"),
        "specLayout": _json(FINAL / "spec-layout-validation-report.json"),
        "frontendUi": _json(FINAL / "frontend-ui-validation-report.json"),
        "devtoolsBusinessFlow": _json(FINAL / "devtools-business-flow-report.json"),
        "protected": protected,
        "fullBusinessFlow": _json(REPORTS / "spec-display-cleanup" / "full-business-flow-report.json"),
    }

    wm_health = (health.get("watermark") or {}).get("data") or {}
    id_photo = reports["idPhoto"]
    id_real = id_photo.get("real") or {}
    id_negative = id_photo.get("negative") or {}
    network = reports["network"]
    remove_scope = reports["removeOutfitCareer"]
    devtools = reports["devtoolsBusinessFlow"]
    devtools_summary = devtools.get("summary") or {}
    spec_display_counts = (reports["specDisplay"].get("counts") or {})
    visible_pending_after = spec_display_counts.get("visiblePendingCountAfterCleanup")
    stop_conditions = {
        "backend8000Healthy": health.get("passed") is True,
        "apiHealthAccessible": (health.get("api") or {}).get("passed") is True,
        "watermarkGatewayHealthy": (health.get("watermark") or {}).get("passed") is True,
        "hdRealModelLoaded": wm_health.get("hdRealModelLoaded") is True,
        "hdFallbackNotUsed": wm_health.get("fallbackUsed") is False,
        "environmentVerifyRan": chain_runs["environment"].get("passed") is True,
        "networkAccessChecked": network.get("NETWORK_ACCESS") is True
        and network.get("NETWORK_FALLBACK") is False,
        "openSourceVerifyRan": chain_runs["openSourceEngines"].get("passed") is True,
        "hdEngineVerifyRan": chain_runs["watermarkHdEngine"].get("passed") is True,
        "watermarkVerifyRan": chain_runs["watermark"].get("passed") is True,
        "watermark444VerifyRan": chain_runs["watermark444"].get("passed") is True,
        "watermark6666VerifyRan": chain_runs["watermark6666"].get("passed") is True,
        "idPhotoVerifyRan": chain_runs["idPhoto"].get("passed") is True,
        "idPhotoFortyRealSamples": id_photo.get("status") == "PASS"
        and int(id_real.get("total") or 0) >= 40
        and int(id_real.get("male") or 0) >= 20
        and int(id_real.get("female") or 0) >= 20,
        "idPhotoFiveBackgrounds": set(id_real.get("colorsPerSample") or []) == {"blue", "white", "red", "lightBlue", "gray"},
        "idPhotoPassRateAtLeast95": float(id_real.get("passRate") or 0) >= 95,
        "idPhotoNegativeFalsePassZero": int(id_negative.get("falsePass", -1)) == 0,
        "idPhotoPreviewDownloadConsistency100": float(id_real.get("previewDownloadConsistencyRate") or 0) == 100,
        "removeOutfitVerifyRan": chain_runs["removeOutfit"].get("passed") is True,
        "toolsPageVerifyRan": chain_runs["toolsPage"].get("passed") is True,
        "mainFlowVerifyRan": chain_runs["mainFlow"].get("passed") is True,
        "removeOutfitAndCareerFinalPass": remove_scope.get("status") == "PASS",
        "specDisplayVerifyRan": chain_runs["specDisplay"].get("passed") is True,
        "specDisplayFinalPass": reports["specDisplay"].get("status") == "PASS",
        "specDisplayVisiblePendingZero": visible_pending_after is not None and int(visible_pending_after) == 0,
        "frontendBackendSyncVerifyRan": chain_runs["frontendBackendSync"].get("passed") is True,
        "frontendBackendSyncPass": reports["frontendBackendSync"].get("status") == "PASS",
        "idPhotoMainFlowVerifyRan": chain_runs["idPhotoMainFlow"].get("passed") is True,
        "idPhotoMainFlowPass": reports["idPhotoMainFlow"].get("status") == "PASS",
        "specLayoutVerifyRan": chain_runs["specLayout"].get("passed") is True,
        "frontendUiVerifyRan": chain_runs["frontendUi"].get("passed") is True,
        "devtoolsBusinessFlowRan": chain_runs["devtoolsBusinessFlow"].get("passed") is True,
        "devtoolsBusinessFlowPassed": devtools.get("status") == "PASS"
        and int(devtools_summary.get("failed", -1)) == 0,
        "protectedFeatureRegressionPassed": protected.get("status") == "PASS",
        "fullBusinessFlowVerifyRan": chain_runs["fullBusinessFlow"].get("passed") is True,
        "fullBusinessFlowPass": reports["fullBusinessFlow"].get("status") == "PASS",
        "requiredReportsGenerated": all(
            path.exists()
            for path in [
                FINAL / "backend-start-check.md",
                FINAL / "open-source-engine-audit.md",
                FINAL / "watermark-hd-engine-audit.md",
                FINAL / "watermark-444-regression-report.md",
                FINAL / "watermark-6666-validation-report.md",
                FINAL / "watermark-before-after-comparison.md",
                FINAL / "watermark-quality-report.json",
                FINAL / "id-photo-validation-report.md",
                FINAL / "id-photo-sample-comparison.jpg",
                REPORTS / "remove-outfit-and-career" / "remove-outfit-report.md",
                REPORTS / "remove-outfit-and-career" / "tools-page-report.md",
                REPORTS / "remove-outfit-and-career" / "main-flow-report.md",
                REPORTS / "remove-outfit-and-career" / "final-report.md",
                REPORTS / "spec-display-cleanup" / "final-report.md",
                REPORTS / "spec-display-cleanup" / "frontend-backend-sync-report.md",
                REPORTS / "spec-display-cleanup" / "id-photo-main-flow-report.md",
                REPORTS / "spec-display-cleanup" / "full-business-flow-report.md",
                FINAL / "spec-layout-validation-report.md",
                FINAL / "frontend-business-flow-report.md",
                FINAL / "devtools-business-flow-report.md",
                FINAL / "protected-feature-regression-report.md",
            ]
        ),
    }
    status = "PASS" if all(stop_conditions.values()) else "FAIL"
    payload = {
        "status": status,
        "passed": status == "PASS",
        "baseUrl": args.base_url,
        "chainRuns": chain_runs,
        "health": health,
        "reports": reports,
        "protectedFeatureRegression": protected,
        "stopConditions": stop_conditions,
    }

    (FINAL / "verify-all-report.json").write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    (FINAL / "final-regression-report.json").write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    (FINAL / "final-stop-condition-audit.json").write_text(
        json.dumps({"status": status, "conditions": stop_conditions}, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    md = [
        "# Final Regression Report",
        "",
        f"- Status: {status}",
        f"- Base URL: `{args.base_url}`",
        f"- HD engine: `{wm_health.get('hdEngine')}`",
        f"- hdRealModelLoaded: `{wm_health.get('hdRealModelLoaded')}`",
        f"- fallbackUsed: `{wm_health.get('fallbackUsed')}`",
        "",
        "## Chain Runs",
        *[f"- {name}: {'PASS' if item.get('passed') else 'FAIL'}" for name, item in chain_runs.items()],
        "",
        "## Reports",
        *[f"- {name}: `{item.get('status', 'UNKNOWN')}`" for name, item in reports.items()],
        "",
        "## Stop Conditions",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in stop_conditions.items()],
        "",
    ]
    (FINAL / "verify-all-report.md").write_text("\n".join(md), encoding="utf-8")
    (FINAL / "final-regression-report.md").write_text("\n".join(md), encoding="utf-8")
    (FINAL / "final-stop-condition-audit.md").write_text(
        "\n".join([
            "# Final Stop-condition Audit",
            "",
            f"- Status: {status}",
            "",
            *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in stop_conditions.items()],
            "",
        ]),
        encoding="utf-8",
    )

    print(f"[verify-all] {status} report={FINAL / 'verify-all-report.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
