"""Verify ID-photo background replacement edge halo cleanup.

Scope: ID-photo matting/composition only. The script calls the real local
backend, prepares real sample photos, composes five background colors, stores
outputs/metrics, and writes the required round reports. Cloud deployment is
audited truthfully; it is not marked passing when no deploy channel exists.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "id-photo-edge-halo-fix"
SOURCE_DIR = REPORT_ROOT / "source"
OUTPUT_DIR = REPORT_ROOT / "output"
DEBUG_DIR = REPORT_ROOT / "debug-json"
FINAL_DIR = REPORT_ROOT / "final"

COLORS: dict[str, str] = {
    "blue": "blue",
    "white": "white",
    "red": "red",
    "lightBlue": "lightBlue",
    "gray": "gray",
}

FALLBACK_SAMPLES = [
    r"C:\Users\zyu33\Desktop\74e6cf5f6cc049042fe20a4b27a97f2f.jpg",
    r"C:\Users\zyu33\Desktop\41dd5d7539032424a4c766a593c6c5af.jpg",
    r"C:\Users\zyu33\Desktop\7d45c5e9e3efe79d374c0c21041d97d7.jpg",
    r"C:\Users\zyu33\Desktop\a9f4e0111e88e54f70b662658d2a70ed.jpg",
    r"C:\Users\zyu33\Desktop\b9fcfc995c64135f4be13197c85a96f0.jpg",
    r"C:\Users\zyu33\Desktop\cs.jpeg",
]

STRICT_THRESHOLDS = {
    "edgeWhiteHaloRatio": 0.015,
    "hairEdgeHaloRatio": 0.025,
    "foregroundLeakRatio": 0.02,
}


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)[:80]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def full_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def request_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = requests.request(method, url, **kwargs)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text[:1000]}
        return {
            "ok": 200 <= response.status_code < 300,
            "statusCode": response.status_code,
            "elapsedMs": elapsed_ms,
            "data": data,
        }
    except Exception as exc:
        return {
            "ok": False,
            "statusCode": 0,
            "elapsedMs": round((time.perf_counter() - started) * 1000, 1),
            "error": str(exc),
            "data": {"success": False, "message": str(exc)},
        }


def reset_dirs() -> None:
    for path in (SOURCE_DIR, OUTPUT_DIR, DEBUG_DIR, FINAL_DIR):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)


def discover_samples(samples_dir: str, limit: int) -> tuple[list[Path], str]:
    found: list[Path] = []
    root = Path(samples_dir)
    if root.exists():
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            found.extend(sorted(root.glob(ext)))
    if found:
        return found[:limit], "provided-directory"
    fallback = [Path(p) for p in FALLBACK_SAMPLES if Path(p).exists()]
    return fallback[:limit], "fallback-desktop"


def copy_samples(samples: list[Path]) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    for idx, sample in enumerate(samples, 1):
        target = SOURCE_DIR / f"sample_{idx:02d}{sample.suffix.lower()}"
        shutil.copy2(sample, target)
        try:
            img = Image.open(target)
            size = list(img.size)
        except Exception:
            size = []
        copied.append({
            "label": f"sample_{idx:02d}",
            "originalPath": str(sample),
            "path": str(target),
            "size": size,
        })
    return copied


def prepare(base_url: str, sample: dict[str, Any]) -> dict[str, Any]:
    path = Path(sample["path"])
    with path.open("rb") as fh:
        result = request_json(
            "POST",
            full_url(base_url, "/api/id-photo/prepare"),
            files={"file": (path.name, fh, "image/jpeg")},
            data={
                "purpose": "official_id_photo",
                "specId": "one-inch",
                "widthPx": "295",
                "heightPx": "413",
                "widthMm": "25",
                "heightMm": "35",
                "mode": "official",
                "composition": "head_shoulder",
                "outfit": "preserve_original",
            },
            timeout=120,
        )
    payload = {"sample": sample["label"], "stage": "prepare", **result}
    write_json(DEBUG_DIR / f"{sample['label']}_prepare.json", payload)
    return payload


def download_image(base_url: str, image_url: str, target: Path) -> dict[str, Any]:
    if not image_url:
        return {"ok": False, "path": str(target), "reason": "missing image url"}
    try:
        response = requests.get(full_url(base_url, image_url), timeout=60)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        img = Image.open(target).convert("RGB")
        return {
            "ok": response.status_code == 200 and bool(response.content),
            "statusCode": response.status_code,
            "path": str(target),
            "bytes": len(response.content),
            "size": {"width": img.width, "height": img.height},
        }
    except Exception as exc:
        return {"ok": False, "path": str(target), "reason": str(exc)}


def extract_quality(payload: dict[str, Any]) -> dict[str, Any]:
    quality = (payload.get("data") or {}).get("quality") or {}
    return quality.get("qualityReport") or {}


def strict_edge_pass(quality_report: dict[str, Any], color: str) -> tuple[bool, list[str]]:
    checks = quality_report.get("checks") or {}
    metrics = quality_report.get("metrics") or {}
    merged = {**metrics, **checks}
    reasons: list[str] = []
    if quality_report.get("passed") is not True:
        reasons.extend(quality_report.get("failReasons") or ["qualityReport.passed is not true"])
    if color != "white":
        for key, threshold in STRICT_THRESHOLDS.items():
            value = float(merged.get(key) or 0)
            if value > threshold:
                reasons.append(f"{key}={value} > {threshold}")
    if color in {"blue", "red", "lightBlue", "gray"}:
        if float(merged.get("backgroundContaminationScore") or 0) > 0.025:
            reasons.append("backgroundContaminationScore above 0.025")
    return not reasons, reasons


def compose(base_url: str, prepared_id: str, sample: dict[str, Any], color: str) -> dict[str, Any]:
    result = request_json(
        "POST",
        full_url(base_url, "/api/id-photo/compose"),
        data={
            "preparedId": prepared_id,
            "bgColor": color,
            "bgColorName": color,
            "outputType": "jpg",
        },
        timeout=120,
    )
    data = result.get("data") or {}
    image_url = data.get("finalImageUrl") or data.get("resultUrl") or data.get("imageUrl") or ""
    out_path = OUTPUT_DIR / f"{sample['label']}_{color}.jpg"
    download = download_image(base_url, image_url, out_path) if result.get("ok") else {
        "ok": False,
        "path": str(out_path),
        "reason": "compose request failed",
    }
    quality_report = extract_quality(result)
    strict_ok, strict_reasons = strict_edge_pass(quality_report, color)
    size = download.get("size") or {}
    checks = {
        "requestOk": result.get("ok") is True and data.get("success") is True,
        "downloadOk": download.get("ok") is True,
        "size295x413": size.get("width") == 295 and size.get("height") == 413,
        "previewEqualsDownload": bool(image_url and image_url == data.get("resultUrl")),
        "qualityPassed": quality_report.get("passed") is True,
        "strictEdgePassed": strict_ok,
    }
    row = {
        "sample": sample["label"],
        "color": color,
        "response": result,
        "download": download,
        "qualityReport": quality_report,
        "strictEdgeReasons": strict_reasons,
        "checks": checks,
        "passed": all(checks.values()),
    }
    write_json(DEBUG_DIR / f"{sample['label']}_{color}_compose.json", row)
    write_json(DEBUG_DIR / f"{sample['label']}_{color}_edge_metrics.json", {
        "sample": sample["label"],
        "color": color,
        "checks": quality_report.get("checks") or {},
        "metrics": quality_report.get("metrics") or {},
        "strictEdgeReasons": strict_reasons,
    })
    return row


def draw_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str) -> None:
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    draw.text(xy, text, fill=(30, 41, 59), font=font)


def make_comparison_sheet(sample: dict[str, Any], rows: dict[str, dict[str, Any]]) -> str:
    labels = ["source", *COLORS.keys()]
    cell_w, cell_h = 180, 285
    sheet = Image.new("RGB", (cell_w * len(labels) + 24, cell_h + 30), (248, 250, 252))
    draw = ImageDraw.Draw(sheet)
    source = Image.open(sample["path"]).convert("RGB")
    source.thumbnail((cell_w - 24, cell_h - 64), Image.Resampling.LANCZOS)
    sheet.paste(source, (12 + (cell_w - source.width) // 2, 12))
    draw_label(draw, (12, cell_h - 38), "source")
    for idx, color in enumerate(COLORS.keys(), 1):
        x0 = 12 + idx * cell_w
        out_path = Path(rows.get(color, {}).get("download", {}).get("path") or "")
        if out_path.exists():
            img = Image.open(out_path).convert("RGB")
            img.thumbnail((cell_w - 24, cell_h - 64), Image.Resampling.LANCZOS)
            sheet.paste(img, (x0 + (cell_w - img.width) // 2, 12))
        draw_label(draw, (x0, cell_h - 38), f"local-{color}")
    target = OUTPUT_DIR / f"{sample['label']}_source_and_five_colors.jpg"
    sheet.save(target, quality=92)
    return str(target)


def run_local_flow(base_url: str, samples: list[dict[str, Any]]) -> dict[str, Any]:
    health = {
        "api": request_json("GET", full_url(base_url, "/api/health"), timeout=15),
        "idPhoto": request_json("GET", full_url(base_url, "/api/id-photo/health"), timeout=60),
    }
    sample_results: list[dict[str, Any]] = []
    for sample in samples:
        prep = prepare(base_url, sample)
        prepared_id = (prep.get("data") or {}).get("preparedId")
        rows: dict[str, dict[str, Any]] = {}
        if prep.get("ok") and prepared_id:
            for color in COLORS:
                rows[color] = compose(base_url, prepared_id, sample, color)
        comparison = make_comparison_sheet(sample, rows)
        sample_results.append({
            "sample": sample,
            "prepare": prep,
            "colors": rows,
            "comparison": comparison,
            "passed": bool(prep.get("ok") and rows and all(row.get("passed") for row in rows.values())),
        })
    total = sum(len(item["colors"]) for item in sample_results)
    passed = sum(1 for item in sample_results for row in item["colors"].values() if row.get("passed"))
    failed_rows = [
        {"sample": item["sample"]["label"], "color": color, "row": row}
        for item in sample_results
        for color, row in item["colors"].items()
        if not row.get("passed")
    ]
    payload = {
        "status": "PASS" if health["api"].get("ok") and health["idPhoto"].get("ok") and not failed_rows and sample_results else "FAIL",
        "baseUrl": base_url,
        "health": health,
        "sampleCount": len(samples),
        "colorChecks": total,
        "passedColorChecks": passed,
        "failedColorChecks": len(failed_rows),
        "samples": sample_results,
        "failedRows": failed_rows[:40],
    }
    write_json(FINAL_DIR / "local-business-flow-report.json", payload)
    lines = [
        "# Local Business Flow Report",
        "",
        f"- Status: {payload['status']}",
        f"- Base URL: `{base_url}`",
        f"- Samples: {payload['sampleCount']}",
        f"- Five-color checks: {passed}/{total}",
        "- Flow: upload real sample -> prepare cutout -> compose blue/white/red/lightBlue/gray -> download image -> verify 295x413 and edge metrics.",
        "",
        "## Comparison Images",
    ]
    for item in sample_results:
        lines.append(f"- {item['sample']['label']}: `{item['comparison']}`")
    if failed_rows:
        lines.extend(["", "## Failures"])
        for row in failed_rows[:20]:
            lines.append(f"- {row['sample']} {row['color']}: {row['row'].get('strictEdgeReasons') or row['row'].get('checks')}")
    write_md(FINAL_DIR / "local-business-flow-report.md", lines)
    return payload


def audit_cloud(cloud_url: str) -> dict[str, Any]:
    env_present = all(
        bool(os.environ.get(name))
        for name in ("ALIBABA_CLOUD_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_SECRET", "ALIBABA_CLOUD_REGION_ID")
    )
    deploy_scripts = all(
        (ROOT / "deploy" / "cloud" / name).exists()
        for name in ("install-release.ps1", "activate-release.ps1", "health-check.ps1")
    )
    health = {
        "api": request_json("GET", full_url(cloud_url, "/api/health"), timeout=15),
        "idPhoto": request_json("GET", full_url(cloud_url, "/api/id-photo/health"), timeout=60),
    }
    blocked = not env_present
    payload = {
        "status": "CLOUD_SYNC_BLOCKED" if blocked else "CLOUD_SYNC_NOT_EXECUTED",
        "cloudUrl": cloud_url,
        "deployScriptsPresent": deploy_scripts,
        "credentialEnvironmentVariablesPresent": env_present,
        "health": health,
        "blocker": "Missing authenticated cloud deployment environment variables in this session." if blocked else "",
    }
    write_json(FINAL_DIR / "cloud-sync-report.json", payload)
    write_md(FINAL_DIR / "cloud-sync-report.md", [
        "# Cloud Sync Report",
        "",
        f"- Status: {payload['status']}",
        f"- Cloud URL: `{cloud_url}`",
        f"- Deploy scripts present: `{deploy_scripts}`",
        f"- Credential environment variables present: `{env_present}`",
        f"- `/api/health`: status={health['api'].get('statusCode')} ok={health['api'].get('ok')}",
        f"- `/api/id-photo/health`: status={health['idPhoto'].get('statusCode')} ok={health['idPhoto'].get('ok')}",
        f"- Blocker: {payload['blocker'] or 'None'}",
        "",
        "No cloud PASS is recorded unless the changed code is deployable and the remote ID-photo edge flow is verified.",
    ])
    write_json(FINAL_DIR / "cloud-edge-halo-report.json", payload)
    write_md(FINAL_DIR / "cloud-edge-halo-report.md", [
        "# Cloud Edge Halo Report",
        "",
        f"- Status: {payload['status']}",
        "- Remote five-color edge verification was not marked passing in this run.",
        f"- Blocker: {payload['blocker'] or 'Cloud verification not executed.'}",
    ])
    write_json(FINAL_DIR / "cloud-business-flow-report.json", payload)
    write_md(FINAL_DIR / "cloud-business-flow-report.md", [
        "# Cloud Business Flow Report",
        "",
        f"- Status: {payload['status']}",
        "- Cloud business flow is not marked PASS in this report.",
        f"- Blocker: {payload['blocker'] or 'Cloud verification not executed.'}",
    ])
    return payload


def write_static_reports(samples: list[dict[str, Any]], local: dict[str, Any], cloud: dict[str, Any], reference: str) -> dict[str, Any]:
    fixed_files = [
        str(ROOT / "server" / "services" / "id_photo_composer.py"),
        str(ROOT / "server" / "services" / "id_photo_quality.py"),
        str(ROOT / "server" / "scripts" / "verify_id_photo_edge_halo.py"),
        str(ROOT / "package.json"),
    ]
    write_md(FINAL_DIR / "current-edge-halo-audit.md", [
        "# Current Edge Halo Audit",
        "",
        "- Scope: ID-photo background replacement edge only.",
        "- Finding: the previous composer cleaned some boundary pixels after matting, but it mainly mixed halos toward the target background and did not reconstruct contaminated foreground RGB.",
        "- Risk: pale source background colors can remain inside semi-transparent hair/ear/shoulder edge pixels and become visible white or gray outlines on blue/red/lightBlue/gray backgrounds.",
        "- Reference image: `" + reference + "`",
    ])
    write_md(FINAL_DIR / "edge-decontamination-fix.md", [
        "# Edge Decontamination Fix",
        "",
        "- Added alpha-boundary decontamination before final background compositing.",
        "- Estimated source matte background from low-saturation transition pixels.",
        "- Reconstructed foreground RGB on halo candidates and blended toward nearby opaque hair/clothes color.",
        "- Trimmed only tiny bright low-alpha haze; no global erosion is applied.",
    ])
    rows = [
        "# Edge Halo Metrics Report",
        "",
        f"- Local status: {local['status']}",
        f"- Checks: {local['passedColorChecks']}/{local['colorChecks']}",
        "",
        "| sample | color | white | hair | leak | contamination | passed |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in local.get("samples") or []:
        for color, row in (item.get("colors") or {}).items():
            report = row.get("qualityReport") or {}
            merged = {**(report.get("metrics") or {}), **(report.get("checks") or {})}
            rows.append(
                f"| {item['sample']['label']} | {color} | "
                f"{float(merged.get('edgeWhiteHaloRatio') or 0):.6f} | "
                f"{float(merged.get('hairEdgeHaloRatio') or 0):.6f} | "
                f"{float(merged.get('foregroundLeakRatio') or 0):.6f} | "
                f"{float(merged.get('backgroundContaminationScore') or 0):.6f} | "
                f"{row.get('passed')} |"
            )
    write_md(FINAL_DIR / "edge-halo-metrics-report.md", rows)
    write_md(FINAL_DIR / "all-colors-comparison-report.md", [
        "# All Colors Comparison Report",
        "",
        f"- Local status: {local['status']}",
        f"- Output directory: `{OUTPUT_DIR}`",
        "",
        *[f"- {item['sample']['label']}: `{item['comparison']}`" for item in local.get("samples") or []],
    ])
    write_md(FINAL_DIR / "fixed-files.md", [
        "# Fixed Files",
        "",
        *[f"- `{path}`" for path in fixed_files],
    ])
    summary = {
        "status": "PASS_WITH_CLOUD_BLOCKED" if local["status"] == "PASS" and cloud["status"] == "CLOUD_SYNC_BLOCKED" else ("PASS" if local["status"] == "PASS" and cloud["status"] == "PASS" else "FAIL"),
        "localPass": local["status"] == "PASS",
        "cloudPass": cloud["status"] == "PASS",
        "cloudStatus": cloud["status"],
        "sampleCount": len(samples),
        "colorChecks": local["colorChecks"],
        "passedColorChecks": local["passedColorChecks"],
        "outputDir": str(OUTPUT_DIR),
        "finalDir": str(FINAL_DIR),
        "fixedFiles": fixed_files,
    }
    write_json(FINAL_DIR / "final-summary.json", summary)
    return summary


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cloud-base-url", default="https://tupzjianzhao.chat")
    parser.add_argument("--samples", default=r"C:\Users\zyu33\Desktop\idphoto-edge-halo-samples")
    parser.add_argument("--reference", default=r"C:\Users\zyu33\AppData\Local\Temp\codex-clipboard-9cb1b73a-3388-4476-aad2-89233c7ed016.png")
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args(argv)

    reset_dirs()
    raw_samples, source_mode = discover_samples(args.samples, args.limit)
    samples = copy_samples(raw_samples)
    write_json(DEBUG_DIR / "sample-manifest.json", {
        "sourceMode": source_mode,
        "requestedSamplesDir": args.samples,
        "samples": samples,
        "reference": args.reference,
    })
    local = run_local_flow(args.base_url.rstrip("/"), samples)
    cloud = audit_cloud(args.cloud_base_url.rstrip("/"))
    summary = write_static_reports(samples, local, cloud, args.reference)
    print(
        "[verify-id-photo-edge-halo] "
        f"status={summary['status']} local={local['passedColorChecks']}/{local['colorChecks']} "
        f"final={FINAL_DIR}"
    )
    return 0 if local.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
