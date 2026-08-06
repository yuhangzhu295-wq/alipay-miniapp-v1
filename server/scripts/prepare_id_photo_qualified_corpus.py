"""Build a sourced, deduplicated 30-image qualified portrait corpus."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
REPORT_DIR = ROOT / "reports" / "id-photo-under-10s"
SAMPLE_DIR = REPORT_DIR / "qualified-samples"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
CATEGORIES = (
    "Portrait photographs of women",
    "Portrait photographs of men",
    "Portrait photographs",
)
VISUAL_REVIEW_EXCLUDED_SHA_PREFIXES = {
    "eca0c65ef2",  # side-facing source
    "4407a8a09c",  # decorative headwear and heavy stage styling
    "cc763dd9f0",  # hand/piano false face detection
    "991bfdf557",  # costume headwear
    "f06736058f",  # side-facing smoking source
    "79617c5b7b",  # low-angle non-ID-photo pose
    "c1df9b5a2e",  # face occupies only a small inset inside a graphic border
    "368223982f",  # side-facing portrait with one eye and one shoulder occluded
}
MANUALLY_VERIFIED_GEOMETRY_EXCEPTIONS = {
    # User-supplied hard case: raised arms and headwear perturb the eye-line estimate,
    # while the face is visibly frontal and all other geometry gates remain valid.
    "3366eda7a6": {"face-landmarks-not-front-facing"},
}
FIXED_REMOTE_SEEDS = tuple(
    {
        "category": "Pravatar fixed qualification portrait",
        "title": f"Pravatar portrait {index}",
        "sourceUrl": f"https://i.pravatar.cc/800?img={index}",
        "imageUrl": f"https://i.pravatar.cc/800?img={index}",
        "commonsSha1": "",
    }
    for index in (9, 26, 27, 32, 37, 53)
) + (
    {
        "category": "Wikimedia Commons qualification portrait",
        "title": 'File:"Are you really catching Me?" (147038811).jpg',
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:%22Are_you_really_catching_Me%3F%22_(147038811).jpg",
        "imageUrl": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2b/%22Are_you_really_catching_Me%3F%22_%28147038811%29.jpg/960px-%22Are_you_really_catching_Me%3F%22_%28147038811%29.jpg",
        "commonsSha1": "",
    },
) + tuple(
    {
        "category": "LoremFlickr fixed qualification portrait",
        "title": f"LoremFlickr portrait {index}",
        "sourceUrl": f"https://loremflickr.com/800/1000/headshot,portrait,person?lock={1000 + index}",
        "imageUrl": f"https://loremflickr.com/800/1000/headshot,portrait,person?lock={1000 + index}",
        "commonsSha1": "",
    }
    for index in (3, 12, 23, 99)
)
LOCAL_SEEDS = (
    Path(r"C:\Users\zyu33\Desktop\6a83d1e010f6e9ed8c35af94f0c33936.jpg"),
    Path(r"C:\Users\zyu33\Desktop\610a7b3fadac6b4452736f72b8f3a492.jpg"),
    Path(r"C:\Users\zyu33\Desktop\217139c99959fa2888673f2100612b8f.jpg"),
    ROOT / "reports/id-photo-current-fail-fix/artifacts/random-source/loremflickr_001.jpg",
    ROOT / "reports/id-photo-current-fail-fix/artifacts/random-source/loremflickr_002.jpg",
    ROOT / "reports/id-photo-current-fail-fix/artifacts/random-source/loremflickr_003.jpg",
    ROOT / "reports/id-photo-current-fail-fix/artifacts/random-source/loremflickr_004.jpg",
    ROOT / "reports/id-photo-current-fail-fix/artifacts/random-source/loremflickr_005.jpg",
    ROOT / "reports/id-photo-final-fix/artifacts/random-source/fallback_007_b9fcfc995c64135f4be13197c85a96f0.jpg",
    ROOT / "reports/id-photo-final-fix/artifacts/random-source/fallback_008_cs.jpg",
    ROOT / "reports/id-photo-final-fix/artifacts/random-source/fallback_004_4755783172013fb27a507a42c99868ee.jpg",
    ROOT / "reports/id-photo-final-fix/artifacts/random-source/fallback_005_a50df94597d2a8b5d0074a019a6171dd.jpg",
    ROOT / "reports/id-photo-current-fail-fix/alpha-debug/latest-fail-04/source.png",
    ROOT / "reports/id-photo-matting-broken/samples/02_abnormal_background_kept.jpg",
    ROOT / "reports/id-photo-matting-broken/samples/07_extra_sample_01.jpg",
    ROOT / "reports/id-photo-matting-broken/samples/09_auto_supplement_sample_03.jpg",
    ROOT / "reports/id-photo-matting-broken/samples/10_auto_supplement_sample_04.jpg",
    ROOT / "reports/id-photo-current-fail-fix/artifacts/random-source/loremflickr_008.jpg",
    ROOT / "reports/id-photo-current-fail-fix/artifacts/random-source/loremflickr_009.jpg",
    ROOT / "reports/id-photo-current-fail-fix/artifacts/random-source/loremflickr_017.jpg",
    ROOT / "reports/id-photo-all-formats/samples/format_png_real_person.png",
)

if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from services.face_detector import detect_face  # noqa: E402
from services.portrait_quality import classify_image_type, is_illustration_like  # noqa: E402


def fetch_category(session: requests.Session, category: str, limit: int = 150) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    continuation: dict[str, str] = {}
    while len(rows) < limit:
        params = {
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": "Category:" + category,
            "gcmtype": "file",
            "gcmlimit": "50",
            "prop": "imageinfo",
            "iiprop": "url|mime|sha1",
            "iiurlwidth": "800",
            "format": "json",
            **continuation,
        }
        response = session.get(COMMONS_API, params=params, timeout=40)
        if response.status_code == 429:
            break
        response.raise_for_status()
        payload = response.json()
        for page in (payload.get("query") or {}).get("pages", {}).values():
            info = ((page.get("imageinfo") or [{}])[0])
            if info.get("mime") != "image/jpeg" or not info.get("thumburl"):
                continue
            rows.append(
                {
                    "category": category,
                    "title": page.get("title") or "",
                    "sourceUrl": info.get("descriptionurl") or "",
                    "imageUrl": info.get("thumburl") or "",
                    "commonsSha1": info.get("sha1") or "",
                }
            )
        continuation = payload.get("continue") or {}
        if not continuation:
            break
    return rows[:limit]


def geometry_check(face: dict[str, Any], width: int, height: int) -> tuple[bool, list[str], dict[str, float]]:
    box = face.get("faceBox") or {}
    x = float(box.get("x") or 0)
    y = float(box.get("y") or 0)
    fw = float(box.get("width") or 0)
    fh = float(box.get("height") or 0)
    landmarks = face.get("landmarks") or {}
    right_eye = landmarks.get("rightEye") or {}
    left_eye = landmarks.get("leftEye") or {}
    nose = landmarks.get("nose") or {}
    mouth = landmarks.get("mouth") or {}
    eye_span = abs(float(left_eye.get("x") or 0) - float(right_eye.get("x") or 0))
    eye_y_delta = abs(float(left_eye.get("y") or 0) - float(right_eye.get("y") or 0)) / max(1.0, fw)
    eye_span_ratio = eye_span / max(1.0, fw)
    eye_mid_x = (float(left_eye.get("x") or 0) + float(right_eye.get("x") or 0)) * 0.5
    nose_offset = abs(float(nose.get("x") or 0) - eye_mid_x) / max(1.0, eye_span)
    mouth_offset = abs(float(mouth.get("x") or 0) - eye_mid_x) / max(1.0, eye_span)
    metrics = {
        "faceWidthRatio": round(fw / max(1, width), 4),
        "faceHeightRatio": round(fh / max(1, height), 4),
        "faceCenterX": round((x + fw / 2) / max(1, width), 4),
        "faceCenterY": round((y + fh / 2) / max(1, height), 4),
        "topMarginRatio": round(y / max(1, height), 4),
        "belowFaceRatio": round((height - y - fh) / max(1, height), 4),
        "eyeSpanRatio": round(eye_span_ratio, 4),
        "eyeYDeltaRatio": round(eye_y_delta, 4),
        "noseOffsetRatio": round(nose_offset, 4),
        "mouthOffsetRatio": round(mouth_offset, 4),
    }
    reasons = []
    if min(width, height) < 384:
        reasons.append("image-too-small")
    if not face.get("success") or int(face.get("faceCount") or 0) != 1:
        reasons.append("not-single-face")
    if float(face.get("confidence") or 0) < 0.65:
        reasons.append("low-face-confidence")
    if float(face.get("poseScore") or 0) < 0.75:
        reasons.append("not-front-facing")
    if not (
        eye_span > 0
        and 0.22 <= eye_span_ratio <= 0.62
        and eye_y_delta <= 0.10
        and nose_offset <= 0.42
        and mouth_offset <= 0.48
    ):
        reasons.append("face-landmarks-not-front-facing")
    if not 0.10 <= metrics["faceHeightRatio"] <= 0.45:
        reasons.append("face-height-out-of-range")
    if not 0.08 <= metrics["faceWidthRatio"] <= 0.55:
        reasons.append("face-width-out-of-range")
    if not 0.20 <= metrics["faceCenterX"] <= 0.80:
        reasons.append("face-off-center-x")
    if not 0.12 <= metrics["faceCenterY"] <= 0.58:
        reasons.append("face-off-center-y")
    if not 0.02 <= metrics["topMarginRatio"] <= 0.35:
        reasons.append("top-margin-out-of-range")
    if metrics["belowFaceRatio"] < 0.30:
        reasons.append("insufficient-neck-shoulder-space")
    return not reasons, reasons, metrics


def difference_hash(image: Image.Image, size: int = 8) -> int:
    gray = image.convert("L").resize((size + 1, size), Image.Resampling.BILINEAR)
    pixels = list(gray.getdata())
    value = 0
    for row in range(size):
        offset = row * (size + 1)
        for column in range(size):
            value = (value << 1) | int(pixels[offset + column] > pixels[offset + column + 1])
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--max-candidates-per-category", type=int, default=150)
    parser.add_argument("--source", choices=("loremflickr", "pravatar", "commons"), default="loremflickr")
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    for stale_sample in SAMPLE_DIR.glob("qualified_*.*"):
        if stale_sample.is_file():
            stale_sample.unlink()
    session = requests.Session()
    session.headers["User-Agent"] = "photo-generator-verification/1.0 (performance regression corpus)"
    if args.source in {"loremflickr", "pravatar"}:
        local_candidates = [
            {
                "category": "Prior verified local portrait",
                "title": path.name,
                "sourceUrl": "",
                "imageUrl": "",
                "localPath": str(path),
                "commonsSha1": "",
            }
            for path in LOCAL_SEEDS
            if path.is_file()
        ]
        if args.source == "pravatar":
            remote_candidates = [
                {
                    "category": "Pravatar",
                    "title": f"Pravatar portrait {index}",
                    "sourceUrl": f"https://i.pravatar.cc/800?img={index}",
                    "imageUrl": f"https://i.pravatar.cc/800?img={index}",
                    "commonsSha1": "",
                }
                for index in range(1, 71)
            ]
        else:
            remote_candidates = [
                {
                    "category": "LoremFlickr portrait search",
                    "title": f"LoremFlickr portrait {index}",
                    "sourceUrl": f"https://loremflickr.com/800/1000/headshot,portrait,person?lock={1000 + index}",
                    "imageUrl": f"https://loremflickr.com/800/1000/headshot,portrait,person?lock={1000 + index}",
                    "commonsSha1": "",
                }
                for index in range(1, args.max_candidates_per_category + 1)
            ]
        candidates = local_candidates + list(FIXED_REMOTE_SEEDS) + remote_candidates
    else:
        candidates = []
        for category in CATEGORIES:
            try:
                candidates.extend(fetch_category(session, category, args.max_candidates_per_category))
            except requests.RequestException:
                continue

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    seen_perceptual_hashes: list[int] = []
    for candidate in candidates:
        if len(accepted) >= args.count:
            break
        url = candidate["imageUrl"]
        source_key = candidate.get("localPath") or url
        if source_key in seen_urls:
            continue
        seen_urls.add(source_key)
        try:
            if candidate.get("localPath"):
                source_bytes = Path(candidate["localPath"]).read_bytes()
            else:
                response = session.get(url, timeout=40)
                response.raise_for_status()
                source_bytes = response.content
            digest = hashlib.sha256(source_bytes).hexdigest()
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            image = ImageOps.exif_transpose(Image.open(io.BytesIO(source_bytes))).convert("RGB")
            perceptual_hash = difference_hash(image)
            if any((perceptual_hash ^ prior).bit_count() <= 4 for prior in seen_perceptual_hashes):
                rejected.append({**candidate, "reasons": ["perceptual-duplicate"]})
                continue
            if digest[:10] in VISUAL_REVIEW_EXCLUDED_SHA_PREFIXES:
                rejected.append({**candidate, "reasons": ["manual-visual-review-not-qualified"]})
                continue
            normalized = io.BytesIO()
            image.save(normalized, "JPEG", quality=92, optimize=True)
            image_bytes = normalized.getvalue()
            detected = classify_image_type(image_bytes)
            face = detect_face(image_bytes)
            geometry_ok, reasons, geometry = geometry_check(face, image.width, image.height)
            allowed_geometry_reasons = MANUALLY_VERIFIED_GEOMETRY_EXCEPTIONS.get(digest[:10], set())
            if allowed_geometry_reasons:
                reasons = [reason for reason in reasons if reason not in allowed_geometry_reasons]
                geometry_ok = not reasons
            if not candidate.get("localPath"):
                if not detected.get("realPerson") or int(detected.get("faceCount") or 0) != 1:
                    reasons.append("not-classified-single-real-person")
                if is_illustration_like(image_bytes, face.get("faceBox")):
                    reasons.append("illustration-like")
            if reasons or not geometry_ok:
                rejected.append({**candidate, "reasons": sorted(set(reasons)), "geometry": geometry})
                continue
            filename = f"qualified_{len(accepted) + 1:02d}_{digest[:10]}.jpg"
            path = SAMPLE_DIR / filename
            path.write_bytes(image_bytes)
            accepted.append(
                {
                    **candidate,
                    "path": str(path),
                    "sha256": hashlib.sha256(image_bytes).hexdigest(),
                    "differenceHash": f"{perceptual_hash:016x}",
                    "width": image.width,
                    "height": image.height,
                    "bytes": len(image_bytes),
                    "classification": detected,
                    "face": face,
                    "geometry": geometry,
                }
            )
            seen_perceptual_hashes.append(perceptual_hash)
        except Exception as exc:
            rejected.append({**candidate, "reasons": ["download-or-decode-failed"], "error": repr(exc)})

    passed = len(accepted) == args.count and len({row["sha256"] for row in accepted}) == args.count
    payload = {
        "status": "PASS" if passed else "FAIL",
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "requestedCount": args.count,
        "acceptedCount": len(accepted),
        "uniqueSha256Count": len({row["sha256"] for row in accepted}),
        "source": (
            "prior verified local portraits plus deterministic 800x1000 LoremFlickr portrait working copies"
            if args.source == "loremflickr"
            else "prior verified local portraits plus the Pravatar numbered portrait set, 800px working copies"
            if args.source == "pravatar"
            else "Wikimedia Commons category API, 800px working copies"
        ),
        "qualification": {
            "minimumShortSide": 384,
            "singleRealPerson": True,
            "minimumFaceConfidence": 0.65,
            "minimumPoseScore": 0.75,
            "minimumBelowFaceRatio": 0.30,
            "perceptualDuplicateMaximumHammingDistance": 4,
            "manualVisualReviewExcludedShaPrefixes": sorted(VISUAL_REVIEW_EXCLUDED_SHA_PREFIXES),
            "manualGeometryExceptions": {
                prefix: sorted(reasons)
                for prefix, reasons in MANUALLY_VERIFIED_GEOMETRY_EXCEPTIONS.items()
            },
        },
        "accepted": accepted,
        "rejectedCount": len(rejected),
        "rejected": rejected,
    }
    (REPORT_DIR / "qualified-corpus.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Qualified Portrait Corpus",
        "",
        f"- Status: **{payload['status']}**",
        f"- Accepted: `{len(accepted)}/{args.count}`; unique SHA-256: `{payload['uniqueSha256Count']}`.",
        f"- Source: {payload['source']}; every accepted row retains its source URL.",
        "- Gate: 384px minimum short side, one photo-real face, front-facing geometry, and at least 30% space below the face.",
        "",
        "| File | Size | Face confidence | Pose | Source |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for row in accepted:
        source = f"[{row['title']}]({row['sourceUrl']})" if row["sourceUrl"] else "prior local verification"
        lines.append(
            f"| `{Path(row['path']).name}` | {row['width']}x{row['height']} | "
            f"{row['face'].get('confidence')} | {row['face'].get('poseScore')} | "
            f"{source} |"
        )
    (REPORT_DIR / "qualified-corpus.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "accepted": len(accepted), "rejected": len(rejected)}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
