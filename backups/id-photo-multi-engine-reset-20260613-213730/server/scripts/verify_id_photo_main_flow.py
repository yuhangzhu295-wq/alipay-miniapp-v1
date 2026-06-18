"""Verify the ID-photo main flow after the spec display cleanup."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "spec-display-cleanup"
FINAL = ROOT / "reports" / "final"
SCRIPTS = ROOT / "server" / "scripts"
RUN_PYTHON = SCRIPTS / "run_python.js"


HARNESS = r"""
const path = require('path');
const ROOT = process.argv[2];
let currentPage = '';
const pages = {};
const wxCalls = [];
global.getApp = () => ({ globalData: {} });
global.getCurrentPages = () => [{ route: currentPage }];
global.Page = function(def) {
  def.data = JSON.parse(JSON.stringify(def.data || {}));
  def.setData = function(next, cb) {
    Object.assign(this.data, next || {});
    if (typeof cb === 'function') cb.call(this);
  };
  pages[currentPage] = def;
};
global.wx = {
  setNavigationBarTitle(opts) { wxCalls.push({ fn: 'setNavigationBarTitle', opts }); },
  showToast(opts) { wxCalls.push({ fn: 'showToast', opts }); },
  navigateTo(opts) { wxCalls.push({ fn: 'navigateTo', opts }); },
};
function load(route) {
  currentPage = route;
  const file = path.join(ROOT, route + '.js');
  delete require.cache[require.resolve(file)];
  require(file);
  return pages[route];
}
const page = load('pages/generate/generate');
page.onLoad({ specId: 'yicun' });
console.log('__ID_MAIN_JSON__' + JSON.stringify({
  status: 'PASS',
  data: {
    currentSpecId: page.data.currentSpecId,
    specName: page.data.specName,
    specSize: page.data.specSize,
    widthPxLabel: page.data.widthPxLabel,
    heightPxLabel: page.data.heightPxLabel,
    availableColors: (page.data.availableColors || []).map(item => item.id),
    hasSourceBadgeField: Object.prototype.hasOwnProperty.call(page.data, 'sourceBadge'),
    hasSourceNoteField: Object.prototype.hasOwnProperty.call(page.data, 'sourceNote'),
    statusText: page.data.statusText,
    canDownload: page.data.canDownload,
  },
  wxCalls,
}, null, 2));
"""


def _run(cmd: list[str], timeout: int = 240) -> dict[str, Any]:
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


def _request_json(url: str, timeout: float = 8.0) -> dict[str, Any]:
    try:
        res = requests.get(url, timeout=timeout)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:500]}
        return {
            "url": url,
            "statusCode": res.status_code,
            "data": data,
            "passed": res.status_code == 200 and bool(data.get("success") or data.get("ok") or data.get("message") == "server running"),
        }
    except Exception as exc:
        return {"url": url, "statusCode": 0, "error": str(exc), "passed": False}


def run_generate_harness() -> dict[str, Any]:
    harness = Path(tempfile.gettempdir()) / "verify_id_photo_main_flow_harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness), str(ROOT)],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
    )
    marker = "__ID_MAIN_JSON__"
    stdout = completed.stdout or ""
    if marker not in stdout:
        return {
            "status": "FAIL",
            "returncode": completed.returncode,
            "stdout": stdout[-4000:],
            "stderr": (completed.stderr or "")[-4000:],
        }
    payload = json.loads(stdout.split(marker, 1)[1])
    payload["returncode"] = completed.returncode
    if completed.stderr:
        payload["stderr"] = completed.stderr[-4000:]
    return payload


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FINAL.mkdir(parents=True, exist_ok=True)

    main_flow_run = _run(
        ["node", str(RUN_PYTHON), "server/scripts/verify_main_flow.py", "--base-url", args.base_url],
        timeout=300,
    )
    generate_runtime = run_generate_harness()
    health = {
        "api": _request_json(args.base_url.rstrip("/") + "/api/health"),
        "watermark": _request_json(args.base_url.rstrip("/") + "/api/watermark/health"),
    }
    main_flow_report_path = ROOT / "reports" / "remove-outfit-and-career" / "final-report.json"
    try:
        main_flow_report = json.loads(main_flow_report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        main_flow_report = {"status": "FAIL", "error": str(exc)}
    generate_wxml = (ROOT / "pages" / "generate" / "generate.wxml").read_text(encoding="utf-8", errors="replace")
    generate_js = (ROOT / "pages" / "generate" / "generate.js").read_text(encoding="utf-8", errors="replace")
    data = generate_runtime.get("data") or {}
    checks = {
        "backendApiHealthAccessible": health["api"].get("passed") is True,
        "watermarkGatewayHealthAccessible": health["watermark"].get("passed") is True,
        "mainFlowCommandRan": main_flow_run.get("passed") is True,
        "mainFlowReportPass": main_flow_report.get("status") == "PASS",
        "uploadGenerateDownloadWorks": ((main_flow_report.get("mainFlow") or {}).get("checks") or {}).get("uploadGenerateDownloadWorks") is True,
        "fiveBackgroundsGenerate": ((main_flow_report.get("mainFlow") or {}).get("checks") or {}).get("fiveBackgroundsGenerate") is True,
        "layoutDownloadWorks": ((main_flow_report.get("mainFlow") or {}).get("checks") or {}).get("layoutDownloadWorks") is True,
        "reuploadAndRetakeWork": ((main_flow_report.get("mainFlow") or {}).get("checks") or {}).get("reuploadAndRetakeWork") is True,
        "sourceBarRemovedFromGenerateWxml": "spec-source-line" not in generate_wxml,
        "sourceRuntimeFieldsRemoved": data.get("hasSourceBadgeField") is False and data.get("hasSourceNoteField") is False,
        "pendingTextNotInVisibleGenerateSource": "待核验" not in generate_wxml and "sourceBadge" not in generate_wxml,
        "oneClickOutfitNotRestored": "outfit" not in generate_wxml and "selectOutfit" not in generate_js,
        "oneInchSpecStillExact": data.get("currentSpecId") == "yicun"
        and data.get("widthPxLabel") == "295px"
        and data.get("heightPxLabel") == "413px",
        "fiveColorControlsStillAvailable": set(data.get("availableColors") or []) == {"blue", "white", "red", "lightBlue", "gray"},
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "status": status,
        "passed": status == "PASS",
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "baseUrl": args.base_url,
        "checks": checks,
        "health": health,
        "mainFlowRun": main_flow_run,
        "mainFlowReport": main_flow_report,
        "generateRuntime": generate_runtime,
    }
    (REPORT_DIR / "id-photo-main-flow-report.json").write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    md = [
        "# ID Photo Main Flow Report",
        "",
        f"- Status: {status}",
        f"- Base URL: `{args.base_url}`",
        "",
        "## Checks",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in checks.items()],
        "",
        "## Runtime",
        f"- currentSpecId: `{data.get('currentSpecId')}`",
        f"- specSize: `{data.get('specSize')}`",
        f"- colors: `{', '.join(data.get('availableColors') or [])}`",
        "",
    ]
    (REPORT_DIR / "id-photo-main-flow-report.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[verify-id-photo-main-flow] {status} report={REPORT_DIR / 'id-photo-main-flow-report.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
