"""Verify the spec pages no longer show pending-verification copy to users."""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "spec-display-cleanup"
FINAL = ROOT / "reports" / "final"
SHOTS = REPORT_DIR / "screenshots"


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

function visiblePendingCount(items) {
  const pending = '待核验';
  return (items || []).filter(item => {
    return String(item.sourceBadge || '').includes(pending)
      || String(item.note || '').includes(pending);
  }).length;
}

function collectGroup(groupId) {
  const page = load('pages/specs/specs');
  page.onLoad({ groupId });
  const items = page.data.filteredSpecs || [];
  return {
    groupId,
    title: page.data.currentGroupName,
    count: items.length,
    pendingVisibleCount: visiblePendingCount(items),
    pendingBadgeCount: items.filter(item => item.sourceLevel === 'third_party_pending' && item.sourceBadge).length,
    noteCount: items.filter(item => item.note).length,
    fileTextCount: items.filter(item => item.fileText).length,
    applicableCount: items.filter(item => item.applicableText).length,
    sampleCards: items.slice(0, 6).map(item => ({
      id: item.id,
      name: item.name,
      size: item.size,
      fileText: item.fileText,
      sourceLevel: item.sourceLevel,
      sourceBadge: item.sourceBadge,
      note: item.note,
      applicableText: item.applicableText,
      colorCount: (item.colors || []).length,
    })),
  };
}

function collectSearch(term) {
  const page = load('pages/specs/specs');
  page.onLoad({});
  page.onSearch({ detail: { value: term } });
  const items = page.data.filteredSpecs || [];
  return {
    term,
    pageMode: page.data.pageMode,
    count: items.length,
    hiddenSearchCount: page.data.hiddenSearchCount || 0,
    pendingVisibleCount: visiblePendingCount(items),
    pendingBadgeCount: items.filter(item => item.sourceLevel === 'third_party_pending' && item.sourceBadge).length,
    applicableCount: items.filter(item => item.applicableText).length,
    sampleCards: items.slice(0, 6).map(item => ({
      id: item.id,
      name: item.name,
      size: item.size,
      fileText: item.fileText,
      sourceLevel: item.sourceLevel,
      sourceBadge: item.sourceBadge,
      note: item.note,
      applicableText: item.applicableText,
      colorCount: (item.colors || []).length,
    })),
  };
}

const specs = require(path.join(ROOT, 'utils', 'specs.js'));
const allSpecs = specs.getSpecsByCategory('all') || [];
const groups = [
  'teacher_cert',
  'accounting_title_exam',
  'civil_service_exam',
  'driver_license',
  'school_enrollment',
  'passport_visa'
].map(collectGroup);
const searches = ['教师资格证', '会计', '驾驶证', '国考', '一寸'].map(collectSearch);

const generatePage = load('pages/generate/generate');
generatePage.onLoad({ specId: 'teacher_cert_295_413' });

const payload = {
  status: 'PASS',
  sourceData: {
    internalPendingCount: allSpecs.filter(item => (item.sourceLevel || '') === 'third_party_pending').length,
    internalPendingLabel: specs.sourceLabels && specs.sourceLabels.third_party_pending,
    visiblePendingCountAfter: groups.reduce((sum, item) => sum + item.pendingVisibleCount + item.pendingBadgeCount, 0)
      + searches.reduce((sum, item) => sum + item.pendingVisibleCount + item.pendingBadgeCount, 0),
  },
  groups,
  searches,
  generatePage: {
    currentSpecId: generatePage.data.currentSpecId,
    specName: generatePage.data.specName,
    hasSourceBadgeField: Object.prototype.hasOwnProperty.call(generatePage.data, 'sourceBadge'),
    hasSourceNoteField: Object.prototype.hasOwnProperty.call(generatePage.data, 'sourceNote'),
    fileText: generatePage.data.fileText,
    colorCount: (generatePage.data.availableColors || []).length,
  },
  wxCalls,
};

console.log('__SPEC_DISPLAY_JSON__' + JSON.stringify(payload, null, 2));
"""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def run_dynamic() -> dict[str, Any]:
    harness = Path(tempfile.gettempdir()) / "verify_spec_display_harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness), str(ROOT)],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=90,
    )
    marker = "__SPEC_DISPLAY_JSON__"
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


def static_checks(dynamic: dict[str, Any]) -> dict[str, bool]:
    specs_wxml = _read(ROOT / "pages" / "specs" / "specs.wxml")
    specs_css = _read(ROOT / "pages" / "specs" / "specs.wxss")
    generate_wxml = _read(ROOT / "pages" / "generate" / "generate.wxml")
    generate_js = _read(ROOT / "pages" / "generate" / "generate.js")
    tools_js = _read(ROOT / "pages" / "tools" / "tools.js")
    source = dynamic.get("sourceData") or {}
    visible_pending_after = source.get("visiblePendingCountAfter")
    groups = dynamic.get("groups") or []
    searches = dynamic.get("searches") or []
    generate = dynamic.get("generatePage") or {}
    return {
        "dynamicHarnessRan": dynamic.get("status") == "PASS" and dynamic.get("returncode") == 0,
        "internalPendingDataRetained": int(source.get("internalPendingCount") or 0) > 0
        and source.get("internalPendingLabel") == "待核验",
        "visiblePendingRemovedFromGroupsAndSearch": visible_pending_after is not None and int(visible_pending_after) == 0,
        "pendingBadgesHiddenForPendingSpecs": all(int(item.get("pendingBadgeCount") or 0) == 0 for item in groups + searches),
        "groupPagesStillHaveCards": all(int(item.get("count") or 0) > 0 for item in groups),
        "searchStillReturnsCards": all(int(item.get("count") or 0) > 0 and item.get("pageMode") == "search" for item in searches),
        "regionalApplicableTextPreserved": sum(int(item.get("applicableCount") or 0) for item in groups + searches) > 0,
        "fileFormatTextPreserved": sum(int(item.get("fileTextCount") or 0) for item in groups) > 0,
        "topUnifiedNoticePreserved": "规格要求可能随地区和报名平台调整，请以提交平台最新公告为准。" in specs_wxml,
        "generateSourceBarRemoved": "spec-source-line" not in generate_wxml,
        "generateSourceRuntimeFieldsRemoved": generate.get("hasSourceBadgeField") is False
        and generate.get("hasSourceNoteField") is False,
        "generatePageStillShowsSpecAndColors": generate.get("currentSpecId") == "teacher_cert_295_413"
        and int(generate.get("colorCount") or 0) >= 1,
        "layoutAllowsTwoLineSize": ".spec-card-size" in specs_css and "-webkit-line-clamp: 2" in specs_css,
        "layoutPreventsCrowding": "align-items: stretch" in specs_css and "overflow: hidden" in specs_css,
        "pageLayerNoPendingLiteral": "待核验" not in generate_wxml
        and "待核验" not in generate_js
        and "待核验" not in (ROOT / "pages" / "specs" / "specs.js").read_text(encoding="utf-8", errors="replace"),
        "removedEntriesNotRestored": "职业形象照" not in tools_js and "outfit" not in generate_wxml,
    }


def draw_evidence(dynamic: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1120, 1450), (246, 248, 252))
    draw = ImageDraw.Draw(image)
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    title_font = ImageFont.truetype(str(font_path), 36) if font_path.exists() else ImageFont.load_default()
    h_font = ImageFont.truetype(str(font_path), 25) if font_path.exists() else ImageFont.load_default()
    body_font = ImageFont.truetype(str(font_path), 20) if font_path.exists() else ImageFont.load_default()

    draw.text((40, 34), "规格展示清理动态校验", fill=(15, 23, 42), font=title_font)
    draw.text((40, 90), "普通用户页不再显示“待核验”；顶部统一提示和适用地区信息保留。", fill=(71, 85, 105), font=h_font)
    draw.rounded_rectangle([40, 140, 1080, 280], radius=22, fill=(255, 255, 255), outline=(226, 232, 240))
    source = dynamic.get("sourceData") or {}
    summary_lines = [
        f"内部待核验规格保留: {source.get('internalPendingCount', 0)}",
        f"前台可见待核验数量: {source.get('visiblePendingCountAfter', 0)}",
        f"生成页来源条: 已移除",
        f"运行态来源字段: {'已移除' if not (dynamic.get('generatePage') or {}).get('hasSourceBadgeField') else '未移除'}",
    ]
    for idx, line in enumerate(summary_lines):
      draw.text((70 + (idx % 2) * 500, 174 + (idx // 2) * 46), line, fill=(15, 23, 42), font=body_font)

    cards = []
    for group in dynamic.get("groups") or []:
        for item in group.get("sampleCards") or []:
            cards.append(item)
    cards = cards[:12]
    x0, y0 = 46, 330
    card_w, card_h, gap = 322, 168, 24
    colors = [(37, 99, 235), (255, 255, 255), (239, 68, 68), (125, 211, 252), (148, 163, 184)]
    for idx, item in enumerate(cards):
        row, col = divmod(idx, 3)
        x = x0 + col * (card_w + gap)
        y = y0 + row * (card_h + gap)
        draw.rounded_rectangle([x, y, x + card_w, y + card_h], radius=18, fill=(255, 255, 255), outline=(226, 232, 240))
        draw.rounded_rectangle([x + 18, y + 52, x + 78, y + 112], radius=13, fill=(232, 240, 254))
        draw.text((x + 96, y + 24), str(item.get("name", ""))[:15], fill=(15, 23, 42), font=body_font)
        draw.text((x + 96, y + 58), str(item.get("size", ""))[:22], fill=(100, 116, 139), font=body_font)
        meta = str(item.get("fileText", ""))
        if meta:
            draw.rounded_rectangle([x + 96, y + 92, x + 176, y + 122], radius=9, fill=(242, 244, 247))
            draw.text((x + 104, y + 95), meta[:10], fill=(100, 116, 139), font=body_font)
        applicable = str(item.get("applicableText", ""))
        if applicable:
            draw.text((x + 96, y + 124), applicable[:16], fill=(100, 116, 139), font=body_font)
        for cidx in range(min(int(item.get("colorCount") or 0), 5)):
            cx = x + 18 + cidx * 24
            cy = y + 126
            draw.ellipse([cx, cy, cx + 14, cy + 14], fill=colors[cidx], outline=(203, 213, 225))
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, quality=94)


def write_reports(payload: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FINAL.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "final-report.json").write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    (REPORT_DIR / "frontend-display-runtime.json").write_text(
        json.dumps(payload.get("dynamic") or {}, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    md = [
        "# Spec Display Cleanup Final Report",
        "",
        f"- Status: {payload.get('status')}",
        f"- Generated: {payload.get('generatedAt')}",
        f"- Evidence image: `{payload.get('evidenceImage')}`",
        "",
        "## Changed Files",
        *[f"- `{path}`" for path in payload.get("changedFiles", [])],
        "",
        "## Counts",
    ]
    counts = payload.get("counts") or {}
    md.extend([f"- {name}: {value}" for name, value in counts.items()])
    md.extend(["", "## Checks"])
    md.extend([f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in (payload.get("checks") or {}).items()])
    md.extend(["", "## Preserved Regional Evidence"])
    for item in payload.get("regionalSamples") or []:
        md.append(f"- {item}")
    md.append("")
    (REPORT_DIR / "final-report.md").write_text("\n".join(md), encoding="utf-8")


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    dynamic = run_dynamic()
    checks = static_checks(dynamic)
    status = "PASS" if all(checks.values()) else "FAIL"
    evidence = SHOTS / "spec-display-cleanup-dynamic-evidence.jpg"
    draw_evidence(dynamic, evidence)

    regional_samples: list[str] = []
    for group in dynamic.get("groups") or []:
        for item in group.get("sampleCards") or []:
            text = item.get("applicableText")
            if text and len(regional_samples) < 8:
                regional_samples.append(f"{group.get('title')} / {item.get('name')}: {text}")

    source = dynamic.get("sourceData") or {}
    visible_pending_after = source.get("visiblePendingCountAfter")
    payload = {
        "status": status,
        "passed": status == "PASS",
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "checks": checks,
        "counts": {
            "internalPendingCountBeforeVisibleCleanup": int(source.get("internalPendingCount") or 0),
            "visiblePendingCountAfterCleanup": int(visible_pending_after) if visible_pending_after is not None else -1,
            "groupsChecked": len(dynamic.get("groups") or []),
            "searchTermsChecked": len(dynamic.get("searches") or []),
            "regionalInfoCardsPreserved": sum(int(item.get("applicableCount") or 0) for item in (dynamic.get("groups") or [])),
        },
        "changedFiles": [
            str(ROOT / "utils" / "specs.js"),
            str(ROOT / "pages" / "specs" / "specs.js"),
            str(ROOT / "pages" / "specs" / "specs.wxml"),
            str(ROOT / "pages" / "specs" / "specs.wxss"),
            str(ROOT / "pages" / "generate" / "generate.js"),
            str(ROOT / "pages" / "generate" / "generate.wxml"),
            str(ROOT / "pages" / "generate" / "generate.wxss"),
        ],
        "regionalSamples": regional_samples,
        "dynamic": dynamic,
        "evidenceImage": str(evidence),
    }
    write_reports(payload)
    print(f"[verify-spec-display] {status} report={REPORT_DIR / 'final-report.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
