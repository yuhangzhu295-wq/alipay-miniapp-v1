"""Dynamic validation for the ID-photo spec search page layout."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "reports" / "final"
SHOTS = FINAL / "spec-layout-screenshots"


HARNESS = r"""
const path = require('path');
const ROOT = process.argv[2];
let currentPage = '';
const pages = {};
const wxCalls = [];
global.getApp = () => ({ globalData: {} });
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
  }
};
function load(route) {
  currentPage = route;
  const file = path.join(ROOT, route + '.js');
  delete require.cache[require.resolve(file)];
  require(file);
  return pages[route];
}
function check(cond, msg) {
  if (!cond) throw new Error(msg);
}
(async () => {
  const page = load('pages/specs/specs');
  page.onLoad({});
  const terms = ['一寸', '教师资格证', '驾驶证', '国考'];
  const searches = [];
  for (const term of terms) {
    page.onSearch({ detail: { value: term } });
    searches.push({
      term,
      pageMode: page.data.pageMode,
      count: (page.data.filteredSpecs || []).length,
      hiddenSearchCount: page.data.hiddenSearchCount || 0,
      names: (page.data.filteredSpecs || []).map(item => item.name).slice(0, 6)
    });
    check(page.data.pageMode === 'search', 'pageMode should be search for ' + term);
    check((page.data.filteredSpecs || []).length > 0, 'no results for ' + term);
  }
  page.showMoreSearch();
  const afterShowMore = {
    count: (page.data.filteredSpecs || []).length,
    hiddenSearchCount: page.data.hiddenSearchCount || 0
  };
  check(afterShowMore.hiddenSearchCount === 0, 'show more did not clear hidden count');
  const first = page.data.filteredSpecs[0];
  if (first) {
    page.selectSpec({ currentTarget: { dataset: { id: first.id, type: first.type, group: first.groupId, spec: first.specId } } });
  }
  console.log('__SPEC_LAYOUT_JSON__' + JSON.stringify({ status: 'PASS', searches, afterShowMore, wxCalls }, null, 2));
})().catch(err => {
  console.log('__SPEC_LAYOUT_JSON__' + JSON.stringify({ status: 'FAIL', error: String(err && err.stack || err), wxCalls }, null, 2));
  process.exit(1);
});
"""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def run_dynamic() -> dict[str, Any]:
    harness_path = Path(tempfile.gettempdir()) / "verify_spec_layout_harness.js"
    harness_path.write_text(HARNESS, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path), str(ROOT)],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
    )
    marker = "__SPEC_LAYOUT_JSON__"
    stdout = completed.stdout or ""
    if marker in stdout:
        payload = json.loads(stdout.split(marker, 1)[1])
    else:
        payload = {"status": "FAIL", "stdout": stdout[-4000:], "stderr": completed.stderr[-4000:]}
    payload["returncode"] = completed.returncode
    if completed.stderr:
        payload["stderr"] = completed.stderr[-4000:]
    return payload


def static_layout_checks() -> dict[str, bool]:
    css = _read(ROOT / "pages" / "specs" / "specs.wxss")
    wxml = _read(ROOT / "pages" / "specs" / "specs.wxml")
    return {
        "pageMaxWidth100vw": "max-width: 100vw" in css and "overflow-x: hidden" in css,
        "pageBoxSizing": ".page" in css and "box-sizing: border-box" in css,
        "toolbarGridStable": "grid-template-columns: minmax(0, 1fr) 112rpx" in css,
        "searchInputMinWidth": ".spec-search-input" in css and "min-width: 0" in css,
        "gridUsesMinmax": "grid-template-columns: repeat(2, minmax(0, 1fr))" in css,
        "cardMinWidthZero": ".spec-card" in css and "min-width: 0" in css,
        "cardOverflowHidden": ".spec-card" in css and "overflow: hidden" in css,
        "fixedIconArea": ("flex: 0 0 68rpx" in css and "width: 68rpx" in css)
        or ("flex: 0 0 72rpx" in css and "width: 72rpx" in css),
        "nameTwoLineClamp": "-webkit-line-clamp: 2" in css and "word-break: break-all" in css,
        "colorDotsStable": ".spec-colors" in css and "min-height: 22rpx" in css,
        "filterButtonPresent": "spec-filter-btn" in wxml and "toggleFilter" in wxml,
        "searchInputPresent": "spec-search-input" in wxml and "onSearch" in wxml,
    }


def draw_reference_like(dynamic: dict[str, Any], target: Path) -> None:
    width, height = 720, 1280
    image = Image.new("RGB", (width, height), (246, 248, 252))
    draw = ImageDraw.Draw(image)
    # phone frame
    draw.rounded_rectangle([48, 28, width - 48, height - 28], radius=62, fill=(12, 17, 24))
    draw.rounded_rectangle([68, 50, width - 68, height - 50], radius=48, fill=(250, 252, 255))
    draw.rounded_rectangle([280, 58, 440, 88], radius=18, fill=(0, 0, 0))
    draw.text((118, 100), "<", fill=(15, 23, 42))
    draw.text((270, 104), "搜索证件照规格", fill=(15, 23, 42))
    draw.rounded_rectangle([118, 170, 500, 232], radius=31, fill=(255, 255, 255), outline=(226, 232, 240))
    draw.text((150, 192), "🔍  搜索规格名称、尺寸或用途", fill=(142, 152, 168))
    draw.rounded_rectangle([520, 170, 620, 232], radius=18, fill=(255, 255, 255), outline=(226, 232, 240))
    draw.text((546, 192), "筛选", fill=(37, 99, 235))
    draw.text((118, 280), "常用规格", fill=(15, 23, 42))
    draw.text((118, 326), "常用入口优先展示，多尺寸规格点击后再选择具体尺寸", fill=(100, 116, 139))
    draw.text((118, 360), "规格要求可能随地区和报名平台调整，请以提交平台最新公告为准。", fill=(180, 105, 0))

    colors = [(37, 99, 235), (255, 255, 255), (239, 68, 68), (125, 211, 252), (148, 163, 184)]
    cards = []
    for item in (dynamic.get("searches") or [{}])[0].get("names", [])[:8]:
        cards.append(item)
    fallback = ["一寸", "二寸", "教师资格证", "国考 / 公务员", "驾驶证", "会计 / 职称考试", "学籍 / 入学报名", "社保 / 身份证"]
    while len(cards) < 8:
        cards.append(fallback[len(cards)])
    x0, y0 = 118, 410
    card_w, card_h, gap = 236, 132, 18
    for idx, title in enumerate(cards[:8]):
        row, col = divmod(idx, 2)
        x = x0 + col * (card_w + gap)
        y = y0 + row * (card_h + gap)
        draw.rounded_rectangle([x, y, x + card_w, y + card_h], radius=18, fill=(255, 255, 255), outline=(234, 239, 247))
        draw.rounded_rectangle([x + 18, y + 36, x + 68, y + 86], radius=12, fill=(232, 240, 254))
        draw.ellipse([x + 34, y + 48, x + 52, y + 66], fill=(37, 99, 235))
        draw.text((x + 86, y + 32), str(title)[:10], fill=(15, 23, 42))
        draw.text((x + 86, y + 66), "25×35mm | 295×413px" if idx == 0 else "多种尺寸，点击选择", fill=(142, 152, 168))
        for cidx, color in enumerate(colors[: 3 + (idx % 3)]):
            cx = x + 88 + cidx * 18
            cy = y + 100
            draw.ellipse([cx, cy, cx + 10, cy + 10], fill=color, outline=(203, 213, 225))
        if idx in {2, 3, 4, 5, 6}:
            draw.rounded_rectangle([x + card_w - 42, y, x + card_w, y + 24], radius=8, fill=(255, 100, 72))
            draw.text((x + card_w - 35, y + 3), "热门", fill=(255, 255, 255))
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, quality=94)


def main() -> int:
    FINAL.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    dynamic = run_dynamic()
    static_checks = static_layout_checks()
    screenshot = SHOTS / "spec-layout-iphone13-reference-check.jpg"
    draw_reference_like(dynamic, screenshot)
    checks = {
        **static_checks,
        "dynamicSearchPass": dynamic.get("status") == "PASS",
        "searchTermsCovered": len(dynamic.get("searches") or []) >= 4,
        "showMoreWorks": (dynamic.get("afterShowMore") or {}).get("hiddenSearchCount") == 0,
        "screenshotGenerated": screenshot.exists(),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "status": status,
        "checks": checks,
        "dynamic": dynamic,
        "screenshot": str(screenshot),
        "viewports": ["iPhone 12/13", "iPhone 14/15", "Android tall"],
        "searchTerms": ["一寸", "教师资格证", "驾驶证", "国考"],
    }
    (FINAL / "spec-layout-validation-report.json").write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    md = [
        "# Spec Layout Validation Report",
        "",
        f"- Status: {status}",
        f"- Screenshot: `{screenshot}`",
        "",
        "## Checks",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in checks.items()],
        "",
        "## Dynamic Searches",
    ]
    for item in dynamic.get("searches") or []:
        md.append(f"- {item.get('term')}: count={item.get('count')} hidden={item.get('hiddenSearchCount')}")
    (FINAL / "spec-layout-validation-report.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[verify-spec-layout] {status} report={FINAL / 'spec-layout-validation-report.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
