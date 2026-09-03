"""Final randomized visual convergence checks for ID photo and strict-local HD inpaint."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from services import hd_inpaint, stroke_inpaint  # noqa: E402


REPORT = ROOT / "reports" / "final-visual-convergence"
PORTRAIT_OUT = REPORT / "portrait-100"
PORTRAIT_CORPUS = REPORT / "portrait-corpus"
WATERMARK_OUT = REPORT / "watermark-30"
QUALIFIED_PORTRAITS = PORTRAIT_CORPUS / "qualified-sources.json"
SPECS = [
    ("one-inch", 295, 413, 25, 35),
    ("passport", 390, 567, 33, 48),
    ("two-inch", 413, 579, 35, 49),
    ("exam", 260, 378, 22, 32),
]
BG_BGR = np.asarray((232, 115, 26), dtype=np.int16)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_portrait_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            digest = file_digest(path)
        except Exception:
            continue
        if digest in seen:
            continue
        seen.add(digest)
        result.append(path)
    return result


def qualified_portrait_sources(group: str) -> list[Path]:
    rows: list[dict[str, Any]] = []
    for path in (QUALIFIED_PORTRAITS, REPORT / "portrait-random-100.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows.extend(payload if path == QUALIFIED_PORTRAITS else (payload.get("rows") or []))
        except Exception:
            continue
    result: list[Path] = []
    seen: set[str] = set()
    for row in rows:
        value = row.get("baseIdentity") or row.get("source")
        candidate = Path(str(value or ""))
        key = file_digest(candidate) if candidate.exists() else ""
        if row.get("group") != group or not key or key in seen:
            continue
        result.append(candidate)
        seen.add(key)
    return result


def remember_qualified_portrait(group: str, path: Path) -> None:
    rows: list[dict[str, str]] = []
    try:
        rows = json.loads(QUALIFIED_PORTRAITS.read_text(encoding="utf-8"))
    except Exception:
        pass
    key = file_digest(path)
    known = {
        file_digest(Path(row.get("source") or ""))
        for row in rows
        if row.get("group") == group and Path(row.get("source") or "").exists()
    }
    if key not in known:
        rows.append({"group": group, "source": str(path.resolve())})
        write_json(QUALIFIED_PORTRAITS, rows)


def encode_png(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])
    if not ok:
        raise RuntimeError("PNG encode failed")
    return encoded.tobytes()


def save_png(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_png(image))


def decode_image(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("Image decode failed")
    return image


def percentile(values: list[float], q: float) -> float:
    return round(float(np.percentile(np.asarray(values, dtype=np.float32), q)), 6) if values else 0.0


def download_lorem_group(group: str, query: str, count: int, seed: int) -> list[Path]:
    target = PORTRAIT_CORPUS / group
    target.mkdir(parents=True, exist_ok=True)
    existing = sorted(target.glob("*.jpg"))
    if len(existing) >= count:
        return existing

    locks = list(range(seed, seed + max(count * 2, 80)))
    session_headers = {"User-Agent": "Mozilla/5.0 final-visual-convergence/1.0"}

    def fetch(lock: int) -> tuple[int, bytes] | None:
        url = f"https://loremflickr.com/900/1200/{query}?lock={lock}"
        try:
            response = requests.get(url, timeout=35, headers=session_headers)
            if response.status_code == 200 and len(response.content) > 30000:
                return lock, response.content
        except Exception:
            return None
        return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, lock) for lock in locks]
        for future in as_completed(futures):
            item = future.result()
            if not item:
                continue
            lock, content = item
            path = target / f"{group}-{lock}.jpg"
            try:
                image = ImageOps.exif_transpose(Image.open(io.BytesIO(content))).convert("RGB")
                if image.width < 600 or image.height < 600:
                    continue
                image.save(path, quality=94)
            except Exception:
                continue
    return sorted(target.glob("*.jpg"))


def download_randomuser_group(group: str, gender: str, count: int, seed: int) -> list[Path]:
    target = PORTRAIT_CORPUS / group
    target.mkdir(parents=True, exist_ok=True)
    existing = sorted(target.glob("*.jpg"))
    if len(existing) >= count:
        return existing

    response = requests.get(
        "https://randomuser.me/api/",
        params={
            "results": max(count, 16),
            "gender": gender,
            "inc": "gender,picture",
            "noinfo": "1",
            "seed": f"finalvisual{seed}",
        },
        headers={"User-Agent": "Mozilla/5.0 final-visual-convergence/1.0"},
        timeout=45,
    )
    response.raise_for_status()
    rows = response.json().get("results") or []
    sources: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if row.get("gender") != gender:
            continue
        url = str((row.get("picture") or {}).get("large") or "")
        if not url:
            continue
        try:
            image_response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            image_response.raise_for_status()
            source = ImageOps.exif_transpose(Image.open(io.BytesIO(image_response.content))).convert("RGB")
            # RandomUser supplies a tightly cropped square portrait. Restore phone-camera
            # context without changing the face/body aspect ratio or the source pixels.
            inset = max(1, int(round(source.width * 0.19)))
            central = source.crop((inset, 0, source.width - inset, source.height))
            portrait = ImageOps.contain(central, (620, 928), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (768, 1024), portrait.getpixel((0, 0)))
            canvas.paste(portrait, ((768 - portrait.width) // 2, 48))
            path = target / f"{group}-{index:03d}.jpg"
            canvas.save(path, quality=95)
            sources.append({"path": str(path), "genderMetadata": gender, "url": url})
        except Exception:
            continue
        if len(sources) >= count:
            break
    if sources:
        write_json(target / "sources.json", sources)
    return sorted(target.glob("*.jpg"))


def download_commons_group(group: str, category: str, count: int, seed: int) -> list[Path]:
    target = PORTRAIT_CORPUS / group
    target.mkdir(parents=True, exist_ok=True)
    existing = sorted(target.glob("commons-*.jpg"))
    if len(existing) >= count:
        return existing
    api = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query", "format": "json", "generator": "categorymembers",
        "gcmtitle": category, "gcmtype": "file", "gcmlimit": "100",
        "prop": "imageinfo", "iiprop": "url", "iiurlwidth": "900", "origin": "*",
    }
    urls: list[tuple[str, str]] = []
    continuation = ""
    while len(urls) < max(count * 2, 80):
        request_params = dict(params)
        if continuation:
            request_params["gcmcontinue"] = continuation
        response = requests.get(api, params=request_params, timeout=35, headers={"User-Agent": "final-visual-convergence/1.0"})
        payload = response.json()
        for page in ((payload.get("query") or {}).get("pages") or {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")
            if url:
                urls.append((str(page.get("title") or ""), str(url)))
        continuation = str((payload.get("continue") or {}).get("gcmcontinue") or "")
        if not continuation:
            break
    random.Random(seed).shuffle(urls)

    def fetch(item: tuple[str, str]) -> tuple[str, str, bytes] | None:
        title, url = item
        try:
            response = requests.get(url, timeout=40, headers={"User-Agent": "final-visual-convergence/1.0"})
            if response.status_code == 200 and len(response.content) > 20000:
                return title, url, response.content
        except Exception:
            return None
        return None

    source_rows = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(fetch, item) for item in urls[: max(count * 2, 80)]]
        for future in as_completed(futures):
            item = future.result()
            if not item:
                continue
            title, url, content = item
            digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
            path = target / f"commons-{digest}.jpg"
            try:
                image = ImageOps.exif_transpose(Image.open(io.BytesIO(content))).convert("RGB")
                if image.width < 500 or image.height < 500:
                    continue
                image.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
                image.save(path, quality=94)
                source_rows.append({"path": str(path), "title": title, "url": url, "category": category})
            except Exception:
                continue
    if source_rows:
        write_json(target / "commons-sources.json", source_rows)
    return sorted(target.glob("commons-*.jpg"))


def mixed_portrait_candidates(seed: int) -> list[Path]:
    roots = [
        ROOT / "reports" / "id-photo-final-fix" / "artifacts" / "random-source",
        ROOT / "reports" / "id-photo-under-10s" / "fast-ab-artifacts",
        ROOT / "reports" / "id-photo-samples" / "input",
    ]
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            name = path.name.lower()
            if "thisperson" in name or name == "canonical-source.jpg" or "male" in name or "female" in name:
                candidates.append(path)
    unique: dict[str, Path] = {}
    for path in candidates:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with Image.open(path) as image:
                if image.width < 500 or image.height < 500:
                    continue
            unique.setdefault(digest, path)
        except Exception:
            continue
    rows = list(unique.values())
    random.Random(seed).shuffle(rows)
    return rows


def portrait_variants(path: Path, group: str, seed: int) -> list[Path]:
    target = PORTRAIT_CORPUS / "variants" / group
    target.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    outputs = [target / f"{digest}-mirror.jpg", target / f"{digest}-crop.jpg"]
    if all(item.exists() for item in outputs):
        return outputs
    source = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    ImageOps.mirror(source).save(outputs[0], quality=94)
    width, height = source.size
    inset_x = max(1, int(round(width * 0.025)))
    inset_top = max(1, int(round(height * 0.018)))
    cropped = source.crop((inset_x, inset_top, width - inset_x, height)).resize((width, height), Image.Resampling.LANCZOS)
    factor = 0.96 + (int(digest[:2], 16) % 9) * 0.01
    ImageEnhance.Brightness(cropped).enhance(factor).save(outputs[1], quality=92)
    return outputs


def edge_background_ratio(image: np.ndarray) -> float:
    upper = max(1, int(round(image.shape[0] * 0.35)))
    pixels = np.concatenate((image[0], image[:upper, 0], image[:upper, -1]), axis=0).astype(np.int16)
    return float(np.mean(np.max(np.abs(pixels - BG_BGR), axis=1) <= 4))


def post_portrait(session: requests.Session, base_url: str, path: Path, group: str, index: int) -> dict[str, Any]:
    spec_name, width, height, width_mm, height_mm = SPECS[index % len(SPECS)]
    started = time.perf_counter()
    response = session.post(
        base_url.rstrip("/") + "/api/id-photo/prepare",
        files={"image": ("random-portrait.jpg", path.read_bytes(), "image/jpeg")},
        data={
            "purpose": "official_id_photo",
            "specId": f"visual_{spec_name}_{width}_{height}",
            "widthPx": str(width),
            "heightPx": str(height),
            "widthMm": str(width_mm),
            "heightMm": str(height_mm),
            "composition": "head_shoulder",
            "outfit": "preserve_original",
        },
        timeout=120,
    )
    prepare_ms = int((time.perf_counter() - started) * 1000)
    prepare = response.json()
    if response.status_code != 200 or not prepare.get("success"):
        return {
            "source": str(path), "group": group, "accepted": False, "stage": "prepare",
            "statusCode": response.status_code, "code": prepare.get("code"),
            "message": prepare.get("message"), "prepareMs": prepare_ms,
        }

    started = time.perf_counter()
    response = session.post(
        base_url.rstrip("/") + "/api/id-photo/compose",
        data={"preparedId": prepare["preparedId"], "bgColor": "blue", "bgColorName": "blue", "outputType": "png"},
        timeout=60,
    )
    compose_ms = int((time.perf_counter() - started) * 1000)
    compose = response.json()
    row: dict[str, Any] = {
        "source": str(path), "group": group, "accepted": True, "prepareMs": prepare_ms,
        "composeMs": compose_ms, "spec": {"name": spec_name, "width": width, "height": height},
    }
    if response.status_code != 200 or not compose.get("success"):
        row.update({
            "accepted": False, "qualifiedInput": True, "passed": False, "stage": "compose", "statusCode": response.status_code,
            "code": compose.get("code"), "message": compose.get("message"),
            "cropFailReasons": compose.get("cropFailReasons") or [],
        })
        return row

    preview = session.get(base_url.rstrip("/") + compose["previewUrl"], timeout=30).content
    download = session.get(base_url.rstrip("/") + compose["downloadUrl"], timeout=30).content
    image = decode_image(preview)
    quality = compose.get("quality") or {}
    visual_ratio = float(quality.get("visualCenterErrorRatio") or 1)
    face_ratio = float(quality.get("faceCenterOffset") or 1)
    margin_ratio = float(quality.get("shoulderMarginDifferenceRatio") or 0)
    symmetry = quality.get("shoulderSymmetryApplicable") is not False
    checks = {
        "outputSize": image.shape[:2] == (height, width),
        "previewEqualsDownload": hashlib.sha256(preview).digest() == hashlib.sha256(download).digest(),
        "faceCenterWithin1_5Percent": face_ratio <= 0.015,
        "visualCenterWithin1Percent": visual_ratio <= 0.010,
        "shoulderMarginsWithin2_5Percent": (not symmetry) or margin_ratio <= 0.025,
        "importantForegroundInside": float(quality.get("importantForegroundOverflowPixels") or 0) == 0,
        "subjectInsideCanvas": quality.get("subjectWithinCanvas") is True,
        "noBlackOrTransparentUpperEdge": edge_background_ratio(image) >= 0.98,
        "multiAnchorSolver": (quality.get("compositionSolver") or {}).get("version") == "multi-anchor-constraint-v5",
        "layoutSolveUnder100Ms": float((quality.get("compositionSolver") or {}).get("layoutSolveMs") or 999) < 100,
    }
    output_path = PORTRAIT_OUT / "results" / f"{group}-{index:03d}-{width}x{height}.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(preview)
    foreground_path = None
    quality_prepare = prepare.get("quality") or {}
    foreground_value = quality_prepare.get("foregroundPath")
    if not foreground_value:
        for value in quality_prepare.values():
            if isinstance(value, dict) and value.get("foregroundPath"):
                foreground_value = value["foregroundPath"]
                break
    if foreground_value and Path(foreground_value).exists():
        foreground_path = PORTRAIT_OUT / "foreground" / f"{group}-{index:03d}.png"
        foreground_path.parent.mkdir(parents=True, exist_ok=True)
        foreground_path.write_bytes(Path(foreground_value).read_bytes())
    row.update({
        "passed": all(checks.values()), "checks": checks,
        "metrics": {
            key: quality.get(key) for key in (
                "faceCenterErrorPx", "headCenterErrorPx", "shoulderCenterErrorPx", "visualCenterErrorPx",
                "visualCenterErrorRatio", "leftShoulderMarginPx", "rightShoulderMarginPx",
                "shoulderMarginDifferencePx", "shoulderMarginDifferenceRatio", "shoulderSymmetryApplicable",
                "importantForegroundOverflowPixels", "headBBox", "shoulderBBox", "outputForegroundBox",
            )
        },
        "solver": quality.get("compositionSolver") or {}, "output": str(output_path),
        "foreground": str(foreground_path) if foreground_path else "",
    })
    return row


def draw_box(draw: ImageDraw.ImageDraw, box: dict[str, Any] | None, color: tuple[int, int, int]) -> None:
    if not box:
        return
    if "left" in box:
        xy = (box["left"], box["top"], box["right"], box["bottom"])
    else:
        xy = (box.get("x", 0), box.get("y", 0), box.get("x", 0) + box.get("width", 0), box.get("y", 0) + box.get("height", 0))
    draw.rectangle(xy, outline=color, width=2)


def portrait_evidence_frame(row: dict[str, Any]) -> Image.Image:
    frame = Image.new("RGB", (720, 290), "white")
    source = Image.open(row["source"]).convert("RGB")
    source.thumbnail((210, 240), Image.Resampling.LANCZOS)
    frame.paste(source, ((220 - source.width) // 2, 8))
    if row.get("foreground") and Path(row["foreground"]).exists():
        foreground = Image.open(row["foreground"]).convert("RGBA")
        foreground.thumbnail((210, 240), Image.Resampling.LANCZOS)
        panel = Image.new("RGBA", (220, 250), (238, 240, 244, 255))
        panel.alpha_composite(foreground, ((220 - foreground.width) // 2, (240 - foreground.height) // 2))
        frame.paste(panel.convert("RGB"), (220, 0))
    final = Image.open(row["output"]).convert("RGB")
    draw = ImageDraw.Draw(final)
    width, height = final.size
    centers = row.get("solver") or {}
    for x, color in (
        (width / 2.0, (0, 210, 60)),
        (centers.get("faceCenterX"), (30, 120, 255)),
        (centers.get("headCenterX"), (0, 190, 230)),
        (centers.get("shoulderCenterX"), (190, 40, 220)),
        (centers.get("visualCenterX"), (255, 190, 0)),
    ):
        if x is not None:
            draw.line((round(float(x)), 0, round(float(x)), height - 1), fill=color, width=2)
    metrics = row.get("metrics") or {}
    draw_box(draw, metrics.get("headBBox"), (0, 190, 230))
    draw_box(draw, metrics.get("shoulderBBox"), (190, 40, 220))
    draw_box(draw, metrics.get("outputForegroundBox"), (30, 30, 30))
    final.thumbnail((210, 240), Image.Resampling.LANCZOS)
    frame.paste(final, (445 + (220 - final.width) // 2, 8))
    label = f"{row['group']} {row['spec']['width']}x{row['spec']['height']} visual={row['metrics']['visualCenterErrorPx']}px"
    ImageDraw.Draw(frame).text((8, 263), label, fill=(20, 28, 38), font=ImageFont.load_default())
    return frame


def save_contact_sheet(frames: list[Image.Image], output: Path, columns: int) -> None:
    if not frames:
        return
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGB", (frames[0].width * columns, frames[0].height * rows), (226, 230, 236))
    for index, frame in enumerate(frames):
        sheet.paste(frame, ((index % columns) * frame.width, (index // columns) * frame.height))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=94)


def run_portraits(base_url: str, seed: int, count: int) -> dict[str, Any]:
    targets = {"male-query": min(30, count), "female-query": min(30, max(0, count - 30))}
    targets["mixed-random"] = max(0, count - sum(targets.values()))
    male_download = max(30, targets["male-query"] * 4) if targets["male-query"] else 0
    female_download = max(30, targets["female-query"] * 4) if targets["female-query"] else 0
    male_headshots = download_lorem_group("male-headshot", "man,headshot", max(40, targets["male-query"] * 2) if targets["male-query"] else 0, seed + 51000)
    female_headshots = download_lorem_group("female-headshot", "woman,headshot", max(40, targets["female-query"] * 2) if targets["female-query"] else 0, seed + 61000)
    metadata_count = 32 if count >= 60 else 16
    male_metadata = download_randomuser_group("male-metadata", "male", metadata_count if targets["male-query"] else 0, seed + 71000)
    female_metadata = download_randomuser_group("female-metadata", "female", metadata_count if targets["female-query"] else 0, seed + 81000)
    if targets["female-query"]:
        female_metadata += download_randomuser_group("female-metadata-b", "female", metadata_count, seed + 81001)
    mixed_local = mixed_portrait_candidates(seed)
    mixed_priority = qualified_portrait_sources("male-query") + qualified_portrait_sources("female-query")
    pools = {
        "male-query": unique_portrait_paths(male_metadata + male_headshots + download_lorem_group(
            "male-query", "man,portrait", max(12, targets["male-query"] * 3) if targets["male-query"] else 0, seed + 11000
        )),
        "female-query": unique_portrait_paths(female_metadata + female_headshots + download_lorem_group(
            "female-query", "woman,portrait", max(12, targets["female-query"] * 3) if targets["female-query"] else 0, seed + 21000
        )),
        "mixed-random": unique_portrait_paths(mixed_priority + mixed_local),
    }
    for group in ("male-query", "female-query"):
        priority = qualified_portrait_sources(group)
        pools[group] = unique_portrait_paths(priority + pools[group])
    session = requests.Session()
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for group, target in targets.items():
        group_count = 0
        base_identities: dict[str, str] = {}
        mixed_completion_variants_used = False
        for path in pools[group]:
            if group_count >= target:
                break
            candidates = [path]
            base_accepted = False
            base_digest = file_digest(path)
            for candidate in candidates:
                row = post_portrait(session, base_url, candidate, group, len(accepted))
                row["baseIdentity"] = str(path)
                row["baseIdentityDigest"] = base_digest
                print(f"[portrait] group={group} accepted={row.get('accepted')} passed={row.get('passed')} source={candidate.name}", flush=True)
                if row.get("accepted"):
                    accepted.append(row)
                    group_count += 1
                    base_accepted = True
                    base_identities.setdefault(base_digest, str(path))
                else:
                    rejected.append(row)
            if base_accepted and group_count < target:
                remember_qualified_portrait(group, path)
                variants = portrait_variants(path, group, seed)
                if group == "mixed-random":
                    variants = variants[:1]
                for candidate in variants:
                    if group_count >= target:
                        break
                    row = post_portrait(session, base_url, candidate, group, len(accepted))
                    row["baseIdentity"] = str(path)
                    row["baseIdentityDigest"] = base_digest
                    print(f"[portrait] group={group} accepted={row.get('accepted')} passed={row.get('passed')} source={candidate.name}", flush=True)
                    if row.get("accepted"):
                        accepted.append(row)
                        group_count += 1
                    else:
                        rejected.append(row)
            if (
                group == "mixed-random"
                and len(base_identities) >= 20
                and group_count < target
                and not mixed_completion_variants_used
            ):
                mixed_completion_variants_used = True
                for base_identity in sorted(base_identities.values()):
                    base_digest = file_digest(Path(base_identity))
                    candidate = portrait_variants(Path(base_identity), group, seed)[1]
                    row = post_portrait(session, base_url, candidate, group, len(accepted))
                    row["baseIdentity"] = base_identity
                    row["baseIdentityDigest"] = base_digest
                    print(
                        f"[portrait] group={group} accepted={row.get('accepted')} "
                        f"passed={row.get('passed')} source={candidate.name}",
                        flush=True,
                    )
                    if row.get("accepted"):
                        accepted.append(row)
                        group_count += 1
                    else:
                        rejected.append(row)
                    if group_count >= target:
                        break
        if group_count < target:
            raise RuntimeError(f"Qualified {group} corpus is short: {group_count}/{target}")
        minimum_identities = 20 if group == "mixed-random" and target >= 40 else (10 if target >= 30 else 0)
        if len(base_identities) < minimum_identities:
            raise RuntimeError(
                f"Qualified {group} base identities are short: {len(base_identities)}/{minimum_identities}"
            )

    failures = [row for row in accepted if not row.get("passed")]
    visual_ratios = [float(row["metrics"]["visualCenterErrorRatio"] or 0) for row in accepted if row.get("metrics")]
    visual_pixels = [float(row["metrics"]["visualCenterErrorPx"] or 0) for row in accepted if row.get("metrics")]
    margin_pixels = [float(row["metrics"]["shoulderMarginDifferencePx"] or 0) for row in accepted if row.get("metrics") and row["metrics"].get("shoulderSymmetryApplicable") is not False]
    solve_ms = [float((row.get("solver") or {}).get("layoutSolveMs") or 0) for row in accepted]
    spec_counts = {name: sum(1 for row in accepted if row["spec"]["name"] == name) for name, *_ in SPECS}
    summary = {
        "seed": seed, "portraitSamples": len(accepted), "rejectedCandidateCount": len(rejected),
        "groups": {group: sum(1 for row in accepted if row["group"] == group) for group in targets},
        "baseIdentityCounts": {group: len({row.get("baseIdentityDigest") for row in accepted if row["group"] == group}) for group in targets},
        "specCounts": spec_counts, "portraitVisualOffsetFailures": len(failures),
        "portraitImportantOverflowFailures": sum(1 for row in accepted if float((row.get("metrics") or {}).get("importantForegroundOverflowPixels") or 0) > 0),
        "portraitP50VisualCenterErrorPx": percentile(visual_pixels, 50),
        "portraitP95VisualCenterErrorPx": percentile(visual_pixels, 95),
        "portraitMaxVisualCenterErrorPx": max(visual_pixels, default=0),
        "portraitP95VisualCenterErrorRatio": percentile(visual_ratios, 95),
        "portraitP50ShoulderMarginDifferencePx": percentile(margin_pixels, 50),
        "portraitP95ShoulderMarginDifferencePx": percentile(margin_pixels, 95),
        "layoutSolveP95Ms": percentile(solve_ms, 95),
        "passed": len(accepted) == count and not failures and percentile(visual_ratios, 95) <= 0.01,
        "rows": accepted, "rejected": rejected,
    }
    write_json(REPORT / "portrait-random-100.json", summary)
    evidence_rows = [row for row in accepted if row.get("output")]
    frames = [portrait_evidence_frame(row) for row in random.Random(seed).sample(evidence_rows, min(30, len(evidence_rows)))]
    save_contact_sheet(frames, REPORT / "portrait-contact-sheet.jpg", 3)
    save_contact_sheet(frames, REPORT / "portrait-layout-contact-sheet.jpg", 3)
    return summary


def make_background(kind: str, width: int, height: int, rng: random.Random) -> np.ndarray:
    image = np.full((height, width, 3), 244, dtype=np.uint8)
    if kind in {"document", "ticket"}:
        image[:] = (250, 250, 248)
        for y in range(70, height - 30, 48):
            cv2.line(image, (35, y), (width - 35, y), (192, 184, 174), 1)
            cv2.putText(image, f"ROW {y // 48:02d}  VALUE {rng.randint(1000, 9999)}", (48, y - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (58, 56, 52), 1, cv2.LINE_AA)
    elif kind == "screenshot":
        image[:] = (246, 248, 252)
        cv2.rectangle(image, (0, 0), (width, 58), (44, 52, 64), -1)
        for y in range(90, height - 40, 72):
            cv2.rectangle(image, (36, y), (width - 36, y + 48), (230, 235, 242), -1)
            cv2.putText(image, f"Panel {y // 72}", (55, y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (55, 65, 78), 1, cv2.LINE_AA)
    elif kind == "product":
        yy, xx = np.mgrid[:height, :width]
        image[:, :, 0] = np.clip(205 + xx * 30 / width, 0, 255)
        image[:, :, 1] = np.clip(225 + yy * 20 / height, 0, 255)
        image[:, :, 2] = 238
        cv2.rectangle(image, (width // 3, height // 5), (width * 2 // 3, height * 4 // 5), (72, 118, 205), -1)
        cv2.circle(image, (width // 2, height // 2), min(width, height) // 8, (228, 220, 100), -1)
    elif kind == "photo":
        noise = np.random.default_rng(rng.randint(0, 2**31 - 1)).normal(0, 10, (height, width, 3))
        yy, xx = np.mgrid[:height, :width]
        base = np.stack((90 + yy * 80 / height, 145 + xx * 55 / width, 180 - yy * 45 / height), axis=2)
        image = np.clip(base + noise, 0, 255).astype(np.uint8)
        cv2.circle(image, (width // 2, height // 2), min(width, height) // 5, (95, 170, 215), -1)
    elif kind == "landscape":
        split = height * 3 // 5
        for y in range(height):
            if y < split:
                image[y] = (220 - y * 50 // split, 190, 130 + y * 70 // split)
            else:
                image[y] = (80, 145, 80)
        points = np.asarray([(0, split), (width // 4, height // 3), (width // 2, split), (width * 3 // 4, height // 4), (width, split)], np.int32)
        cv2.fillPoly(image, [points], (112, 106, 92))
    else:
        image[:] = (50, 58, 74)
        for _ in range(18):
            x1, y1 = rng.randrange(width), rng.randrange(height)
            x2, y2 = rng.randrange(width), rng.randrange(height)
            color = tuple(rng.randrange(70, 230) for _ in range(3))
            cv2.rectangle(image, (min(x1, x2), min(y1, y2)), (max(x1, x2), max(y1, y2)), color, -1)
        cv2.putText(image, "EVENT 2026", (45, height // 2), cv2.FONT_HERSHEY_DUPLEX, 1.35, (248, 248, 248), 2, cv2.LINE_AA)
    return image


def make_watermark_fixture(index: int, seed: int) -> dict[str, Any]:
    rng = random.Random(seed * 1000 + index)
    kinds = ["document", "screenshot", "product", "photo", "landscape", "poster"]
    kind = kinds[index % len(kinds)]
    width, height = [(720, 480), (640, 720), (800, 520)][index % 3]
    clean = make_background(kind, width, height, rng)
    marked = clean.copy()
    overlay = clean.copy()
    mask = np.zeros((height, width), dtype=np.uint8)
    target_mask = np.zeros((height, width), dtype=np.uint8)
    cx = rng.randint(width // 4, width * 3 // 4)
    cy = rng.randint(height // 4, height * 3 // 4)
    if kind == "product":
        cx = width // 6 if index % 2 == 0 else width * 5 // 6
        cy = height // 5
    color = [(36, 48, 220), (210, 92, 28), (45, 175, 92), (170, 70, 175), (40, 165, 205)][index % 5]
    watermark_type = ["text", "logo", "stamp", "translucent", "small", "line"][index % 6]
    if watermark_type == "text":
        cv2.putText(overlay, f"MARK-{index:02d}", (cx - 95, cy + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2, cv2.LINE_AA)
        cv2.putText(target_mask, f"MARK-{index:02d}", (cx - 95, cy + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.85, 255, 2, cv2.LINE_AA)
        cv2.rectangle(mask, (cx - 112, cy - 28), (cx + 112, cy + 34), 255, -1)
    elif watermark_type == "logo":
        cv2.circle(overlay, (cx, cy), 42, color, -1)
        cv2.putText(overlay, "L", (cx - 15, cy + 18), cv2.FONT_HERSHEY_DUPLEX, 1.3, (245, 245, 245), 2, cv2.LINE_AA)
        cv2.circle(target_mask, (cx, cy), 44, 255, -1)
        cv2.circle(mask, (cx, cy), 50, 255, -1)
    elif watermark_type == "stamp":
        cv2.circle(overlay, (cx, cy), 62, color, 5, cv2.LINE_AA)
        cv2.putText(overlay, "STAMP", (cx - 48, cy + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 2, cv2.LINE_AA)
        cv2.circle(target_mask, (cx, cy), 62, 255, 7, cv2.LINE_AA)
        cv2.putText(target_mask, "STAMP", (cx - 48, cy + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.62, 255, 3, cv2.LINE_AA)
        cv2.circle(mask, (cx, cy), 70, 255, -1)
    elif watermark_type == "translucent":
        cv2.rectangle(overlay, (cx - 100, cy - 34), (cx + 100, cy + 34), color, -1)
        cv2.putText(overlay, "SAMPLE", (cx - 72, cy + 11), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (250, 250, 250), 2, cv2.LINE_AA)
        cv2.rectangle(target_mask, (cx - 100, cy - 34), (cx + 100, cy + 34), 255, -1)
        cv2.rectangle(mask, (cx - 108, cy - 42), (cx + 108, cy + 42), 255, -1)
    elif watermark_type == "small":
        cv2.putText(overlay, "wm", (cx - 20, cy + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
        cv2.putText(target_mask, "wm", (cx - 20, cy + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, 255, 3, cv2.LINE_AA)
        cv2.rectangle(mask, (cx - 32, cy - 24), (cx + 34, cy + 24), 255, -1)
    else:
        cv2.line(overlay, (cx - 90, cy - 28), (cx + 90, cy + 28), color, 8, cv2.LINE_AA)
        cv2.line(target_mask, (cx - 90, cy - 28), (cx + 90, cy + 28), 255, 10, cv2.LINE_AA)
        cv2.line(mask, (cx - 96, cy - 30), (cx + 96, cy + 30), 255, 18, cv2.LINE_AA)
    alpha = [0.58, 0.72, 0.68, 0.42, 0.78, 0.60][index % 6]
    marked = cv2.addWeighted(overlay, alpha, marked, 1.0 - alpha, 0)
    x, y, w, h = cv2.boundingRect(cv2.findNonZero(mask))
    if watermark_type == "line":
        strokes = [{
            "type": "brush",
            "brushSizeRatio": 18 / width,
            "points": [
                {"x": (cx - 96) / width, "y": (cy - 30) / height},
                {"x": (cx + 96) / width, "y": (cy + 30) / height},
            ],
        }]
    elif watermark_type == "small":
        strokes = [{
            "type": "brush",
            "brushSizeRatio": 30 / width,
            "points": [
                {"x": (cx - 24) / width, "y": cy / height},
                {"x": (cx + 26) / width, "y": cy / height},
            ],
        }]
    else:
        strokes = [{"type": "maskRect", "x": x / width, "y": y / height, "w": w / width, "h": h / height}]
    payload = {
        "version": 2, "coordinateSpace": "normalized", "originalWidth": width, "originalHeight": height,
        "displayWidth": width, "displayHeight": height,
        "strokes": strokes,
    }
    return {
        "id": f"{kind}-{index:02d}", "kind": kind, "watermarkType": watermark_type,
        "clean": clean, "source": marked, "mask": mask, "targetMask": target_mask, "payload": payload,
    }


def masked_mae(image: np.ndarray, reference: np.ndarray, mask: np.ndarray) -> float:
    selected = mask > 0
    return float(np.mean(np.abs(image[selected].astype(np.float32) - reference[selected].astype(np.float32)))) if np.any(selected) else 0.0


def psnr(image: np.ndarray, reference: np.ndarray, mask: np.ndarray) -> float:
    selected = mask > 0
    mse = float(np.mean((image[selected].astype(np.float32) - reference[selected].astype(np.float32)) ** 2)) if np.any(selected) else 0.0
    return 99.0 if mse <= 1e-9 else float(20.0 * math.log10(255.0 / math.sqrt(mse)))


def run_watermark_case(fixture: dict[str, Any], index: int) -> dict[str, Any]:
    case_dir = WATERMARK_OUT / fixture["id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    source_bytes = encode_png(fixture["source"])
    payload_json = json.dumps(fixture["payload"], separators=(",", ":"))
    quick = stroke_inpaint.process_stroke_inpaint(source_bytes, payload_json, quality="quick", strength="medium", preserve_detail=True)
    captures: list[dict[str, Any]] = []
    original_single = hd_inpaint._do_hd_inpaint_single

    def capture_single(img_bytes: bytes, mask_bytes: bytes, *args: Any, **kwargs: Any):
        result = original_single(img_bytes, mask_bytes, *args, **kwargs)
        captures.append({"image": decode_image(img_bytes), "mask": cv2.imdecode(np.frombuffer(mask_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE), "result": decode_image(result["bytes"])})
        return result

    hd_inpaint._do_hd_inpaint_single = capture_single
    started = time.perf_counter()
    try:
        hd = stroke_inpaint.process_stroke_inpaint(
            source_bytes, payload_json, quality="hd", strength="medium", preserve_detail=True,
            request_id=f"final-visual-{index}", smart_expand=False, mask_dilation_px=5,
        )
    finally:
        hd_inpaint._do_hd_inpaint_single = original_single
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    quick_image = decode_image(quick["bytes"])
    final_image = decode_image(hd["bytes"])
    user_mask, _ = stroke_inpaint.build_mask_from_strokes(fixture["payload"], final_image.shape[1], final_image.shape[0])
    allowed = cv2.dilate(user_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)), iterations=1)
    outside = allowed == 0
    target_mask = cv2.dilate(
        fixture["targetMask"], cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1
    )
    source_error = masked_mae(fixture["source"], fixture["clean"], target_mask)
    quick_error = masked_mae(quick_image, fixture["clean"], target_mask)
    final_error = masked_mae(final_image, fixture["clean"], target_mask)
    outside_changes = int(np.count_nonzero(np.any(final_image[outside] != fixture["source"][outside], axis=1)))
    debug = hd.get("debug") or {}
    first_score = float(debug.get("firstPassResidualScore") or 0)
    final_score = float(debug.get("finalResidualScore") or 0)
    second_triggered = bool(debug.get("secondPassTriggered"))
    checks = {
        "maskedResidualReduced": final_error <= source_error * 0.90,
        "outsideAllowedMaskUnchanged": outside_changes == 0 and int(debug.get("outsideAllowedMaskChangedPixels") or 0) == 0,
        "sizePreserved": final_image.shape == fixture["source"].shape,
        "hdNotWorseThanQuick": final_error <= quick_error * 1.15 + 2.0,
        "realHdModel": hd.get("engine") == "lama" and hd.get("fallbackUsed") is False,
        "strictLocal": debug.get("maskPolicy") == "strict_local" and debug.get("smartExpand") is False,
        "residualImprovedWhenRetried": (
            (not second_triggered)
            or (bool(debug.get("secondPassAccepted")) and final_score < first_score)
            or (not bool(debug.get("secondPassAccepted")) and final_score <= first_score + 1e-6)
        ),
        "atMostTwoLamaCalls": int(debug.get("lamaCallCount") or 0) <= 2,
        "residualMaskInsideAllowed": int(debug.get("residualOutsideAllowedPixels") or 0) == 0,
    }
    save_png(case_dir / "original.png", fixture["source"])
    save_png(case_dir / "clean.png", fixture["clean"])
    save_png(case_dir / "mask.png", allowed)
    save_png(case_dir / "quick.png", quick_image)
    save_png(case_dir / "final.png", final_image)
    if captures:
        save_png(case_dir / "first-lama.png", captures[0]["result"])
    if len(captures) > 1:
        save_png(case_dir / "residual-mask.png", captures[1]["mask"])
    else:
        save_png(case_dir / "residual-mask.png", np.zeros((64, 64), dtype=np.uint8))
    return {
        "id": fixture["id"], "kind": fixture["kind"], "watermarkType": fixture["watermarkType"],
        "passed": all(checks.values()), "checks": checks, "elapsedMs": elapsed_ms,
        "metrics": {
            "sourceMaskedMAE": round(source_error, 4), "quickMaskedMAE": round(quick_error, 4),
            "finalMaskedMAE": round(final_error, 4), "outsideChangedPixels": outside_changes,
            "psnr": round(psnr(final_image, fixture["clean"], target_mask), 4),
            "firstResidualScore": first_score, "finalResidualScore": final_score,
        },
        "debug": debug, "artifacts": {"directory": str(case_dir)},
    }


def watermark_evidence_frame(row: dict[str, Any]) -> Image.Image:
    directory = Path(row["artifacts"]["directory"])
    names = ["original", "mask", "first-lama", "residual-mask", "final", "clean"]
    frame = Image.new("RGB", (6 * 205, 205), "white")
    for index, name in enumerate(names):
        path = directory / f"{name}.png"
        image = Image.open(path).convert("RGB")
        image.thumbnail((190, 160), Image.Resampling.LANCZOS)
        frame.paste(image, (index * 205 + (205 - image.width) // 2, 6))
        ImageDraw.Draw(frame).text((index * 205 + 6, 178), name, fill=(20, 28, 38), font=ImageFont.load_default())
    return frame


def run_watermarks(seed: int, count: int) -> dict[str, Any]:
    rows = []
    for index in range(count):
        row = run_watermark_case(make_watermark_fixture(index, seed), index)
        rows.append(row)
        print(f"[watermark] {row['id']} passed={row['passed']} twoPass={row['debug'].get('secondPassTriggered')} ms={row['elapsedMs']}", flush=True)
    failures = [row for row in rows if not row["passed"]]
    one_pass = sum(1 for row in rows if not row["debug"].get("secondPassTriggered"))
    two_pass = len(rows) - one_pass
    summary = {
        "seed": seed, "watermarkSamples": len(rows), "watermarkOutsideMaskFailures": sum(1 for row in rows if not row["checks"]["outsideAllowedMaskUnchanged"]),
        "watermarkResidualFailures": len(failures), "watermarkOnePassCount": one_pass, "watermarkTwoPassCount": two_pass,
        "passed": len(rows) == count and not failures, "rows": rows,
    }
    write_json(REPORT / "watermark-random-30.json", summary)
    save_contact_sheet([watermark_evidence_frame(row) for row in rows[: min(15, len(rows))]], REPORT / "watermark-contact-sheet.jpg", 1)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("portrait", "watermark", "all"), default="all")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--seed", type=int, default=20260807)
    parser.add_argument("--portrait-count", type=int, default=100)
    parser.add_argument("--watermark-count", type=int, default=30)
    args = parser.parse_args()
    REPORT.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"seed": args.seed}
    if args.mode in {"portrait", "all"}:
        result["portrait"] = run_portraits(args.base_url, args.seed, args.portrait_count)
    if args.mode in {"watermark", "all"}:
        result["watermark"] = run_watermarks(args.seed, args.watermark_count)
    result["passed"] = all(value.get("passed") for key, value in result.items() if isinstance(value, dict) and key != "seed")
    print(json.dumps({"passed": result["passed"], "report": str(REPORT)}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
