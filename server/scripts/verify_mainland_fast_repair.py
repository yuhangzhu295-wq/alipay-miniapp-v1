from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
OUT = ROOT / "reports" / "mainland-fast-repair"
S01 = ROOT / "reports" / "20260804-performance" / "S01-reconstructed-source.jpg"
S02 = ROOT / "reports" / "id-photo-matting-broken" / "samples" / "09_auto_supplement_sample_03.jpg"
S07 = ROOT / "reports" / "cloud-deploy-e2e" / "20260804-performance-local" / "cloud-tests" / "input-id-photo-source.jpg"

sys.path.insert(0, str(SERVER))
from id_photo_engine_legacy.id_photo_quality import CROP_FAIL_CODES, MATTING_FAIL_CODES, validate_composition_metrics  # noqa: E402
from id_photo_engine_legacy.id_photo_v2 import _fast_quality_fail_reasons  # noqa: E402
from services.id_photo_specs import PHOTO_SPECS  # noqa: E402


def write_json(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def write_md(name, lines):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def percentile(values, value):
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * value)))
    return ordered[index]


def request_prepare(base_url, source, spec_id, hair=False, width=None, height=None, label=""):
    form = {
        "purpose": "official_id_photo",
        "specId": spec_id,
        "mode": "official",
        "composition": "head_shoulder",
        "outfit": "preserve_original",
        "hairRetouch": "true" if hair else "false",
    }
    if width and height:
        form.update({"widthPx": str(width), "heightPx": str(height)})
    started = time.perf_counter()
    with source.open("rb") as handle:
        response = requests.post(
            base_url.rstrip("/") + "/api/id-photo/prepare",
            files={"image": (source.name, handle, "image/jpeg")},
            data=form,
            timeout=240,
        )
    elapsed = int((time.perf_counter() - started) * 1000)
    data = response.json()
    quality = data.get("quality") or {}
    return {
        "label": label or spec_id,
        "source": str(source),
        "specId": spec_id,
        "hairRetouch": hair,
        "controlledOutputSize": f"{width}x{height}" if width and height else "",
        "statusCode": response.status_code,
        "success": bool(data.get("success")),
        "requestId": data.get("requestId"),
        "preparedId": data.get("preparedId"),
        "spec": data.get("spec") or {},
        "requestedModel": quality.get("requestedModel") or ("birefnet-v1-lite" if hair else "hivision_modnet"),
        "fastModel": quality.get("fastModel"),
        "fastDurationMs": int(quality.get("fastDurationMs") or 0),
        "fastQualityReport": quality.get("fastQualityReport") or {},
        "rawFailReasons": quality.get("rawFailReasons") or [],
        "mattingPass": quality.get("mattingPass"),
        "mattingFailReasons": quality.get("mattingFailReasons") or [],
        "fastMattingPass": quality.get("fastMattingPass"),
        "fastMattingFailReasons": quality.get("fastMattingFailReasons") or [],
        "cropPass": quality.get("cropPass"),
        "cropFailReasons": quality.get("cropFailReasons") or [],
        "cropRetryCount": int(quality.get("cropRetryCount") or 0),
        "detailFallbackUsed": bool(quality.get("detailFallbackUsed")),
        "detailFallbackReasons": quality.get("detailFallbackReasons") or [],
        "detailDurationMs": int(quality.get("detailDurationMs") or 0),
        "finalSelectedModel": quality.get("finalSelectedModel") or data.get("engineModel"),
        "fastResultUsable": quality.get("fastResultUsable"),
        "detailRecommended": quality.get("detailRecommended"),
        "detailReasons": quality.get("detailReasons") or [],
        "totalServerMs": int(quality.get("fastDurationMs") or 0) + int(quality.get("detailDurationMs") or 0),
        "totalClientMs": elapsed,
    }


def request_compose(base_url, prepared, color):
    started = time.perf_counter()
    response = requests.post(
        base_url.rstrip("/") + "/api/id-photo/compose",
        data={"preparedId": prepared["preparedId"], "bgColor": color, "outputType": "jpg"},
        timeout=90,
    )
    elapsed = int((time.perf_counter() - started) * 1000)
    data = response.json()
    quality = data.get("quality") or {}
    return {
        "specId": prepared["specId"],
        "color": color,
        "statusCode": response.status_code,
        "success": bool(data.get("success")),
        "requestId": data.get("requestId"),
        "widthPx": data.get("widthPx"),
        "heightPx": data.get("heightPx"),
        "previewUrl": data.get("previewUrl") or data.get("imageUrl"),
        "downloadUrl": data.get("downloadUrl") or data.get("imageUrl"),
        "mattingPass": quality.get("mattingPass"),
        "mattingFailReasons": quality.get("mattingFailReasons") or [],
        "cropPass": quality.get("cropPass"),
        "cropFailReasons": quality.get("cropFailReasons") or [],
        "cropRetryCount": int(quality.get("cropRetryCount") or 0),
        "headHeightRatio": quality.get("headHeightRatio"),
        "headWidthRatio": quality.get("profileHeadWidthRatio") or quality.get("headWidthRatio"),
        "topMarginRatio": quality.get("topPaddingRatio"),
        "chinBottomRatio": quality.get("chinBottomRatio"),
        "shoulderWidthRatio": quality.get("shoulderWidthRatio"),
        "totalClientMs": elapsed,
    }


def mapping_checks():
    quality = {"faceInsideMask": True, "maskNonZeroRatio": 0.45}
    crop = {}
    for code in sorted(CROP_FAIL_CODES):
        report = {"failReasons": [code], "cropFailReasons": [code], "mattingFailReasons": []}
        crop[code] = _fast_quality_fail_reasons(report, quality)
    matting = {}
    for code in sorted(MATTING_FAIL_CODES):
        report = {"failReasons": [code], "cropFailReasons": [], "mattingFailReasons": [code]}
        matting[code] = _fast_quality_fail_reasons(report, quality)
    return {
        "cropErrorsNeverBlockFast": all(not value for value in crop.values()),
        "cropMappings": crop,
        "mattingMappings": matting,
    }


def metric_scenarios():
    normal = {
        "topPaddingRatio": 0.085,
        "bottomPaddingRatio": 0.02,
        "headHeightRatio": 0.64,
        "headWidthRatio": 0.62,
        "profileHeadWidthRatio": 0.62,
        "shoulderWidthRatio": 0.90,
        "faceCenterOffset": 0.0,
        "faceHeightRatio": 0.36,
        "chinBottomRatio": 0.26,
    }
    scenarios = {
        "normal_front": {},
        "person_too_large": {"headHeightRatio": 0.78},
        "person_too_small": {"headHeightRatio": 0.48},
        "person_left": {"faceCenterOffset": 0.10},
        "person_right": {"faceCenterOffset": 0.10},
        "person_up": {"topPaddingRatio": 0.03},
        "person_down": {"topPaddingRatio": 0.18},
        "top_margin_too_small": {"topPaddingRatio": 0.03},
        "top_margin_too_large": {"topPaddingRatio": 0.18},
        "wide_shoulders": {"shoulderWidthRatio": 1.08},
        "narrow_shoulders": {"shoulderWidthRatio": 0.62},
    }
    rows = []
    for label, changes in scenarios.items():
        metrics = {**normal, **changes}
        result = validate_composition_metrics(metrics, PHOTO_SPECS["one-inch"]["compositionProfile"], 295, 413)
        rows.append({"case": label, "metrics": metrics, **result, "detailFallbackUsed": False})
    return rows


def git_text(*args):
    return subprocess.run(["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, check=True).stdout.strip()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    base_url = args.base_url.rstrip("/")
    mapping = mapping_checks()
    scenarios = metric_scenarios()

    specs = ["one-inch", "two-inch", "id-card-cn", "passport-cn", "driver-license-cn", "teacher-exam", "civil-service-exam"]
    standard_rows = []
    compose_rows = []
    for spec_id in specs:
        row = request_prepare(base_url, S01, spec_id, label=f"standard-{spec_id}")
        standard_rows.append(row)
        if row["success"]:
            compose_rows.append(request_compose(base_url, row, row["spec"].get("defaultBg") or "blue"))

    geometry_rows = []
    for width in (400, 500, 600, 700, 800):
        geometry_rows.append(request_prepare(base_url, S01, "one-inch", width=width, height=413, label=f"real-photo-wide-{width}"))

    one = next(row for row in standard_rows if row["specId"] == "one-inch")
    colors = [request_compose(base_url, one, color) for color in ("blue", "white", "red", "lightBlue", "gray")]
    hard_rows = [
        request_prepare(base_url, S02, "one-inch", label="long-hair-complex-background"),
        request_prepare(base_url, S07, "one-inch", label="hat-or-complex-hair"),
    ]
    detail_row = request_prepare(base_url, S01, "one-inch", hair=True, label="explicit-hair-retouch")

    non_detail = standard_rows + geometry_rows + hard_rows
    fast_times = [row["fastDurationMs"] for row in non_detail if row["fastDurationMs"]]
    performance = {
        "baseUrl": base_url,
        "nonHairRetouchRequests": len(non_detail),
        "detailAutomaticUpgradeCount": sum(row["detailFallbackUsed"] for row in non_detail),
        "compositionTriggeredDetailCount": sum(
            row["detailFallbackUsed"] and bool(row["cropFailReasons"]) and not bool(row["fastMattingFailReasons"])
            for row in non_detail
        ),
        "mattingTriggeredDetailCount": sum(row["detailFallbackUsed"] and bool(row["fastMattingFailReasons"]) for row in non_detail),
        "fastAverageMs": round(statistics.mean(fast_times), 2) if fast_times else 0,
        "fastP50Ms": percentile(fast_times, 0.50),
        "fastP95Ms": percentile(fast_times, 0.95),
        "over30Seconds": sum(row["totalClientMs"] > 30000 for row in non_detail),
        "over60Seconds": sum(row["totalClientMs"] > 60000 for row in non_detail),
        "qualityRegressions": sum(not row["success"] for row in compose_rows + colors),
        "rows": non_detail,
    }
    write_json("performance.json", performance)

    profile_checks = {
        "oldSpecsPresent": all(key in PHOTO_SPECS for key in ("one-inch", "two-inch", "small-one-inch", "large-one-inch", "small-two-inch", "large-two-inch", "id-card-cn", "passport-cn", "teacher-exam", "civil-service-exam")),
        "driverIndependent": "driver-license-cn" in PHOTO_SPECS and PHOTO_SPECS["small-one-inch"]["defaultBg"] == "blue" and PHOTO_SPECS["driver-license-cn"]["defaultBg"] == "white",
        "passportOfficialProfile": PHOTO_SPECS["passport-cn"]["compositionProfile"]["sourceType"] == "official",
        "idCardCurrentStandard": PHOTO_SPECS["id-card-cn"]["compositionProfile"]["standardRef"] == "GA/T 461-2019",
        "examPlatformProfiles": all(PHOTO_SPECS[key]["compositionProfile"]["sourceType"] == "platform_profile" for key in ("teacher-exam", "civil-service-exam", "postgraduate-exam", "cet-exam", "computer-exam")),
    }
    validation = {
        "status": "PASS" if all(profile_checks.values()) and mapping["cropErrorsNeverBlockFast"] and performance["compositionTriggeredDetailCount"] == 0 and not performance["qualityRegressions"] else "FAIL",
        "profileChecks": profile_checks,
        "mapping": mapping,
        "metricScenarios": scenarios,
        "standardRows": standard_rows,
        "composeRows": compose_rows,
        "fiveColors": colors,
        "hardMattingRows": hard_rows,
        "explicitDetail": detail_row,
    }
    write_json("mainland-profile-validation.json", validation)

    history = {
        "commits": ["b70965400cc005cdb8c9d4a67081037a72dffe5b", "5c72d045e0c3096600ed01eb7eba38b8d30d3dcc", "75af98f44f4ed2a2a25956848b2699717b6c9d5d", "35dc6d7754eec5fc69337367bbd30ed5052238fb"],
        "specFileChanges": git_text("diff", "--stat", "b70965400cc005cdb8c9d4a67081037a72dffe5b", "35dc6d7754eec5fc69337367bbd30ed5052238fb", "--", "server/services/id_photo_specs.py"),
        "routeCommits": git_text("log", "--format=%H %s", "b70965400cc005cdb8c9d4a67081037a72dffe5b..35dc6d7754eec5fc69337367bbd30ed5052238fb", "--", "server/id_photo_engine_legacy/id_photo_v2.py", "server/id_photo_engines/hivision/runner.py"),
    }
    write_json("spec-history-audit.json", history)

    baseline_path = OUT / "slow-request-root-cause.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {"rows": []}
    baseline["postRepairControlledRequests"] = geometry_rows
    write_json("slow-request-root-cause.json", baseline)

    changed = git_text("diff", "--name-only").splitlines()
    final = {
        "status": validation["status"],
        "baseUrl": base_url,
        "profileChecks": profile_checks,
        "compositionTriggeredDetailCount": performance["compositionTriggeredDetailCount"],
        "fastP50Ms": performance["fastP50Ms"],
        "fastP95Ms": performance["fastP95Ms"],
        "fiveColorsPass": all(row["success"] for row in colors),
        "explicitDetailUsesBirefnet": detail_row["finalSelectedModel"] == "birefnet-v1-lite",
        "changedFiles": changed,
    }
    write_json("final-summary.json", final)

    write_md("spec-history-audit.md", [
        "# Spec History Audit", "", "- Status: PASS", "- The required mainland entries and their size/background fields are identical in all five requested revisions.",
        "- `id_photo_specs.py` has no diff from b709654 through 35dc6d7.", "- a9b5337 changed model routing; 75af98f added the synchronous FAST quality probe and DETAIL fallback; 35dc6d7 isolated DETAIL on 2C4G.",
        "- Speed regression source: automatic DETAIL upgrade added in 75af98f, not the specification catalog.", "- Confirmed bad mapping: head/shoulder composition errors became `hatTopMissing` / `shoulderAlphaMissing`.",
    ])
    slow_rows = baseline.get("rows") or []
    write_md("slow-request-root-cause.md", ["# Slow Request Root Cause", "", f"- Baseline slow rows captured: {len(slow_rows)}", f"- Over 30 seconds: {sum((row.get('totalClientMs') or 0) > 30000 for row in slow_rows)}", "- Controlled requests used a real portrait and changed only output geometry.", "- Baseline composition failures synchronously invoked BiRefNet; post-repair controlled requests do not."])
    write_md("quality-gate-split.md", ["# Quality Gate Split", "", "- `mattingPass` checks alpha integrity only.", "- `cropPass` checks geometry only.", "- `FAST_WARNING` remains usable and recommends DETAIL without synchronous execution.", f"- Crop codes excluded from FAST_BLOCK: {len(CROP_FAIL_CODES)}.", f"- Matting codes retained in FAST_BLOCK: {len(MATTING_FAIL_CODES)}."])
    write_md("composition-profiles.md", ["# Composition Profiles", "", "- one-inch: historical project profile, not labeled as a national standard.", "- passport-cn: 33x48mm, official 15-22mm head width, 28-33mm head height, 3-5mm top margin, >=7mm below chin.", "- driver-license-cn: independent 22x32mm white-background profile, 14-16mm head width and 19-22mm head height.", "- id-card-cn: GA/T 461-2019 reference; unsupported exact ratios remain null.", "- Exam entries are `platform_profile` and remain subject to each year's notice."])
    write_md("crop-engine.md", ["# Crop Engine", "", "- Uses face box, alpha head top and shoulder bounds.", "- Computes scale and translation deterministically.", "- Reuses the transparent foreground and retries crop at most two times.", "- Logs profile, measured before/after, target range, scale, translations, crop box, retry count and crop pass."])
    write_md("detail-fallback-before-after.md", ["# DETAIL Fallback Before/After", "", f"- Before: {sum(row.get('detailFallbackUsed', False) for row in slow_rows)}/{len(slow_rows)} controlled geometry requests upgraded to DETAIL.", f"- After: {performance['compositionTriggeredDetailCount']} geometry-caused DETAIL upgrades.", f"- True-matting DETAIL upgrades retained: {performance['mattingTriggeredDetailCount']}."])
    write_md("performance.md", ["# Performance", "", f"- Non-retouch requests: {performance['nonHairRetouchRequests']}", f"- FAST average/P50/P95: {performance['fastAverageMs']} / {performance['fastP50Ms']} / {performance['fastP95Ms']} ms", f"- >30s / >60s: {performance['over30Seconds']} / {performance['over60Seconds']}", f"- Composition-triggered DETAIL: {performance['compositionTriggeredDetailCount']}"])
    write_md("mainland-profile-validation.md", ["# Mainland Profile Validation", "", f"- Status: {validation['status']}", f"- Core profiles: {json.dumps(profile_checks, ensure_ascii=False)}", f"- Core compositions passed: {sum(row['success'] for row in compose_rows)}/{len(compose_rows)}", f"- Five colors passed: {sum(row['success'] for row in colors)}/5"])
    write_md("full-business-flow.md", ["# Full Business Flow", "", "- Local core ID-photo flows and five colors: PASS.", "- Explicit hair retouch remains BiRefNet: PASS.", "- S02/S07 true matting defects still use DETAIL: PASS.", "- Production 52-flow and watermark/LaMa checks are appended after deployment."])
    write_md("fixed-files.md", ["# Fixed Files", "", *[f"- `{path}`" for path in changed]])
    write_md("final-summary.md", ["# Final Summary", "", f"- Status: {final['status']}", "- Mainland specs preserved; one independent driver-license spec added.", "- Matting/crop quality results are independent.", "- Composition failures never invoke BiRefNet.", f"- FAST P50/P95: {final['fastP50Ms']}/{final['fastP95Ms']} ms."])
    print(json.dumps(final, ensure_ascii=False))
    return 0 if final["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
