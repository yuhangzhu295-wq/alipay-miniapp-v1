"""Audit and validate the ID-photo specification catalog."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "spec-cleanup"
FINAL = REPORT_ROOT / "final"


NODE_READ_CATALOG = r"""
const specs = require('./utils/specs.js');
const raw = [];
const seen = new Set();
function pushSpec(spec, group) {
  if (!spec || !spec.id || seen.has(spec.id)) return;
  seen.add(spec.id);
  raw.push(Object.assign({
    groupId: group && group.groupId || '',
    groupName: group && group.groupName || '',
    groupCategory: group && group.category || '',
  }, spec));
}
(specs.photoSpecs || []).forEach(s => pushSpec(s, null));
(specs.specGroups || []).forEach(g => (g.specs || []).forEach(s => pushSpec(s, g)));
const enabled = specs.getSpecsByCategory ? specs.getSpecsByCategory('all') : raw.filter(s => s.enabled !== false && s.active !== false);
const popular = specs.getSpecGroupCards ? specs.getSpecGroupCards('') : [];
const groupCards = specs.getSpecGroupCards ? specs.getSpecGroupCards('全部') : [];
console.log(JSON.stringify({
  raw,
  enabled,
  popular,
  groupCards,
  groups: specs.specGroups || [],
  sourceLabels: specs.sourceLabels || {},
}, null, 2));
"""

ALLOWED_SOURCE_LEVELS = {"official", "local_common", "platform", "deprecated", "custom", "unknown"}
BAD_TEACHER_IDS = {"teacher_cert_150_200", "teacher_cert_180_240", "teacher_cert_384_512"}
POPULAR_IDS = ["one_inch", "small_one_inch", "two_inch", "large_one_inch", "teacher_cert", "driver_license"]
REQUIRED_FINAL_REPORTS = [
    "spec-catalog-report.md",
    "spec-diff-before-after.md",
    "fixed-files.md",
]


def read_catalog() -> dict[str, Any]:
    out = subprocess.check_output(
        ["node", "-e", NODE_READ_CATALOG],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return json.loads(out)


def source_level(spec: dict[str, Any]) -> str:
    return str(spec.get("sourceLevel") or "")


def enabled(spec: dict[str, Any]) -> bool:
    return spec.get("enabled") is not False and spec.get("active") is not False


def size_px(spec: dict[str, Any]) -> str:
    return f"{spec.get('widthPx') or ''}x{spec.get('heightPx') or ''}"


def size_mm(spec: dict[str, Any]) -> str:
    return f"{spec.get('widthMm') or ''}x{spec.get('heightMm') or ''}"


def colors(spec: dict[str, Any]) -> list[str]:
    return list(spec.get("backgrounds") or spec.get("bgColors") or spec.get("colors") or [])


def file_limit(spec: dict[str, Any]) -> str:
    if spec.get("fileSizeLimit"):
        return str(spec["fileSizeLimit"])
    parts = []
    if spec.get("minFileKB"):
        parts.append(f">={spec['minFileKB']}KB")
    if spec.get("maxFileKB"):
        parts.append(f"<={spec['maxFileKB']}KB")
    return ", ".join(parts) or "按平台要求"


def classify_issue(spec: dict[str, Any]) -> tuple[bool, bool, str]:
    sid = str(spec.get("id") or "")
    name = str(spec.get("displayName") or spec.get("name") or "")
    px = size_px(spec)
    mm = size_mm(spec)
    level = source_level(spec)
    reasons: list[str] = []
    missing = False
    wrong = False
    if level not in ALLOWED_SOURCE_LEVELS:
        wrong = True
        missing = True
        reasons.append("sourceLevel 不在规范枚举")
    if not spec.get("notice"):
        missing = True
        reasons.append("缺少 notice")
    if not spec.get("dpi"):
        missing = True
        reasons.append("缺少 dpi")
    if not colors(spec):
        wrong = True
        reasons.append("缺少底色")
    if ("teacher" in sid or "教师" in name) and px in {"150x200", "180x240", "384x512"} and level == "official":
        wrong = True
        reasons.append("低分辨率教资规格被标为官方")
    if ("civil_service" in sid or "公务员" in name or "国考" in name) and mm == "35x53" and level == "official":
        wrong = True
        reasons.append("35x53mm 公务员规格被标为官方")
    if sid in {"driver", "driver_common"} and not (mm == "22x32" and px == "260x378" and colors(spec) == ["white"]):
        wrong = True
        reasons.append("驾驶证默认规格不是 22x32mm/260x378px/白底")
    if "accounting" in sid and px == "114x156" and level == "official":
        wrong = True
        reasons.append("114x156px 会计规格被标为官方")
    if sid == "insurance_practice_210_370" and level == "official":
        wrong = True
        reasons.append("18x31mm 保险执业规格被标为官方")
    if (mm == "33x48" or px == "390x567") and sid in {"dayicun", "large-one-inch"} and level != "local_common":
        wrong = True
        reasons.append("33x48mm/390x567px 未标为地方常用")
    return wrong, missing, "；".join(reasons) or "保留"


def row_action(spec: dict[str, Any], wrong: bool, missing: bool) -> str:
    if not enabled(spec):
        return "禁用/后置"
    if source_level(spec) in {"deprecated", "unknown"}:
        return "后置/按公告"
    if wrong:
        return "需修正"
    if missing:
        return "补充依据"
    return "保留"


def write_audit(catalog: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Current Spec Audit",
        "",
        f"- Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Raw spec count: {len(catalog.get('raw') or [])}",
        f"- Enabled spec count: {len(catalog.get('enabled') or [])}",
        "",
        "| id | 名称 | 分类 | mm | px | DPI | 底色 | 文件大小 | 展示 | 疑似错误 | 缺少依据 | 处理建议 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for spec in catalog.get("raw") or []:
        wrong, missing, reason = classify_issue(spec)
        lines.append(
            "| {id} | {name} | {cat} | {mm} | {px} | {dpi} | {bg} | {limit} | {show} | {wrong} | {missing} | {action}: {reason} |".format(
                id=spec.get("id", ""),
                name=spec.get("displayName") or spec.get("name", ""),
                cat=spec.get("category") or spec.get("groupCategory") or "",
                mm=spec.get("mm") or size_mm(spec),
                px=spec.get("px") or size_px(spec),
                dpi=spec.get("dpi") or "",
                bg=",".join(colors(spec)),
                limit=file_limit(spec),
                show="是" if enabled(spec) else "否",
                wrong="是" if wrong else "否",
                missing="是" if missing else "否",
                action=row_action(spec, wrong, missing),
                reason=reason,
            )
        )
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    raw = catalog.get("raw") or []
    enabled_specs = catalog.get("enabled") or []
    by_id = {s.get("id"): s for s in raw}
    enabled_by_id = {s.get("id"): s for s in enabled_specs}
    popular_ids = [item.get("id") for item in catalog.get("popular") or []]
    failures: list[str] = []
    for spec in enabled_specs:
        sid = spec.get("id")
        if source_level(spec) not in ALLOWED_SOURCE_LEVELS:
            failures.append(f"{sid}: invalid sourceLevel {source_level(spec)}")
        # Platform specifications may be defined only in pixels. Millimeter
        # dimensions are optional unless the source explicitly publishes them.
        for key in ["id", "name", "category", "widthPx", "heightPx", "dpi", "backgrounds", "fileSizeLimit", "sourceLevel", "notice", "enabled", "sort", "aliases"]:
            if key not in spec:
                failures.append(f"{sid}: missing {key}")
    for sid in BAD_TEACHER_IDS:
        spec = by_id.get(sid)
        if spec and source_level(spec) == "official":
            failures.append(f"{sid}: teacher low-res spec marked official")
    civil_two = by_id.get("civil_service_two_inch") or by_id.get("civil_service_413_626")
    if civil_two and enabled(civil_two) and source_level(civil_two) == "official":
        failures.append("civil_service 35x53mm spec incorrectly marked official")
    driver = enabled_by_id.get("driver_common") or enabled_by_id.get("driver")
    if not driver or not (driver.get("widthMm") == 22 and driver.get("heightMm") == 32 and driver.get("widthPx") == 260 and driver.get("heightPx") == 378 and colors(driver) == ["white"]):
        failures.append("driver default is not 22x32mm / 260x378px / white")
    accounting_low = by_id.get("accounting_middle_114_156")
    if accounting_low and enabled(accounting_low) and source_level(accounting_low) == "official":
        failures.append("accounting 114x156px spec incorrectly marked official")
    insurance = by_id.get("insurance_practice_210_370")
    if insurance and enabled(insurance) and source_level(insurance) == "official":
        failures.append("insurance 18x31mm spec incorrectly marked official")
    dayicun = enabled_by_id.get("dayicun")
    if not dayicun or source_level(dayicun) != "local_common":
        failures.append("33x48mm / 390x567px dayicun is not local_common")
    if popular_ids != POPULAR_IDS:
        failures.append(f"popular ids mismatch: {popular_ids}")
    return {
        "status": "PASS" if not failures else "FAIL",
        "rawSpecCount": len(raw),
        "enabledSpecCount": len(enabled_specs),
        "popularIds": popular_ids,
        "failures": failures,
    }


def write_final_reports(catalog: dict[str, Any], result: dict[str, Any]) -> None:
    FINAL.mkdir(parents=True, exist_ok=True)
    enabled_specs = catalog.get("enabled") or []
    lines = [
        "# Spec Catalog Report",
        "",
        f"- Status: {result['status']}",
        f"- Raw specs: {result['rawSpecCount']}",
        f"- Enabled specs: {result['enabledSpecCount']}",
        f"- Popular ids: `{', '.join(result['popularIds'])}`",
        "",
        "## Enabled Specs",
        "| id | 名称 | 分类 | mm | px | dpi | 底色 | sourceLevel | 文件大小 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for spec in enabled_specs:
        lines.append(
            f"| {spec.get('id')} | {spec.get('displayName') or spec.get('name')} | {spec.get('category')} | {spec.get('mm') or size_mm(spec)} | {spec.get('px') or size_px(spec)} | {spec.get('dpi')} | {','.join(colors(spec))} | {source_level(spec)} | {file_limit(spec)} |"
        )
    if result["failures"]:
        lines.extend(["", "## Failures", *[f"- {x}" for x in result["failures"]]])
    (FINAL / "spec-catalog-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (FINAL / "spec-diff-before-after.md").write_text(
        "\n".join([
            "# Spec Diff Before After",
            "",
            "- 教师资格证：保留 295x413 主规格；150x200、180x240、384x512 仅作为平台专用像素规格，不标为官方通用入口。",
            "- 国考/公务员：保留主规格与平台专用规格；35x53mm 二寸类不标为官方默认标准。",
            "- 驾驶证：默认规格为 22x32mm / 260x378px / 白底；35x49mm 地方/平台项后置。",
            "- 会计/职称：主推 295x413；114x156px 仅按对应平台要求展示。",
            "- 医护/导游/保险：18x31mm 保险执业规格仅按对应平台要求展示；医护/导游保留常用报名照尺寸。",
            "- 学籍/入学：保留 295x413、413x531 通用项；纯像素学校/平台项允许展示，但不补造毫米尺寸。",
            "- 33x48mm / 390x567px：标注为 local_common 地方常用，不再标成全国统一标准。",
        ]) + "\n",
        encoding="utf-8",
    )
    (FINAL / "fixed-files.md").write_text(
        "\n".join([
            "# Fixed Files",
            "",
            "- `utils/specs.js`: 规格来源级别、启用状态、热门入口、分类与展示元数据规范化。",
            "- `pages/specs/specs.js`: 筛选分类改为规范分类，卡片数据只保留短标签。",
            "- `pages/specs/specs.wxml`: 顶部统一公告提示，移除卡片大段说明展示。",
            "- `server/scripts/verify_id_photo_spec_catalog.py`: 新增规格库审计与规则验证。",
            "- `server/scripts/verify_id_photo_spec_ui.py`: 新增规格页面展示验证。",
            "- `package.json`: 新增本轮规格验证命令并串入总回归。",
        ]) + "\n",
        encoding="utf-8",
    )
    (FINAL / "spec-catalog-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args(argv)
    catalog = read_catalog()
    write_audit(catalog, REPORT_ROOT / "current-spec-audit.md")
    if args.audit_only:
        print(f"[verify-id-photo-spec-catalog] AUDIT report={REPORT_ROOT / 'current-spec-audit.md'}")
        return 0
    result = validate_catalog(catalog)
    write_final_reports(catalog, result)
    print(f"[verify-id-photo-spec-catalog] {result['status']} report={FINAL / 'spec-catalog-report.md'}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
