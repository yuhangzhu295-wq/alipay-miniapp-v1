"""Verify the real one-click outfit business flow.

The verifier uses a fresh passing ID-photo sample, runs the same
prepare/compose chain used by the mini program for six production outfit
templates, downloads every result, and checks the frontend surface and stale
download guard.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "reports" / "final"
OUT_DIR = ROOT / "reports" / "outfit-samples"
ID_REPORT = FINAL / "id-photo-validation-report.json"
TEMPLATE_IDS = [
    "mist_gray_suit",
    "elegant_black_suit",
    "deep_blue_suit",
    "red_tie_suit",
    "pure_black_suit",
    "white_shirt",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _post(base_url: str, path: str, *, data: dict[str, Any], files=None, timeout=90) -> dict[str, Any]:
    started = time.perf_counter()
    response = requests.post(base_url.rstrip("/") + path, data=data, files=files, timeout=timeout)
    try:
        payload = response.json()
    except Exception:
        payload = {"success": False, "message": response.text[:500]}
    payload["_statusCode"] = response.status_code
    payload["_costMs"] = int((time.perf_counter() - started) * 1000)
    return payload


def _download(base_url: str, remote_url: str, output: Path) -> dict[str, Any]:
    response = requests.get(urljoin(base_url.rstrip("/") + "/", remote_url.lstrip("/")), timeout=45)
    output.write_bytes(response.content)
    with Image.open(output) as image:
        size = list(image.size)
    return {
        "statusCode": response.status_code,
        "size": size,
        "sha256": hashlib.sha256(response.content).hexdigest(),
        "path": str(output),
    }


def _load_source() -> tuple[Path, str]:
    report = json.loads(ID_REPORT.read_text(encoding="utf-8"))
    for sample in (report.get("real") or {}).get("samples") or []:
        source = Path(sample.get("input_path") or "")
        if sample.get("passed") and source.exists():
            return source, sample.get("sample_id") or source.stem
    raise RuntimeError("No fresh passing ID-photo sample is available")


def _contact_sheet(rows: list[dict[str, Any]], output: Path) -> None:
    thumb_w, thumb_h = 177, 248
    cell_w, cell_h = 205, 286
    cols = 3
    sheet = Image.new("RGB", (cell_w * cols, cell_h * 2), "white")
    draw = ImageDraw.Draw(sheet)
    for index, row in enumerate(rows):
        x = (index % cols) * cell_w
        y = (index // cols) * cell_h
        with Image.open(row["download"]["path"]).convert("RGB") as image:
            image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            px = x + (cell_w - image.width) // 2
            sheet.paste(image, (px, y))
        draw.text((x + 8, y + thumb_h + 8), row["templateId"], fill="#101828")
    sheet.save(output, quality=94)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    base_url = args.base_url.rstrip("/")
    FINAL.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    source, sample_id = _load_source()
    health = requests.get(base_url + "/api/health", timeout=10).json()
    capabilities = requests.get(base_url + "/api/id-photo/capabilities", timeout=10).json()
    capability_templates = {
        item.get("id"): item
        for item in capabilities.get("templates") or []
        if item.get("available")
    }

    rows: list[dict[str, Any]] = []
    for template_id in TEMPLATE_IDS:
        with source.open("rb") as source_file:
            prepare = _post(
                base_url,
                "/api/id-photo/prepare",
                data={
                    "purpose": "official_id_photo",
                    "specId": "one-inch",
                    "widthPx": "295",
                    "heightPx": "413",
                    "mode": "official",
                    "composition": "head_shoulder",
                    "outfit": template_id,
                },
                files={"image": (source.name, source_file, "image/jpeg")},
                timeout=90,
            )
        compose: dict[str, Any] = {}
        download: dict[str, Any] = {}
        if prepare.get("success") and prepare.get("preparedId"):
            compose = _post(
                base_url,
                "/api/id-photo/compose",
                data={
                    "preparedId": prepare["preparedId"],
                    "bgColor": "#1A73E8",
                    "bgColorName": "blue",
                    "outputType": "jpg",
                },
                timeout=45,
            )
        if compose.get("success") and compose.get("finalImageUrl"):
            download = _download(base_url, compose["finalImageUrl"], OUT_DIR / f"{template_id}.jpg")
        outfit = compose.get("outfit") or {}
        quality = compose.get("quality") or {}
        quality_report = quality.get("qualityReport") or {}
        failures = []
        if template_id not in capability_templates:
            failures.append("template_not_in_capabilities")
        if not prepare.get("success"):
            failures.append(f"prepare_failed:{prepare.get('code')}")
        if not compose.get("success"):
            failures.append(f"compose_failed:{compose.get('code')}")
        if outfit.get("id") != template_id or outfit.get("applied") is not True:
            failures.append("outfit_not_applied")
        if (
            outfit.get("renderer") != "photorealistic_raster_template"
            or quality.get("outfitRenderer") != "photorealistic_raster_template"
        ):
            failures.append("photorealistic_renderer_not_used")
        if download.get("statusCode") != 200 or download.get("size") != [295, 413]:
            failures.append("invalid_download")
        if quality_report and quality_report.get("passed") is not True:
            failures.append("quality_report_failed")
        rows.append({
            "templateId": template_id,
            "templateName": (capability_templates.get(template_id) or {}).get("name", template_id),
            "prepare": prepare,
            "compose": compose,
            "download": download,
            "failures": failures,
            "passed": not failures,
        })

    hashes = [row.get("download", {}).get("sha256") for row in rows if row.get("download")]
    frontend = {
        "generateUiHasOutfitGrid": "outfit-grid" in _read(ROOT / "pages" / "generate" / "generate.wxml"),
        "generateUiHasOutfitBinding": 'bindtap="selectOutfit"' in _read(ROOT / "pages" / "generate" / "generate.wxml"),
        "generateUsesSelectedOutfit": "outfit: that.data.outfitId || 'preserve_original'" in _read(ROOT / "pages" / "generate" / "generate.js"),
        "generateCacheSeparatesOutfit": "requestPayload.outfit" in _read(ROOT / "pages" / "generate" / "generate.js"),
        "generateDownloadGuardsOutfit": "resultOutfitId !== that.data.outfitId" in _read(ROOT / "pages" / "generate" / "generate.js"),
    }
    contact_sheet = FINAL / "outfit-template-contact-sheet.jpg"
    if all(row.get("download", {}).get("path") for row in rows):
        _contact_sheet(rows, contact_sheet)

    stop_conditions = {
        "backendHealthy": health.get("success") is True,
        "sixProductionTemplatesAvailable": all(template_id in capability_templates for template_id in TEMPLATE_IDS),
        "sixTemplatesGenerated": len(rows) == 6 and all(row["passed"] for row in rows),
        "allOutputsDistinct": len(hashes) == 6 and len(set(hashes)) == 6,
        "allOutputs295x413": all(row.get("download", {}).get("size") == [295, 413] for row in rows),
        "allUsePhotorealisticRenderer": all(
            (row.get("compose", {}).get("outfit") or {}).get("renderer") == "photorealistic_raster_template"
            for row in rows
        ),
        "frontendFunctionalSurface": all(frontend.values()),
        "contactSheetGenerated": contact_sheet.exists(),
    }
    passed = all(stop_conditions.values())
    payload = {
        "status": "PASS" if passed else "FAIL",
        "mode": "photorealistic-functional",
        "baseUrl": base_url,
        "sampleId": sample_id,
        "source": str(source),
        "templateIds": TEMPLATE_IDS,
        "frontend": frontend,
        "rows": rows,
        "stopConditions": stop_conditions,
        "contactSheet": str(contact_sheet),
    }
    (FINAL / "outfit-validation-report.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    md = [
        "# One-click Outfit Functional Verification",
        "",
        f"- Status: {payload['status']}",
        f"- Source sample: `{sample_id}`",
        f"- Generated templates: {sum(1 for row in rows if row['passed'])}/6",
        f"- Contact sheet: `{contact_sheet}`",
        "",
        "## Templates",
        *[
            f"- {'PASS' if row['passed'] else 'FAIL'}: {row['templateId']}"
            + (f" ({', '.join(row['failures'])})" if row["failures"] else "")
            for row in rows
        ],
        "",
        "## Stop Conditions",
        *[f"- {name}: {'PASS' if value else 'FAIL'}" for name, value in stop_conditions.items()],
        "",
    ]
    (FINAL / "outfit-validation-report.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[verify-outfit] {payload['status']} report={FINAL / 'outfit-validation-report.md'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
