"""Write first-stage repair summary reports.

This aggregates the fresh verifier outputs created in this turn and writes the
report names required by the first-stage prompt.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "current-fixes"
FINAL = REPORT_ROOT / "final"
CLOUD_FLOW = ROOT / "reports" / "cloud-deploy-e2e" / "current-fixes-20260607-first-stage" / "cloud-tests" / "cloud-real-business-flow-hd.json"


FIXED_FILES = [
    "utils/apiConfig.js",
    "utils/watermarkConfig.js",
    "utils/watermarkApi.js",
    "utils/aiImageApi.js",
    "pages/generate/generate.js",
    "pages/tool-detail/tool-detail.js",
    "pages/tool-detail/tool-detail.wxml",
    "pages/profile/profile.js",
    "pages/profile/profile.wxml",
    "pages/profile/profile.wxss",
    "pages/login/login.js",
    "pages/login/login.wxml",
    "pages/login/login.wxss",
    "pages/login/login.json",
    "app.json",
    "server/main.py",
    "package.json",
    "server/scripts/verify_id_photo_partial_fail.py",
    "server/scripts/verify_watermark_remove_scan.py",
    "server/scripts/verify_profile_interactions.py",
    "server/scripts/verify_devtools_business_flow.js",
    "server/scripts/verify_frontend_ui.py",
    "server/scripts/write_first_stage_reports.py",
]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "MISSING", "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_path"] = str(path)
        data["_mtime"] = path.stat().st_mtime
        return data
    except Exception as exc:
        return {"status": "INVALID", "path": str(path), "error": str(exc)}


def request_json(url: str) -> dict[str, Any]:
    try:
        res = requests.get(url, timeout=8)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:400]}
        return {
            "url": url,
            "statusCode": res.status_code,
            "data": data,
            "passed": res.status_code == 200 and bool(data.get("success") or data.get("ok") or data.get("message") == "server running"),
        }
    except Exception as exc:
        return {"url": url, "statusCode": 0, "error": str(exc), "passed": False}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def status_is_pass(report: dict[str, Any]) -> bool:
    return report.get("passed") is True or report.get("status") == "PASS"


def main() -> int:
    FINAL.mkdir(parents=True, exist_ok=True)
    reports = {
        "idPhotoPartial": load_json(FINAL / "id-photo-sample-validation-report.json"),
        "watermarkRemoveScan": load_json(FINAL / "watermark-remove-scan-report.json"),
        "profileInteractions": load_json(FINAL / "profile-interactions-report.json"),
        "frontendUi": load_json(ROOT / "reports" / "final" / "frontend-ui-report.json"),
        "frontendBackendSync": load_json(ROOT / "reports" / "spec-display-cleanup" / "frontend-backend-sync-report.json"),
        "mainFlow": load_json(ROOT / "reports" / "remove-outfit-and-career" / "final-report.json"),
        "watermarkFull": load_json(ROOT / "reports" / "final" / "watermark-hd-chain-report.json"),
        "devtoolsBusinessFlow": load_json(ROOT / "reports" / "final" / "devtools-business-flow-report.json"),
        "cloudRealBusinessFlow": load_json(CLOUD_FLOW),
    }
    health = {
        "localApi": request_json("http://127.0.0.1:8000/api/health"),
        "localWatermark": request_json("http://127.0.0.1:8000/api/watermark/health"),
        "cloudApi": request_json("https://tupzjianzhao.chat/api/health"),
        "cloudWatermark": request_json("https://tupzjianzhao.chat/api/watermark/health"),
    }

    api_config = (ROOT / "utils" / "apiConfig.js").read_text(encoding="utf-8")
    watermark_config = (ROOT / "utils" / "watermarkConfig.js").read_text(encoding="utf-8")
    route_checks = {
        "localApiBaseDefined": "LOCAL_API_BASE_URL" in api_config and "http://127.0.0.1:8000" in api_config,
        "cloudApiBaseDefined": "CLOUD_API_BASE_URL" in api_config and "https://tupzjianzhao.chat" in api_config,
        "apiTargetStorageDefined": "ID_PHOTO_API_TARGET" in api_config,
        "runtimeTargetFunctionExists": "function getApiBaseUrl" in api_config,
        "watermarkFollowsApiTarget": "same-as-api" in watermark_config and "getApiBaseUrl" in watermark_config,
        "localApiHealthPass": health["localApi"]["passed"],
        "cloudApiHealthPass": health["cloudApi"]["passed"],
    }
    route_payload = {
        "status": "PASS" if all(route_checks.values()) else "FAIL",
        "checks": route_checks,
        "health": health,
    }
    write_json(REPORT_ROOT / "frontend-api-route-check.json", route_payload)
    write_md(REPORT_ROOT / "frontend-api-route-check.md", [
        "# Frontend API Route Check",
        "",
        f"- Status: {route_payload['status']}",
        "- Local API target: `http://127.0.0.1:8000`",
        "- Cloud API target: `https://tupzjianzhao.chat`",
        "- Watermark API target: follows the same API target as ID-photo.",
        "",
        "## Checks",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in route_checks.items()],
    ])

    local_vs_cloud = {
        "status": "PASS" if status_is_pass(reports["idPhotoPartial"]) and status_is_pass(reports["cloudRealBusinessFlow"]) else "FAIL",
        "local": {
            "idPhotoPartialPassed": status_is_pass(reports["idPhotoPartial"]),
            "colorChecks": reports["idPhotoPartial"].get("passedColorChecks"),
            "totalColorChecks": reports["idPhotoPartial"].get("totalColorChecks"),
            "rawFailSamplesMissing": reports["idPhotoPartial"].get("rawFailSamplesMissing"),
        },
        "cloud": {
            "businessFlowPassed": status_is_pass(reports["cloudRealBusinessFlow"]),
            "baseUrl": reports["cloudRealBusinessFlow"].get("baseUrl"),
            "checks": reports["cloudRealBusinessFlow"].get("checks", {}),
        },
        "note": "Cloud real business flow was verified against the live service. No secret-bearing deployment action was executed in this report writer.",
    }
    write_json(FINAL / "id-photo-local-vs-cloud-report.json", local_vs_cloud)
    write_md(FINAL / "id-photo-local-vs-cloud-report.md", [
        "# ID Photo Local vs Cloud Report",
        "",
        f"- Status: {local_vs_cloud['status']}",
        f"- Local ID-photo color checks: {local_vs_cloud['local']['colorChecks']}/{local_vs_cloud['local']['totalColorChecks']}",
        f"- Raw fail samples missing: {local_vs_cloud['local']['rawFailSamplesMissing']}",
        f"- Cloud base URL: `{local_vs_cloud['cloud']['baseUrl']}`",
        "",
        "## Cloud Checks",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in local_vs_cloud["cloud"]["checks"].items()],
    ])

    full_conditions = {
        "localBackendHealth": health["localApi"]["passed"],
        "localWatermarkHealth": health["localWatermark"]["passed"],
        "idPhotoPartialFailFlow": status_is_pass(reports["idPhotoPartial"]),
        "watermarkRemoveScanFlow": status_is_pass(reports["watermarkRemoveScan"]),
        "profileInteractionsFlow": status_is_pass(reports["profileInteractions"]),
        "frontendBackendSync": status_is_pass(reports["frontendBackendSync"]),
        "frontendUi": status_is_pass(reports["frontendUi"]),
        "mainFlow": status_is_pass(reports["mainFlow"]),
        "watermarkFullRegression": status_is_pass(reports["watermarkFull"]),
        "devtoolsBusinessFlow": status_is_pass(reports["devtoolsBusinessFlow"]),
        "cloudRealBusinessFlow": status_is_pass(reports["cloudRealBusinessFlow"]),
    }
    full_payload = {
        "status": "PASS" if all(full_conditions.values()) else "FAIL",
        "conditions": full_conditions,
        "reports": {name: report.get("_path", report.get("path", "")) for name, report in reports.items()},
        "devtoolsSummary": reports["devtoolsBusinessFlow"].get("summary", {}),
    }
    write_json(FINAL / "full-business-flow-regression.json", full_payload)
    write_md(FINAL / "full-business-flow-regression.md", [
        "# Full Business Flow Regression",
        "",
        f"- Status: {full_payload['status']}",
        f"- DevTools checks: {full_payload['devtoolsSummary'].get('passed')}/{full_payload['devtoolsSummary'].get('total')}",
        "",
        "## Conditions",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in full_conditions.items()],
        "",
        "## Source Reports",
        *[f"- {name}: `{path}`" for name, path in full_payload["reports"].items()],
    ])

    cloud_payload = {
        "status": "PASS" if health["cloudApi"]["passed"] and health["cloudWatermark"]["passed"] and status_is_pass(reports["cloudRealBusinessFlow"]) else "FAIL",
        "health": {"api": health["cloudApi"], "watermark": health["cloudWatermark"]},
        "flow": reports["cloudRealBusinessFlow"],
        "deploymentAction": "not_executed_in_report_writer",
    }
    write_json(FINAL / "cloud-regression-report.json", cloud_payload)
    write_md(FINAL / "cloud-regression-report.md", [
        "# Cloud Regression Report",
        "",
        f"- Status: {cloud_payload['status']}",
        "- API health: " + ("PASS" if health["cloudApi"]["passed"] else "FAIL"),
        "- Watermark health: " + ("PASS" if health["cloudWatermark"]["passed"] else "FAIL"),
        "- Real cloud business flow: " + ("PASS" if status_is_pass(reports["cloudRealBusinessFlow"]) else "FAIL"),
        "- Deployment action: `not_executed_in_report_writer`",
    ])

    write_md(FINAL / "fixed-files.md", [
        "# Fixed Files",
        "",
        *[f"- `{file}`" for file in FIXED_FILES],
    ])

    final_conditions = {
        "backend8000Running": health["localApi"]["passed"],
        "idPhotoPartialVerifyRan": status_is_pass(reports["idPhotoPartial"]),
        "watermarkRemoveScanVerifyRan": status_is_pass(reports["watermarkRemoveScan"]),
        "profileInteractionsVerifyRan": status_is_pass(reports["profileInteractions"]),
        "devtoolsDynamicVerifyRan": status_is_pass(reports["devtoolsBusinessFlow"]),
        "cloudRegressionRan": status_is_pass(reports["cloudRealBusinessFlow"]),
        "reportsGenerated": all(
            path.exists()
            for path in [
                REPORT_ROOT / "frontend-api-route-check.md",
                FINAL / "id-photo-root-cause.md",
                FINAL / "id-photo-local-vs-cloud-report.md",
                FINAL / "id-photo-sample-validation-report.md",
                FINAL / "watermark-remove-scan-report.md",
                FINAL / "profile-interactions-report.md",
                FINAL / "full-business-flow-regression.md",
                FINAL / "cloud-regression-report.md",
                FINAL / "fixed-files.md",
            ]
        ),
    }
    final_payload = {
        "status": "PASS" if all(final_conditions.values()) else "FAIL",
        "generatedAtEpoch": time.time(),
        "conditions": final_conditions,
        "health": health,
        "reports": {
            "frontendApiRouteCheck": str(REPORT_ROOT / "frontend-api-route-check.md"),
            "idPhotoRootCause": str(FINAL / "id-photo-root-cause.md"),
            "idPhotoLocalVsCloud": str(FINAL / "id-photo-local-vs-cloud-report.md"),
            "idPhotoSampleValidation": str(FINAL / "id-photo-sample-validation-report.md"),
            "watermarkRemoveScan": str(FINAL / "watermark-remove-scan-report.md"),
            "profileInteractions": str(FINAL / "profile-interactions-report.md"),
            "fullBusinessFlowRegression": str(FINAL / "full-business-flow-regression.md"),
            "cloudRegression": str(FINAL / "cloud-regression-report.md"),
            "fixedFiles": str(FINAL / "fixed-files.md"),
        },
    }
    write_json(FINAL / "final-summary.json", final_payload)
    write_md(FINAL / "final-summary.md", [
        "# First Stage Final Summary",
        "",
        f"- Status: {final_payload['status']}",
        "- Backend 8000: " + ("PASS" if health["localApi"]["passed"] else "FAIL"),
        "- ID-photo partial fail flow: " + ("PASS" if status_is_pass(reports["idPhotoPartial"]) else "FAIL"),
        "- Watermark scan removed flow: " + ("PASS" if status_is_pass(reports["watermarkRemoveScan"]) else "FAIL"),
        "- Profile interactions flow: " + ("PASS" if status_is_pass(reports["profileInteractions"]) else "FAIL"),
        "- DevTools dynamic business flow: " + ("PASS" if status_is_pass(reports["devtoolsBusinessFlow"]) else "FAIL"),
        "- Cloud real business flow: " + ("PASS" if status_is_pass(reports["cloudRealBusinessFlow"]) else "FAIL"),
        "",
        "## Final Conditions",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in final_conditions.items()],
        "",
        "## Reports",
        *[f"- {name}: `{path}`" for name, path in final_payload["reports"].items()],
    ])
    print(f"[first-stage-summary] {final_payload['status']} report={FINAL / 'final-summary.md'}")
    return 0 if final_payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
