"""Verify restoration of ID-photo spec visibility, search, category, and UI flow.

This round intentionally stays in the spec-display scope. It verifies that old
spec cards were restored as visible/searchable/category entries while the
corrected dimensions and source-level labels remain in place.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "spec-restore"
FINAL = REPORT_ROOT / "final"

GROUP_IDS = [
    "one_inch",
    "small_one_inch",
    "two_inch",
    "large_one_inch",
    "teacher_cert",
    "civil_service_exam",
    "driver_license",
    "accounting_title_exam",
    "language_computer_exam",
    "school_enrollment",
    "professional_license_exam",
    "social_id_card",
    "passport_visa",
    "custom_size",
]

GROUP_MIN_COUNTS = {
    "teacher_cert": 6,
    "civil_service_exam": 4,
    "driver_license": 3,
    "accounting_title_exam": 4,
    "language_computer_exam": 2,
    "school_enrollment": 15,
    "professional_license_exam": 5,
    "social_id_card": 2,
    "passport_visa": 5,
}

RESTORED_VISIBLE_IDS = [
    "teacher_cert_413_579",
    "teacher_cert_180_240",
    "teacher_cert_150_200",
    "teacher_cert_384_512",
    "teacher_cert_province_pending",
    "civil_service_min_295_413",
    "civil_service_two_inch",
    "driver_guangdong_common",
    "driver_other_province_common",
    "accounting_middle_240_320",
    "accounting_middle_114_156",
    "accounting_middle_shanghai_215_300",
    "school_status_307_378",
    "school_net_472_630",
    "school_qingdao_fushan_195_240",
    "school_lingnan_120_150",
    "school_status_390_480",
    "school_status_150_200",
    "school_status_90_120",
    "school_status_300_420",
    "primary_enroll_300_420",
    "cau_enroll_420_564",
    "bnu_enroll_250_350",
    "znufe_enroll_180_240",
    "insurance_practice_210_370",
    "judicial_exam_413_626",
    "passport_cn_390_567",
    "visa_general_390_567",
    "hongkong_macao_pass_390_567",
    "taiwan_pass_390_567",
    "entry_exit_photo_390_567",
]

NON_OFFICIAL_IDS = [
    "teacher_cert_180_240",
    "teacher_cert_150_200",
    "teacher_cert_384_512",
    "civil_service_two_inch",
    "accounting_middle_114_156",
    "insurance_practice_210_370",
]

SIZE_EXPECTATIONS = {
    "yicun": (295, 413),
    "xiaoyicun": (260, 378),
    "ercun": (413, 579),
    "dayicun": (390, 567),
    "teacher_cert_295_413": (295, 413),
    "driver_common": (260, 378),
    "civil_service_min_295_413": (295, 413),
    "accounting_junior_295_413": (295, 413),
}

SEARCH_EXPECTATIONS = {
    "teacher": {
        "term": "\u6559\u5e08",
        "must": ["teacher_cert_295_413", "teacher_cert_180_240", "teacher_cert_150_200"],
    },
    "civil": {
        "term": "\u56fd\u8003",
        "must": ["civil_service_common", "civil_service_min_295_413", "civil_service_two_inch"],
    },
    "driver": {
        "term": "\u9a7e\u9a76",
        "must": ["driver_common", "driver_guangdong_common", "driver_other_province_common"],
    },
    "accounting": {
        "term": "\u4f1a\u8ba1",
        "must": ["accounting_junior_295_413", "accounting_middle_114_156"],
    },
    "school": {
        "term": "\u5b66\u7c4d",
        "must": ["school_status_307_378", "school_status_90_120", "enroll_295_413"],
    },
    "passport": {
        "term": "\u62a4\u7167",
        "must": ["passport_cn_390_567", "visa_general_390_567", "entry_exit_photo_390_567"],
    },
    "size114": {"term": "114x156", "must": ["accounting_middle_114_156"]},
    "size150": {"term": "150x200", "must": ["teacher_cert_150_200", "school_status_150_200"]},
}


NODE_SNAPSHOT = r"""
const path = require('path');
const specs = require('./utils/specs.js');
const groupIds = __GROUP_IDS__;
const specIds = __SPEC_IDS__;
const searchTerms = __SEARCH_TERMS__;

function simpleSpec(spec) {
  if (!spec) return null;
  return {
    id: spec.id,
    name: spec.displayName || spec.name || spec.id,
    groupId: spec.groupId || '',
    groupName: spec.groupName || '',
    category: spec.category || '',
    mm: spec.mm || '',
    px: spec.px || '',
    widthMm: spec.widthMm || null,
    heightMm: spec.heightMm || null,
    widthPx: spec.widthPx || null,
    heightPx: spec.heightPx || null,
    sourceLevel: spec.sourceLevel || '',
    enabled: spec.enabled !== false && spec.active !== false,
    showInSearch: spec.showInSearch !== false,
    showInCategory: spec.showInCategory !== false,
    keepSeparate: spec.keepSeparate === true,
    colors: spec.backgrounds || spec.bgColors || spec.colors || [],
    fileText: spec.fileText || ((spec.fileFormat || ['jpg', 'jpeg']).join('/').toUpperCase()),
    notice: spec.notice || spec.note || '',
  };
}

function simpleCard(card) {
  return {
    id: card.id,
    specId: card.specId || '',
    groupId: card.groupId || '',
    type: card.type || '',
    name: card.name || '',
    size: card.size || '',
    category: card.category || '',
    fileText: card.fileText || '',
    sourceBadge: card.sourceBadge || '',
    applicableText: card.applicableText || '',
    colors: card.colors || [],
  };
}

const raw = [];
const rawSeen = new Set();
function pushRaw(spec, group) {
  if (!spec || !spec.id || rawSeen.has(spec.id)) return;
  rawSeen.add(spec.id);
  raw.push(Object.assign(simpleSpec(spec), {
    rawGroupId: group && group.groupId || '',
    rawGroupName: group && group.groupName || '',
  }));
}
(specs.photoSpecs || []).forEach(s => pushRaw(s, null));
(specs.specGroups || []).forEach(g => (g.specs || []).forEach(s => pushRaw(s, g)));

const enabled = specs.getSpecsByCategory('all').map(simpleSpec);
const groups = {};
for (const gid of groupIds) {
  const group = specs.getGroupById(gid);
  const items = specs.getGroupSpecs(gid).map(simpleSpec);
  groups[gid] = {
    id: gid,
    exists: !!group,
    name: group && group.groupName || '',
    category: group && group.category || '',
    displayMode: group && group.displayMode || '',
    enabled: !(group && group.enabled === false),
    mergeSpecs: group && group.mergeSpecs,
    count: items.length,
    ids: items.map(s => s.id),
    items,
  };
}

const searches = {};
for (const [name, term] of Object.entries(searchTerms)) {
  const rows = specs.searchSpecEntries(term).map(simpleCard);
  searches[name] = { term, count: rows.length, ids: rows.map(r => r.specId), rows };
}

let currentRoute = '';
const pages = {};
const wxCalls = [];
global.getApp = () => ({ globalData: {} });
global.Page = function(def) {
  def.data = JSON.parse(JSON.stringify(def.data || {}));
  def.setData = function(next, cb) {
    Object.assign(this.data, next || {});
    if (typeof cb === 'function') cb.call(this);
  };
  pages[currentRoute] = def;
};
global.wx = {
  setNavigationBarTitle(opts) { wxCalls.push({ fn: 'setNavigationBarTitle', opts }); },
  navigateTo(opts) { wxCalls.push({ fn: 'navigateTo', opts }); },
  showActionSheet(opts) { wxCalls.push({ fn: 'showActionSheet', opts }); },
};
function loadPage(route) {
  currentRoute = route;
  const file = path.join(process.cwd(), route + '.js');
  delete require.cache[require.resolve(file)];
  require(file);
  return pages[route];
}
function pageRun(loadArgs) {
  const page = loadPage('pages/specs/specs');
  page.onLoad(loadArgs || {});
  return {
    args: loadArgs || {},
    pageMode: page.data.pageMode,
    currentGroupId: page.data.currentGroupId || '',
    currentGroupName: page.data.currentGroupName || '',
    count: (page.data.filteredSpecs || []).length,
    ids: (page.data.filteredSpecs || []).map(item => item.specId || item.groupId || item.id),
    names: (page.data.filteredSpecs || []).map(item => item.name).slice(0, 30),
  };
}
function pageSearch(term) {
  const page = loadPage('pages/specs/specs');
  page.onLoad({});
  page.onSearch({ detail: { value: term } });
  return {
    term,
    pageMode: page.data.pageMode,
    count: (page.data.filteredSpecs || []).length,
    hiddenSearchCount: page.data.hiddenSearchCount || 0,
    ids: (page.data.filteredSpecs || []).map(item => item.specId || item.groupId || item.id),
  };
}

let page = { status: 'PASS', wxCalls };
try {
  page.default = pageRun({});
  page.teacher = pageRun({ groupId: 'teacher_cert' });
  page.accounting = pageRun({ groupId: 'accounting_title_exam' });
  page.school = pageRun({ groupId: 'school_enrollment' });
  page.passport = pageRun({ groupId: 'passport_visa' });
  page.searches = {};
  for (const [name, term] of Object.entries(searchTerms)) {
    page.searches[name] = pageSearch(term);
  }
} catch (err) {
  page = { status: 'FAIL', error: String(err && err.stack || err), wxCalls };
}

const byId = {};
for (const id of specIds) byId[id] = simpleSpec(specs.getSpecById(id));

console.log(JSON.stringify({
  generatedAt: new Date().toISOString(),
  rawCount: raw.length,
  enabledCount: enabled.length,
  raw,
  enabled,
  homeCards: specs.getSpecGroupCards('').map(simpleCard),
  allGroupCards: specs.getSpecGroupCards('\u5168\u90e8').map(simpleCard),
  groups,
  searches,
  byId,
  page,
}, null, 2));
"""


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def collect_snapshot() -> dict[str, Any]:
    search_terms = {name: item["term"] for name, item in SEARCH_EXPECTATIONS.items()}
    node_code = (
        NODE_SNAPSHOT
        .replace("__GROUP_IDS__", json.dumps(GROUP_IDS))
        .replace("__SPEC_IDS__", json.dumps(sorted(set(RESTORED_VISIBLE_IDS + list(SIZE_EXPECTATIONS.keys()) + NON_OFFICIAL_IDS))))
        .replace("__SEARCH_TERMS__", json.dumps(search_terms))
    )
    out = subprocess.check_output(
        ["node", "-e", node_code],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return json.loads(out)


def has_spec(snapshot: dict[str, Any], spec_id: str) -> bool:
    spec = (snapshot.get("byId") or {}).get(spec_id)
    return bool(spec and spec.get("enabled"))


def validate(snapshot: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, dict[str, bool]] = {
        "restore": {},
        "visibility": {},
        "search": {},
        "category": {},
        "ui": {},
    }

    groups = snapshot.get("groups") or {}
    searches = snapshot.get("searches") or {}
    by_id = snapshot.get("byId") or {}
    page = snapshot.get("page") or {}

    checks["restore"]["enabledSpecCountAtLeast90"] = int(snapshot.get("enabledCount") or 0) >= 90
    checks["restore"]["allGroupCardsRestored"] = len(snapshot.get("allGroupCards") or []) >= 12
    checks["restore"]["restoredIdsEnabled"] = all(has_spec(snapshot, spec_id) for spec_id in RESTORED_VISIBLE_IDS)
    checks["restore"]["correctedMainSizesKept"] = all(
        (by_id.get(spec_id) or {}).get("widthPx") == size[0] and (by_id.get(spec_id) or {}).get("heightPx") == size[1]
        for spec_id, size in SIZE_EXPECTATIONS.items()
    )
    checks["restore"]["lowOrHistoricalNotOfficial"] = all((by_id.get(spec_id) or {}).get("sourceLevel") != "official" for spec_id in NON_OFFICIAL_IDS)
    checks["restore"]["passportSearchKeepsSeparateCards"] = all((by_id.get(spec_id) or {}).get("keepSeparate") is True for spec_id in [
        "passport_cn_390_567",
        "visa_general_390_567",
        "entry_exit_photo_390_567",
    ])

    checks["visibility"]["allRestoredShownInSearch"] = all((by_id.get(spec_id) or {}).get("showInSearch") is not False for spec_id in RESTORED_VISIBLE_IDS)
    checks["visibility"]["allRestoredShownInCategory"] = all((by_id.get(spec_id) or {}).get("showInCategory") is not False for spec_id in RESTORED_VISIBLE_IDS)
    checks["visibility"]["homePageShowsOldCategoryGrid"] = (page.get("default") or {}).get("count", 0) >= 12
    checks["visibility"]["teacherPageShowsSixCards"] = (page.get("teacher") or {}).get("count", 0) >= 6
    checks["visibility"]["passportPageShowsFiveCards"] = (page.get("passport") or {}).get("count", 0) >= 5

    for name, expectation in SEARCH_EXPECTATIONS.items():
        ids = set((searches.get(name) or {}).get("ids") or [])
        checks["search"][f"{name}SearchContainsRequired"] = all(spec_id in ids for spec_id in expectation["must"])
    checks["search"]["searchPageDynamicWorks"] = page.get("status") == "PASS" and all(
        (item or {}).get("count", 0) > 0 for item in (page.get("searches") or {}).values()
    )

    for group_id, min_count in GROUP_MIN_COUNTS.items():
        checks["category"][f"{group_id}CountAtLeast{min_count}"] = (groups.get(group_id) or {}).get("count", 0) >= min_count
    checks["category"]["categoryCardsAllPresent"] = all((groups.get(group_id) or {}).get("exists") for group_id in GROUP_IDS)
    checks["category"]["passportMergeDisabledOnlyForPassport"] = (groups.get("passport_visa") or {}).get("mergeSpecs") is False

    specs_js = (ROOT / "pages" / "specs" / "specs.js").read_text(encoding="utf-8", errors="replace")
    specs_wxml = (ROOT / "pages" / "specs" / "specs.wxml").read_text(encoding="utf-8", errors="replace")
    specs_wxss = (ROOT / "pages" / "specs" / "specs.wxss").read_text(encoding="utf-8", errors="replace")
    checks["ui"]["defaultLoadUsesAllCategories"] = "getSpecGroupCards(cat || '全部')" in specs_js
    checks["ui"]["fileTextRendered"] = "spec-file-text" in specs_wxml and "item.fileText" in specs_wxml
    checks["ui"]["shortApplicableRendered"] = "spec-card-apply" in specs_wxml and "item.applicableText" in specs_wxml
    checks["ui"]["sourceClassesStyled"] = all(name in specs_wxss for name in [
        "source-platform",
        "source-local_common",
        "source-deprecated",
        "source-custom",
    ])
    checks["ui"]["dynamicPageHarnessPass"] = page.get("status") == "PASS"

    return checks


def flatten_failures(checks: dict[str, dict[str, bool]], mode: str) -> list[str]:
    selected = [mode] if mode in checks else list(checks)
    failures: list[str] = []
    for section in selected:
        for name, ok in checks.get(section, {}).items():
            if not ok:
                failures.append(f"{section}.{name}")
    return failures


def write_reports(snapshot: dict[str, Any], checks: dict[str, dict[str, bool]], mode: str, failures: list[str]) -> None:
    FINAL.mkdir(parents=True, exist_ok=True)
    write_json(FINAL / "spec-restore-snapshot.json", snapshot)

    old_expected = [
        ("one_inch", "one-inch common entry"),
        ("two_inch", "two-inch common entry"),
        ("teacher_cert", "teacher certificate category"),
        ("civil_service_exam", "national/civil-service category"),
        ("driver_license", "driver license category"),
        ("accounting_title_exam", "accounting/title exam category"),
        ("school_enrollment", "school/enrollment category"),
        ("language_computer_exam", "language/computer exam category"),
        ("professional_license_exam", "nurse/doctor/guide category"),
        ("social_id_card", "social/security/id-card category"),
        ("passport_visa", "passport/visa/entry-exit category"),
        ("custom_size", "custom size entry"),
    ]
    category_lines = [
        "# Old Vs Current Category Report",
        "",
        f"- Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Current all-category card count: {len(snapshot.get('allGroupCards') or [])}",
        "",
        "| expected old entry | current status | current spec count |",
        "|---|---:|---:|",
    ]
    groups = snapshot.get("groups") or {}
    for gid, label in old_expected:
        group = groups.get(gid) or {}
        category_lines.append(f"| {label} (`{gid}`) | {'restored' if group.get('exists') and group.get('enabled') else 'missing'} | {group.get('count', 0)} |")
    write_md(FINAL / "old-vs-current-category-report.md", category_lines)

    audit_lines = [
        "# Current Visible Spec Audit",
        "",
        f"- Enabled specs: {snapshot.get('enabledCount')}",
        "",
        "| id | name | category | mm | px | source | colors |",
        "|---|---|---|---|---|---|---|",
    ]
    for spec in snapshot.get("enabled") or []:
        audit_lines.append(
            f"| {spec.get('id')} | {spec.get('name')} | {spec.get('category')} | {spec.get('mm')} | {spec.get('px')} | {spec.get('sourceLevel')} | {','.join(spec.get('colors') or [])} |"
        )
    write_md(FINAL / "current-visible-spec-audit.md", audit_lines)

    visibility_lines = [
        "# Spec Visibility Before After",
        "",
        "- Before: this round was triggered because the previous cleanup hid historical/platform specs from category and search pages.",
        "- After: restored specs are enabled, searchable, and visible in their original category pages, while corrected main dimensions remain unchanged.",
        "",
        "| section | status |",
        "|---|---|",
    ]
    for section, section_checks in checks.items():
        visibility_lines.append(f"| {section} | {'PASS' if all(section_checks.values()) else 'FAIL'} |")
    write_md(FINAL / "spec-visibility-before-after.md", visibility_lines)

    restored_lines = ["# Restored Spec List", "", "| id | enabled | search | category | source | px |", "|---|---:|---:|---:|---|---|"]
    by_id = snapshot.get("byId") or {}
    for spec_id in RESTORED_VISIBLE_IDS:
        spec = by_id.get(spec_id) or {}
        restored_lines.append(
            f"| {spec_id} | {bool(spec.get('enabled'))} | {spec.get('showInSearch') is not False} | {spec.get('showInCategory') is not False} | {spec.get('sourceLevel', '')} | {spec.get('px', '')} |"
        )
    write_md(FINAL / "restored-spec-list.md", restored_lines)

    search_lines = ["# Spec Search Report", "", "| search | term | count | required ids present | result ids |", "|---|---|---:|---:|---|"]
    searches = snapshot.get("searches") or {}
    for name, expectation in SEARCH_EXPECTATIONS.items():
        ids = searches.get(name, {}).get("ids") or []
        ok = all(spec_id in ids for spec_id in expectation["must"])
        search_lines.append(f"| {name} | `{expectation['term']}` | {len(ids)} | {ok} | `{', '.join(ids[:25])}` |")
    write_md(FINAL / "spec-search-report.md", search_lines)

    spec_category_lines = ["# Spec Category Report", "", "| group | count | ids |", "|---|---:|---|"]
    for gid in GROUP_IDS:
        group = groups.get(gid) or {}
        spec_category_lines.append(f"| {gid} | {group.get('count', 0)} | `{', '.join((group.get('ids') or [])[:40])}` |")
    write_md(FINAL / "spec-category-report.md", spec_category_lines)

    fixed_files = [
        "# Fixed Files",
        "",
        "- `utils/specs.js`: restored hidden historical/platform specs, kept corrected main sizes, added per-group merge bypass for passport/visa cards, and kept passport search cards separate.",
        "- `pages/specs/specs.js`: default specs page now loads the full category grid instead of the reduced popular-only set.",
        "- `pages/specs/specs.wxml`: restored compact file/source/applicable metadata needed for old-style cards without long blocking text.",
        "- `pages/specs/specs.wxss`: restored source badge styles for platform/local/deprecated/custom entries.",
        "- `server/scripts/verify_id_photo_spec_restore.py`: added this round's fresh spec-restore verification and reports.",
    ]
    write_md(FINAL / "fixed-files.md", fixed_files)

    payload = {
        "status": "PASS" if not failures else "FAIL",
        "mode": mode,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "enabledSpecCount": snapshot.get("enabledCount"),
        "allCategoryCardCount": len(snapshot.get("allGroupCards") or []),
        "checks": checks,
        "failures": failures,
        "reports": {
            "oldVsCurrentCategory": str(FINAL / "old-vs-current-category-report.md"),
            "currentVisibleSpecAudit": str(FINAL / "current-visible-spec-audit.md"),
            "visibilityBeforeAfter": str(FINAL / "spec-visibility-before-after.md"),
            "restoredSpecList": str(FINAL / "restored-spec-list.md"),
            "specSearch": str(FINAL / "spec-search-report.md"),
            "specCategory": str(FINAL / "spec-category-report.md"),
            "fixedFiles": str(FINAL / "fixed-files.md"),
        },
    }
    write_json(FINAL / "final-summary.json", payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["restore", "visibility", "search", "category", "ui", "all"], default="all")
    args = parser.parse_args(argv)

    snapshot = collect_snapshot()
    checks = validate(snapshot)
    failures = flatten_failures(checks, args.mode)
    write_reports(snapshot, checks, args.mode, failures)
    status = "PASS" if not failures else "FAIL"
    print(f"[verify-id-photo-spec-restore] {status} mode={args.mode} report={FINAL / 'final-summary.json'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
