"""Verify frontend spec data and backend gateway are synchronized for this scope."""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "spec-display-cleanup"


HARNESS = r"""
const path = require('path');
const ROOT = process.argv[2];
const EXPECTED_BASE_URL = (process.argv[3] || '').replace(/\/$/, '');
const useCloudTarget = EXPECTED_BASE_URL && EXPECTED_BASE_URL !== 'http://127.0.0.1:8000';
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
  getStorageSync(key) {
    if (key === 'ID_PHOTO_API_TARGET') return useCloudTarget ? 'cloud' : 'local';
    return '';
  },
  getAccountInfoSync() {
    return { miniProgram: { envVersion: useCloudTarget ? 'release' : 'develop' } };
  },
  setNavigationBarTitle(opts) { wxCalls.push({ fn: 'setNavigationBarTitle', opts }); },
  navigateTo(opts) { wxCalls.push({ fn: 'navigateTo', opts }); },
  showActionSheet(opts) {
    wxCalls.push({ fn: 'showActionSheet', opts });
    if (opts && opts.success) opts.success({ tapIndex: 0 });
  },
  showToast(opts) { wxCalls.push({ fn: 'showToast', opts }); },
};

function load(route) {
  currentPage = route;
  const file = path.join(ROOT, route + '.js');
  delete require.cache[require.resolve(file)];
  require(file);
  return pages[route];
}

const specs = require(path.join(ROOT, 'utils', 'specs.js'));
const apiConfig = require(path.join(ROOT, 'utils', 'apiConfig.js'));
const groups = ['teacher_cert', 'accounting_title_exam', 'civil_service_exam', 'driver_license', 'school_enrollment', 'passport_visa'];
const groupSync = groups.map(groupId => {
  const direct = specs.getGroupSpecs(groupId) || [];
  const page = load('pages/specs/specs');
  page.onLoad({ groupId });
  const visible = page.data.filteredSpecs || [];
  return {
    groupId,
    directCount: direct.length,
    pageCount: visible.length,
    idsMatch: JSON.stringify(direct.map(item => item.id)) === JSON.stringify(visible.map(item => item.specId || item.id)),
    pendingDataRetained: direct.some(item => item.sourceLevel === 'third_party_pending'),
    pendingVisibleCount: visible.filter(item => String(item.sourceBadge || item.note || '').includes('待核验')).length,
    applicablePreserved: visible.some(item => item.applicableText),
  };
});

const searchTerms = ['一寸', '教师资格证', '会计', '驾驶证', '国考'];
const searchSync = searchTerms.map(term => {
  const direct = specs.searchSpecEntries(term) || [];
  const page = load('pages/specs/specs');
  page.onLoad({});
  page.onSearch({ detail: { value: term } });
  const visible = page.data.filteredSpecs || [];
  page.showMoreSearch();
  const expanded = page.data.filteredSpecs || [];
  return {
    term,
    directCount: direct.length,
    firstPageCount: visible.length,
    expandedCount: expanded.length,
    expandedMatchesDirect: expanded.length === direct.length,
    hiddenSearchCount: page.data.hiddenSearchCount || 0,
    pendingVisibleCount: expanded.filter(item => String(item.sourceBadge || item.note || '').includes('待核验')).length,
  };
});

const generate = load('pages/generate/generate');
generate.onLoad({ specId: 'yicun' });
const allSpecs = specs.getSpecsByCategory('all') || [];
console.log('__SYNC_JSON__' + JSON.stringify({
  status: 'PASS',
  apiBaseUrl: apiConfig.API_BASE_URL,
  enableAi: apiConfig.ENABLE_AI,
  allSpecCount: allSpecs.length,
  groupSync,
  searchSync,
  generateSync: {
    currentSpecId: generate.data.currentSpecId,
    specSize: generate.data.specSize,
    availableColors: (generate.data.availableColors || []).map(item => item.id),
    fileText: generate.data.fileText,
  },
  v2Specs: specs.idPhotoSpecsV2 || [],
  wxCalls,
}, null, 2));
"""


def _request_json(url: str, timeout: float = 20.0, attempts: int = 3) -> dict[str, Any]:
    last_error = ""
    for attempt in range(1, attempts + 1):
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
                "attempts": attempt,
                "passed": res.status_code == 200 and bool(data.get("success") or data.get("ok") or data.get("message") == "server running" or data.get("templates") or data.get("specs")),
            }
        except Exception as exc:
            last_error = str(exc)
            if attempt < attempts:
                time.sleep(2)
    return {"url": url, "statusCode": 0, "error": last_error, "attempts": attempts, "passed": False}


def run_frontend_harness(base_url: str) -> dict[str, Any]:
    harness = Path(tempfile.gettempdir()) / "verify_frontend_backend_sync_harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness), str(ROOT), base_url.rstrip("/")],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=90,
    )
    marker = "__SYNC_JSON__"
    stdout = completed.stdout or ""
    if marker not in stdout:
        return {
            "status": "FAIL",
            "returncode": completed.returncode,
            "stdout": stdout[-5000:],
            "stderr": (completed.stderr or "")[-5000:],
        }
    payload = json.loads(stdout.split(marker, 1)[1])
    payload["returncode"] = completed.returncode
    if completed.stderr:
        payload["stderr"] = completed.stderr[-5000:]
    return payload


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    base_url = args.base_url.rstrip("/")
    frontend = run_frontend_harness(base_url)
    health = {
        "api": _request_json(base_url + "/api/health"),
        "watermark": _request_json(base_url + "/api/watermark/health"),
        "idPhotoCapabilities": _request_json(base_url + "/api/id-photo/capabilities"),
    }
    group_sync = frontend.get("groupSync") or []
    search_sync = frontend.get("searchSync") or []
    capabilities = (health["idPhotoCapabilities"].get("data") or {})
    backend_templates = capabilities.get("templates") or []
    backend_specs = capabilities.get("specs") or capabilities.get("idPhotoSpecs") or []
    checks = {
        "frontendHarnessRan": frontend.get("status") == "PASS" and frontend.get("returncode") == 0,
        "apiBaseUrlMatchesBackend": str(frontend.get("apiBaseUrl", "")).rstrip("/") == base_url,
        "apiHealthPass": health["api"].get("passed") is True,
        "watermarkGatewayHealthPass": health["watermark"].get("passed") is True,
        "idPhotoCapabilitiesPass": health["idPhotoCapabilities"].get("passed") is True,
        "frontendSpecDataPresent": int(frontend.get("allSpecCount") or 0) >= 20,
        "groupCountsSynced": all(item.get("directCount") == item.get("pageCount") and item.get("idsMatch") for item in group_sync),
        "searchCountsSyncedAfterShowMore": all(item.get("expandedMatchesDirect") for item in search_sync),
        "legacyPendingInternalRemoved": all(not item.get("pendingDataRetained") for item in group_sync),
        "pendingNotVisibleAfterSync": all(int(item.get("pendingVisibleCount") or 0) == 0 for item in group_sync + search_sync),
        "regionalInfoCompactVisible": all(item.get("applicablePreserved") for item in group_sync),
        "generateSpecSyncsToOneInch": (frontend.get("generateSync") or {}).get("currentSpecId") == "yicun"
        and "295" in str((frontend.get("generateSync") or {}).get("specSize")),
        "backendCapabilitiesNonEmpty": bool(backend_templates or backend_specs or capabilities.get("backgrounds")),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "status": status,
        "passed": status == "PASS",
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "baseUrl": base_url,
        "checks": checks,
        "frontend": frontend,
        "backendHealth": health,
        "backendCapabilitiesSummary": {
            "templates": len(backend_templates),
            "specs": len(backend_specs),
            "keys": sorted(list(capabilities.keys())) if isinstance(capabilities, dict) else [],
        },
    }
    (REPORT_DIR / "frontend-backend-sync-report.json").write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    md = [
        "# Frontend Backend Sync Report",
        "",
        f"- Status: {status}",
        f"- Base URL: `{base_url}`",
        f"- Frontend specs: {frontend.get('allSpecCount')}",
        f"- Backend capability keys: {', '.join(payload['backendCapabilitiesSummary']['keys'])}",
        "",
        "## Checks",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in checks.items()],
        "",
        "## Group Sync",
        *[
            f"- {item.get('groupId')}: direct={item.get('directCount')} page={item.get('pageCount')} "
            f"pendingInternal={item.get('pendingDataRetained')} pendingVisible={item.get('pendingVisibleCount')} "
            f"regionalInfoCompactVisible={item.get('applicablePreserved')}"
            for item in group_sync
        ],
        "",
        "## Search Sync",
        *[
            f"- {item.get('term')}: direct={item.get('directCount')} expanded={item.get('expandedCount')} pendingVisible={item.get('pendingVisibleCount')}"
            for item in search_sync
        ],
        "",
    ]
    (REPORT_DIR / "frontend-backend-sync-report.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[verify-frontend-backend-sync] {status} report={REPORT_DIR / 'frontend-backend-sync-report.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
