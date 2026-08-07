"""Verify every frontend ID-photo spec through the real backend chain.

This script is intentionally focused on the current repair scope: non-one-inch
ID-photo specs being rejected by the final quality gate. It enumerates the
frontend spec library, sends every spec/color through /prepare + /compose,
saves the resulting images and debug JSON, and writes final reports under
reports/id-photo-all-formats/.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "id-photo-all-formats"
SAMPLES = REPORT_ROOT / "samples"
DEBUG = REPORT_ROOT / "debug-json"
LOCAL = REPORT_ROOT / "local-results"
CLOUD = REPORT_ROOT / "cloud-results"
SCREENSHOTS = REPORT_ROOT / "screenshots"
FINAL = REPORT_ROOT / "final"
GLOBAL_FINAL = ROOT / "reports" / "final"

PRIMARY_SAMPLE = Path(r"C:\Users\zyu33\Desktop\b9fcfc995c64135f4be13197c85a96f0.jpg")
SECONDARY_SAMPLE = Path(r"C:\Users\zyu33\Desktop\cs.jpeg")
EXTRA_SAMPLES = [
    Path(r"C:\Users\zyu33\Desktop\hv-qfFEF9eT275863cae88cc29b7a8a07cc16208a5dc.jpg"),
    Path(r"C:\Users\zyu33\Desktop\KiszNixLAvn9762c1e322e0653b1f816be08a918b1f6.jpg"),
]
REPO_SAMPLE_FALLBACKS = [
    ROOT / "reports" / "cloud-deploy-e2e" / "id-photo-camera-flow-valid-source-20260805" / "cloud-tests" / "input-id-photo-source.jpg",
    ROOT / "reports" / "id-photo-current-fail-fix" / "samples" / "real-source.jpg",
]

NODE_SPEC_JS = r"""
const specs = require('./utils/specs.js');
const seen = new Set();
const list = [];
for (const x of (specs.getSpecsByCategory ? specs.getSpecsByCategory('all') : [])) {
  if (!seen.has(x.id) && x.enabled !== false && x.active !== false) {
    seen.add(x.id);
    list.push(Object.assign({ groupId: x.groupId || '', groupName: x.groupName || '' }, x));
  }
}
console.log(JSON.stringify(list.map(x => ({
  id: x.id,
  name: x.displayName || x.name || x.id,
  groupId: x.groupId || '',
  groupName: x.groupName || '',
  category: x.category || '',
  widthPx: Number(x.widthPx || 295),
  heightPx: Number(x.heightPx || 413),
  widthMm: x.widthMm || '',
  heightMm: x.heightMm || '',
  defaultBg: x.defaultBg || ((x.bgColors || x.colors || ['blue'])[0]),
  bgColors: Array.from(new Set(x.backgrounds || x.bgColors || x.colors || [x.defaultBg || 'blue'])).filter(Boolean),
  sourceLevel: x.sourceLevel || '',
  notice: x.notice || '',
  enabled: x.enabled !== false
}))));
"""


def ensure_dirs() -> None:
    for path in [REPORT_ROOT, SAMPLES, DEBUG, LOCAL, CLOUD, SCREENSHOTS, FINAL, GLOBAL_FINAL]:
        path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def request_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    attempts = int(kwargs.pop("attempts", os.environ.get("ID_PHOTO_VERIFY_HTTP_ATTEMPTS", "3")))
    started = time.perf_counter()
    last: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        try:
            res = requests.request(method, url, **kwargs)
            try:
                data = res.json()
            except Exception:
                data = {"text": res.text[:1200]}
            last = {
                "ok": 200 <= res.status_code < 300,
                "statusCode": res.status_code,
                "durationMs": int((time.perf_counter() - started) * 1000),
                "attempts": attempt,
                "data": data,
            }
            if res.status_code < 500:
                return last
        except Exception as exc:
            last = {
                "ok": False,
                "statusCode": 0,
                "durationMs": int((time.perf_counter() - started) * 1000),
                "attempts": attempt,
                "error": str(exc),
            }
        if attempt < attempts:
            time.sleep(2)
    return last or {"ok": False, "statusCode": 0, "durationMs": int((time.perf_counter() - started) * 1000), "attempts": attempts}


def full_url(base_url: str, image_url: str) -> str:
    if image_url.startswith(("http://", "https://")):
        return image_url
    return base_url.rstrip("/") + "/" + image_url.lstrip("/")


def get_frontend_specs() -> list[dict[str, Any]]:
    out = subprocess.check_output(
        ["node", "-e", NODE_SPEC_JS],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    specs = json.loads(out)
    return [s for s in specs if s.get("id") and s.get("widthPx") and s.get("heightPx")]


def purpose_for_spec(spec: dict[str, Any]) -> str:
    sid = (spec.get("id") or "").lower()
    group = (spec.get("groupId") or "").lower()
    category = spec.get("category") or ""
    if "civil" in sid or "civil" in group:
        return "civil_service_exam"
    if any(key in sid for key in ["teacher", "exam", "cet", "computer", "nurse", "doctor", "guide", "judicial", "accounting", "school", "enroll"]):
        return "teacher_exam"
    if "social" in sid:
        return "social_security"
    if "id_card" in sid or "residence" in sid:
        return "id_card"
    if "passport" in sid or "visa" in sid or "pass_" in sid or "entry" in sid:
        return "passport"
    if "resume" in sid or "jianli" in sid:
        return "resume"
    if "考试" in category or "学籍" in category or "入学" in category or "职业资格" in category:
        return "teacher_exam"
    return "official_id_photo"


def available_source_images() -> list[Path]:
    ordered = [PRIMARY_SAMPLE, SECONDARY_SAMPLE, *EXTRA_SAMPLES, *REPO_SAMPLE_FALLBACKS]
    return [p for p in ordered if p.exists()]


def prepare_sample_artifacts() -> dict[str, Any]:
    sources = available_source_images()
    copied: list[dict[str, Any]] = []
    for idx, source in enumerate(sources):
        target = SAMPLES / f"real_source_{idx + 1}{source.suffix.lower() or '.jpg'}"
        shutil.copyfile(source, target)
        img = Image.open(target)
        copied.append({
            "label": f"real_source_{idx + 1}",
            "source": str(source),
            "path": str(target),
            "size": {"width": img.width, "height": img.height},
        })

    primary = sources[0] if sources else None
    variants: list[dict[str, Any]] = []
    if primary:
        base = ImageOps.exif_transpose(Image.open(primary)).convert("RGB")
        png_path = SAMPLES / "format_png_real_person.png"
        base.save(png_path)
        variants.append({"label": "png_real_person", "path": str(png_path), "size": {"width": base.width, "height": base.height}})

        large = base.resize((1800, max(1200, int(base.height * 1800 / max(1, base.width)))), Image.Resampling.LANCZOS)
        large_path = SAMPLES / "large_jpg_real_person.jpg"
        large.save(large_path, quality=94)
        variants.append({"label": "large_jpg_real_person", "path": str(large_path), "size": {"width": large.width, "height": large.height}})

        small = base.copy()
        small.thumbnail((420, 560), Image.Resampling.LANCZOS)
        small_path = SAMPLES / "small_jpg_real_person.jpg"
        small.save(small_path, quality=94)
        variants.append({"label": "small_jpg_real_person", "path": str(small_path), "size": {"width": small.width, "height": small.height}})

        exif_path = SAMPLES / "exif_rotated_phone.jpg"
        # Simulate a real phone JPEG: pixels are stored sideways and EXIF
        # orientation tells readers to rotate it back before analysis.
        exif_img = base.transpose(Image.Transpose.ROTATE_90)
        exif = exif_img.getexif()
        exif[274] = 6
        exif_img.save(exif_path, quality=94, exif=exif.tobytes())
        normalized = ImageOps.exif_transpose(Image.open(exif_path))
        variants.append({
            "label": "exif_rotated_phone",
            "path": str(exif_path),
            "size": {"width": exif_img.width, "height": exif_img.height},
            "normalizedSize": {"width": normalized.width, "height": normalized.height},
        })

    negative_path = SAMPLES / "negative_landscape_no_person.png"
    neg = Image.new("RGB", (640, 420), (226, 238, 255))
    draw = ImageDraw.Draw(neg)
    draw.rectangle([0, 260, 640, 420], fill=(166, 201, 138))
    draw.polygon([(60, 260), (210, 80), (360, 260)], fill=(118, 146, 170))
    draw.polygon([(260, 260), (430, 100), (610, 260)], fill=(146, 162, 178))
    draw.ellipse([470, 36, 548, 114], fill=(255, 218, 95))
    neg.save(negative_path)

    payload = {
        "realSources": copied,
        "variants": variants,
        "negative": {"label": "negative_landscape_no_person", "path": str(negative_path)},
    }
    write_json(DEBUG / "sample-manifest.json", payload)
    return payload


def download_output(base_url: str, image_url: str, target: Path) -> dict[str, Any]:
    attempts = int(os.environ.get("ID_PHOTO_VERIFY_HTTP_ATTEMPTS", "3"))
    url = full_url(base_url, image_url)
    last: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        try:
            res = requests.get(url, timeout=60)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(res.content)
            img = Image.open(target).convert("RGB")
            last = {
                "ok": res.status_code == 200 and bool(res.content),
                "statusCode": res.status_code,
                "bytes": len(res.content),
                "path": str(target),
                "size": {"width": img.width, "height": img.height},
                "attempts": attempt,
            }
            if res.status_code < 500:
                return last
        except Exception as exc:
            last = {"ok": False, "error": str(exc), "path": str(target), "attempts": attempt}
        if attempt < attempts:
            time.sleep(2)
    return last or {"ok": False, "error": "download failed", "path": str(target), "attempts": attempts}


def prepare_id_photo(base_url: str, sample_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    data = {
        "purpose": purpose_for_spec(spec),
        "specId": spec["id"],
        "widthPx": str(spec["widthPx"]),
        "heightPx": str(spec["heightPx"]),
        "widthMm": str(spec.get("widthMm") or ""),
        "heightMm": str(spec.get("heightMm") or ""),
        "mode": "official",
        "composition": "head_shoulder",
        "outfit": "preserve_original",
    }
    with sample_path.open("rb") as fh:
        return request_json(
            "POST",
            base_url.rstrip("/") + "/api/id-photo/prepare",
            files={"file": (sample_path.name, fh, "image/jpeg")},
            data=data,
            timeout=120,
        )


def compose_id_photo(base_url: str, prepared_id: str, spec: dict[str, Any], color: str, sample_label: str) -> dict[str, Any]:
    result = request_json(
        "POST",
        base_url.rstrip("/") + "/api/id-photo/compose",
        data={"preparedId": prepared_id, "bgColor": color, "bgColorName": color, "outputType": "jpg"},
        timeout=90,
    )
    payload = result.get("data") or {}
    image_url = payload.get("finalImageUrl") or payload.get("resultUrl") or payload.get("imageUrl") or ""
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in spec["id"])
    target = LOCAL / f"{sample_label}_{safe_id}_{color}.jpg"
    download = download_output(base_url, image_url, target) if image_url else {"ok": False, "error": "missing image url", "path": str(target)}
    quality_report = (payload.get("quality") or {}).get("qualityReport") or {}
    size = download.get("size") or {}
    checks = {
        "requestOk": result.get("ok") is True and payload.get("success") is True,
        "downloadOk": download.get("ok") is True,
        "sizeOk": size.get("width") == int(spec["widthPx"]) and size.get("height") == int(spec["heightPx"]),
        "qualityPassed": quality_report.get("passed") is True,
        "previewEqualsDownload": ((quality_report.get("checks") or {}).get("previewEqualsDownload") is True),
    }
    row = {
        "specId": spec["id"],
        "specName": spec.get("name"),
        "sample": sample_label,
        "color": color,
        "request": result,
        "download": download,
        "qualityReport": quality_report,
        "checks": checks,
        "passed": all(checks.values()),
    }
    write_json(DEBUG / f"{sample_label}_{safe_id}_{color}.json", row)
    return row


def run_all_specs(
    base_url: str,
    spec_limit: int = 0,
    default_color_only: bool = False,
    max_prepare_ms: int = 0,
    max_compose_ms: int = 0,
) -> dict[str, Any]:
    specs = get_frontend_specs()
    if spec_limit:
        specs = specs[:spec_limit]
    manifest = prepare_sample_artifacts()
    real_sample = Path(manifest["realSources"][0]["path"]) if manifest["realSources"] else None
    if real_sample is None:
        return {"status": "FAIL", "reason": "no real source images found", "specs": specs}

    health = request_json("GET", base_url.rstrip("/") + "/api/health", timeout=10)
    rows: list[dict[str, Any]] = []
    prepare_rows: list[dict[str, Any]] = []
    prepare_failures: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, 1):
        prep = prepare_id_photo(base_url, real_sample, spec)
        prepare_rows.append({
            "specId": spec["id"],
            "durationMs": prep.get("durationMs", 0),
            "statusCode": prep.get("statusCode", 0),
        })
        prepared_id = (prep.get("data") or {}).get("preparedId")
        if not prep.get("ok") or not prepared_id:
            prepare_failures.append({"index": index, "spec": spec, "prepare": prep})
            write_json(DEBUG / f"prepare_fail_{spec['id']}.json", {"spec": spec, "prepare": prep})
            continue
        colors = [spec.get("defaultBg") or "blue"] if default_color_only else list(
            dict.fromkeys([spec.get("defaultBg") or "blue", *(spec.get("bgColors") or [])])
        )
        for color in colors:
            rows.append(compose_id_photo(base_url, prepared_id, spec, color, "primary"))

    negative = run_negative_check(base_url, specs[0] if specs else {"id": "yicun", "widthPx": 295, "heightPx": 413})
    contact = make_contact_sheet(rows)
    total = len(rows)
    passed = sum(1 for row in rows if row.get("passed"))
    failed_rows = [row for row in rows if not row.get("passed")]
    slow_prepare_rows = [row for row in prepare_rows if max_prepare_ms and row["durationMs"] > max_prepare_ms]
    slow_compose_rows = [
        {"specId": row["specId"], "color": row["color"], "durationMs": row["request"].get("durationMs", 0)}
        for row in rows
        if max_compose_ms and row["request"].get("durationMs", 0) > max_compose_ms
    ]
    spec_ids_with_output = sorted({row["specId"] for row in rows if row.get("passed")})
    payload = {
        "status": "PASS" if health.get("ok") and not prepare_failures and not failed_rows and not slow_prepare_rows and not slow_compose_rows and negative.get("passed") else "FAIL",
        "baseUrl": base_url,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "health": health,
        "sampleManifest": manifest,
        "specCount": len(specs),
        "validatedSpecCount": len(spec_ids_with_output),
        "colorChecks": total,
        "passedColorChecks": passed,
        "failedColorChecks": len(failed_rows),
        "defaultColorOnly": default_color_only,
        "speedLimitsMs": {"prepare": max_prepare_ms, "compose": max_compose_ms},
        "speed": {
            "maxPrepareMs": max((row["durationMs"] for row in prepare_rows), default=0),
            "maxComposeMs": max((row["request"].get("durationMs", 0) for row in rows), default=0),
            "slowPrepareRows": slow_prepare_rows,
            "slowComposeRows": slow_compose_rows,
        },
        "prepareRows": prepare_rows,
        "prepareFailures": prepare_failures,
        "failedRows": failed_rows[:40],
        "negative": negative,
        "contactSheet": str(contact),
        "allRowsDebugDir": str(DEBUG),
        "localResultsDir": str(LOCAL),
    }
    write_reports(payload)
    return payload


def run_negative_check(base_url: str, spec: dict[str, Any]) -> dict[str, Any]:
    negative_path = SAMPLES / "negative_landscape_no_person.png"
    prep = prepare_id_photo(base_url, negative_path, spec)
    data = prep.get("data") or {}
    rejected = prep.get("statusCode") >= 400 or data.get("success") is False or not data.get("preparedId")
    payload = {
        "passed": rejected,
        "expected": "reject non-real/no-face input",
        "statusCode": prep.get("statusCode"),
        "code": data.get("code"),
        "message": data.get("message"),
        "response": prep,
    }
    write_json(DEBUG / "negative_landscape_no_person.json", payload)
    return payload


def make_contact_sheet(rows: list[dict[str, Any]]) -> Path:
    chosen = [row for row in rows if row.get("passed")][:24]
    thumbs: list[tuple[str, Image.Image]] = []
    for row in chosen:
        path = Path(row["download"]["path"])
        if not path.exists():
            continue
        img = Image.open(path).convert("RGB")
        img.thumbnail((110, 150), Image.Resampling.LANCZOS)
        thumbs.append((f"{row['specId']}\n{row['color']}", img.copy()))
    cols = 6
    cell_w, cell_h = 150, 196
    sheet = Image.new("RGB", (cols * cell_w + 20, max(1, ((len(thumbs) + cols - 1) // cols)) * cell_h + 20), (246, 248, 251))
    draw = ImageDraw.Draw(sheet)
    for idx, (label, img) in enumerate(thumbs):
        x = 10 + (idx % cols) * cell_w
        y = 10 + (idx // cols) * cell_h
        sheet.paste(img, (x + (cell_w - img.width) // 2, y + 6))
        draw.text((x + 8, y + 158), label[:42], fill=(30, 41, 59))
    target = SCREENSHOTS / "spec-format-contact-sheet.jpg"
    sheet.save(target, quality=92)
    shutil.copyfile(target, FINAL / "spec-format-sample-comparison.jpg")
    shutil.copyfile(target, GLOBAL_FINAL / "id-photo-all-format-comparison.jpg")
    return target


def write_reports(payload: dict[str, Any]) -> None:
    write_json(FINAL / "spec-format-validation-report.json", payload)
    write_json(GLOBAL_FINAL / "id-photo-all-formats-report.json", payload)
    lines = [
        "# Spec Format Validation Report",
        "",
        f"- Status: {payload['status']}",
        f"- Base URL: `{payload['baseUrl']}`",
        f"- Frontend specs verified: {payload['validatedSpecCount']}/{payload['specCount']}",
        f"- Color checks: {payload['passedColorChecks']}/{payload['colorChecks']}",
        f"- Prepare failures: {len(payload['prepareFailures'])}",
        f"- Failed color checks: {payload['failedColorChecks']}",
        f"- Default color only: {payload.get('defaultColorOnly', False)}",
        f"- Maximum prepare time: {payload.get('speed', {}).get('maxPrepareMs', 0)}ms",
        f"- Maximum compose time: {payload.get('speed', {}).get('maxComposeMs', 0)}ms",
        f"- Slow prepare/compose checks: {len(payload.get('speed', {}).get('slowPrepareRows', []))}/{len(payload.get('speed', {}).get('slowComposeRows', []))}",
        f"- Negative non-real rejected: {'PASS' if payload['negative'].get('passed') else 'FAIL'}",
        f"- Contact sheet: `{payload['contactSheet']}`",
        "",
        "## Failed Specs",
    ]
    if payload["prepareFailures"]:
        lines.extend([f"- prepare: `{item['spec']['id']}` status={item['prepare'].get('statusCode')}" for item in payload["prepareFailures"][:30]])
    if payload["failedRows"]:
        lines.extend([f"- compose: `{row['specId']}` `{row['color']}` checks={row['checks']}" for row in payload["failedRows"][:30]])
    if not payload["prepareFailures"] and not payload["failedRows"]:
        lines.append("- None")
    write_md(FINAL / "spec-format-validation-report.md", lines)

    root_cause = [
        "# Root Cause",
        "",
        "- The generation service was not failing at face detection or matting for the reproduced real-person samples.",
        "- The final quality gate used one-inch composition thresholds for every output size.",
        "- Non-one-inch formats failed when pixel quantization made top padding land around 6.6%-6.9%, or when narrow aspect ratios made the normalized head-width estimate exceed the one-inch max of 0.82.",
        "- The fix keeps hard checks for size, pure background, real-person input, foreground usage, head height, center, and edge artifacts, while making top-padding tolerance and head-width max depend on output size/aspect ratio.",
        "",
    ]
    write_md(FINAL / "root-cause.md", root_cause)

    fixed = [
        "# Fixed Files",
        "",
        "- `server/services/id_photo_quality.py`: made final composition quality thresholds size/aspect aware.",
        "- `server/scripts/verify_id_photo_all_formats.py`: added real backend all-spec/all-color validation.",
        "- `server/scripts/verify_id_photo_quality_regression.py`: added sample/format regression validation.",
        "- `server/scripts/verify_id_photo_local_vs_cloud.py`: added local/cloud comparison report.",
        "- `server/scripts/verify_id_photo_full_business_flow.py`: added current-scope business-flow aggregation.",
        "- `server/scripts/verify_id_photo_first_stage_all.py`: added current-scope full verifier chain.",
        "- `package.json`: added required npm verification commands.",
        "",
    ]
    write_md(FINAL / "fixed-files.md", fixed)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--spec-limit", type=int, default=0)
    parser.add_argument("--default-color-only", action="store_true")
    parser.add_argument("--max-prepare-ms", type=int, default=0)
    parser.add_argument("--max-compose-ms", type=int, default=0)
    args = parser.parse_args(argv)
    os.environ.setdefault("PYTHONUTF8", "1")
    ensure_dirs()
    payload = run_all_specs(
        args.base_url.rstrip("/"),
        spec_limit=args.spec_limit,
        default_color_only=args.default_color_only,
        max_prepare_ms=args.max_prepare_ms,
        max_compose_ms=args.max_compose_ms,
    )
    print(
        f"[verify-id-photo-all-formats] {payload['status']} "
        f"specs={payload.get('validatedSpecCount')}/{payload.get('specCount')} "
        f"colors={payload.get('passedColorChecks')}/{payload.get('colorChecks')} "
        f"report={FINAL / 'spec-format-validation-report.md'}"
    )
    return 0 if payload.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
