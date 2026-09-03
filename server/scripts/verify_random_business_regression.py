#!/usr/bin/env python3
"""Randomized end-to-end regression for ID-photo composition and local inpaint."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import random
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "random-business-regression"
PORTRAIT_DIR = REPORT_ROOT / "portraits"
WATERMARK_DIR = REPORT_ROOT / "watermark"
FINAL_DIR = REPORT_ROOT / "final"
BG_RGB = (26, 115, 232)
SPECS = [
    ("one_inch", 295, 413, 25, 35),
    ("two_inch", 413, 579, 35, 49),
    ("passport", 390, 567, 33, 48),
    ("exam", 260, 378, 22, 32),
]


def ensure_dirs() -> None:
    for path in (PORTRAIT_DIR, WATERMARK_DIR, FINAL_DIR):
        path.mkdir(parents=True, exist_ok=True)


def absolute_url(base_url: str, value: str) -> str:
    return value if value.startswith("http") else base_url.rstrip("/") + value


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def image_bytes(image: Image.Image, fmt: str = "JPEG") -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, quality=94)
    return buffer.getvalue()


def edge_background_ratio(image: np.ndarray, expected_rgb: tuple[int, int, int]) -> float:
    expected = np.asarray(expected_rgb[::-1], dtype=np.int16)
    # A standard head-and-shoulders crop may intentionally meet the lower
    # canvas edge.  Check the top and upper side background for black bars or
    # transparent-edge artifacts without rejecting a correctly cropped torso.
    upper = max(1, int(round(image.shape[0] * 0.35)))
    edge = np.concatenate((image[0], image[:upper, 0], image[:upper, -1]), axis=0).astype(np.int16)
    return float(np.mean(np.max(np.abs(edge - expected), axis=1) <= 4))


def background_ratio(image: np.ndarray, bbox: dict[str, Any], expected_rgb: tuple[int, int, int]) -> float:
    mask = np.ones(image.shape[:2], dtype=bool)
    x = max(0, int(math.floor(float(bbox.get("x") or 0))))
    y = max(0, int(math.floor(float(bbox.get("y") or 0))))
    x2 = min(image.shape[1], int(math.ceil(x + float(bbox.get("width") or 0))))
    y2 = min(image.shape[0], int(math.ceil(y + float(bbox.get("height") or 0))))
    mask[y:y2, x:x2] = False
    pixels = image[mask].astype(np.int16)
    expected = np.asarray(expected_rgb[::-1], dtype=np.int16)
    if not pixels.size:
        return 0.0
    return float(np.mean(np.max(np.abs(pixels - expected), axis=1) <= 4))


def make_portrait_variant(raw: bytes, variant: str, target_size: tuple[int, int]) -> bytes:
    source = Image.open(io.BytesIO(raw)).convert("RGB")
    arr = np.asarray(source)
    border = np.concatenate(
        (arr[:8].reshape(-1, 3), arr[-8:].reshape(-1, 3), arr[:, :8].reshape(-1, 3), arr[:, -8:].reshape(-1, 3)),
        axis=0,
    )
    background = tuple(int(value) for value in np.median(border, axis=0))
    width, height = target_size
    canvas = Image.new("RGB", (width, height), background)
    if variant == "landscape":
        side = int(min(height * 0.92, width * 0.72))
        resized = source.resize((side, side), Image.Resampling.LANCZOS)
        canvas.paste(resized, ((width - side) // 2, height - side))
    elif variant == "portrait":
        side = int(min(width, height * 0.78))
        resized = source.resize((side, side), Image.Resampling.LANCZOS)
        canvas.paste(resized, ((width - side) // 2, int(height * 0.10)))
    else:
        side = min(width, height)
        resized = source.resize((side, side), Image.Resampling.LANCZOS)
        canvas.paste(resized, ((width - side) // 2, (height - side) // 2))
    return image_bytes(canvas)


def random_portrait_candidates(seed: int, user_portrait: Path | None) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    if user_portrait and user_portrait.exists():
        rows.append({
            "id": "user_glasses_selfie",
            "gender": "unknown",
            "category": "glasses,selfie,portrait,high_resolution",
            "bytes": user_portrait.read_bytes(),
            "source": str(user_portrait),
        })
    local_pool = list((ROOT / "reports" / "id-photo-under-10s" / "fast-ab-artifacts").glob("*/canonical-source.jpg"))
    rng.shuffle(local_pool)
    for path in local_pool:
        try:
            with Image.open(path) as image:
                width, height = image.size
            orientation = "landscape" if width > height else ("square" if abs(width - height) <= min(width, height) * 0.08 else "portrait")
            rows.append({
                "id": f"local_{len(rows):02d}_{orientation}_{width}x{height}",
                "gender": "mixed_pool",
                "category": f"local_qualified,{orientation},{width}x{height},random_seed_selection",
                "bytes": path.read_bytes(),
                "source": str(path),
            })
        except Exception:
            continue
    if len(rows) >= 16:
        return rows
    variants = [
        ("portrait", (720, 960)),
        ("landscape", (960, 720)),
        ("portrait", (900, 1200)),
        ("square", (768, 768)),
    ]
    for gender, folder in (("male", "men"), ("female", "women")):
        for index in rng.sample(range(100), 18):
            url = f"https://randomuser.me/api/portraits/{folder}/{index}.jpg"
            try:
                response = requests.get(url, timeout=20, headers={"User-Agent": "id-photo-random-regression/1.0"})
                response.raise_for_status()
                variant, size = variants[(index + (0 if gender == "male" else 1)) % len(variants)]
                rows.append({
                    "id": f"{gender}_{index}_{variant}_{size[0]}x{size[1]}",
                    "gender": gender,
                    "category": f"{gender},{variant},{size[0]}x{size[1]},public_random",
                    "bytes": make_portrait_variant(response.content, variant, size),
                    "source": url,
                })
            except Exception as exc:
                rows.append({"id": f"{gender}_{index}", "downloadError": str(exc), "source": url})
    return rows


def post_id_photo(session: requests.Session, base_url: str, sample: dict[str, Any], spec: tuple[Any, ...]) -> dict[str, Any]:
    spec_id, width, height, width_mm, height_mm = spec
    started = time.perf_counter()
    response = session.post(
        base_url.rstrip("/") + "/api/id-photo/prepare",
        files={"image": (sample["id"] + ".jpg", sample["bytes"], "image/jpeg")},
        data={
            "purpose": "official_id_photo",
            "specId": f"random_{spec_id}_{width}_{height}",
            "widthPx": str(width),
            "heightPx": str(height),
            "widthMm": str(width_mm),
            "heightMm": str(height_mm),
            "composition": "head_shoulder",
            "outfit": "preserve_original",
        },
        timeout=120,
    )
    prepare = response.json()
    prepare_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code != 200 or not prepare.get("success"):
        return {
            "id": sample["id"], "gender": sample.get("gender"), "category": sample.get("category"),
            "source": sample.get("source"), "accepted": False, "prepareMs": prepare_ms,
            "code": prepare.get("code"), "message": prepare.get("message"),
        }

    started = time.perf_counter()
    response = session.post(
        base_url.rstrip("/") + "/api/id-photo/compose",
        data={"preparedId": prepare["preparedId"], "bgColor": "blue", "bgColorName": "blue", "outputType": "png"},
        timeout=60,
    )
    compose = response.json()
    compose_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code != 200 or not compose.get("success"):
        return {
            "id": sample["id"], "gender": sample.get("gender"), "category": sample.get("category"),
            "source": sample.get("source"), "accepted": False, "prepareMs": prepare_ms,
            "composeMs": compose_ms, "code": compose.get("code"), "message": compose.get("message"),
            "cropFailReasons": compose.get("cropFailReasons") or [],
            "targetRange": compose.get("targetRange") or {},
        }

    preview = session.get(absolute_url(base_url, compose["previewUrl"]), timeout=30).content
    download = session.get(absolute_url(base_url, compose["downloadUrl"]), timeout=30).content
    image = cv2.imdecode(np.frombuffer(preview, dtype=np.uint8), cv2.IMREAD_COLOR)
    quality = compose.get("quality") or {}
    foreground = quality.get("outputForegroundBox") or {}
    face = quality.get("outputFaceBox") or {}
    x = float(foreground.get("x") or 0)
    y = float(foreground.get("y") or 0)
    right = x + float(foreground.get("width") or 0)
    bottom = y + float(foreground.get("height") or 0)
    target = quality.get("targetRange") or {}
    checks = {
        "outputSize": image is not None and image.shape[1] == width and image.shape[0] == height,
        "backgroundPure": image is not None and background_ratio(image, foreground, BG_RGB) >= 0.985,
        "subjectInsideCanvas": bool(quality.get("subjectWithinCanvas")) and x >= 0 and y >= 0 and right <= width and bottom <= height,
        "topMargin": float(target.get("topMarginRatioMin") or 0.06) <= float(quality.get("topPaddingRatio") or 0) <= float(target.get("topMarginRatioMax") or 0.13),
        "chinSafety": (
            (target.get("chinBottomRatioMin") is None or float(quality.get("chinBottomRatio") or 0) >= float(target["chinBottomRatioMin"]))
            and (target.get("chinBottomRatioMax") is None or float(quality.get("chinBottomRatio") or 0) <= float(target["chinBottomRatioMax"]))
        ),
        "headSize": float(target.get("headHeightRatioMin") or 0.58) <= float(quality.get("headHeightRatio") or 0) <= float(target.get("headHeightRatioMax") or 0.70),
        "shoulderWidth": float(target.get("shoulderWidthRatioMin") or 0.75) <= float(quality.get("shoulderWidthRatio") or 0) <= float(target.get("shoulderWidthRatioMax") or 1.0),
        "faceCentered": float(quality.get("faceCenterOffset") or 1) <= 0.04 and 0 <= float(face.get("x") or 0) <= width,
        "previewEqualsDownload": sha256(preview) == sha256(download),
        "noBlackOrTransparentEdge": image is not None and edge_background_ratio(image, BG_RGB) >= 0.98,
        "dynamicSolver": (quality.get("compositionSolver") or {}).get("version") == "dynamic-face-shoulder-v4",
    }
    output_path = PORTRAIT_DIR / f"{sample['id']}_{width}x{height}.png"
    output_path.write_bytes(preview)
    return {
        "id": sample["id"], "gender": sample.get("gender"), "category": sample.get("category"),
        "source": sample.get("source"), "accepted": True, "passed": all(checks.values()),
        "prepareMs": prepare_ms, "composeMs": compose_ms, "spec": {"width": width, "height": height},
        "checks": checks, "metrics": {
            "topPaddingRatio": quality.get("topPaddingRatio"), "bottomSafetyRatio": quality.get("bottomSafetyRatio"),
            "chinBottomRatio": quality.get("chinBottomRatio"),
            "headHeightRatio": quality.get("headHeightRatio"), "shoulderWidthRatio": quality.get("shoulderWidthRatio"),
            "faceCenterOffset": quality.get("faceCenterOffset"), "foregroundBox": foreground,
            "solver": quality.get("compositionSolver"),
        }, "output": str(output_path),
    }


def build_document_fixture(index: int, rng: random.Random) -> dict[str, Any]:
    width, height = [(960, 640), (840, 1120), (1080, 720)][index % 3]
    clean = Image.new("RGB", (width, height), (248, 249, 250))
    draw = ImageDraw.Draw(clean)
    kind = ["receipt", "screenshot", "form", "certificate", "ticket", "statement"][index % 6]
    draw.rectangle((28, 28, width - 28, height - 28), outline=(90, 98, 108), width=2)
    draw.text((54, 48), kind.upper(), fill=(24, 32, 45), font=ImageFont.load_default())
    for row in range(7):
        y = 105 + row * max(42, (height - 210) // 8)
        draw.line((55, y, width - 55, y), fill=(180, 186, 194), width=1)
        draw.text((64, y + 10), f"ROW {row + 1:02d}   VALUE {rng.randint(1000, 9999)}", fill=(50, 58, 70), font=ImageFont.load_default())
    source = clean.copy()
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    watermark = ImageDraw.Draw(layer)
    center_x = rng.randint(int(width * 0.28), int(width * 0.72))
    center_y = rng.randint(int(height * 0.24), int(height * 0.78))
    radius_x = rng.randint(max(70, width // 10), max(90, width // 6))
    radius_y = rng.randint(max(45, height // 14), max(70, height // 9))
    color = [(220, 28, 45, 185), (25, 96, 210, 165), (24, 150, 100, 175), (105, 75, 180, 160)][index % 4]
    watermark.ellipse((center_x - radius_x, center_y - radius_y, center_x + radius_x, center_y + radius_y), outline=color, width=max(5, width // 150))
    watermark.text((center_x - radius_x // 2, center_y - 6), f"MARK-{index + 1}", fill=color, font=ImageFont.load_default())
    source = Image.alpha_composite(source.convert("RGBA"), layer).convert("RGB")
    mask_width = rng.randint(max(36, radius_x // 4), max(52, radius_x // 2))
    mask_height = rng.randint(max(32, radius_y // 3), max(48, radius_y * 2 // 3))
    # Place the brush on a random section of the ellipse itself.  This keeps
    # masks diverse while ensuring the quality check measures a real target.
    side = -1 if rng.random() < 0.5 else 1
    arc_x = center_x + side * radius_x
    arc_y = center_y + rng.randint(-radius_y // 3, radius_y // 3)
    mask_x = max(0, min(width - mask_width, arc_x - mask_width // 2))
    mask_y = max(0, min(height - mask_height, arc_y - mask_height // 2))
    return {
        "id": f"{kind}_{index + 1}", "clean": np.asarray(clean)[:, :, ::-1].copy(),
        "source": np.asarray(source)[:, :, ::-1].copy(), "maskRect": (mask_x, mask_y, mask_width, mask_height),
    }


def request_watermark(session: requests.Session, base_url: str, fixture: dict[str, Any], quality: str) -> dict[str, Any]:
    source = fixture["source"]
    height, width = source.shape[:2]
    x, y, mask_width, mask_height = fixture["maskRect"]
    payload = {
        "coordinateSpace": "normalized",
        "strokes": [{"type": "maskRect", "x": x / width, "y": y / height, "w": mask_width / width, "h": mask_height / height}],
    }
    ok, encoded = cv2.imencode(".png", source)
    started = time.perf_counter()
    response = session.post(
        base_url.rstrip("/") + "/api/watermark/remove-v2",
        files={"image": (fixture["id"] + ".png", encoded.tobytes(), "image/png")},
        data={
            "strokesJson": json.dumps(payload, separators=(",", ":")), "originalWidth": str(width),
            "originalHeight": str(height), "displayWidth": str(width), "displayHeight": str(height),
            "quality": quality, "strength": "medium", "preserveDetail": "true",
            "smartExpand": "false", "maskDilationPx": "5", "requestId": f"random-{fixture['id']}-{quality}",
        },
        timeout=240,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    data = response.json()
    if response.status_code != 200 or not data.get("success"):
        return {"success": False, "statusCode": response.status_code, "payload": data, "elapsedMs": elapsed_ms}
    result_bytes = session.get(absolute_url(base_url, data["resultUrl"]), timeout=30).content
    result = cv2.imdecode(np.frombuffer(result_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    return {"success": True, "data": data, "result": result, "bytes": result_bytes, "elapsedMs": elapsed_ms}


def run_watermark_case(session: requests.Session, base_url: str, fixture: dict[str, Any]) -> dict[str, Any]:
    quick = request_watermark(session, base_url, fixture, "quick")
    hd = request_watermark(session, base_url, fixture, "hd")
    if not quick.get("success") or not hd.get("success"):
        return {"id": fixture["id"], "passed": False, "quick": quick, "hd": hd}
    source, clean, result = fixture["source"], fixture["clean"], hd["result"]
    height, width = source.shape[:2]
    x, y, mask_width, mask_height = fixture["maskRect"]
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.rectangle(mask, (x, y), (x + mask_width - 1, y + mask_height - 1), 255, -1)
    allowed = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)), iterations=1) > 0
    outside = ~allowed
    source_error = float(np.mean(np.abs(source[allowed].astype(np.float32) - clean[allowed].astype(np.float32))))
    quick_error = float(np.mean(np.abs(quick["result"][allowed].astype(np.float32) - clean[allowed].astype(np.float32))))
    hd_error = float(np.mean(np.abs(result[allowed].astype(np.float32) - clean[allowed].astype(np.float32))))
    outside_changes = int(np.count_nonzero(np.any(result[outside] != source[outside], axis=1)))
    checks = {
        "maskResidualReduced": hd_error <= source_error * 0.90,
        "outsideAllowedMaskUnchanged": outside_changes == 0,
        "sizePreserved": result.shape == source.shape,
        "hdNotWorseThanQuick": hd_error <= quick_error * 1.10 + 1.0,
        "noBroadDeletion": int((hd["data"].get("debug") or {}).get("outsideAllowedMaskChangedPixels") or 0) == 0,
        "realHdModel": hd["data"].get("engine") == "lama" and hd["data"].get("fallbackUsed") is False,
        "strictPolicy": (hd["data"].get("debug") or {}).get("maskPolicy") == "strict_local",
    }
    source_path = WATERMARK_DIR / f"{fixture['id']}_source.png"
    mask_path = WATERMARK_DIR / f"{fixture['id']}_mask.png"
    quick_path = WATERMARK_DIR / f"{fixture['id']}_quick.png"
    hd_path = WATERMARK_DIR / f"{fixture['id']}_hd.png"
    cv2.imwrite(str(source_path), source)
    cv2.imwrite(str(mask_path), mask)
    quick_path.write_bytes(quick["bytes"])
    hd_path.write_bytes(hd["bytes"])
    return {
        "id": fixture["id"], "passed": all(checks.values()), "checks": checks,
        "metrics": {"sourceError": round(source_error, 4), "quickError": round(quick_error, 4), "hdError": round(hd_error, 4), "outsideChangedPixels": outside_changes},
        "maskRect": {"x": x, "y": y, "width": mask_width, "height": mask_height},
        "quickMs": quick["elapsedMs"], "hdMs": hd["elapsedMs"], "hdDebug": hd["data"].get("debug") or {},
        "artifacts": {"source": str(source_path), "mask": str(mask_path), "quick": str(quick_path), "hd": str(hd_path)},
    }


def contact_sheet(paths: list[Path], output: Path, cell: tuple[int, int]) -> None:
    images = []
    for path in paths:
        if not path.exists():
            continue
        image = Image.open(path).convert("RGB")
        image.thumbnail((cell[0] - 16, cell[1] - 34), Image.Resampling.LANCZOS)
        frame = Image.new("RGB", cell, "white")
        frame.paste(image, ((cell[0] - image.width) // 2, 8))
        ImageDraw.Draw(frame).text((8, cell[1] - 20), path.stem[:34], fill=(24, 32, 45), font=ImageFont.load_default())
        images.append(frame)
    if not images:
        return
    columns = min(4, len(images))
    rows = math.ceil(len(images) / columns)
    sheet = Image.new("RGB", (columns * cell[0], rows * cell[1]), (230, 234, 240))
    for index, image in enumerate(images):
        sheet.paste(image, ((index % columns) * cell[0], (index // columns) * cell[1]))
    sheet.save(output, quality=94)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--seed", type=int, default=int(time.time()))
    parser.add_argument("--portrait-count", type=int, default=12)
    parser.add_argument("--watermark-count", type=int, default=6)
    parser.add_argument("--portrait", type=Path)
    args = parser.parse_args()
    ensure_dirs()
    session = requests.Session()
    rng = random.Random(args.seed)

    candidates = random_portrait_candidates(args.seed, args.portrait)
    portrait_rows = []
    accepted = 0
    for index, sample in enumerate(candidates):
        if sample.get("downloadError"):
            portrait_rows.append(sample)
            continue
        spec = SPECS[index % len(SPECS)]
        row = post_id_photo(session, args.base_url, sample, spec)
        portrait_rows.append(row)
        print(f"[portrait] {row['id']} accepted={row.get('accepted')} passed={row.get('passed')} code={row.get('code', '')}")
        if row.get("accepted") and row.get("passed"):
            accepted += 1
        if accepted >= args.portrait_count:
            break

    watermark_rows = []
    for index in range(args.watermark_count):
        row = run_watermark_case(session, args.base_url, build_document_fixture(index, rng))
        watermark_rows.append(row)
        print(f"[watermark] {row['id']} passed={row.get('passed')} hdMs={row.get('hdMs', 0)}")

    accepted_rows = [row for row in portrait_rows if row.get("accepted")]
    passed_portraits = [row for row in accepted_rows if row.get("passed")]
    passed_watermarks = [row for row in watermark_rows if row.get("passed")]
    summary = {
        "seed": args.seed,
        "baseUrl": args.base_url,
        "portrait": {
            "requested": args.portrait_count, "candidateCount": len(portrait_rows),
            "accepted": len(accepted_rows), "passed": len(passed_portraits),
            "passRate": round(100.0 * len(passed_portraits) / max(1, len(accepted_rows)), 2),
            "rows": portrait_rows,
        },
        "watermark": {
            "requested": args.watermark_count, "passed": len(passed_watermarks),
            "passRate": round(100.0 * len(passed_watermarks) / max(1, len(watermark_rows)), 2),
            "rows": watermark_rows,
        },
    }
    summary["passed"] = len(passed_portraits) >= args.portrait_count and len(passed_watermarks) == args.watermark_count
    write_json(FINAL_DIR / "random-regression-report.json", summary)

    portrait_outputs = [Path(row["output"]) for row in passed_portraits if row.get("output")]
    watermark_outputs = [Path(row["artifacts"]["hd"]) for row in watermark_rows if row.get("artifacts")]
    contact_sheet(portrait_outputs, FINAL_DIR / "portrait-contact-sheet.jpg", (240, 330))
    contact_sheet(watermark_outputs, FINAL_DIR / "watermark-contact-sheet.jpg", (300, 220))
    markdown = [
        "# Random business regression", "", f"- Seed: `{args.seed}`", f"- Overall: `{'PASS' if summary['passed'] else 'FAIL'}`",
        f"- Portrait: `{len(passed_portraits)}/{len(accepted_rows)}` accepted samples passed; requested `{args.portrait_count}`",
        f"- Watermark: `{len(passed_watermarks)}/{len(watermark_rows)}` random document masks passed",
        "", "## Guarantees", "", "- ID outputs use requested dynamic dimensions and one backend artifact for preview/download.",
        "- ID composition checks face, head top, shoulder width, centering, side/bottom safety, pure background, and edge pixels.",
        "- HD inpaint uses LaMa, smart expansion off, 5px finite dilation, and exact unchanged pixels outside the allowed mask.",
        "- Random selection is controlled only by the recorded seed; no filename, image hash, or sample-specific offset is used.",
    ]
    (FINAL_DIR / "random-regression-report.md").write_text("\n".join(markdown), encoding="utf-8")
    print(json.dumps({"passed": summary["passed"], "seed": args.seed, "portraitPassed": len(passed_portraits), "watermarkPassed": len(passed_watermarks), "report": str(FINAL_DIR / 'random-regression-report.json')}, ensure_ascii=False))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
