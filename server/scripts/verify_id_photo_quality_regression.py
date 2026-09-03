"""Regression tests for ID-photo quality thresholds and sample formats."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from verify_id_photo_all_formats import (
    DEBUG,
    FINAL,
    GLOBAL_FINAL,
    LOCAL,
    SAMPLES,
    SCREENSHOTS,
    compose_id_photo,
    ensure_dirs,
    get_frontend_specs,
    prepare_id_photo,
    prepare_sample_artifacts,
    request_json,
    write_json,
    write_md,
)


PROBLEM_SPEC_IDS = {
    "dayicun",
    "xiaoyicun",
    "civil_service_two_inch",
    "accounting_middle_240_320",
    "accounting_middle_114_156",
    "accounting_middle_shanghai_215_300",
    "school_status_90_120",
    "school_status_300_420",
    "insurance_practice_210_370",
    "teacher_cert_180_240",
    "teacher_cert_150_200",
    "teacher_cert_384_512",
    "nurse_exam_295_413",
    "doctor_exam_413_531",
}


def selected_specs() -> list[dict[str, Any]]:
    specs = get_frontend_specs()
    by_id = {spec["id"]: spec for spec in specs}
    selected = [by_id[sid] for sid in sorted(PROBLEM_SPEC_IDS) if sid in by_id]
    if not selected:
        selected = specs[:12]
    return selected


def selected_samples() -> list[dict[str, Any]]:
    manifest = prepare_sample_artifacts()
    rows = []
    for item in manifest.get("realSources") or []:
        rows.append({"label": item["label"], "path": item["path"], "kind": "provided-real"})
    for item in manifest.get("variants") or []:
        rows.append({"label": item["label"], "path": item["path"], "kind": "format-variant"})
    return rows


def make_cartoon_negative(target: Path) -> Path:
    img = Image.new("RGB", (420, 420), (236, 244, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse([110, 80, 310, 280], fill=(255, 224, 189), outline=(42, 70, 120), width=5)
    draw.ellipse([155, 150, 180, 178], fill=(20, 20, 35))
    draw.ellipse([240, 150, 265, 178], fill=(20, 20, 35))
    draw.arc([165, 185, 255, 240], 10, 170, fill=(180, 50, 80), width=4)
    draw.rectangle([150, 282, 270, 390], fill=(90, 120, 220))
    target.parent.mkdir(parents=True, exist_ok=True)
    img.save(target)
    return target


def run_quality_regression(base_url: str) -> dict[str, Any]:
    ensure_dirs()
    health = request_json("GET", base_url.rstrip("/") + "/api/health", timeout=10)
    specs = selected_specs()
    samples = selected_samples()
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for sample in samples:
        sample_path = Path(sample["path"])
        for spec in specs:
            prep = prepare_id_photo(base_url, sample_path, spec)
            prepared_id = (prep.get("data") or {}).get("preparedId")
            if not prep.get("ok") or not prepared_id:
                failure = {"sample": sample, "spec": spec, "stage": "prepare", "response": prep}
                failures.append(failure)
                write_json(DEBUG / f"quality_prepare_fail_{sample['label']}_{spec['id']}.json", failure)
                continue
            colors = [spec.get("defaultBg") or "blue"]
            if sample["label"] in {"real_source_1", "real_source_2"}:
                colors = list(dict.fromkeys([spec.get("defaultBg") or "blue", *(spec.get("bgColors") or [])]))
            for color in colors:
                row = compose_id_photo(base_url, prepared_id, spec, color, sample["label"])
                rows.append(row)
                if not row.get("passed"):
                    failures.append({"sample": sample, "spec": spec, "stage": "compose", "row": row})

    negative_landscape = SAMPLES / "negative_landscape_no_person.png"
    negative_cartoon = make_cartoon_negative(SAMPLES / "negative_cartoon_face.png")
    negative_rows = []
    for neg in [negative_landscape, negative_cartoon]:
        prep = prepare_id_photo(base_url, neg, specs[0])
        data = prep.get("data") or {}
        rejected = prep.get("statusCode") >= 400 or data.get("success") is False or not data.get("preparedId")
        negative_rows.append({
            "path": str(neg),
            "statusCode": prep.get("statusCode"),
            "code": data.get("code"),
            "rejected": rejected,
            "response": prep,
        })

    contact = make_quality_contact_sheet(rows)
    total = len(rows)
    passed = sum(1 for row in rows if row.get("passed"))
    payload = {
        "status": "PASS" if health.get("ok") and not failures and all(row["rejected"] for row in negative_rows) else "FAIL",
        "baseUrl": base_url,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "health": health,
        "sampleCount": len(samples),
        "specCount": len(specs),
        "qualityChecks": total,
        "passedQualityChecks": passed,
        "failedQualityChecks": len(failures),
        "samples": samples,
        "specs": [{"id": s["id"], "widthPx": s["widthPx"], "heightPx": s["heightPx"], "name": s.get("name")} for s in specs],
        "failures": failures[:40],
        "negative": negative_rows,
        "contactSheet": str(contact),
        "localResultsDir": str(LOCAL),
    }
    write_json(FINAL / "quality-threshold-fix-report.json", payload)
    write_json(GLOBAL_FINAL / "id-photo-quality-regression-report.json", payload)
    lines = [
        "# Quality Threshold Fix Report",
        "",
        f"- Status: {payload['status']}",
        f"- Base URL: `{base_url}`",
        f"- Samples: {payload['sampleCount']}",
        f"- Problem specs: {payload['specCount']}",
        f"- Quality checks: {payload['passedQualityChecks']}/{payload['qualityChecks']}",
        f"- Negative false pass: {sum(1 for row in negative_rows if not row['rejected'])}",
        f"- Contact sheet: `{contact}`",
        "",
        "## Covered Sample Kinds",
        *[f"- {item['label']}: {item['kind']} `{item['path']}`" for item in samples],
        "",
        "## Failures",
    ]
    if failures:
        lines.extend([f"- {item.get('stage')}: sample={item.get('sample', {}).get('label')} spec={item.get('spec', {}).get('id')}" for item in failures[:30]])
    else:
        lines.append("- None")
    write_md(FINAL / "quality-threshold-fix-report.md", lines)
    return payload


def make_quality_contact_sheet(rows: list[dict[str, Any]]) -> Path:
    chosen = [row for row in rows if row.get("passed")][:30]
    cols = 6
    cell_w, cell_h = 150, 198
    sheet = Image.new("RGB", (cols * cell_w + 20, max(1, ((len(chosen) + cols - 1) // cols)) * cell_h + 20), (248, 250, 252))
    draw = ImageDraw.Draw(sheet)
    for idx, row in enumerate(chosen):
        path = Path(row["download"]["path"])
        if not path.exists():
            continue
        img = Image.open(path).convert("RGB")
        img.thumbnail((110, 150), Image.Resampling.LANCZOS)
        x = 10 + (idx % cols) * cell_w
        y = 10 + (idx // cols) * cell_h
        sheet.paste(img, (x + (cell_w - img.width) // 2, y + 4))
        draw.text((x + 8, y + 158), f"{row['sample']}\n{row['specId']}"[:44], fill=(30, 41, 59))
    target = SCREENSHOTS / "quality-regression-contact-sheet.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, quality=92)
    return target


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    payload = run_quality_regression(args.base_url.rstrip("/"))
    print(
        f"[verify-id-photo-quality-regression] {payload['status']} "
        f"checks={payload.get('passedQualityChecks')}/{payload.get('qualityChecks')} "
        f"report={FINAL / 'quality-threshold-fix-report.md'}"
    )
    return 0 if payload.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
