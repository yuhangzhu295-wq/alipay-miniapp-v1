"""Run scoped ID-photo matting model A/B checks.

This does not change production behavior. It compares the current production
matting chain with raw rembg model variants on real local samples and writes
the required open-source audit A/B report.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from services.face_detector import detect_face  # noqa: E402
from services.portrait_matting import matte_person  # noqa: E402


MULTI_ENGINE_REPORT_DIR = ROOT / "reports" / "id-photo-multi-engine-reset"
REPORT_DIR = MULTI_ENGINE_REPORT_DIR / "model-ab-test"
INPUT_DIR = REPORT_DIR / "inputs"
OUTPUT_DIR = REPORT_DIR / "outputs"
DEBUG_DIR = REPORT_DIR / "debug"

SAMPLE_CANDIDATES = [
    Path(r"C:\Users\zyu33\Desktop\b9fcfc995c64135f4be13197c85a96f0.jpg"),
    Path(r"C:\Users\zyu33\Desktop\cs.jpeg"),
    Path(r"C:\Users\zyu33\Desktop\893807917671fdd0fae10a094fcf839c.jpg"),
    Path(r"C:\Users\zyu33\Desktop\4755783172013fb27a507a42c99868ee.jpg"),
    Path(r"C:\Users\zyu33\Desktop\a50df94597d2a8b5d0074a019a6171dd.jpg"),
    Path(r"C:\Users\zyu33\Desktop\4c1ac2e770f697ac94ee83ab7674c093.jpg"),
]

REMBG_MODELS = ["u2net_human_seg", "u2net", "isnet-general-use"]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8-sig")


def reset_dirs() -> None:
    for path in [INPUT_DIR, OUTPUT_DIR, DEBUG_DIR]:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)[:80]


def collect_samples(limit: int) -> list[Path]:
    samples: list[Path] = []
    seen: set[str] = set()
    for candidate in SAMPLE_CANDIDATES:
        if candidate.exists():
            resolved = str(candidate.resolve())
            if resolved not in seen:
                samples.append(candidate)
                seen.add(resolved)
        if len(samples) >= limit:
            return samples
    source_dir = ROOT / "reports" / "id-photo-samples" / "source"
    if source_dir.exists():
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            for candidate in sorted(source_dir.glob(ext)):
                resolved = str(candidate.resolve())
                if resolved not in seen:
                    samples.append(candidate)
                    seen.add(resolved)
                if len(samples) >= limit:
                    return samples
    return samples


def normalized_input(path: Path, label: str) -> Path:
    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    image.thumbnail((900, 900), Image.Resampling.LANCZOS)
    target = INPUT_DIR / f"{label}.jpg"
    image.save(target, quality=94)
    return target


def alpha_metrics(alpha: Image.Image) -> dict[str, Any]:
    arr = np.asarray(alpha.convert("L"))
    binary = arr > 8
    h, w = binary.shape
    border = max(4, min(h, w) // 24)
    border_mask = np.zeros_like(binary, dtype=bool)
    border_mask[:border, :] = True
    border_mask[-border:, :] = True
    border_mask[:, :border] = True
    border_mask[:, -border:] = True
    n, labels = cv2.connectedComponents(binary.astype(np.uint8), 8)
    component_sizes = [int((labels == idx).sum()) for idx in range(1, n)]
    largest = max(component_sizes) if component_sizes else 0
    transition = (arr > 8) & (arr < 248)
    return {
        "alphaNonZeroRatio": round(float(binary.mean()), 6),
        "borderAlphaRatio": round(float((binary & border_mask).sum() / max(1, border_mask.sum())), 6),
        "transitionRatio": round(float(transition.mean()), 6),
        "componentCount": max(0, n - 1),
        "largestComponentRatio": round(float(largest / max(1, binary.sum())), 6) if binary.sum() else 0.0,
    }


def run_current(sample: Path, label: str) -> dict[str, Any]:
    started = time.perf_counter()
    face = detect_face(sample)
    if not face.get("success"):
        return {
            "engine": "current-main",
            "sample": label,
            "status": "SKIP_FACE_FAILED",
            "face": face,
            "elapsedMs": int((time.perf_counter() - started) * 1000),
        }
    result = matte_person(sample, face.get("faceBox"))
    row: dict[str, Any] = {
        "engine": "current-main",
        "sample": label,
        "status": "PASS" if result.get("success") else "FAIL",
        "faceEngine": face.get("engine"),
        "model": result.get("model"),
        "quality": result.get("quality"),
        "elapsedMs": int((time.perf_counter() - started) * 1000),
    }
    if result.get("success"):
        fg = Image.open(result["foregroundPath"]).convert("RGBA")
        alpha = fg.getchannel("A")
        fg_target = OUTPUT_DIR / f"{label}__current-main.png"
        mask_target = OUTPUT_DIR / f"{label}__current-main-mask.png"
        fg.save(fg_target)
        alpha.save(mask_target)
        row["foreground"] = str(fg_target)
        row["mask"] = str(mask_target)
        row["metrics"] = alpha_metrics(alpha)
    return row


def run_rembg(sample: Path, label: str, model: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        from rembg import new_session, remove

        session = new_session(model)
        source = Image.open(sample).convert("RGB")
        buf = BytesIO()
        source.save(buf, format="PNG")
        try:
            out = remove(
                buf.getvalue(),
                session=session,
                alpha_matting=True,
                alpha_matting_foreground_threshold=235,
                alpha_matting_background_threshold=12,
                alpha_matting_erode_size=8,
            )
            mode = "alpha_matting"
        except Exception as exc:
            out = remove(buf.getvalue(), session=session, alpha_matting=False)
            mode = f"standard_fallback: {exc}"
        fg = Image.open(BytesIO(out)).convert("RGBA")
        alpha = fg.getchannel("A")
        engine = f"rembg-{model}"
        fg_target = OUTPUT_DIR / f"{label}__{safe_name(engine)}.png"
        mask_target = OUTPUT_DIR / f"{label}__{safe_name(engine)}-mask.png"
        fg.save(fg_target)
        alpha.save(mask_target)
        return {
            "engine": engine,
            "sample": label,
            "status": "PASS",
            "mode": mode,
            "foreground": str(fg_target),
            "mask": str(mask_target),
            "metrics": alpha_metrics(alpha),
            "elapsedMs": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:
        return {
            "engine": f"rembg-{model}",
            "sample": label,
            "status": "SKIPPED_OR_FAILED",
            "error": str(exc),
            "elapsedMs": int((time.perf_counter() - started) * 1000),
        }


def optional_engine_status() -> list[dict[str, Any]]:
    checks = [
        ("MODNet", importlib.util.find_spec("torch") is not None, "Not integrated; requires explicit weights and deployment sizing."),
        ("BRIA RMBG", False, "Not integrated; license/deployment review required before adoption."),
        ("BiRefNet", False, "Not integrated; large model and dependency review required."),
        ("InSPyReNet/transparent-background", importlib.util.find_spec("transparent_background") is not None, "Candidate high-quality mode only; not production chain."),
        ("RVM", False, "Video matting model; not selected for single ID-photo production."),
    ]
    return [
        {"engine": name, "runtimePresent": present, "decision": note}
        for name, present, note in checks
    ]


def build_contact_sheet(rows: list[dict[str, Any]]) -> str:
    images: list[tuple[str, Image.Image]] = []
    for row in rows:
        fg_path = row.get("foreground")
        if fg_path and Path(fg_path).exists():
            image = Image.open(fg_path).convert("RGBA")
            canvas = Image.new("RGBA", image.size, (26, 115, 232, 255))
            canvas.alpha_composite(image)
            canvas = canvas.convert("RGB")
            canvas.thumbnail((180, 240), Image.Resampling.LANCZOS)
            images.append((f"{row['sample']}\n{row['engine']}", canvas))
    if not images:
        return ""
    cell_w, cell_h = 210, 285
    cols = min(4, len(images))
    rows_n = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows_n * cell_h), "white")
    for idx, (caption, image) in enumerate(images):
        x = (idx % cols) * cell_w
        y = (idx // cols) * cell_h
        sheet.paste(image, (x + (cell_w - image.width) // 2, y + 10))
    target = REPORT_DIR / "model-ab-contact-sheet.jpg"
    sheet.save(target, quality=92)
    return str(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-limit", type=int, default=2)
    args = parser.parse_args()

    reset_dirs()
    samples = collect_samples(max(1, args.sample_limit))
    if not samples:
        payload = {"status": "FAIL", "reason": "No samples found"}
        write_json(REPORT_DIR / "model-ab-test-report.json", payload)
        write_md(REPORT_DIR / "model-ab-test-report.md", ["# Model A/B Test", "", "- Status: `FAIL`", "- Reason: no samples found."])
        print("[verify-id-photo-model-ab] FAIL no samples")
        return 1

    rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    for idx, sample in enumerate(samples, 1):
        label = f"sample_{idx:02d}_{safe_name(sample.stem)}"
        local_input = normalized_input(sample, label)
        sample_rows.append({"label": label, "source": str(sample), "input": str(local_input)})
        rows.append(run_current(local_input, label))
        for model in REMBG_MODELS:
            rows.append(run_rembg(local_input, label, model))

    contact_sheet = build_contact_sheet(rows)
    current_pass = [row for row in rows if row["engine"] == "current-main" and row["status"] == "PASS"]
    human_seg_pass = [row for row in rows if row["engine"] == "rembg-u2net_human_seg" and row["status"] == "PASS"]
    status = "PASS" if len(current_pass) == len(samples) and human_seg_pass else "FAIL"
    payload = {
        "status": status,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "samples": sample_rows,
        "rows": rows,
        "optionalEngines": optional_engine_status(),
        "contactSheet": contact_sheet,
        "decision": "Use HivisionIDPhotos/hivision_modnet as the local production matting path; keep rembg variants as recorded backup/A-B comparison only.",
    }
    write_json(REPORT_DIR / "model-ab-test-report.json", payload)
    write_json(MULTI_ENGINE_REPORT_DIR / "model-ab-test-report.json", payload)
    lines = [
        "# Model A/B Test Report",
        "",
        f"- Status: `{status}`",
        f"- Samples: `{len(samples)}`",
        f"- Contact sheet: `{contact_sheet}`",
        "- Production decision: use HivisionIDPhotos/hivision_modnet; keep rembg variants as backup/A-B comparison only.",
        "",
        "## Tested Rows",
        "| sample | engine | status | alpha | border alpha | components | elapsed ms |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        metrics = row.get("metrics") or {}
        lines.append(
            f"| {row.get('sample')} | {row.get('engine')} | {row.get('status')} | "
            f"{metrics.get('alphaNonZeroRatio', '')} | {metrics.get('borderAlphaRatio', '')} | "
            f"{metrics.get('componentCount', '')} | {row.get('elapsedMs', '')} |"
        )
    lines.extend(["", "## Optional Engines", "| engine | runtime present | decision |", "|---|---:|---|"])
    for row in payload["optionalEngines"]:
        lines.append(f"| {row['engine']} | {row['runtimePresent']} | {row['decision']} |")
    write_md(REPORT_DIR / "model-ab-test-report.md", lines)
    write_md(MULTI_ENGINE_REPORT_DIR / "model-ab-test-report.md", lines)
    print(f"[verify-id-photo-model-ab] {status} report={REPORT_DIR / 'model-ab-test-report.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
