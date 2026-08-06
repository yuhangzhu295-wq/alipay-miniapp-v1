"""Run a real FAST-A / photographic MODNet ID-photo matting comparison.

This script is verification-only. It imports the vendored Hivision ONNX models
directly so the candidate can be measured before it is added to production
worker routing.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
HIVISION_ROOT = ROOT / "third_party" / "HivisionIDPhotos"
REPORT_ROOT = ROOT / "reports" / "id-photo-under-10s"
ARTIFACT_ROOT = REPORT_ROOT / "fast-ab-artifacts"

HIVISION_IMPORT_ROOT = HIVISION_ROOT
if platform.system() == "Windows":
    ascii_base = Path(tempfile.gettempdir()) / "idphoto_hivision_worker"
    ascii_root = ascii_base / "HivisionIDPhotos"
    ascii_base.mkdir(parents=True, exist_ok=True)
    if not ascii_root.exists():
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(ascii_root), str(HIVISION_ROOT)],
            cwd=str(ascii_base),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
            check=False,
        )
    if ascii_root.exists():
        HIVISION_IMPORT_ROOT = ascii_root

for module_root in (str(SERVER), str(HIVISION_IMPORT_ROOT)):
    if module_root not in sys.path:
        sys.path.insert(0, module_root)

os.environ["RUN_MODE"] = "beast"

from hivision.creator import human_matting as hm  # noqa: E402
from id_photo_engine_legacy.portrait_matting import _finalize_matting_rgba  # noqa: E402
from services.face_detector import detect_face  # noqa: E402


MODELS = {
    "FAST-A": {
        "name": "hivision_modnet",
        "session": "HIVISION_MODNET_SESS",
    },
    "FAST-B": {
        "name": "modnet_photographic_portrait_matting",
        "session": "MODNET_PHOTOGRAPHIC_PORTRAIT_MATTING_SESS",
    },
}

DEFAULT_SOURCES = [
    Path(r"C:\Users\zyu33\Desktop\6a83d1e010f6e9ed8c35af94f0c33936.jpg"),
    Path(r"C:\Users\zyu33\Desktop\610a7b3fadac6b4452736f72b8f3a492.jpg"),
    Path(r"C:\Users\zyu33\Desktop\217139c99959fa2888673f2100612b8f.jpg"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 3)


def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(max(1, denominator)), 6)


def face_values(face_box: dict[str, Any]) -> tuple[float, float, float, float, float]:
    x = float(face_box.get("x") or 0)
    y = float(face_box.get("y") or 0)
    width = max(1.0, float(face_box.get("width") or 1))
    height = max(1.0, float(face_box.get("height") or 1))
    return x, y, width, height, x + width / 2.0


def bounded_box(box: tuple[float, float, float, float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    left, top, right, bottom = box
    left = max(0, min(width - 1, int(round(left))))
    top = max(0, min(height - 1, int(round(top))))
    right = max(left + 1, min(width, int(round(right))))
    bottom = max(top + 1, min(height, int(round(bottom))))
    return left, top, right, bottom


def checkerboard(size: tuple[int, int], cell: int = 24) -> Image.Image:
    board = Image.new("RGBA", size, (242, 242, 242, 255))
    draw = ImageDraw.Draw(board)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(196, 202, 210, 255))
    return board


def composite(foreground: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    background = Image.new("RGBA", foreground.size, (*color, 255))
    background.alpha_composite(foreground)
    return background.convert("RGB")


def save_zoom(source: Image.Image, target: Path, box: tuple[float, float, float, float]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    crop = source.crop(bounded_box(box, source.size))
    crop.thumbnail((960, 720), Image.Resampling.LANCZOS)
    crop.save(target, format="PNG", optimize=True)


def save_artifacts(
    source: Image.Image,
    foreground: Image.Image,
    face_box: dict[str, Any],
    target: Path,
) -> dict[str, str]:
    target.mkdir(parents=True, exist_ok=True)
    source_path = target / "source.jpg"
    alpha_path = target / "alpha.png"
    foreground_path = target / "foreground.png"
    checker_path = target / "checkerboard.png"
    blue_path = target / "blue.jpg"
    white_path = target / "white.jpg"

    source.convert("RGB").save(source_path, format="JPEG", quality=95)
    foreground.getchannel("A").save(alpha_path, format="PNG", optimize=True)
    foreground.save(foreground_path, format="PNG", optimize=True)
    board = checkerboard(foreground.size)
    board.alpha_composite(foreground)
    checker_rgb = board.convert("RGB")
    checker_rgb.save(checker_path, format="PNG", optimize=True)
    composite(foreground, (67, 142, 219)).save(blue_path, format="JPEG", quality=94)
    composite(foreground, (255, 255, 255)).save(white_path, format="JPEG", quality=94)

    fx, fy, fw, fh, cx = face_values(face_box)
    zooms = {
        "hair-zoom.png": (fx - fw * 0.50, fy - fh * 0.90, fx + fw * 1.50, fy + fh * 0.35),
        "ear-zoom.png": (fx - fw * 0.72, fy, fx + fw * 1.72, fy + fh * 1.05),
        "shoulder-zoom.png": (cx - fw * 2.55, fy + fh * 0.85, cx + fw * 2.55, fy + fh * 2.45),
        "clothing-zoom.png": (cx - fw * 2.20, fy + fh * 1.55, cx + fw * 2.20, fy + fh * 3.65),
    }
    for name, box in zooms.items():
        save_zoom(checker_rgb, target / name, box)

    return {
        "source": str(source_path),
        "alpha": str(alpha_path),
        "foreground": str(foreground_path),
        "checkerboard": str(checker_path),
        "blue": str(blue_path),
        "white": str(white_path),
        "hairZoom": str(target / "hair-zoom.png"),
        "earZoom": str(target / "ear-zoom.png"),
        "shoulderZoom": str(target / "shoulder-zoom.png"),
        "clothingZoom": str(target / "clothing-zoom.png"),
    }


def internal_hole_ratio(binary: np.ndarray) -> float:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary.astype("uint8"), 8)
    if count <= 1:
        return 0.0
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    main = np.where(labels == largest, 255, 0).astype("uint8")
    padded = cv2.copyMakeBorder(main, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    flooded = padded.copy()
    flood_mask = np.zeros((padded.shape[0] + 2, padded.shape[1] + 2), np.uint8)
    cv2.floodFill(flooded, flood_mask, (0, 0), 255)
    holes = cv2.bitwise_not(flooded)[1:-1, 1:-1] > 0
    return safe_ratio(np.count_nonzero(holes), stats[largest, cv2.CC_STAT_AREA])


def zone_missing_ratio(binary: np.ndarray, zone: np.ndarray) -> float:
    return safe_ratio(np.count_nonzero(zone & (binary == 0)), np.count_nonzero(zone))


def alpha_quality_metrics(alpha: Image.Image, face_box: dict[str, Any], quality: dict[str, Any]) -> dict[str, float]:
    array = np.asarray(alpha.convert("L"))
    binary = array > 12
    height, width = binary.shape
    yy, xx = np.indices((height, width))
    fx, fy, fw, fh, cx = face_values(face_box)

    hair_core = (
        (yy >= max(0.0, fy - fh * 0.56))
        & (yy <= fy + fh * 0.16)
        & (xx >= fx + fw * 0.12)
        & (xx <= fx + fw * 0.88)
    )
    left_shoulder = (
        (yy >= fy + fh * 1.15)
        & (yy <= min(height - 1, fy + fh * 2.45))
        & (xx >= cx - fw * 1.55)
        & (xx <= cx - fw * 0.52)
    )
    right_shoulder = (
        (yy >= fy + fh * 1.15)
        & (yy <= min(height - 1, fy + fh * 2.45))
        & (xx >= cx + fw * 0.52)
        & (xx <= cx + fw * 1.55)
    )

    transition = (array > 8) & (array < 248)
    foreground_pixels = np.count_nonzero(array > 8)
    contours, _ = cv2.findContours(binary.astype("uint8"), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if contours:
        main_contour = max(contours, key=cv2.contourArea)
        contour_area = max(1.0, cv2.contourArea(main_contour))
        contour_perimeter = cv2.arcLength(main_contour, True)
        boundary_complexity = float(contour_perimeter * contour_perimeter / (4.0 * np.pi * contour_area))
    else:
        boundary_complexity = 99.0
    row_runs = []
    for row in binary.astype("uint8"):
        transitions = np.diff(np.pad(row, (1, 1)))
        row_runs.append(int(np.count_nonzero(transitions == 1)))
    fragmented_row_ratio = safe_ratio(sum(runs > 2 for runs in row_runs), len(row_runs))
    shoulder_missing = max(
        zone_missing_ratio(binary, left_shoulder),
        zone_missing_ratio(binary, right_shoulder),
    )
    background_leak = float(quality.get("backgroundLeakRatio") or 0.0)
    retained_background = max(
        float(quality.get("remainingBackgroundSheetRatio") or 0.0),
        float(quality.get("remainingHeadSideBackgroundRatio") or 0.0),
    )
    structural_old_bg_risk = max(0.0, (boundary_complexity - 1.65) / 8.0)
    foreground_old_bg = max(retained_background, structural_old_bg_risk, fragmented_row_ratio)
    return {
        "backgroundLeakRatio": round(background_leak, 6),
        "subjectHoleRatio": internal_hole_ratio(binary),
        "shoulderCutoffRatio": round(shoulder_missing, 6),
        "hairCutoffRatio": zone_missing_ratio(binary, hair_core),
        "edgeHaloRatio": safe_ratio(np.count_nonzero(transition), foreground_pixels),
        "foregroundOldBgRatio": round(foreground_old_bg, 6),
        "boundaryComplexity": round(boundary_complexity, 6),
        "fragmentedRowRatio": fragmented_row_ratio,
    }


def quality_score(metrics: dict[str, float]) -> float:
    risk = (
        metrics["backgroundLeakRatio"] * 1.8
        + metrics["subjectHoleRatio"] * 5.0
        + metrics["shoulderCutoffRatio"] * 0.6
        + metrics["hairCutoffRatio"] * 1.2
        + metrics["edgeHaloRatio"] * 0.2
        + metrics["foregroundOldBgRatio"] * 3.0
    )
    return round(100.0 / (1.0 + risk * 4.0), 3)


def prepare_source(path: Path) -> tuple[Image.Image, float]:
    started = time.perf_counter()
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGBA")
        image.load()
    return image, elapsed_ms(started)


def resize_working_image(image: Image.Image, max_side: int) -> tuple[np.ndarray, dict[str, Any], float]:
    started = time.perf_counter()
    original_size = image.size
    working = image.convert("RGB")
    if max(original_size) > max_side:
        scale = max_side / float(max(original_size))
        working = working.resize(
            (max(1, round(original_size[0] * scale)), max(1, round(original_size[1] * scale))),
            Image.Resampling.LANCZOS,
        )
    rgb = np.asarray(working)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return bgr, {
        "original": f"{original_size[0]}x{original_size[1]}",
        "working": f"{working.size[0]}x{working.size[1]}",
        "onnx": "512x512",
    }, elapsed_ms(started)


def ensure_session(model: str, session_name: str) -> tuple[Any, float, bool]:
    existing = getattr(hm, session_name, None)
    if existing is not None:
        return existing, 0.0, True
    started = time.perf_counter()
    session = hm.load_onnx_model(hm.WEIGHTS[model], set_cpu=True)
    setattr(hm, session_name, session)
    return session, elapsed_ms(started), False


def infer_model(
    source: Image.Image,
    model_key: str,
    face_box: dict[str, Any],
    max_side: int,
) -> tuple[Image.Image, dict[str, Any]]:
    config = MODELS[model_key]
    model = config["name"]
    total_started = time.perf_counter()

    bgr, input_size, worker_resize_ms = resize_working_image(source, max_side)
    session, model_load_ms, reused = ensure_session(model, config["session"])

    resize_started = time.perf_counter()
    tensor, work_width, work_height = hm.read_modnet_image(bgr, ref_size=512)
    normalize_resize_ms = elapsed_ms(resize_started)

    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    inference_started = time.perf_counter()
    output = session.run([output_name], {input_name: tensor})
    inference_ms = elapsed_ms(inference_started)

    postprocess_started = time.perf_counter()
    matte = np.squeeze((output[0] * 255).astype("uint8"))
    alpha = cv2.resize(matte, (work_width, work_height), interpolation=cv2.INTER_AREA)
    bgra = np.dstack((bgr, alpha))
    original_size = source.size
    if (work_width, work_height) != original_size:
        rgb = cv2.resize(bgra[:, :, :3], original_size, interpolation=cv2.INTER_LANCZOS4)
        alpha = cv2.resize(bgra[:, :, 3], original_size, interpolation=cv2.INTER_LINEAR)
        bgra = np.dstack((rgb, alpha))
    rgba_array = cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGBA)
    raw_foreground = Image.fromarray(rgba_array, mode="RGBA")
    raw_postprocess_ms = elapsed_ms(postprocess_started)

    quality_started = time.perf_counter()
    finalized = _finalize_matting_rgba(
        raw_foreground.copy(),
        face_box,
        source,
        "hivision",
        model,
        "hivision_human_matting",
        extra_debug={"trustedAlpha": True, "verificationDirectOnnx": True},
    )
    if finalized.get("success"):
        foreground = Image.open(finalized["foregroundPath"]).convert("RGBA")
        foreground.load()
    else:
        foreground = raw_foreground
    quality = dict(finalized.get("quality") or {})
    metrics = alpha_quality_metrics(foreground.getchannel("A"), face_box, quality)
    quality_gate_ms = elapsed_ms(quality_started)

    for key in ("foregroundPath", "maskPath"):
        temporary = finalized.get(key)
        if temporary:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass

    timings = {
        "decodeMs": 0.0,
        "resizeMs": round(worker_resize_ms + normalize_resize_ms, 3),
        "inferenceMs": inference_ms,
        "postprocessMs": raw_postprocess_ms,
        "qualityGateMs": quality_gate_ms,
        "modelLoadMs": model_load_ms,
        "totalMs": elapsed_ms(total_started),
    }
    return foreground, {
        "modelKey": model_key,
        "modelName": model,
        "modelPath": str((HIVISION_ROOT / "hivision" / "creator" / "weights" / f"{model}.onnx").resolve()),
        "modelLoaded": Path(hm.WEIGHTS[model]).is_file(),
        "sessionReused": reused,
        "inputSize": input_size,
        **timings,
        **metrics,
        "qualityScore": quality_score(metrics),
        "mattingPassed": bool(finalized.get("success")),
        "mattingFailReasons": quality.get("mattingFailReasons") or [],
    }


def compare_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        pairs.setdefault(row["sample"], {})[row["modelKey"]] = row

    comparisons = []
    b_better = 0
    a_better = 0
    for sample, pair in pairs.items():
        a = pair["FAST-A"]
        b = pair["FAST-B"]
        delta = round(float(b["qualityScore"]) - float(a["qualityScore"]), 3)
        winner = "FAST-B" if delta > 1.0 else ("FAST-A" if delta < -1.0 else "TIE")
        if winner == "FAST-B":
            b_better += 1
        elif winner == "FAST-A":
            a_better += 1
        comparisons.append({"sample": sample, "winner": winner, "fastBMinusFastA": delta})

    a_rows = [row for row in rows if row["modelKey"] == "FAST-A"]
    b_rows = [row for row in rows if row["modelKey"] == "FAST-B"]
    a_mean = round(sum(float(row["qualityScore"]) for row in a_rows) / max(1, len(a_rows)), 3)
    b_mean = round(sum(float(row["qualityScore"]) for row in b_rows) / max(1, len(b_rows)), 3)
    return {
        "comparisons": comparisons,
        "fastABetterCount": a_better,
        "fastBBetterCount": b_better,
        "tieCount": len(comparisons) - a_better - b_better,
        "fastAMeanQualityScore": a_mean,
        "fastBMeanQualityScore": b_mean,
        "candidateEligibleByAutomatedMetrics": b_better >= 2 and b_mean >= a_mean,
        "visualReviewRequired": True,
    }


def write_report(payload: dict[str, Any]) -> None:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (REPORT_ROOT / "fast-ab.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# FAST-A / FAST-B verification",
        "",
        f"- Generated: `{payload['generatedAt']}`",
        f"- Status: `{payload['status']}`",
        "- FAST-A: `hivision_modnet`",
        "- FAST-B: `modnet_photographic_portrait_matting`",
        f"- Shared pre-resize maximum side: `{payload['maxSide']}`",
        "- OpenVINO: skipped; this comparison uses ONNX Runtime CPUExecutionProvider.",
        "- Automated metrics are evidence, not the final routing decision; paired visual review is mandatory.",
        "",
        "| sample | model | reused | inference ms | total ms | leak | holes | shoulder cutoff | hair cutoff | edge transition | old-bg risk | score |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["rows"]:
        if row.get("modelKey") not in MODELS:
            lines.append(
                f"| {row.get('sample', 'unknown')} | FACE-DETECT | - | - | - | - | - | - | - | - | - | - |"
            )
            continue
        lines.append(
            f"| {row['sample']} | {row['modelKey']} | {row['sessionReused']} | "
            f"{row['inferenceMs']:.3f} | {row['totalMs']:.3f} | {row['backgroundLeakRatio']:.6f} | "
            f"{row['subjectHoleRatio']:.6f} | {row['shoulderCutoffRatio']:.6f} | "
            f"{row['hairCutoffRatio']:.6f} | {row['edgeHaloRatio']:.6f} | "
            f"{row['foregroundOldBgRatio']:.6f} | {row['qualityScore']:.3f} |"
        )
    summary = payload["summary"]
    lines.extend([
        "",
        "## Automated comparison",
        "",
        f"- FAST-A mean quality score: `{summary['fastAMeanQualityScore']}`",
        f"- FAST-B mean quality score: `{summary['fastBMeanQualityScore']}`",
        f"- Pair wins: FAST-A `{summary['fastABetterCount']}`, FAST-B `{summary['fastBBetterCount']}`, tie `{summary['tieCount']}`.",
        f"- FAST-B eligible by automated metrics: `{summary['candidateEligibleByAutomatedMetrics']}`.",
        "- Final decision: pending paired visual inspection of hair, ears, shoulders, clothing, and retained source background.",
        "",
        "## Metric definitions",
        "",
        "- `backgroundLeakRatio`: foreground outside the face-driven valid subject prior.",
        "- `subjectHoleRatio`: enclosed transparent holes inside the largest foreground component.",
        "- `shoulderCutoffRatio`: missing alpha in symmetric shoulder zones derived from the detected face.",
        "- `hairCutoffRatio`: missing alpha in the central crown zone derived from the detected face.",
        "- `edgeHaloRatio`: partially transparent pixels divided by nontransparent foreground pixels.",
        "- `foregroundOldBgRatio`: maximum of retained-background, contour-complexity, and fragmented-row risk signals.",
        "- `boundaryComplexity`: contour compactness; thin attached background structures increase it.",
        "- `fragmentedRowRatio`: rows containing more than two disjoint foreground runs.",
    ])
    (REPORT_ROOT / "fast-ab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--max-side", type=int, default=768)
    args = parser.parse_args()

    sources = [Path(item) for item in args.source] if args.source else DEFAULT_SOURCES
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        print(json.dumps({"status": "FAIL", "missing": missing}, ensure_ascii=False))
        return 2

    rows: list[dict[str, Any]] = []
    for source_path in sources:
        source, decode_ms = prepare_source(source_path)
        canonical_dir = ARTIFACT_ROOT / source_path.stem
        canonical_dir.mkdir(parents=True, exist_ok=True)
        canonical_source = canonical_dir / "canonical-source.jpg"
        source.convert("RGB").save(canonical_source, format="JPEG", quality=95)
        face = detect_face(canonical_source)
        if not face.get("success"):
            rows.append({
                "sample": source_path.name,
                "status": "FAIL",
                "reason": "face detection failed",
                "face": face,
            })
            continue
        face_box = face.get("faceBox") or {}
        for model_key in MODELS:
            foreground, metrics = infer_model(source, model_key, face_box, args.max_side)
            metrics["decodeMs"] = decode_ms
            metrics["totalMs"] = round(float(metrics["totalMs"]) + decode_ms, 3)
            target = canonical_dir / metrics["modelName"]
            artifacts = save_artifacts(source, foreground, face_box, target)
            rows.append({
                "sample": source_path.name,
                "sourcePath": str(source_path),
                "status": "PASS" if metrics["mattingPassed"] else "FAIL",
                "faceBox": face_box,
                **metrics,
                "artifacts": artifacts,
            })

    complete_rows = [row for row in rows if row.get("modelKey") in MODELS]
    complete = len(complete_rows) == len(sources) * len(MODELS)
    summary = compare_rows(complete_rows) if complete else {
        "comparisons": [],
        "fastABetterCount": 0,
        "fastBBetterCount": 0,
        "tieCount": 0,
        "fastAMeanQualityScore": 0,
        "fastBMeanQualityScore": 0,
        "candidateEligibleByAutomatedMetrics": False,
        "visualReviewRequired": True,
    }
    payload = {
        "status": "PASS" if complete and all(row.get("status") == "PASS" for row in complete_rows) else "FAIL",
        "generatedAt": now_iso(),
        "maxSide": args.max_side,
        "provider": "CPUExecutionProvider",
        "executionNotes": [
            "The first Windows run with the vendored virtual environment could not load the OpenCV face cascade through the Unicode project path.",
            "The completed run uses the system Python runtime, which has the same ONNX Runtime and OpenCV versions plus the production MediaPipe detector.",
        ],
        "rows": rows,
        "summary": summary,
    }
    write_report(payload)
    print(json.dumps({
        "status": payload["status"],
        "rows": len(rows),
        "summary": summary,
        "report": str(REPORT_ROOT / "fast-ab.json"),
    }, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
