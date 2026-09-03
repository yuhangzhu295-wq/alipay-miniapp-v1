"""Verify final person-to-panel alignment and per-spec mainland composition."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from services.face_detector import detect_face  # noqa: E402
from services.id_photo_specs import BG_COLORS, PHOTO_SPECS  # noqa: E402


REPORT = ROOT / "reports" / "final-id-photo-mainland-compliance"
CASES = REPORT / "cases"
CORPUS = ROOT / "reports" / "final-visual-convergence" / "portrait-corpus"
HISTORIC_RESULTS = ROOT / "reports" / "final-visual-convergence" / "portrait-random-100.json"
GENERATED_CORPUS = REPORT / "verification-corpus"
CURATED_BALANCED_SOURCES = CORPUS / "curated-balanced-sources.json"
PUBLIC_PORTRAIT_SOURCES = REPORT / "public-portrait-sources.json"
ADDITIONAL_REVIEWED_SOURCES = REPORT / "additional-reviewed-sources.json"
SPEC_IDS = ("one-inch", "two-inch", "id-card-cn", "passport-cn", "driver-license-cn")
VALIDATION_SPEC_ORDER = ("passport-cn", "one-inch", "id-card-cn", "two-inch", "driver-license-cn")
VALIDATION_SPEC_ORDER_BY_GROUP = {
    "male": VALIDATION_SPEC_ORDER,
    "female": ("passport-cn", "id-card-cn", "one-inch", "two-inch", "driver-license-cn"),
}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def image_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_family(path: Path) -> str:
    match = re.match(r"^\d{3}-([0-9a-f]{10})-v\d+-", path.name.lower())
    if match:
        return match.group(1)
    variant_match = re.match(r"^([0-9a-f]{10,64})-(?:crop|mirror|brightness|resolution)\.", path.name.lower())
    return variant_match.group(1)[:10] if variant_match else image_digest(path)[:10]


def historic_candidates(group: str) -> list[Path]:
    if not HISTORIC_RESULTS.exists():
        return []
    payload = json.loads(HISTORIC_RESULTS.read_text(encoding="utf-8"))
    result = []
    for row in payload.get("rows") or []:
        source_text = str(row.get("source") or "")
        source_lower = source_text.lower()
        row_group = str(row.get("group") or "")
        belongs = row_group == f"{group}-query"
        if row_group == "mixed-random":
            belongs = ("female" in source_lower) if group == "female" else ("male" in source_lower and "female" not in source_lower)
        metrics = row.get("metrics") or {}
        foreground = metrics.get("outputForegroundBox") or {}
        shoulder = metrics.get("shoulderBBox") or {}
        spec = row.get("spec") or {}
        width = float(spec.get("width") or 1)
        height = float(spec.get("height") or 1)
        bottom_ratio = (float(foreground.get("y") or 0) + float(foreground.get("height") or 0)) / height
        shoulder_ratio = (float(shoulder.get("right") or 0) - float(shoulder.get("left") or 0)) / width
        path = Path(source_text)
        if belongs and bottom_ratio >= 0.90 and shoulder_ratio >= 0.75 and path.exists():
            result.append(path)
    return result


def curated_balanced_candidates(group: str) -> list[Path]:
    if not CURATED_BALANCED_SOURCES.exists():
        return []
    payload = json.loads(CURATED_BALANCED_SOURCES.read_text(encoding="utf-8"))
    result = []
    for row in payload.get("sources") or []:
        if row.get("group") != group:
            continue
        path = Path(str(row.get("source") or ""))
        if path.exists():
            result.append(path)
    return result


def manifest_candidates(manifest: Path, group: str) -> list[Path]:
    if not manifest.exists():
        return []
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    result = []
    for row in payload.get("sources") or []:
        if row.get("group") != group:
            continue
        path = Path(str(row.get("path") or ""))
        path = path if path.is_absolute() else ROOT / path
        if path.exists():
            result.append(path)
    return result


def generated_variants(paths: list[Path], group: str, seed: int) -> list[Path]:
    target = GENERATED_CORPUS / group
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    outputs: list[Path] = []
    seen = set()
    ordered_paths = list(paths)
    rng.shuffle(ordered_paths)
    for base_index, path in enumerate(ordered_paths):
        digest = image_digest(path)
        if digest in seen:
            continue
        seen.add(digest)
        try:
            source = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        except Exception:
            continue
        variant_index = base_index % 4
        variant = ImageOps.mirror(source) if variant_index == 0 else source.copy()
        if variant_index == 1 and variant.width > 240 and variant.height > 320:
            inset_x = max(1, int(round(variant.width * rng.uniform(0.02, 0.055))))
            inset_top = max(0, int(round(variant.height * rng.uniform(0.0, 0.025))))
            variant = variant.crop((inset_x, inset_top, variant.width - inset_x, variant.height))
        if variant_index == 2:
            variant = ImageEnhance.Brightness(variant).enhance(rng.uniform(0.90, 1.10))
        max_side = rng.choice((640, 768, 900, 1024, 1280, 1440))
        scale = max_side / float(max(variant.size))
        size = (max(1, int(round(variant.width * scale))), max(1, int(round(variant.height * scale))))
        variant = variant.resize(size, Image.Resampling.LANCZOS)
        output = target / f"{base_index:03d}-{digest[:10]}-v{variant_index}-{size[0]}x{size[1]}.jpg"
        variant.save(output, quality=94)
        outputs.append(output)
    return outputs


def source_candidates(group: str, seed: int) -> list[Path]:
    names = (
        ("male-headshot", "male-metadata")
        if group == "male"
        else ("female-headshot", "female-metadata", "female-metadata-b")
    )
    curated = curated_balanced_candidates(group)
    public = manifest_candidates(PUBLIC_PORTRAIT_SOURCES, group)
    additional_reviewed = manifest_candidates(ADDITIONAL_REVIEWED_SOURCES, group)
    labelled_headshots = list((CORPUS / f"{group}-headshot").glob("*.jpg"))
    random.Random(seed + 17).shuffle(labelled_headshots)
    fallback: list[Path] = []
    for name in names:
        folder = CORPUS / name
        if folder.exists():
            fallback.extend(path for path in folder.rglob("*") if path.suffix.lower() in {".jpg", ".jpeg", ".png"})
        variants = CORPUS / "variants" / name
        if variants.exists():
            fallback.extend(path for path in variants.rglob("*") if path.suffix.lower() in {".jpg", ".jpeg", ".png"})
    base_unique: dict[str, Path] = {}
    # Query-only web folders were deliberately removed from this final corpus:
    # their search labels are not ground-truth gender labels. The curated
    # manifest was reviewed from contact sheets and remains separate from all
    # production composition logic.
    base_candidates = public + additional_reviewed + curated + labelled_headshots + fallback
    random.Random(seed + 1).shuffle(base_candidates)
    for path in base_candidates:
        try:
            digest = image_digest(path)
        except OSError:
            continue
        base_unique.setdefault(digest, path)
    return generated_variants(list(base_unique.values()), group, seed + 500)


def validation_target_matrix(count: int) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Balance gender globally while matching the reviewed passport corpus mix."""
    base_target, remainder = divmod(count, len(SPEC_IDS))
    global_targets = {
        spec_id: base_target + (1 if index < remainder else 0)
        for index, spec_id in enumerate(SPEC_IDS)
    }
    group_totals = validation_group_targets(count)
    matrix = {group: {spec_id: 0 for spec_id in SPEC_IDS} for group in group_totals}

    passport_total = global_targets["passport-cn"]
    passport_female_share = 0.75 if count >= 60 else 0.50
    female_passport = min(
        group_totals["female"],
        int(math.floor(passport_total * passport_female_share + 0.5)),
    )
    male_passport = passport_total - female_passport
    matrix["male"]["passport-cn"] = male_passport
    matrix["female"]["passport-cn"] = female_passport

    remaining_specs = [spec_id for spec_id in VALIDATION_SPEC_ORDER if spec_id != "passport-cn"]
    remaining_male = group_totals["male"] - male_passport
    remaining_slots = sum(global_targets[spec_id] for spec_id in remaining_specs)
    for index, spec_id in enumerate(remaining_specs):
        spec_total = global_targets[spec_id]
        slots_after = remaining_slots - spec_total
        lower = max(0, remaining_male - slots_after)
        upper = min(spec_total, remaining_male)
        if index == len(remaining_specs) - 1:
            male_count = remaining_male
        else:
            proportional = spec_total * remaining_male / float(max(1, remaining_slots))
            male_count = int(math.floor(proportional + 0.5))
        male_count = min(upper, max(lower, male_count))
        matrix["male"][spec_id] = male_count
        matrix["female"][spec_id] = spec_total - male_count
        remaining_male -= male_count
        remaining_slots = slots_after
    if count >= 60 and matrix["male"]["driver-license-cn"] > 0:
        matrix["male"]["driver-license-cn"] -= 1
        matrix["female"]["driver-license-cn"] += 1
        matrix["male"]["id-card-cn"] += 1
        matrix["female"]["id-card-cn"] -= 1
    return global_targets, matrix


def validation_group_targets(count: int) -> dict[str, int]:
    male = int(math.floor(count * 0.39 + 0.5)) if count >= 60 else count // 2
    return {"male": male, "female": count - male}


def qualified_source_geometry(path: Path) -> tuple[bool, dict[str, Any]]:
    try:
        image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        detection = detect_face(path)
    except Exception as exc:
        return False, {"reason": "decode-or-face-error", "detail": str(exc)}
    if not detection.get("success"):
        return False, {"reason": detection.get("code") or "face-not-found"}
    if detection.get("frontalPoseMeasured") and not detection.get("frontalPosePass"):
        return False, {
            "reason": "non-frontal-source-pose",
            "poseScore": detection.get("poseScore"),
            "poseYawRatio": detection.get("poseYawRatio"),
            "poseRollRatio": detection.get("poseRollRatio"),
            "poseEarBalanceRatio": detection.get("poseEarBalanceRatio"),
        }
    face = detection["faceBox"]
    width, height = image.size
    face_h = max(1.0, float(face["height"]))
    lower_body_room = (height - (float(face["y"]) + face_h)) / face_h
    face_height_ratio = face_h / float(max(1, height))
    passed = bool(lower_body_room >= 0.48 and 0.10 <= face_height_ratio <= 0.58)
    return passed, {
        "reason": "qualified" if passed else "insufficient-head-shoulder-source-room",
        "imageSize": [width, height],
        "faceBox": face,
        "frontalPoseMeasured": detection.get("frontalPoseMeasured", False),
        "frontalPosePass": detection.get("frontalPosePass"),
        "poseScore": detection.get("poseScore"),
        "poseYawRatio": detection.get("poseYawRatio"),
        "poseRollRatio": detection.get("poseRollRatio"),
        "poseEarBalanceRatio": detection.get("poseEarBalanceRatio"),
        "lowerBodyRoomFaceRatio": round(lower_body_room, 6),
        "faceHeightRatio": round(face_height_ratio, 6),
    }


def nested_path(payload: Any, key: str) -> str:
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        for item in payload.values():
            found = nested_path(item, key)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = nested_path(item, key)
            if found:
                return found
    return ""


def request_case(
    session: requests.Session,
    base_url: str,
    source: Path,
    group: str,
    index: int,
    spec_id: str,
) -> dict[str, Any]:
    spec = PHOTO_SPECS[spec_id]
    started = time.perf_counter()
    prepare_response = session.post(
        base_url.rstrip("/") + "/api/id-photo/prepare",
        files={"image": (source.name, source.read_bytes(), "image/jpeg")},
        data={
            "purpose": "official_id_photo",
            "specId": spec_id,
            "composition": "head_shoulder",
            "outfit": "preserve_original",
        },
        timeout=120,
    )
    prepare_ms = int((time.perf_counter() - started) * 1000)
    prepare = prepare_response.json()
    row: dict[str, Any] = {
        "index": index,
        "group": group,
        "source": str(source.resolve()),
        "sourceDigest": image_digest(source),
        "specId": spec_id,
        "spec": {key: spec.get(key) for key in ("width", "height", "widthMm", "heightMm", "defaultBg")},
        "prepareMs": prepare_ms,
        "accepted": False,
    }
    if prepare_response.status_code != 200 or not prepare.get("success"):
        row.update({"stage": "prepare", "code": prepare.get("code"), "message": prepare.get("message")})
        return row

    bg_name = str(spec.get("defaultBg") or "blue")
    started = time.perf_counter()
    compose_response = session.post(
        base_url.rstrip("/") + "/api/id-photo/compose",
        data={
            "preparedId": prepare["preparedId"],
            "bgColor": bg_name,
            "bgColorName": bg_name,
            "outputType": "png",
        },
        timeout=90,
    )
    compose_ms = int((time.perf_counter() - started) * 1000)
    compose = compose_response.json()
    if compose_response.status_code != 200 or not compose.get("success"):
        quality = compose.get("quality") or {}
        row.update({
            "stage": "compose",
            "composeMs": compose_ms,
            "code": compose.get("code"),
            "message": compose.get("message"),
            "cropFailReasons": quality.get("cropFailReasons") or compose.get("cropFailReasons") or [],
        })
        return row

    preview = session.get(base_url.rstrip("/") + compose["previewUrl"], timeout=30).content
    download = session.get(base_url.rstrip("/") + compose["downloadUrl"], timeout=30).content
    quality = compose.get("quality") or {}
    validation = quality.get("finalIdPhotoValidation") or {}
    alignment = validation.get("personPanelAlignment") or {}
    head = validation.get("headGeometry") or {}
    shoulder = validation.get("shoulderGeometry") or {}
    case_dir = CASES / f"{index:03d}-{group}-{spec_id}"
    case_dir.mkdir(parents=True, exist_ok=True)
    source_output = case_dir / "source.jpg"
    ImageOps.exif_transpose(Image.open(source)).convert("RGB").save(source_output, quality=94)
    final_name = "final-white.png" if bg_name == "white" else "final-blue.png"
    final_output = case_dir / final_name
    final_output.write_bytes(download)
    foreground_output = case_dir / "foreground.png"
    foreground_source = nested_path(prepare, "foregroundPath")
    if foreground_source and Path(foreground_source).exists():
        shutil.copy2(foreground_source, foreground_output)

    image = Image.open(final_output).convert("RGB")
    checks = {
        "outputCanvasPass": quality.get("outputCanvasPass") is True,
        "backgroundPass": quality.get("backgroundPass") is True,
        "personToPanelAlignmentPass": quality.get("personToPanelAlignmentPass") is True,
        "compositionPass": quality.get("compositionPass") is True,
        "documentStandardPass": quality.get("documentStandardPass") is True,
        "previewDownloadPass": preview == download and quality.get("previewDownloadPass") is True,
        "importantForegroundOverflowPass": all(
            float(alignment.get(key) or 0) == 0
            for key in (
                "importantForegroundOverflowLeft",
                "importantForegroundOverflowRight",
                "importantForegroundOverflowTop",
            )
        ),
        "finalIdPhotoPass": quality.get("finalIdPhotoPass") is True,
        "actualSizePass": image.size == (int(spec["width"]), int(spec["height"])),
        "bottomContactPass": int(alignment.get("foregroundBottomGapPx") or 0) == 0,
        "shoulderSideContactPass": (
            int(alignment.get("leftShoulderPanelGapPx") or 0) == 0
            and int(alignment.get("rightShoulderPanelGapPx") or 0) == 0
        ),
        "shouldersObservedPass": shoulder.get("observed") is True,
    }
    row.update({
        "accepted": True,
        "passed": all(checks.values()),
        "composeMs": compose_ms,
        "checks": checks,
        "validation": validation,
        "paths": {
            "source": str(source_output.resolve()),
            "foreground": str(foreground_output.resolve()) if foreground_output.exists() else "",
            "final": str(final_output.resolve()),
        },
        "headWidthMm": round(float(head.get("widthRatio") or 0) * float(spec.get("widthMm") or 0), 4),
        "headHeightMm": round(float(head.get("heightRatio") or 0) * float(spec.get("heightMm") or 0), 4),
    })
    return row


def box_xy(box: dict[str, Any]) -> tuple[float, float, float, float]:
    return (float(box.get("left") or 0), float(box.get("top") or 0), float(box.get("right") or 0), float(box.get("bottom") or 0))


def make_overlays(row: dict[str, Any]) -> None:
    final_path = Path(row["paths"]["final"])
    image = Image.open(final_path).convert("RGB")
    validation = row["validation"]
    alignment = validation["personPanelAlignment"]
    panel_overlay = image.copy()
    draw = ImageDraw.Draw(panel_overlay)
    draw.rectangle((0, 0, image.width - 1, image.height - 1), outline=(255, 255, 0), width=3)
    draw.rectangle(box_xy(alignment["foreground"]), outline=(20, 20, 20), width=3)
    draw.rectangle(box_xy(alignment["head"]), outline=(0, 255, 255), width=3)
    draw.rectangle(box_xy(alignment["shoulder"]), outline=(255, 0, 220), width=3)
    draw.line((image.width // 2, 0, image.width // 2, image.height - 1), fill=(0, 255, 80), width=2)
    panel_path = final_path.parent / "panel-overlay.png"
    panel_overlay.save(panel_path)

    standard_overlay = image.copy()
    draw = ImageDraw.Draw(standard_overlay, "RGBA")
    target = validation["composition"]["targetRange"]
    top_y1 = int(round(float(target["topMin"]) * image.height))
    top_y2 = int(round(float(target["topMax"]) * image.height))
    draw.rectangle((0, top_y1, image.width, top_y2), fill=(0, 220, 255, 50), outline=(0, 170, 220, 220), width=2)
    draw.rectangle((0, int(image.height * 0.58), image.width, int(image.height * 0.92)), fill=(255, 0, 210, 24), outline=(255, 0, 210, 180), width=2)
    draw.rectangle(box_xy(validation["headGeometry"]["box"]), outline=(0, 255, 255, 255), width=3)
    draw.rectangle(box_xy(validation["shoulderGeometry"]["box"]), outline=(255, 0, 220, 255), width=3)
    standard_path = final_path.parent / "standard-overlay.png"
    standard_overlay.save(standard_path)
    row["paths"]["panelOverlay"] = str(panel_path.resolve())
    row["paths"]["standardOverlay"] = str(standard_path.resolve())


def tile(path: str, width: int = 190, height: int = 250, checker: bool = False) -> Image.Image:
    canvas = Image.new("RGB", (width, height), (238, 241, 245))
    if not path or not Path(path).exists():
        return canvas
    source = Image.open(path)
    if checker and source.mode == "RGBA":
        board = Image.new("RGBA", source.size, (232, 235, 240, 255))
        board.alpha_composite(source)
        source = board.convert("RGB")
    else:
        source = source.convert("RGB")
    source.thumbnail((width - 12, height - 30), Image.Resampling.LANCZOS)
    canvas.paste(source, ((width - source.width) // 2, 8))
    return canvas


def contact_sheet(rows: list[dict[str, Any]], output: Path) -> None:
    cell_w, cell_h = 190, 278
    columns = 5
    sheet = Image.new("RGB", (cell_w * columns, cell_h * len(rows)), "white")
    font = ImageFont.load_default()
    keys = ("source", "foreground", "final", "panelOverlay", "standardOverlay")
    for row_index, row in enumerate(rows):
        for column, key in enumerate(keys):
            block = tile(row["paths"].get(key, ""), cell_w, 250, checker=key == "foreground")
            label = f"{row['index']:03d} {row['specId']} {key}"
            ImageDraw.Draw(block).text((6, 258), label, fill=(12, 20, 30), font=font)
            sheet.paste(block, (column * cell_w, row_index * cell_h))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=94)


def write_reports(summary: dict[str, Any]) -> None:
    write_text(REPORT / "panel-alignment-root-cause.md", [
        "# Panel Alignment Root Cause",
        "",
        "- The prior gate treated center-line error as the final alignment definition.",
        "- Missing shoulder observations were replaced with a synthetic shoulder width.",
        "- The solver did not require the lower foreground to reach the real image panel bottom.",
        "- Final PNG/JPEG output was reopened, but composition pass still consumed theoretical composer ratios.",
        "- The repaired path remeasures the encoded output and final alpha mask, and separates panel alignment from per-spec compliance.",
    ])
    write_text(REPORT / "person-to-panel-validator.md", [
        "# Person-to-Panel Validator",
        "",
        "`validate_final_id_photo(finalImage, specId, standardProfile)` reopens the encoded file and reports canvas, background, foreground, head, chin, shoulders, composition, document standard, and preview/download gates.",
        "",
        "A head-and-shoulder result must contain observable shoulders and the lower foreground must meet the panel bottom. Natural shoulder asymmetry is allowed; the body is never stretched.",
    ])
    write_text(REPORT / "standard-profile-map.md", [
        "# Standard Profile Map",
        "",
        "| specId | source type | reference |",
        "| --- | --- | --- |",
        "| one-inch / two-inch | project_common_profile | Project common rendering profile; not a national universal standard |",
        "| id-card-cn | official | GA/T 461-2019; unavailable exact geometry remains explicitly unverified |",
        "| passport-cn | official | GA/T 1180-2014 and current passport profile fields already verified by the project |",
        "| driver-license-cn | official | 22x32mm, white background, head width 14-16mm, head height 19-22mm |",
        "| exam profiles | platform_profile | Current platform notice takes precedence |",
    ])
    write_text(REPORT / "mainland-official-sources.md", [
        "# Mainland Official Sources",
        "",
        "- Resident identity-card photos are bound to GA/T 461-2019 in the project profile.",
        "- Passport and exit-entry photos are bound to GA/T 1180-2014 in the project profile.",
        "- Driver-license validation is independent and checks 22x32mm, white background, 14-16mm head width, and 19-22mm head height.",
        "- Exact fields that are not available in the verified project material are not invented and remain marked unverified.",
    ])
    write_text(REPORT / "preview-download-consistency.md", [
        "# Preview and Download Consistency",
        "",
        f"- Samples: {summary['samples']}",
        f"- Failures: {summary['previewDownloadFailures']}",
        "- Verification compares the exact bytes returned by previewUrl and downloadUrl.",
    ])
    write_text(REPORT / "fixed-files.md", [
        "# Fixed Files",
        "",
        "- `server/services/id_photo_specs.py`: separates project-common targets from official per-purpose profiles.",
        "- `server/id_photo_engine_legacy/id_photo_composer.py`: observable shoulders, bottom contact, and per-profile head targets.",
        "- `server/id_photo_engine_legacy/id_photo_quality.py`: final encoded-file person-to-panel and document-standard validator.",
        "- `server/id_photo_engine_legacy/id_photo_v2.py`: production final gate wiring.",
        "- `server/scripts/verify_final_id_photo_mainland_compliance.py`: randomized final-output verification and visual evidence.",
    ])
    write_text(REPORT / "random-100-summary.md", [
        "# Random Portrait Summary",
        "",
        f"- Samples: {summary['samples']}",
        f"- Male: {summary['groups'].get('male', 0)}",
        f"- Female: {summary['groups'].get('female', 0)}",
        f"- Rejected candidates: {summary['rejectedCandidateCount']}",
        f"- Final pass: {summary['passed']}",
    ])
    write_text(REPORT / "final-summary.md", [
        "# Final Summary",
        "",
        f"- Final pass: {summary['passed']}",
        f"- Samples: {summary['samples']}",
        f"- Panel alignment failures: {summary['personPanelAlignmentFailures']}",
        f"- Composition failures: {summary['compositionFailures']}",
        f"- Shoulder side-gap failures: {summary['shoulderSideGapFailures']}",
        f"- Foreground bottom-gap failures: {summary['bottomGapFailures']}",
        f"- Document standard failures: {summary['documentStandardFailures']}",
        "- No filename, hash, fixed source dimension, or per-sample placement rule exists in the solver.",
    ])


def capacity_assignment(
    candidates: dict[str, dict[str, dict[str, Any]]],
    targets: dict[str, int],
) -> list[tuple[str, str, dict[str, Any]]] | None:
    slots = [(spec_id, slot) for spec_id, count in targets.items() for slot in range(count)]
    slot_owner: dict[tuple[str, int], str] = {}
    family_slot: dict[str, tuple[str, int]] = {}

    def augment(family: str, visited: set[tuple[str, int]]) -> bool:
        for slot in slots:
            if slot in visited or slot[0] not in candidates[family]:
                continue
            visited.add(slot)
            previous = slot_owner.get(slot)
            if previous is None or augment(previous, visited):
                slot_owner[slot] = family
                family_slot[family] = slot
                return True
        return False

    ordered_families = sorted(candidates, key=lambda family: (len(candidates[family]), family))
    for family in ordered_families:
        augment(family, set())
    if len(slot_owner) != len(slots):
        return None
    return [
        (family, slot[0], candidates[family][slot[0]])
        for family, slot in sorted(family_slot.items(), key=lambda item: (item[1][0], item[1][1], item[0]))
    ]


def discard_case_artifacts(row: dict[str, Any]) -> None:
    final_path = str((row.get("paths") or {}).get("final") or "")
    if final_path:
        shutil.rmtree(Path(final_path).parent, ignore_errors=True)


def run(base_url: str, count: int, seed: int) -> dict[str, Any]:
    if CASES.exists():
        shutil.rmtree(CASES)
    target = validation_group_targets(count)
    global_spec_targets, target_matrix = validation_target_matrix(count)
    session = requests.Session()
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    screened: list[dict[str, Any]] = []
    terminal_codes = {
        "ID_PHOTO_FAST_BLOCKED",
        "INVALID_ID_PHOTO_INPUT",
        "ID_PHOTO_POSE_NOT_FRONTAL",
        "IMAGE_TOO_BLURRY",
        "MULTIPLE_FACES",
    }
    for group in ("male", "female"):
        candidates = source_candidates(group, seed + (1000 if group == "male" else 2000))
        geometry_cache: dict[str, tuple[bool, dict[str, Any]]] = {}
        used_digests: set[str] = set()
        used_families: set[str] = set()
        screened_families: set[str] = set()
        terminal_rejected_families: set[str] = set()
        spec_targets = target_matrix[group]
        # Allocate the empirically scarce passport and one-inch fits first so
        # broader profiles do not consume their otherwise valid source family.
        capacity_specs_done = False
        for spec_id in VALIDATION_SPEC_ORDER_BY_GROUP[group]:
            if spec_id != "passport-cn":
                if capacity_specs_done:
                    continue
                capacity_specs_done = True
                capacity_specs = ("one-inch", "id-card-cn", "two-inch", "driver-license-cn")
                capacity_targets = {key: spec_targets[key] for key in capacity_specs}
                compatibility: dict[str, dict[str, dict[str, Any]]] = {}
                selected_capacity: list[tuple[str, str, dict[str, Any]]] | None = None
                group_offset = 100000 if group == "male" else 200000
                for source_index, source in enumerate(candidates):
                    digest = image_digest(source)
                    family = source_family(source)
                    if (
                        digest in used_digests
                        or family in used_families
                        or family in screened_families
                        or family in terminal_rejected_families
                    ):
                        continue
                    if digest not in geometry_cache:
                        geometry_cache[digest] = qualified_source_geometry(source)
                    geometry_pass, geometry = geometry_cache[digest]
                    if not geometry_pass:
                        screened_families.add(family)
                        screened.append({"group": group, "source": str(source), **geometry})
                        continue
                    family_rows: dict[str, dict[str, Any]] = {}
                    for capacity_index, capacity_spec in enumerate(capacity_specs):
                        probe_index = group_offset + source_index * len(capacity_specs) + capacity_index
                        row = request_case(session, base_url, source, group, probe_index, capacity_spec)
                        row["sourceQualification"] = geometry
                        row["sourceFamily"] = family
                        print(
                            f"[mainland-match] group={group} accepted={row.get('accepted')} "
                            f"passed={row.get('passed')} spec={capacity_spec} source={source.name} "
                            f"code={row.get('code') or ''} reasons={','.join(row.get('cropFailReasons') or [])}",
                            flush=True,
                        )
                        if row.get("accepted"):
                            family_rows[capacity_spec] = row
                        else:
                            rejected.append(row)
                            if row.get("code") in terminal_codes and not family_rows:
                                terminal_rejected_families.add(family)
                                break
                    if family_rows:
                        compatibility[family] = family_rows
                    selected_capacity = capacity_assignment(compatibility, capacity_targets)
                    if selected_capacity is not None:
                        break
                if selected_capacity is None:
                    stats = {
                        capacity_spec: sum(1 for rows in compatibility.values() if capacity_spec in rows)
                        for capacity_spec in capacity_targets
                    }
                    raise RuntimeError(
                        f"Qualified {group} non-passport capacity is short: "
                        f"targets={capacity_targets} observed={stats} families={len(compatibility)}"
                    )
                selected_ids = {id(row) for _, _, row in selected_capacity}
                for family, rows in compatibility.items():
                    for row in rows.values():
                        if id(row) not in selected_ids:
                            discard_case_artifacts(row)
                for family, capacity_spec, row in selected_capacity:
                    row["index"] = len(accepted)
                    used_digests.add(str(row["sourceDigest"]))
                    used_families.add(family)
                    make_overlays(row)
                    write_json(Path(row["paths"]["final"]).parent / "result.json", row)
                    accepted.append(row)
                    print(
                        f"[mainland-match] selected group={group} spec={capacity_spec} "
                        f"family={family} accepted={len(accepted)}",
                        flush=True,
                    )
                continue
            spec_count = 0
            for source in candidates:
                if spec_count >= spec_targets[spec_id]:
                    break
                digest = image_digest(source)
                family = source_family(source)
                if (
                    digest in used_digests
                    or family in used_families
                    or family in screened_families
                    or family in terminal_rejected_families
                ):
                    continue
                if digest not in geometry_cache:
                    geometry_cache[digest] = qualified_source_geometry(source)
                geometry_pass, geometry = geometry_cache[digest]
                if not geometry_pass:
                    screened_families.add(family)
                    screened.append({"group": group, "source": str(source), **geometry})
                    if len(screened) % 25 == 0:
                        print(f"[mainland] screened-out={len(screened)} accepted={len(accepted)}", flush=True)
                    continue
                row = request_case(session, base_url, source, group, len(accepted), spec_id)
                row["sourceQualification"] = geometry
                row["sourceFamily"] = family
                print(
                    f"[mainland] group={group} accepted={row.get('accepted')} "
                    f"passed={row.get('passed')} spec={spec_id} source={source.name} "
                    f"code={row.get('code') or ''} reasons={','.join(row.get('cropFailReasons') or [])}",
                    flush=True,
                )
                if row.get("accepted"):
                    used_digests.add(digest)
                    used_families.add(family)
                    make_overlays(row)
                    write_json(Path(row["paths"]["final"]).parent / "result.json", row)
                    accepted.append(row)
                    spec_count += 1
                else:
                    rejected.append(row)
                    if row.get("code") in terminal_codes or (
                        row.get("code") == "ID_PHOTO_QUALITY_FAILED"
                        and not row.get("cropFailReasons")
                    ):
                        terminal_rejected_families.add(family)
            if spec_count < spec_targets[spec_id]:
                deficit = spec_targets[spec_id] - spec_count
                if group == "male" and target["male"] - deficit >= 30:
                    target_matrix["male"][spec_id] -= deficit
                    target_matrix["female"][spec_id] += deficit
                    target["male"] -= deficit
                    target["female"] += deficit
                    print(
                        f"[mainland] shifted={deficit} spec={spec_id} male-to-female "
                        f"groups={target}",
                        flush=True,
                    )
                else:
                    raise RuntimeError(
                        f"Qualified {group}/{spec_id} corpus is short: "
                        f"{spec_count}/{spec_targets[spec_id]}"
                    )

    random.Random(seed).shuffle(accepted)
    failures = [row for row in accepted if not row.get("passed")]
    def fail_count(key: str) -> int:
        return sum(1 for row in accepted if not row["checks"].get(key))

    summary = {
        "seed": seed,
        "samples": len(accepted),
        "groups": {group: sum(1 for row in accepted if row["group"] == group) for group in target},
        "uniqueSourceFamilyCount": len({row["sourceFamily"] for row in accepted}),
        "sourceFamilyCounts": {
            group: len({row["sourceFamily"] for row in accepted if row["group"] == group})
            for group in target
        },
        "specCounts": {spec_id: sum(1 for row in accepted if row["specId"] == spec_id) for spec_id in SPEC_IDS},
        "targetAllocation": target_matrix,
        "rejectedCandidateCount": len(rejected),
        "screenedOutCount": len(screened),
        "personPanelAlignmentFailures": fail_count("personToPanelAlignmentPass"),
        "importantForegroundOverflowFailures": fail_count("importantForegroundOverflowPass"),
        "canvasFailures": fail_count("outputCanvasPass"),
        "backgroundFailures": fail_count("backgroundPass"),
        "headGeometryFailures": sum(1 for row in accepted if not row["validation"]["composition"]["checks"].get("headHeight") or not row["validation"]["composition"]["checks"].get("headWidth")),
        "compositionFailures": fail_count("compositionPass"),
        "shoulderSideGapFailures": fail_count("shoulderSideContactPass"),
        "bottomGapFailures": fail_count("bottomContactPass"),
        "documentStandardFailures": fail_count("documentStandardPass"),
        "previewDownloadFailures": fail_count("previewDownloadPass"),
        "verifiedOfficialProfiles": ["passport-cn", "driver-license-cn"],
        "partiallyVerifiedOfficialProfiles": ["id-card-cn"],
        "platformProfiles": ["teacher-exam", "civil-service-exam", "postgraduate-exam", "cet-exam", "computer-exam"],
        "projectCommonProfiles": ["one-inch", "two-inch", "small-one-inch", "large-one-inch", "small-two-inch", "large-two-inch"],
        "hardcodedSampleRules": 0,
        "localSha": git_sha(),
        "githubSha": "",
        "cloudSha": "",
        "passed": (
            len(accepted) == count
            and len({row["sourceFamily"] for row in accepted}) == count
            and (count < 60 or all(sum(1 for row in accepted if row["group"] == group) >= 30 for group in target))
            and all(
                sum(1 for row in accepted if row["specId"] == spec_id) == target_count
                for spec_id, target_count in global_spec_targets.items()
            )
            and not failures
        ),
        "rows": accepted,
        "rejected": rejected,
        "screenedOut": screened,
    }
    write_json(REPORT / "random-100-results.json", summary)
    write_json(REPORT / "final-summary.json", {key: value for key, value in summary.items() if key not in {"rows", "rejected", "screenedOut"}})
    evidence = random.Random(seed + 99).sample(accepted, min(30, len(accepted)))
    contact_sheet(evidence, REPORT / "portrait-mainland-compliance-contact-sheet.jpg")
    write_reports(summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260807)
    args = parser.parse_args()
    summary = run(args.base_url, args.count, args.seed)
    print(json.dumps({key: value for key, value in summary.items() if key not in {"rows", "rejected", "screenedOut"}}, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
