"""Real 6666.jpg tiled-watermark regression with magnified residue checks."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from services.hd_inpaint import _detect_repeating_diagonal_grid_mask, _residual_quality  # noqa: E402


SOURCE = Path(r"C:\Users\zyu33\Desktop\6666.jpg")
FINAL = ROOT / "reports" / "final"
REPORT_DIR = FINAL / "watermark-6666"
WATERMARK_DIR = ROOT / "reports" / "watermark"
DEBUG_DIR = WATERMARK_DIR / "debug"
ITERATIONS_DIR = WATERMARK_DIR / "iterations"


def cv_read(path: Path, flags: int = cv2.IMREAD_COLOR):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, flags) if data.size else None


def cv_write(path: Path, image: np.ndarray) -> None:
    ok, encoded = cv2.imencode(path.suffix or ".png", image)
    if not ok:
        raise RuntimeError(f"cannot encode {path}")
    encoded.tofile(str(path))


def get_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    try:
        res = requests.get(url, timeout=timeout)
        data = res.json()
        data["_statusCode"] = res.status_code
        return data
    except Exception as exc:
        return {"_statusCode": 0, "success": False, "message": str(exc)}


def result_url(base_url: str, url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return base_url.rstrip("/") + (url if url.startswith("/") else "/" + url)


def download(base_url: str, url: str, target: Path) -> dict[str, Any]:
    if not url:
        return {"statusCode": 0, "bytes": 0, "passed": False, "error": "missing result URL"}
    try:
        res = requests.get(result_url(base_url, url), timeout=60)
        target.write_bytes(res.content)
        image = Image.open(target)
        image.verify()
        image = Image.open(target)
        return {
            "statusCode": res.status_code,
            "bytes": len(res.content),
            "width": image.width,
            "height": image.height,
            "passed": res.status_code == 200 and len(res.content) > 0,
        }
    except Exception as exc:
        return {
            "statusCode": locals().get("res").status_code if "res" in locals() else 0,
            "bytes": len(locals().get("res").content or b"") if "res" in locals() else 0,
            "passed": False,
            "error": str(exc),
        }


def post_remove(base_url: str, endpoint: str, image_path: Path, mask_path: Path) -> dict[str, Any]:
    with image_path.open("rb") as image_fh, mask_path.open("rb") as mask_fh:
        started = time.perf_counter()
        res = requests.post(
            base_url.rstrip("/") + endpoint,
            files={
                "image": (image_path.name, image_fh, "image/jpeg"),
                "mask": (mask_path.name, mask_fh, "image/png"),
            },
            data={"strength": "medium", "preserveDetail": "true"},
            timeout=300,
        )
    try:
        data = res.json()
    except Exception:
        data = {"success": False, "message": res.text[:500]}
    data["_statusCode"] = res.status_code
    data["_costMs"] = int((time.perf_counter() - started) * 1000)
    return data


def scan_template(base_url: str, image_path: Path) -> dict[str, Any]:
    with image_path.open("rb") as image_fh:
        res = requests.post(
            base_url.rstrip("/") + "/api/watermark/scan-template",
            files={"image": (image_path.name, image_fh, "image/jpeg")},
            data={"x": "35", "y": "60", "w": "105", "h": "50", "threshold": "0.58"},
            timeout=120,
        )
    data = res.json()
    data["_statusCode"] = res.status_code
    return data


def image_diff(a_path: Path, b_path: Path) -> dict[str, Any]:
    a = cv_read(a_path)
    b = cv_read(b_path)
    if a is None or b is None:
        return {"mean": 0.0, "max": 0}
    if a.shape[:2] != b.shape[:2]:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR)
    diff = cv2.absdiff(a, b)
    return {"mean": round(float(diff.mean()), 6), "max": int(diff.max())}


def build_artifacts(source: Path, mask_path: Path, hd_path: Path) -> dict[str, Any]:
    source_cv = cv_read(source)
    mask = cv_read(mask_path, cv2.IMREAD_GRAYSCALE)
    hd_cv = cv_read(hd_path)
    grid_mask, source_grid = _detect_repeating_diagonal_grid_mask(source_cv)
    expanded = cv2.bitwise_or(mask, grid_mask)
    output_grid_mask, output_grid = _detect_repeating_diagonal_grid_mask(hd_cv)
    del output_grid_mask

    gray = cv2.cvtColor(hd_cv, cv2.COLOR_BGR2GRAY)
    dark = cv2.subtract(cv2.medianBlur(gray, 31), gray)
    residual = np.where((dark > 8) & (expanded > 0), 255, 0).astype(np.uint8)
    residual = cv2.morphologyEx(
        residual,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    )

    cv_write(DEBUG_DIR / "mask-original.png", mask)
    cv_write(DEBUG_DIR / "mask-hd-expanded.png", expanded)
    cv_write(DEBUG_DIR / "mask-residual.png", residual)
    cv_write(REPORT_DIR / "mask-hd-expanded.png", expanded)
    cv_write(REPORT_DIR / "mask-residual.png", residual)

    return {
        "sourceGrid": source_grid,
        "outputGrid": output_grid,
        "maskRatio": round(float(np.count_nonzero(mask)) / float(mask.size), 6),
        "expandedMaskRatio": round(float(np.count_nonzero(expanded)) / float(expanded.size), 6),
        "residualMaskRatio": round(float(np.count_nonzero(residual)) / float(residual.size), 6),
        "residualQuality": _residual_quality(hd_cv, grid_mask if source_grid.get("gridDetected") else expanded),
    }


def make_comparisons(source: Path, mask: Path, quick: Path, hd: Path) -> list[str]:
    items = [("SOURCE", source), ("SCAN MASK", mask), ("QUICK", quick), ("HD FINAL", hd)]
    thumb_w, thumb_h = 250, 375
    sheet = Image.new("RGB", (thumb_w * len(items), thumb_h + 40), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (label, path) in enumerate(items):
        image = Image.open(path).convert("RGB")
        image.thumbnail((thumb_w - 12, thumb_h - 12))
        x = index * thumb_w + (thumb_w - image.width) // 2
        y = 34 + (thumb_h - image.height) // 2
        sheet.paste(image, (x, y))
        draw.text((index * thumb_w + 8, 8), label, fill="black")
    contact = REPORT_DIR / "watermark-6666-contact-sheet.jpg"
    sheet.save(contact, quality=96)

    zoom_paths = []
    regions = {
        "top": (20, 35, 650, 260),
        "flower": (90, 300, 630, 660),
        "lower": (20, 650, 650, 1000),
    }
    for name, box in regions.items():
        rows = []
        for label, path in [("SOURCE", source), ("HD FINAL", hd)]:
            crop = Image.open(path).convert("RGB").crop(box)
            scale = min(1000 / crop.width, 650 / crop.height)
            crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.Resampling.LANCZOS)
            tile = Image.new("RGB", (crop.width, crop.height + 30), "white")
            tile.paste(crop, (0, 30))
            ImageDraw.Draw(tile).text((8, 8), label, fill="black")
            rows.append(tile)
        zoom = Image.new("RGB", (sum(row.width for row in rows), max(row.height for row in rows)), "white")
        x = 0
        for row in rows:
            zoom.paste(row, (x, 0))
            x += row.width
        zoom_path = REPORT_DIR / f"watermark-6666-zoom-{name}.jpg"
        zoom.save(zoom_path, quality=98)
        zoom_paths.append(str(zoom_path))
    return [str(contact), *zoom_paths]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    base_url = args.base_url.rstrip("/")
    for directory in [FINAL, REPORT_DIR, WATERMARK_DIR, DEBUG_DIR, ITERATIONS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

    if not SOURCE.exists():
        print(f"[verify-watermark-6666] FAIL missing {SOURCE}")
        return 1

    source_copy = REPORT_DIR / "source-6666.jpg"
    shutil.copy2(SOURCE, source_copy)
    health = get_json(base_url + "/api/watermark/health")
    scan = scan_template(base_url, source_copy)
    mask_path = REPORT_DIR / "scan-mask-6666.png"
    scan_download = download(base_url, scan.get("imageUrl", ""), mask_path)

    quick_response = post_remove(base_url, "/api/watermark/quick-remove", source_copy, mask_path)
    quick_path = REPORT_DIR / "quick-6666.jpg"
    quick_download = download(base_url, quick_response.get("resultUrl", ""), quick_path)

    hd_path = REPORT_DIR / "hd-final-6666.jpg"
    hd_response: dict[str, Any] = {}
    hd_download: dict[str, Any] = {"passed": False}
    for attempt in range(1, 4):
        hd_response = post_remove(base_url, "/api/watermark/hd-remove", source_copy, mask_path)
        hd_response["_attempt"] = attempt
        hd_download = download(base_url, hd_response.get("resultUrl", ""), hd_path)
        if hd_response.get("_statusCode") == 200 and hd_response.get("success") is True and hd_download.get("passed") is True:
            break
        time.sleep(2)
    debug = hd_response.get("debug") or {}

    if hd_download.get("passed"):
        artifact_metrics = build_artifacts(source_copy, mask_path, hd_path)
        comparisons = make_comparisons(source_copy, mask_path, quick_path, hd_path)
        quick_vs_hd = image_diff(quick_path, hd_path) if quick_download.get("passed") else {"passed": False, "reason": "quick download failed"}
        source_grid = artifact_metrics["sourceGrid"]
        output_grid = artifact_metrics["outputGrid"]
    else:
        source_grid = _detect_repeating_diagonal_grid_mask(cv_read(source_copy), None)
        output_grid = {"gridDetected": True, "reason": "HD output unavailable"}
        artifact_metrics = {
            "maskRatio": 0.0,
            "expandedMaskRatio": 0.0,
            "sourceGrid": source_grid,
            "outputGrid": output_grid,
            "residual": {},
        }
        comparisons = {"contactSheet": "", "zoomTop": "", "zoomFlower": "", "zoomLower": ""}
        quick_vs_hd = {"passed": False, "reason": "HD output unavailable"}
    rects = scan.get("rects") or []
    edge_rects = [
        rect for rect in rects
        if int(rect.get("w") or 0) < 105 or int(rect.get("h") or 0) < 50
    ]

    if hd_download.get("passed"):
        shutil.copy2(hd_path, ITERATIONS_DIR / "hd-pass-1.png")
        shutil.copy2(hd_path, ITERATIONS_DIR / "hd-final.png")
    quality = {
        "engine": hd_response.get("engine"),
        "hdRealModelLoaded": health.get("hdRealModelLoaded"),
        "fallbackUsed": hd_response.get("fallbackUsed"),
        "inputImage": str(SOURCE),
        "maskCoverageRatio": artifact_metrics["maskRatio"],
        "expandedMaskCoverageRatio": artifact_metrics["expandedMaskRatio"],
        "residualScoreBefore": debug.get("residualScoreBefore"),
        "residualScoreAfter": debug.get("residualScoreAfter"),
        "residualDetected": debug.get("residualDetected"),
        "autoRetryCount": debug.get("autoRetryCount"),
        "gridDetectedBefore": source_grid.get("gridDetected"),
        "gridDetectedAfter": output_grid.get("gridDetected"),
    }
    (ITERATIONS_DIR / "hd-pass-1-quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    (ITERATIONS_DIR / "hd-final-quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")

    checks = {
        "sourceExists": SOURCE.exists(),
        "gatewayHealthy": health.get("_statusCode") == 200 and health.get("success") is True,
        "realLamaLoaded": health.get("hdRealModelLoaded") is True and health.get("fallbackUsed") is False,
        "scanTemplatePassed": scan.get("_statusCode") == 200 and scan.get("success") is True,
        "scanFoundRepeatedTiles": len(rects) >= 20,
        "scanCoveredPartialEdgeTiles": len(edge_rects) >= 4,
        "scanMaskDownloaded": scan_download.get("passed") is True,
        "quickPassed": quick_response.get("_statusCode") == 200 and quick_response.get("success") is True,
        "hdPassed": hd_response.get("_statusCode") == 200 and hd_response.get("success") is True,
        "hdUsesRealLama": hd_response.get("engine") == "lama" and hd_response.get("fallbackUsed") is False,
        "backendExpandedGridMask": debug.get("gridMaskExpanded") is True and debug.get("gridDetected") is True,
        "sourceGridDetected": source_grid.get("gridDetected") is True,
        "outputGridNotDetected": output_grid.get("gridDetected") is False,
        "residualScoreLow": float(debug.get("residualScoreAfter") or 99) <= 1.6,
        "residualP90Low": float(debug.get("residualP90After") or 99) <= 4.0,
        "residualDarkRatioLow": float(debug.get("residualDarkRatioAfter") or 99) <= 0.05,
        "backendReportsNoResidual": debug.get("residualDetected") is False,
        "quickAndHdDifferent": quick_vs_hd["mean"] >= 0.25,
        "hdSizePreserved": hd_download.get("width") == 668 and hd_download.get("height") == 1002,
        "magnifiedComparisonsGenerated": len(comparisons) == 4 and all(Path(path).exists() for path in comparisons),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    quality["pass"] = status == "PASS"
    quality["failReasons"] = [name for name, passed in checks.items() if not passed]
    (WATERMARK_DIR / "residual-quality.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")

    payload = {
        "status": status,
        "baseUrl": base_url,
        "sample": str(SOURCE),
        "health": health,
        "scan": scan,
        "quick": {"response": quick_response, "download": quick_download},
        "hd": {"response": hd_response, "download": hd_download},
        "metrics": {**artifact_metrics, "quickVsHd": quick_vs_hd},
        "checks": checks,
        "artifacts": {
            "source": str(source_copy),
            "mask": str(mask_path),
            "quick": str(quick_path),
            "hd": str(hd_path),
            "comparisons": comparisons,
        },
    }
    report_json = FINAL / "watermark-6666-validation-report.json"
    report_md = FINAL / "watermark-6666-validation-report.md"
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Watermark 6666 HD Validation Report",
        "",
        f"- Status: {status}",
        f"- Sample: `{SOURCE}`",
        f"- Engine: `{hd_response.get('engine')}`",
        f"- fallbackUsed: `{hd_response.get('fallbackUsed')}`",
        f"- Scan tiles / edge tiles: `{len(rects)}` / `{len(edge_rects)}`",
        f"- Grid score before: `{source_grid.get('gridPlusScore')}` / `{source_grid.get('gridMinusScore')}`",
        f"- Grid detected after: `{output_grid.get('gridDetected')}`",
        f"- Residual mean / p90 / dark ratio: `{debug.get('residualScoreAfter')}` / `{debug.get('residualP90After')}` / `{debug.get('residualDarkRatioAfter')}`",
        f"- Auto retry count: `{debug.get('autoRetryCount')}`",
        "",
        "## Checks",
        *[f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items()],
        "",
        "## Magnified Evidence",
        *[f"- `{path}`" for path in comparisons],
        "",
    ]
    report_md.write_text("\n".join(lines), encoding="utf-8")

    audit = [
        "# Watermark Current-state Audit",
        "",
        "- Scope: image watermark removal only",
        f"- Gateway: `{base_url}`",
        f"- HD engine: `{health.get('hdEngine')}`",
        f"- hdRealModelLoaded: `{health.get('hdRealModelLoaded')}`",
        f"- fallbackUsed: `{health.get('fallbackUsed')}`",
        "- HD path: FastAPI `/api/watermark/hd-remove` -> local IOPaint `/api/v1/inpaint` -> LaMa",
        "- Mask path: template scan rectangles -> edge-tile extrapolation -> periodic diagonal-grid expansion",
        "- Residue cause: incomplete edge tiles and low-opacity diagonal strokes were outside the previous mask",
        "- Modified files: `server/services/hd_inpaint.py`, `server/services/scan_template.py`, verification scripts",
        "",
    ]
    (WATERMARK_DIR / "current-state-audit.md").write_text("\n".join(audit), encoding="utf-8")
    (WATERMARK_DIR / "final-watermark-report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (WATERMARK_DIR / "final-watermark-report.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"[verify-watermark-6666] {status} report={report_md}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
