"""Aggregate the current full business-flow evidence for the active scope."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "reports" / "final"
REPORT_DIR = ROOT / "reports" / "spec-display-cleanup"
WATERMARK = ROOT / "reports" / "watermark"
MAX_REPORT_AGE_SECONDS = 4 * 60 * 60


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "FAIL", "missing": True, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_path"] = str(path)
        data["_fresh"] = time.time() - path.stat().st_mtime <= MAX_REPORT_AGE_SECONDS
        return data
    except Exception as exc:
        return {"status": "FAIL", "error": str(exc), "path": str(path), "_fresh": False}


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


def copy_final(payload: dict[str, Any], markdown: str) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FINAL.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "full-business-flow-report.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    (REPORT_DIR / "full-business-flow-report.md").write_text(markdown, encoding="utf-8")
    (FINAL / "full-business-flow-report.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    (FINAL / "full-business-flow-report.md").write_text(markdown, encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    base_url = args.base_url.rstrip("/")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FINAL.mkdir(parents=True, exist_ok=True)

    reports = {
        "specDisplay": load(REPORT_DIR / "final-report.json"),
        "frontendBackendSync": load(REPORT_DIR / "frontend-backend-sync-report.json"),
        "idPhotoMainFlow": load(REPORT_DIR / "id-photo-main-flow-report.json"),
        "idPhotoSamples": load(FINAL / "id-photo-validation-report.json"),
        "watermark": load(WATERMARK / "watermark-regression-report.json"),
        "watermark6666": load(FINAL / "watermark-6666-validation-report.json"),
        "specLayout": load(FINAL / "spec-layout-validation-report.json"),
        "frontendUi": load(FINAL / "frontend-ui-validation-report.json"),
        "devtoolsBusinessFlow": load(FINAL / "devtools-business-flow-report.json"),
        "protected": load(FINAL / "protected-feature-regression-report.json"),
    }
    health = {
        "api": request_json(base_url + "/api/health"),
        "watermark": request_json(base_url + "/api/watermark/health"),
        "idPhotoCapabilities": request_json(base_url + "/api/id-photo/capabilities"),
    }
    id_real = reports["idPhotoSamples"].get("real") or {}
    id_negative = reports["idPhotoSamples"].get("negative") or {}
    wm_stop = reports["watermark"].get("stopConditions") or {}
    devtools_summary = reports["devtoolsBusinessFlow"].get("summary") or {}
    spec_counts = reports["specDisplay"].get("counts") or {}
    visible_pending_after = spec_counts.get("visiblePendingCountAfterCleanup")
    protected_checks = reports["protected"].get("checks") or {}
    conditions = {
        "apiHealthPass": health["api"].get("passed") is True,
        "watermarkGatewayHealthPass": health["watermark"].get("passed") is True,
        "idPhotoCapabilitiesPass": health["idPhotoCapabilities"].get("passed") is True,
        "specDisplayReportFreshPass": reports["specDisplay"].get("status") == "PASS" and reports["specDisplay"].get("_fresh") is True,
        "frontendBackendSyncFreshPass": reports["frontendBackendSync"].get("status") == "PASS" and reports["frontendBackendSync"].get("_fresh") is True,
        "idPhotoMainFlowFreshPass": reports["idPhotoMainFlow"].get("status") == "PASS" and reports["idPhotoMainFlow"].get("_fresh") is True,
        "visiblePendingCountZero": visible_pending_after is not None and int(visible_pending_after) == 0,
        "internalPendingDataStillRetained": int(spec_counts.get("internalPendingCountBeforeVisibleCleanup") or 0) > 0,
        "idPhotoSamplesFreshPass": reports["idPhotoSamples"].get("status") == "PASS" and reports["idPhotoSamples"].get("_fresh") is True,
        "idPhotoFortyRealSamplesBalanced": int(id_real.get("total") or 0) >= 40
        and int(id_real.get("male") or 0) >= 20
        and int(id_real.get("female") or 0) >= 20,
        "idPhotoPassRateAtLeast95": float(id_real.get("passRate") or 0) >= 95,
        "negativeFalsePassZero": int(id_negative.get("falsePass", -1)) == 0,
        "watermarkFreshPass": reports["watermark"].get("status") == "PASS" and reports["watermark"].get("_fresh") is True,
        "watermarkNormalHdPass": wm_stop.get("manualChainOk") is True
        and wm_stop.get("quickChainOk") is True
        and wm_stop.get("hdChainOk") is True,
        "watermark6666ResidualCheckPass": reports["watermark6666"].get("status") == "PASS" and reports["watermark6666"].get("_fresh") is True,
        "specLayoutFreshPass": reports["specLayout"].get("status") == "PASS" and reports["specLayout"].get("_fresh") is True,
        "frontendUiFreshPass": reports["frontendUi"].get("status") == "PASS" and reports["frontendUi"].get("_fresh") is True,
        "devtoolsBusinessFlowFreshPass": reports["devtoolsBusinessFlow"].get("status") == "PASS"
        and reports["devtoolsBusinessFlow"].get("_fresh") is True
        and int(devtools_summary.get("failed", -1)) == 0,
        "removedEntriesNotRestored": protected_checks.get("oneClickOutfitRemovedFromGenerator") is True
        and protected_checks.get("careerEntryRemovedFromToolsPage") is True,
        "requiredReportsGenerated": all(
            path.exists()
            for path in [
                REPORT_DIR / "final-report.md",
                REPORT_DIR / "frontend-backend-sync-report.md",
                REPORT_DIR / "id-photo-main-flow-report.md",
                FINAL / "id-photo-validation-report.md",
                WATERMARK / "watermark-regression-report.md",
                FINAL / "watermark-6666-validation-report.md",
                FINAL / "devtools-business-flow-report.md",
            ]
        ),
    }
    status = "PASS" if all(conditions.values()) else "FAIL"
    payload = {
        "status": status,
        "passed": status == "PASS",
        "generatedAtEpoch": time.time(),
        "baseUrl": base_url,
        "conditions": conditions,
        "health": health,
        "summary": {
            "visiblePendingCountAfterCleanup": int(visible_pending_after) if visible_pending_after is not None else -1,
            "internalPendingCountBeforeVisibleCleanup": int(spec_counts.get("internalPendingCountBeforeVisibleCleanup") or 0),
            "realSamples": int(id_real.get("total") or 0),
            "maleSamples": int(id_real.get("male") or 0),
            "femaleSamples": int(id_real.get("female") or 0),
            "negativeFalsePass": int(id_negative.get("falsePass", -1)),
            "devtoolsChecks": int(devtools_summary.get("total") or 0),
            "devtoolsFailed": int(devtools_summary.get("failed", -1)),
        },
        "reports": reports,
    }
    md_lines = [
        "# Full Business Flow Report",
        "",
        f"- Status: {status}",
        f"- Base URL: `{base_url}`",
        f"- Visible pending count after cleanup: {payload['summary']['visiblePendingCountAfterCleanup']}",
        f"- Real ID-photo samples: {payload['summary']['realSamples']} "
        f"(male {payload['summary']['maleSamples']}, female {payload['summary']['femaleSamples']})",
        f"- Negative false pass: {payload['summary']['negativeFalsePass']}",
        f"- DevTools checks: {payload['summary']['devtoolsChecks']}, failed {payload['summary']['devtoolsFailed']}",
        "",
        "## Conditions",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in conditions.items()],
        "",
        "## Report Files",
        *[f"- {name}: `{item.get('_path', item.get('path', ''))}` status={item.get('status')}" for name, item in reports.items()],
        "",
    ]
    markdown = "\n".join(md_lines)
    copy_final(payload, markdown)
    print(f"[verify-full-business-flow] {status} report={REPORT_DIR / 'full-business-flow-report.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
