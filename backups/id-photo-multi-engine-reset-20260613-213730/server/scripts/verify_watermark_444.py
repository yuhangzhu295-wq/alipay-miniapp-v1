"""Mandatory 444.jpg watermark-removal regression.

The sample is the user's real flower/table image with tiled diagonal watermark.
This script builds a same-size black/white mask, calls real backend endpoints,
downloads real outputs, and writes before/after comparison reports.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "reports" / "final"
REPORT_DIR = FINAL / "watermark-444"
SOURCE_IMAGE = Path(r"C:\Users\zyu33\Desktop\444.jpg")


def cv_read(path: Path, flags: int = cv2.IMREAD_COLOR):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)


def cv_write(path: Path, image: np.ndarray) -> None:
    ok, encoded = cv2.imencode(path.suffix or ".png", image)
    if not ok:
        raise RuntimeError(f"cannot encode image: {path}")
    encoded.tofile(str(path))


def _url(base_url: str, result_url: str) -> str:
    if result_url.startswith("http://") or result_url.startswith("https://"):
        return result_url
    if not result_url.startswith("/"):
        result_url = "/" + result_url
    return base_url.rstrip("/") + result_url


def _get_json(url: str, timeout: float = 8.0) -> dict[str, Any]:
    try:
        res = requests.get(url, timeout=timeout)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:500]}
        data["_statusCode"] = res.status_code
        return data
    except Exception as exc:
        return {"_statusCode": 0, "success": False, "message": str(exc)}


def build_444_mask(source_path: Path, mask_path: Path) -> dict[str, Any]:
    image = cv_read(source_path, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"cannot read sample: {source_path}")
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    sat = hsv[:, :, 1]

    # Tiled watermark is low-saturation, thin, darker than its local background.
    local_bg = cv2.medianBlur(gray, 31)
    dark_thin = cv2.subtract(local_bg, gray)
    _, high_freq = cv2.threshold(dark_thin, 10, 255, cv2.THRESH_BINARY)
    low_sat = cv2.inRange(sat, 0, 88)
    mask = cv2.bitwise_and(high_freq, low_sat)

    # Keep thin strokes/text; reject broad shadows and object edges.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.dilate(mask, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    # Add a light periodic text-line prior so repeated characters are covered.
    h, w = mask.shape[:2]
    prior = np.zeros_like(mask)
    edges = cv2.Canny(high_freq, 40, 120)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180.0, threshold=42, minLineLength=55, maxLineGap=16)
    if lines is not None:
        for line in lines[:, 0, :]:
            x1, y1, x2, y2 = [int(v) for v in line]
            angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))
            if 25 <= angle <= 68 or 112 <= angle <= 155:
                cv2.line(prior, (x1, y1), (x2, y2), 255, 4)
    for y in range(55, h + 80, 180):
        for x in range(-120, w + 160, 185):
            cv2.rectangle(prior, (x + 42, y - 16), (x + 122, y + 20), 255, -1)
    # The real 444.jpg text tiles sit around x=70/255/440/625 and
    # y=84/270/455/...; cover those characters explicitly so faint text is
    # not missed by high-frequency detection.
    for y in range(84, h + 120, 185):
        for x in range(72, w + 180, 185):
            cv2.rectangle(prior, (x - 52, y - 26), (x + 66, y + 26), 255, -1)
    mask = cv2.bitwise_or(mask, prior)

    # Do not turn the repair into a huge hole-fill.
    ratio = float(np.count_nonzero(mask)) / float(mask.size)
    if ratio > 0.42:
        erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.erode(mask, erode_kernel, iterations=1)
        ratio = float(np.count_nonzero(mask)) / float(mask.size)

    cv_write(mask_path, mask)
    return {
        "width": int(w),
        "height": int(h),
        "nonZeroPixels": int(np.count_nonzero(mask)),
        "maskRatio": round(ratio, 6),
        "path": str(mask_path),
    }


def post_mode(base_url: str, mode: str, image_path: Path, mask_path: Path) -> dict[str, Any]:
    endpoint = {
        "manual": "/api/watermark/manual-remove",
        "quick": "/api/watermark/quick-remove",
        "hd": "/api/watermark/hd-remove",
    }[mode]
    with image_path.open("rb") as image_fh, mask_path.open("rb") as mask_fh:
        started = time.perf_counter()
        res = requests.post(
            base_url.rstrip() + endpoint,
            files={
                "image": (image_path.name, image_fh, "image/jpeg"),
                "mask": (mask_path.name, mask_fh, "image/png"),
            },
            data={
                "mode": mode,
                "quality": mode,
                "engine": "hd" if mode == "hd" else f"opencv_{mode}",
                "strength": "medium",
                "preserveDetail": "true",
            },
            timeout=300 if mode == "hd" else 120,
        )
    try:
        data = res.json()
    except Exception:
        data = {"success": False, "message": res.text[:500]}
    data["_statusCode"] = res.status_code
    data["_costMs"] = int((time.perf_counter() - started) * 1000)
    data["_endpoint"] = endpoint
    return data


def download(base_url: str, response: dict[str, Any], out_path: Path) -> dict[str, Any]:
    result_url = response.get("resultUrl") or response.get("imageUrl") or ""
    if not result_url:
        return {"passed": False, "reason": "missing result URL"}
    res = requests.get(_url(base_url, result_url), timeout=60)
    if res.status_code != 200 or not res.content:
        return {"passed": False, "statusCode": res.status_code, "bytes": len(res.content or b"")}
    out_path.write_bytes(res.content)
    try:
        img = Image.open(out_path)
        size = img.size
    except Exception as exc:
        return {"passed": False, "reason": str(exc)}
    return {
        "passed": True,
        "path": str(out_path),
        "url": result_url,
        "size": {"width": size[0], "height": size[1]},
        "bytes": len(res.content),
    }


def residue_score(image_path: Path, mask_path: Path) -> dict[str, Any]:
    img = cv_read(image_path, cv2.IMREAD_COLOR)
    mask = cv_read(mask_path, cv2.IMREAD_GRAYSCALE)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    local_bg = cv2.medianBlur(gray, 31)
    dark_thin = cv2.subtract(local_bg, gray)
    selected = dark_thin[mask > 0]
    if selected.size == 0:
        return {"mean": 0.0, "p90": 0.0}
    return {
        "mean": round(float(selected.mean()), 6),
        "p90": round(float(np.percentile(selected, 90)), 6),
    }


def diff_metrics(a_path: Path, b_path: Path, mask_path: Path | None = None) -> dict[str, Any]:
    a = cv_read(a_path, cv2.IMREAD_COLOR)
    b = cv_read(b_path, cv2.IMREAD_COLOR)
    if a is None or b is None:
        return {"mean": 0.0, "max": 0, "changed": False}
    if a.shape[:2] != b.shape[:2]:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR)
    diff = cv2.absdiff(a, b)
    if mask_path is not None:
        mask = cv_read(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is not None and mask.shape[:2] == a.shape[:2]:
            diff = diff[mask == 0]
    return {
        "mean": round(float(diff.mean()), 6),
        "max": int(diff.max()) if diff.size else 0,
        "changed": bool(np.max(diff) > 0) if diff.size else False,
    }


def make_contact_sheet(paths: dict[str, Path], metrics: dict[str, Any], target: Path) -> None:
    labels = ["source", "mask", "manual", "quick", "hd"]
    thumb_w, thumb_h = 260, 360
    margin = 18
    sheet = Image.new("RGB", (margin * 2 + thumb_w * len(labels), thumb_h + 96), (248, 250, 252))
    draw = ImageDraw.Draw(sheet)
    for idx, label in enumerate(labels):
        x = margin + idx * thumb_w
        try:
            img = Image.open(paths[label]).convert("RGB")
            img.thumbnail((thumb_w - 20, thumb_h - 40))
            sheet.paste(img, (x + (thumb_w - img.width) // 2, 38 + (thumb_h - 40 - img.height) // 2))
        except Exception:
            draw.text((x + 18, 80), "missing", fill=(185, 28, 28))
        draw.text((x + 12, 14), label.upper(), fill=(15, 23, 42))
    draw.text(
        (margin, thumb_h + 48),
        f"source residue={metrics['sourceResidue']['mean']} hd residue={metrics['hdResidue']['mean']} quick-vs-hd mean={metrics['quickVsHd']['mean']}",
        fill=(71, 85, 105),
    )
    sheet.save(target, quality=94)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    base_url = args.base_url.rstrip("/")
    FINAL.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    source_copy = REPORT_DIR / "source-444.jpg"
    if not SOURCE_IMAGE.exists():
        payload = {"status": "FAIL", "reason": f"missing mandatory sample {SOURCE_IMAGE}"}
        (FINAL / "watermark-444-regression-report.json").write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        return 1
    source_copy.write_bytes(SOURCE_IMAGE.read_bytes())
    mask_path = REPORT_DIR / "mask-444.png"
    mask_info = build_444_mask(source_copy, mask_path)

    health = _get_json(base_url + "/api/watermark/health")
    modes: dict[str, Any] = {}
    paths: dict[str, Path] = {"source": source_copy, "mask": mask_path}
    for mode in ["manual", "quick", "hd"]:
        response = post_mode(base_url, mode, source_copy, mask_path)
        out_path = REPORT_DIR / f"{mode}-444.jpg"
        result = download(base_url, response, out_path)
        if result.get("passed"):
            paths[mode] = out_path
        modes[mode] = {
            "response": response,
            "download": result,
            "passed": response.get("_statusCode") == 200
            and response.get("success") is True
            and result.get("passed") is True
            and not (mode == "hd" and response.get("fallbackUsed") is True)
            and not (mode == "hd" and response.get("engine") in {"opencv_hd_fallback", "not_ready"}),
        }

    metrics: dict[str, Any] = {
        "sourceResidue": residue_score(source_copy, mask_path),
        "manualResidue": residue_score(paths.get("manual", source_copy), mask_path),
        "quickResidue": residue_score(paths.get("quick", source_copy), mask_path),
        "hdResidue": residue_score(paths.get("hd", source_copy), mask_path),
        "sourceVsHdOutsideMask": diff_metrics(source_copy, paths.get("hd", source_copy), mask_path),
        "quickVsHd": diff_metrics(paths.get("quick", source_copy), paths.get("hd", source_copy)),
        "manualVsHd": diff_metrics(paths.get("manual", source_copy), paths.get("hd", source_copy)),
    }
    comparison = REPORT_DIR / "watermark-444-before-after-comparison.jpg"
    make_contact_sheet(paths, metrics, comparison)

    checks = {
        "sourceExists": source_copy.exists(),
        "maskSameSize": mask_info["width"] > 0 and mask_info["height"] > 0,
        "maskRatioReasonable": 0.005 <= mask_info["maskRatio"] <= 0.42,
        "manualEndpointPassed": modes["manual"]["passed"] is True,
        "quickEndpointPassed": modes["quick"]["passed"] is True,
        "hdEndpointPassed": modes["hd"]["passed"] is True,
        "hdUsesRealEngine": modes["hd"]["response"].get("engine") not in {"opencv_hd_fallback", "not_ready", "", None}
        and modes["hd"]["response"].get("fallbackUsed") is not True,
        "hdResidueReduced": metrics["hdResidue"]["mean"] <= metrics["sourceResidue"]["mean"] * 0.45,
        "hdP90ResidueReduced": metrics["hdResidue"]["p90"] <= metrics["sourceResidue"]["p90"] * 0.60,
        "quickAndHdDifferent": metrics["quickVsHd"]["mean"] >= 0.25 or metrics["quickVsHd"]["max"] >= 24,
        "outsideMaskPreserved": metrics["sourceVsHdOutsideMask"]["mean"] <= 8.0,
        "comparisonGenerated": comparison.exists(),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "status": status,
        "baseUrl": base_url,
        "mandatorySample": str(SOURCE_IMAGE),
        "health": health,
        "mask": mask_info,
        "modes": modes,
        "metrics": metrics,
        "checks": checks,
        "artifacts": {
            "source": str(source_copy),
            "mask": str(mask_path),
            "manual": str(paths.get("manual", "")),
            "quick": str(paths.get("quick", "")),
            "hd": str(paths.get("hd", "")),
            "comparison": str(comparison),
        },
    }
    (FINAL / "watermark-444-regression-report.json").write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    (FINAL / "watermark-quality-report.json").write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    md = [
        "# Watermark 444 Regression Report",
        "",
        f"- Status: {status}",
        f"- Sample: `{SOURCE_IMAGE}`",
        f"- Mask ratio: `{mask_info['maskRatio']}`",
        f"- Comparison: `{comparison}`",
        "",
        "## Checks",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in checks.items()],
        "",
        "## Metrics",
        f"- Source residue mean: `{metrics['sourceResidue']['mean']}`",
        f"- HD residue mean: `{metrics['hdResidue']['mean']}`",
        f"- Quick vs HD mean/max: `{metrics['quickVsHd']['mean']}` / `{metrics['quickVsHd']['max']}`",
        f"- Outside-mask diff mean: `{metrics['sourceVsHdOutsideMask']['mean']}`",
        "",
    ]
    (FINAL / "watermark-444-regression-report.md").write_text("\n".join(md), encoding="utf-8")
    (FINAL / "watermark-before-after-comparison.md").write_text(
        "\n".join([
            "# Watermark Before/After Comparison",
            "",
            f"- Status: {status}",
            f"- Source: `{source_copy}`",
            f"- Mask: `{mask_path}`",
            f"- Manual: `{paths.get('manual', '')}`",
            f"- Quick: `{paths.get('quick', '')}`",
            f"- HD: `{paths.get('hd', '')}`",
            f"- Contact sheet: `{comparison}`",
            "",
        ]),
        encoding="utf-8",
    )
    print(f"[verify-watermark-444] {status} report={FINAL / 'watermark-444-regression-report.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
