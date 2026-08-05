"""Verify first-stage watermark scan removal.

This script checks that the mini-program no longer exposes or calls the
scan-template workflow, then exercises real manual / quick / HD watermark
removal endpoints with a local image and mask.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "current-fixes"
FINAL_DIR = REPORT_ROOT / "final"
WM_DIR = REPORT_ROOT / "watermark"
SOURCE_CANDIDATES = [
    Path(r"C:\Users\zyu33\Desktop\2nE7fvSrsz95e91b9badb05df6ad15ee9f5155af2f81.jpg"),
    Path(r"C:\Users\zyu33\Desktop\444.jpg"),
]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_fallback_source(path: Path) -> None:
    img = Image.new("RGB", (720, 960), (246, 221, 185))
    draw = ImageDraw.Draw(img)
    for x in range(-160, 880, 190):
        draw.line([(x, 0), (x + 720, 960)], fill=(150, 135, 118), width=3)
        draw.line([(x + 120, 0), (x - 600, 960)], fill=(150, 135, 118), width=3)
    for y in range(80, 960, 180):
        for x in range(70, 720, 185):
            draw.text((x, y), "WM", fill=(120, 105, 92))
    draw.rectangle([260, 420, 420, 780], outline=(155, 130, 90), width=5)
    draw.ellipse([190, 340, 360, 500], fill=(236, 184, 52))
    draw.line([(340, 390), (395, 255), (470, 355)], fill=(94, 111, 45), width=7)
    img.save(path, quality=92)


def get_source_image() -> Path:
    for candidate in SOURCE_CANDIDATES:
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    fallback = WM_DIR / "source" / "synthetic-watermark-source.jpg"
    fallback.parent.mkdir(parents=True, exist_ok=True)
    make_fallback_source(fallback)
    return fallback


def build_mask(source: Path, mask_path: Path) -> dict[str, Any]:
    img = Image.open(source).convert("RGB")
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    line_width = max(5, int(min(w, h) * 0.008))
    step_x = max(110, int(w * 0.23))
    step_y = max(95, int(h * 0.18))
    for x in range(-w, w * 2, step_x):
        draw.line([(x, 0), (x + w, h)], fill=255, width=line_width)
        draw.line([(x + int(step_x * 0.6), 0), (x - w, h)], fill=255, width=line_width)
    rect_w = max(46, int(w * 0.12))
    rect_h = max(24, int(h * 0.035))
    for y in range(int(h * 0.08), h, step_y):
        for x in range(int(w * 0.06), w, step_x):
            draw.rectangle([x, y, min(w, x + rect_w), min(h, y + rect_h)], fill=255)
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    mask.save(mask_path)
    non_zero = w * h - mask.histogram()[0]
    return {
        "path": str(mask_path),
        "width": w,
        "height": h,
        "maskRatio": round(non_zero / float(w * h), 6),
    }


def health(base_url: str) -> dict[str, Any]:
    try:
        res = requests.get(base_url.rstrip("/") + "/api/health", timeout=8)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:300]}
        data["_statusCode"] = res.status_code
        return data
    except Exception as exc:
        return {"success": False, "_statusCode": 0, "message": str(exc)}


def result_url(base_url: str, value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if not value.startswith("/"):
        value = "/" + value
    return base_url.rstrip("/") + value


def post_endpoint(base_url: str, mode: str, source: Path, mask: Path) -> dict[str, Any]:
    endpoint = {
        "manual": "/api/watermark/manual-remove",
        "quick": "/api/watermark/quick-remove",
        "hd": "/api/watermark/hd-remove",
    }[mode]
    started = time.perf_counter()
    try:
        with source.open("rb") as image_fh, mask.open("rb") as mask_fh:
            res = requests.post(
                base_url.rstrip("/") + endpoint,
                files={
                    "image": (source.name, image_fh, "image/jpeg"),
                    "mask": (mask.name, mask_fh, "image/png"),
                },
                data={"mode": mode, "quality": mode, "strength": "medium", "preserveDetail": "true"},
                timeout=180 if mode == "hd" else 90,
            )
        try:
            data = res.json()
        except Exception:
            data = {"success": False, "message": res.text[:500]}
        data["_statusCode"] = res.status_code
    except Exception as exc:
        data = {"success": False, "_statusCode": 0, "message": str(exc)}
    data["_endpoint"] = endpoint
    data["_costMs"] = int((time.perf_counter() - started) * 1000)
    return data


def download_output(base_url: str, response: dict[str, Any], target: Path, source_size: tuple[int, int]) -> dict[str, Any]:
    url = response.get("resultUrl") or response.get("imageUrl") or ""
    if not url:
        return {"passed": False, "reason": "missing resultUrl"}
    try:
        res = requests.get(result_url(base_url, url), timeout=60)
        if res.status_code != 200 or not res.content:
            return {"passed": False, "statusCode": res.status_code, "bytes": len(res.content or b"")}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(res.content)
        out = Image.open(target)
        same_size = out.size == source_size
        return {
            "passed": same_size,
            "path": str(target),
            "size": {"width": out.size[0], "height": out.size[1]},
            "bytes": len(res.content),
            "sameSize": same_size,
        }
    except Exception as exc:
        return {"passed": False, "reason": str(exc)}


def static_checks() -> list[dict[str, Any]]:
    page_js = read_text(ROOT / "pages" / "tool-detail" / "tool-detail.js")
    page_wxml = read_text(ROOT / "pages" / "tool-detail" / "tool-detail.wxml")
    api_js = read_text(ROOT / "utils" / "watermarkApi.js")
    checks = [
        ("scan chip removed", 'data-mode="scan"' not in page_wxml and "扫描水印" not in page_wxml),
        ("scan panel removed", "wmMode === 'scan'" not in page_wxml),
        ("frontend scan API removed", "scanTemplate" not in api_js and "/api/watermark/scan-template" not in api_js),
        ("page scan state removed", "scanResult" not in page_js and "scanIntensity" not in page_js and "onWmScanThresholdChange" not in page_js),
        (
            "old scan mode degrades",
            (
                "mode = 'manual'" in page_js
                and (
                    "mode !== 'manual' && mode !== 'stamp'" in page_js
                    or "allowedModes" in page_js
                )
            ),
        ),
        (
            "fast mode uses quick endpoint",
            "/api/watermark/remove-v2" in page_js
            and "wmApi.removeV2" in page_js
            and "modeKey" in page_js
            and "'quick'" in page_js,
        ),
        ("manual and stamp remain", 'data-mode="manual"' in page_wxml and 'data-mode="stamp"' in page_wxml),
    ]
    return [{"name": name, "passed": bool(passed)} for name, passed in checks]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    (WM_DIR / "output").mkdir(parents=True, exist_ok=True)

    source = get_source_image()
    source_copy = WM_DIR / "source" / source.name
    source_copy.parent.mkdir(parents=True, exist_ok=True)
    source_copy.write_bytes(source.read_bytes())
    source_size = Image.open(source_copy).size
    mask_path = WM_DIR / "mask" / "watermark-business-mask.png"
    mask_info = build_mask(source_copy, mask_path)

    static = static_checks()
    health_result = health(args.base_url)
    results: dict[str, Any] = {}
    if health_result.get("_statusCode") == 200 and health_result.get("success") is True:
        for mode in ("manual", "quick", "hd"):
            response = post_endpoint(args.base_url, mode, source_copy, mask_path)
            output = download_output(
                args.base_url,
                response,
                WM_DIR / "output" / f"{source_copy.stem}-{mode}.jpg",
                source_size,
            )
            results[mode] = {
                "response": response,
                "output": output,
                "passed": response.get("_statusCode") == 200 and response.get("success") is True and output.get("passed") is True,
            }
    else:
        for mode in ("manual", "quick", "hd"):
            results[mode] = {"passed": False, "reason": "backend health failed"}

    summary = {
        "baseUrl": args.base_url,
        "health": health_result,
        "source": {"path": str(source_copy), "size": {"width": source_size[0], "height": source_size[1]}},
        "mask": mask_info,
        "staticChecks": static,
        "endpointResults": results,
    }
    summary["passed"] = all(item["passed"] for item in static) and all(item["passed"] for item in results.values())

    json_path = FINAL_DIR / "watermark-remove-scan-report.json"
    md_path = FINAL_DIR / "watermark-remove-scan-report.md"
    write_json(json_path, summary)
    lines = [
        "# Watermark Remove Scan Report",
        "",
        f"- Base URL: `{args.base_url}`",
        f"- Backend health: {'PASS' if health_result.get('_statusCode') == 200 and health_result.get('success') is True else 'FAIL'}",
        f"- Source image: `{source_copy}`",
        f"- Mask ratio: `{mask_info['maskRatio']}`",
        f"- Overall: {'PASS' if summary['passed'] else 'FAIL'}",
        "",
        "## Static Checks",
    ]
    lines.extend([f"- {'PASS' if c['passed'] else 'FAIL'}: {c['name']}" for c in static])
    lines.append("")
    lines.append("## Endpoint Checks")
    for mode, result in results.items():
        response = result.get("response", {})
        output = result.get("output", {})
        lines.append(
            f"- {mode}: {'PASS' if result.get('passed') else 'FAIL'} "
            f"status={response.get('_statusCode')} costMs={response.get('_costMs')} "
            f"output={output.get('path') or output.get('reason')}"
        )
    write_markdown(md_path, lines)
    print(f"[verify:watermark-remove-scan] report={md_path} passed={summary['passed']}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
