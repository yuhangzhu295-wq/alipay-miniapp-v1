"""Verify the tools page after removing the career portrait entry."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "remove-outfit-and-career"


EXPECTED_TOOL_IDS = [
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


HARNESS = r"""
const path = require('path');
const ROOT = process.argv[2];
const expected = JSON.parse(process.argv[3]);
let pageDef = null;
const wxCalls = [];
function assert(cond, msg) { if (!cond) throw new Error(msg); }

global.Page = function(def) {
  def.data = JSON.parse(JSON.stringify(def.data || {}));
  def.setData = function(next, cb) {
    Object.assign(this.data, next || {});
    if (typeof cb === 'function') cb.call(this);
  };
  pageDef = def;
};
global.wx = {
  navigateTo(opts) { wxCalls.push({ fn: 'navigateTo', opts }); },
  showShareMenu(opts) { wxCalls.push({ fn: 'showShareMenu', opts }); },
};

require(path.join(ROOT, 'pages/tools/tools.js'));
const tools = (pageDef.data && pageDef.data.tools) || [];
const ids = tools.map(item => item.id);
assert(!ids.includes('professional'), 'professional/career portrait entry still exists');
assert(JSON.stringify(ids) === JSON.stringify(expected), 'tools order/count changed: ' + JSON.stringify(ids));
for (const id of expected) {
  pageDef.openTool({ currentTarget: { dataset: { id } } });
}
const routed = wxCalls
  .filter(call => call.fn === 'navigateTo')
  .map(call => ((call.opts || {}).url || '').split('type=')[1]);
assert(JSON.stringify(routed) === JSON.stringify(expected), 'tool navigation did not preserve all expected entries');
console.log(JSON.stringify({
  status: 'PASS',
  checks: {
    careerEntryRemoved: true,
    expectedToolsRemain: true,
    allExpectedToolsNavigate: true,
  },
  ids,
  routed,
}, null, 2));
"""


def _write_report(payload: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "tools-page-report.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    md = [
        "# Tools Page Verification",
        "",
        f"- Status: {payload.get('status', 'FAIL')}",
        f"- Tool count: {len(payload.get('ids') or [])}",
        "",
        "## Checks",
    ]
    for name, value in (payload.get("checks") or {}).items():
        md.append(f"- {name}: {'PASS' if value else 'FAIL'}")
    if payload.get("error"):
        md.extend(["", "## Error", "```", str(payload["error"])[-4000:], "```"])
    (REPORT_DIR / "tools-page-report.md").write_text("\n".join(md), encoding="utf-8")


def main() -> int:
    tools_js = (ROOT / "pages" / "tools" / "tools.js").read_text(encoding="utf-8", errors="replace")
    static_checks = {
        "sourceHasNoProfessionalToolId": "id: 'professional'" not in tools_js and 'id: "professional"' not in tools_js,
        "sourceKeepsRemoveWatermark": "removeWatermark" in tools_js,
        "sourceKeepsLayoutAndCollect": "layout" in tools_js and "collect" in tools_js,
    }
    harness_path = Path(tempfile.gettempdir()) / "verify_tools_page_harness.js"
    harness_path.write_text(HARNESS, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path), str(ROOT), json.dumps(EXPECTED_TOOL_IDS)],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=45,
    )
    try:
        runtime = json.loads(completed.stdout)
    except Exception:
        runtime = {
            "status": "FAIL",
            "error": (completed.stderr or completed.stdout)[-4000:],
            "returncode": completed.returncode,
        }
    checks = {**static_checks, **(runtime.get("checks") or {})}
    status = "PASS" if completed.returncode == 0 and runtime.get("status") == "PASS" and all(checks.values()) else "FAIL"
    payload = {
        "status": status,
        "passed": status == "PASS",
        "checks": checks,
        "ids": runtime.get("ids") or [],
        "routed": runtime.get("routed") or [],
        "runtime": runtime,
    }
    _write_report(payload)
    print(f"[verify-tools-page] {status} report={REPORT_DIR / 'tools-page-report.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
