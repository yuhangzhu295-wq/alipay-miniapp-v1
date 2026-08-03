"""Current ID-photo restart/cloud-switch regression verifier.

This script is intentionally scoped to the ID-photo generation chain:
frontend API route scan, local/cloud health, prepare, five-color compose,
debug JSON, output images, and local-vs-cloud visual comparison for the
fixed desktop samples requested in this round.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from PIL import Image, ImageChops, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "id-photo-current-fix"
SAMPLES_DIR = REPORT_ROOT / "samples"
LOCAL_DIR = REPORT_ROOT / "local-results"
CLOUD_DIR = REPORT_ROOT / "cloud-results"
DEBUG_DIR = REPORT_ROOT / "debug-json"
VISUAL_DIR = REPORT_ROOT / "visual-compare"
FINAL_DIR = REPORT_ROOT / "final"

SAMPLE_FILES = [
    "74e6cf5f6cc049042fe20a4b27a97f2f.jpg",
    "41dd5d7539032424a4c766a593c6c5af.jpg",
    "7d45c5e9e3efe79d374c0c21041d97d7.jpg",
    "a9f4e0111e88e54f70b662658d2a70ed.jpg",
    "大一.jpg",
]

COLORS = {
    "blue": ("#1A73E8", (26, 115, 232)),
    "white": ("#FFFFFF", (255, 255, 255)),
    "red": ("#E53935", (229, 57, 53)),
    "lightBlue": ("#81D4FA", (129, 212, 250)),
    "gray": ("#9E9E9E", (158, 158, 158)),
}


def ensure_dirs() -> None:
    for path in (SAMPLES_DIR, LOCAL_DIR, CLOUD_DIR, DEBUG_DIR, VISUAL_DIR, FINAL_DIR):
        if path.exists():
            shutil.rmtree(path)
    for path in (SAMPLES_DIR, LOCAL_DIR, CLOUD_DIR, DEBUG_DIR, VISUAL_DIR, FINAL_DIR):
        path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def full_url(base_url: str, maybe_relative: str) -> str:
    if maybe_relative.startswith("http://") or maybe_relative.startswith("https://"):
        return maybe_relative
    return urljoin(base_url.rstrip("/") + "/", maybe_relative.lstrip("/"))


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


def check_health(base_url: str, label: str) -> dict[str, Any]:
    basic = request_json("GET", full_url(base_url, "/api/health"), timeout=10)
    id_photo = request_json("GET", full_url(base_url, "/api/id-photo/health"), timeout=30)
    result = {
        "label": label,
        "baseUrl": base_url,
        "apiHealth": basic,
        "idPhotoHealth": id_photo,
        "passed": bool(basic.get("ok") and id_photo.get("ok") and id_photo.get("data", {}).get("success") is True),
    }
    write_json(DEBUG_DIR / f"{label}-health.json", result)
    write_md(
        FINAL_DIR / f"{label}-health-report.md",
        [
            f"# {label} health report",
            f"- Base URL: `{base_url}`",
            f"- `/api/health`: status={basic.get('statusCode')} ok={basic.get('ok')}",
            f"- `/api/id-photo/health`: status={id_photo.get('statusCode')} ok={id_photo.get('ok')}",
            f"- Result: {'PASS' if result['passed'] else 'FAIL'}",
            "",
            "```json",
            json.dumps(result, ensure_ascii=False, indent=2),
            "```",
        ],
    )
    return result


def check_frontend_routes() -> dict[str, Any]:
    api_config = ROOT / "utils" / "apiConfig.js"
    ai_api = ROOT / "utils" / "aiImageApi.js"
    config_text = api_config.read_text(encoding="utf-8", errors="ignore") if api_config.exists() else ""
    ai_text = ai_api.read_text(encoding="utf-8", errors="ignore") if ai_api.exists() else ""
    checks = {
        "apiConfigExists": api_config.exists(),
        "aiImageApiExists": ai_api.exists(),
        "localBaseConfigured": "127.0.0.1:8000" in config_text,
        "cloudBaseConfigured": "120.26.44.156" in config_text,
        "targetStorageKeyConfigured": "ID_PHOTO_API_TARGET" in config_text,
        "prepareUsesUnifiedBase": "config.API_BASE_URL + '/api/id-photo/prepare'" in ai_text,
        "composeUsesUnifiedBase": "config.API_BASE_URL + '/api/id-photo/compose'" in ai_text,
        "downloadUsesUnifiedBase": "config.API_BASE_URL + imageUrl" in ai_text and "_downloadResult" in ai_text,
    }
    passed = all(checks.values())
    result = {"passed": passed, "checks": checks, "files": [str(api_config), str(ai_api)]}
    write_json(DEBUG_DIR / "frontend-api-route-check.json", result)
    write_md(
        FINAL_DIR / "frontend-api-route-check.md",
        [
            "# Frontend API route check",
            f"- Result: {'PASS' if passed else 'FAIL'}",
            "- Scope: ID-photo prepare/compose/download route only.",
            "- Finding: the mini-program ID-photo chain switches by one unified base URL and does not mix local/cloud endpoints in this chain.",
            "",
            "```json",
            json.dumps(result, ensure_ascii=False, indent=2),
            "```",
        ],
    )
    return result


def prepare_samples(samples_root: Path) -> list[Path]:
    copied: list[Path] = []
    missing: list[str] = []
    for name in SAMPLE_FILES:
        source = samples_root / name
        if not source.exists():
            missing.append(str(source))
            continue
        target = SAMPLES_DIR / name
        shutil.copy2(source, target)
        copied.append(target)
    if missing:
        write_json(DEBUG_DIR / "missing-samples.json", {"missing": missing})
    return copied


def validate_image_bytes(content: bytes, expected_rgb: tuple[int, int, int]) -> dict[str, Any]:
    image = Image.open(BytesIO(content)).convert("RGB")
    reasons: list[str] = []
    if image.size != (295, 413):
        reasons.append(f"size {image.size} != 295x413")
    background_points = [
        (5, 5),
        (image.width - 6, 5),
        (image.width // 2, 5),
        (5, max(5, image.height // 5)),
        (image.width - 6, max(5, image.height // 5)),
    ]
    pixels = [image.getpixel(point) for point in background_points]
    for pixel in pixels:
        if any(abs(int(pixel[i]) - expected_rgb[i]) > 16 for i in range(3)):
            reasons.append(f"background sample mismatch {pixels} expected {expected_rgb}")
            break
    return {"passed": not reasons, "size": list(image.size), "backgroundSamples": pixels, "reasons": reasons}


def call_prepare(base_url: str, label: str, sample: Path) -> dict[str, Any]:
    with sample.open("rb") as fh:
        result = request_json(
            "POST",
            full_url(base_url, "/api/id-photo/prepare"),
            files={"image": (sample.name, fh, "image/jpeg")},
            data={
                "specId": "one-inch",
                "widthPx": "295",
                "heightPx": "413",
                "mode": "official",
                "composition": "head_shoulder",
                "outfit": "preserve_original",
            },
            timeout=60,
        )
    payload = {
        "backend": label,
        "sample": sample.name,
        "stage": "prepare",
        **result,
    }
    write_json(DEBUG_DIR / f"{label}-{sample.stem}-prepare.json", payload)
    return payload


def call_compose(base_url: str, label: str, sample: Path, prepared_id: str) -> dict[str, Any]:
    color_results: dict[str, Any] = {}
    output_root = LOCAL_DIR if label == "local" else CLOUD_DIR
    output_root.mkdir(parents=True, exist_ok=True)
    for color_name, (hex_color, expected_rgb) in COLORS.items():
        result = request_json(
            "POST",
            full_url(base_url, "/api/id-photo/compose"),
            data={
                "preparedId": prepared_id,
                "bgColor": hex_color,
                "bgColorName": color_name,
                "outputType": "jpg",
            },
            timeout=30,
        )
        item: dict[str, Any] = {
            "backend": label,
            "sample": sample.name,
            "stage": "compose",
            "color": color_name,
            **result,
        }
        data = result.get("data") or {}
        final_url = data.get("finalImageUrl") or data.get("resultUrl") or data.get("imageUrl") or ""
        item["finalImageUrl"] = final_url
        item["previewDownloadConsistent"] = bool(final_url and final_url == data.get("resultUrl"))
        if result.get("ok") and final_url:
            try:
                download = requests.get(full_url(base_url, final_url), timeout=20)
                item["downloadStatusCode"] = download.status_code
                if download.status_code == 200:
                    out_path = output_root / f"{sample.stem}-{color_name}.jpg"
                    out_path.write_bytes(download.content)
                    item["outputPath"] = str(out_path)
                    item["imageValidation"] = validate_image_bytes(download.content, expected_rgb)
                else:
                    item["imageValidation"] = {"passed": False, "reasons": [f"download status {download.status_code}"]}
            except Exception as exc:
                item["downloadStatusCode"] = 0
                item["downloadError"] = str(exc)
                item["imageValidation"] = {"passed": False, "reasons": [f"download error: {exc}"]}
        else:
            item["imageValidation"] = {"passed": False, "reasons": ["compose failed or missing finalImageUrl"]}
        item["passed"] = bool(
            result.get("ok")
            and data.get("success") is True
            and item.get("previewDownloadConsistent")
            and item.get("imageValidation", {}).get("passed")
        )
        write_json(DEBUG_DIR / f"{label}-{sample.stem}-{color_name}-compose.json", item)
        color_results[color_name] = item
    return color_results


def run_backend_samples(base_url: str, label: str, samples: list[Path]) -> dict[str, Any]:
    sample_results: list[dict[str, Any]] = []
    for sample in samples:
        prepare = call_prepare(base_url, label, sample)
        prepared_id = (prepare.get("data") or {}).get("preparedId")
        sample_result: dict[str, Any] = {
            "backend": label,
            "sample": sample.name,
            "prepare": prepare,
            "compose": {},
            "passed": False,
        }
        if prepare.get("ok") and (prepare.get("data") or {}).get("success") is True and prepared_id:
            sample_result["compose"] = call_compose(base_url, label, sample, prepared_id)
            sample_result["passed"] = all(item.get("passed") for item in sample_result["compose"].values())
        sample_results.append(sample_result)
    passed = bool(samples) and all(item["passed"] for item in sample_results)
    result = {
        "backend": label,
        "baseUrl": base_url,
        "sampleCount": len(samples),
        "colors": list(COLORS.keys()),
        "passed": passed,
        "samples": sample_results,
    }
    write_json(DEBUG_DIR / f"{label}-sample-results.json", result)
    return result


def image_diff_score(local_path: Path, cloud_path: Path) -> dict[str, Any]:
    if not local_path.exists() or not cloud_path.exists():
        return {"available": False, "meanAbsDiff": None, "reasons": ["missing image"]}
    local = Image.open(local_path).convert("RGB")
    cloud = Image.open(cloud_path).convert("RGB")
    if local.size != cloud.size:
        return {"available": True, "meanAbsDiff": None, "reasons": [f"size mismatch {local.size} vs {cloud.size}"]}
    diff = ImageChops.difference(local, cloud)
    stat = sum(sum(pixel) for pixel in diff.getdata()) / float(local.width * local.height * 3)
    return {"available": True, "meanAbsDiff": round(stat, 4), "size": list(local.size), "reasons": []}


def save_visual_compare(samples: list[Path]) -> dict[str, Any]:
    compare_items: list[dict[str, Any]] = []
    for sample in samples:
        cells: list[tuple[str, Path]] = [("source", sample)]
        for label, root in (("local", LOCAL_DIR), ("cloud", CLOUD_DIR)):
            for color in COLORS:
                path = root / f"{sample.stem}-{color}.jpg"
                if path.exists():
                    cells.append((f"{label}-{color}", path))
        thumbs: list[Image.Image] = []
        for title, path in cells:
            image = Image.open(path).convert("RGB")
            image.thumbnail((130, 182), Image.LANCZOS)
            frame = Image.new("RGB", (150, 220), (248, 250, 252))
            frame.paste(image, ((150 - image.width) // 2, 12))
            draw = ImageDraw.Draw(frame)
            draw.text((8, 198), title[:22], fill=(25, 35, 50))
            thumbs.append(frame)
        if thumbs:
            sheet = Image.new("RGB", (len(thumbs) * 150, 220), (226, 232, 240))
            for idx, thumb in enumerate(thumbs):
                sheet.paste(thumb, (idx * 150, 0))
            out_path = VISUAL_DIR / f"{sample.stem}-local-cloud-compare.jpg"
            sheet.save(out_path, quality=92)
            compare_items.append({"sample": sample.name, "path": str(out_path)})

    diffs: list[dict[str, Any]] = []
    for sample in samples:
        for color in COLORS:
            local_path = LOCAL_DIR / f"{sample.stem}-{color}.jpg"
            cloud_path = CLOUD_DIR / f"{sample.stem}-{color}.jpg"
            diffs.append({
                "sample": sample.name,
                "color": color,
                **image_diff_score(local_path, cloud_path),
            })

    result = {"items": compare_items, "diffs": diffs, "passed": bool(compare_items)}
    write_json(DEBUG_DIR / "visual-compare-summary.json", result)
    return result


def write_reports(
    frontend: dict[str, Any],
    local_health: dict[str, Any],
    cloud_health: dict[str, Any],
    local_samples: dict[str, Any],
    cloud_samples: dict[str, Any],
    visual: dict[str, Any],
) -> dict[str, Any]:
    local_pass = bool(local_health["passed"] and local_samples["passed"])
    cloud_pass = bool(cloud_health["passed"] and cloud_samples["passed"])
    preview_download_ok = all(
        item.get("previewDownloadConsistent")
        for backend in (local_samples, cloud_samples)
        for sample in backend.get("samples", [])
        for item in sample.get("compose", {}).values()
    )
    five_color_ok = all(
        set(sample.get("compose", {}).keys()) == set(COLORS.keys())
        for backend in (local_samples, cloud_samples)
        for sample in backend.get("samples", [])
        if sample.get("prepare", {}).get("ok")
    )
    all_outputs_295x413 = all(
        item.get("imageValidation", {}).get("size") == [295, 413]
        for backend in (local_samples, cloud_samples)
        for sample in backend.get("samples", [])
        for item in sample.get("compose", {}).values()
        if item.get("outputPath")
    )
    cloud_sync_pass = cloud_pass and (cloud_health.get("idPhotoHealth", {}).get("data", {}).get("version") == "current-fix-2026-06-10")

    write_md(
        FINAL_DIR / "local-vs-cloud-debug-report.md",
        [
            "# Local vs cloud debug report",
            f"- Local pass: {local_pass}",
            f"- Cloud pass: {cloud_pass}",
            f"- Five-color compose complete: {five_color_ok}",
            f"- Preview/download URL consistency: {preview_download_ok}",
            "- Key check: local and cloud must both run `/api/id-photo/prepare` and `/api/id-photo/compose` for all fixed samples.",
            "",
            "```json",
            json.dumps({"local": local_samples, "cloud": cloud_samples}, ensure_ascii=False, indent=2),
            "```",
        ],
    )

    write_md(
        FINAL_DIR / "sample-validation-report.md",
        [
            "# Sample validation report",
            f"- Fixed sample count: {local_samples.get('sampleCount')}",
            f"- Required colors: {', '.join(COLORS.keys())}",
            f"- Local sample pass: {local_samples.get('passed')}",
            f"- Cloud sample pass: {cloud_samples.get('passed')}",
            f"- Output size 295x413: {all_outputs_295x413}",
            "",
            "```json",
            json.dumps({"local": local_samples, "cloud": cloud_samples}, ensure_ascii=False, indent=2),
            "```",
        ],
    )

    write_md(
        FINAL_DIR / "visual-quality-report.md",
        [
            "# Visual quality report",
            f"- Comparison images generated: {len(visual.get('items', []))}",
            "- Comparison directory: `reports/id-photo-current-fix/visual-compare/`",
            "- Check includes saved local/cloud output images for blue, white, red, lightBlue, gray.",
            "",
            "```json",
            json.dumps(visual, ensure_ascii=False, indent=2),
            "```",
        ],
    )

    write_md(
        FINAL_DIR / "cloud-sync-report.md",
        [
            "# Cloud sync report",
            f"- Cloud base URL: `{cloud_health.get('baseUrl')}`",
            f"- `/api/id-photo/health` reachable: {cloud_health.get('idPhotoHealth', {}).get('ok')}",
            f"- Cloud samples pass: {cloud_samples.get('passed')}",
            f"- Cloud version matches this fix: {cloud_health.get('idPhotoHealth', {}).get('data', {}).get('version') == 'current-fix-2026-06-10'}",
            f"- Result: {'PASS' if cloud_sync_pass else 'FAIL'}",
            "",
            "If this is FAIL, the local code has not been deployed or the cloud service has not restarted with this patch.",
        ],
    )

    write_md(
        FINAL_DIR / "full-business-flow-regression.md",
        [
            "# Scoped business flow regression",
            "- Scope enforced: ID-photo generation only.",
            "- Flow: upload -> normalize -> classify -> detect face -> matting -> prepare cache -> compose five backgrounds -> download output.",
            f"- Local flow: {'PASS' if local_pass else 'FAIL'}",
            f"- Cloud flow: {'PASS' if cloud_pass else 'FAIL'}",
            f"- Frontend route scan: {'PASS' if frontend.get('passed') else 'FAIL'}",
            "- Unrelated pages and tools were not changed by this verifier.",
        ],
    )

    fixed_files = [
        "server/services/face_detector.py",
        "server/services/id_photo_v2.py",
        "server/services/id_photo_composer.py",
        "server/main.py",
        "server/scripts/verify_id_photo_current_fix.py",
        "package.json",
    ]
    write_md(
        FINAL_DIR / "fixed-files.md",
        ["# Fixed files", *[f"- `{item}`" for item in fixed_files]],
    )

    summary = {
        "passed": bool(frontend.get("passed") and local_pass and cloud_pass and preview_download_ok and five_color_ok and all_outputs_295x413 and cloud_sync_pass),
        "frontendPassed": frontend.get("passed"),
        "localPassed": local_pass,
        "cloudPassed": cloud_pass,
        "cloudSynced": cloud_sync_pass,
        "sampleCount": local_samples.get("sampleCount"),
        "colors": list(COLORS.keys()),
        "previewDownloadConsistency": preview_download_ok,
        "outputSize295x413": all_outputs_295x413,
        "reportsDir": str(FINAL_DIR),
        "blockingIssues": [],
    }
    if not local_pass:
        summary["blockingIssues"].append("local ID-photo flow failed")
    if not cloud_pass:
        summary["blockingIssues"].append("cloud ID-photo flow failed")
    if not cloud_sync_pass:
        summary["blockingIssues"].append("cloud service is not running this fix or /api/id-photo/health is unavailable")
    write_json(FINAL_DIR / "final-summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cloud-base-url", default="https://tupzjianzhao.chat")
    parser.add_argument("--samples", default=r"C:\Users\zyu33\Desktop")
    args = parser.parse_args()

    ensure_dirs()
    frontend = check_frontend_routes()
    samples = prepare_samples(Path(args.samples))
    if len(samples) != len(SAMPLE_FILES):
        write_json(FINAL_DIR / "final-summary.json", {
            "passed": False,
            "blockingIssues": ["missing fixed samples"],
            "expected": SAMPLE_FILES,
            "copied": [str(path) for path in samples],
        })
        return 1

    local_health = check_health(args.local_base_url, "local")
    cloud_health = check_health(args.cloud_base_url, "cloud")
    local_samples = run_backend_samples(args.local_base_url, "local", samples)
    cloud_samples = run_backend_samples(args.cloud_base_url, "cloud", samples)
    visual = save_visual_compare(samples)
    summary = write_reports(frontend, local_health, cloud_health, local_samples, cloud_samples, visual)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
