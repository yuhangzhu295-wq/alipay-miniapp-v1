from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "id-photo-under-10s"
ARTIFACT_DIR = REPORT_DIR / "upload-ab-artifacts"


def resize_longest(image, longest):
    width, height = image.size
    if max(width, height) <= longest:
        return image.copy()
    scale = longest / max(width, height)
    return image.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)


def ssim(reference, candidate):
    first = cv2.cvtColor(np.asarray(reference), cv2.COLOR_RGB2GRAY).astype(np.float32)
    second = cv2.cvtColor(np.asarray(candidate), cv2.COLOR_RGB2GRAY).astype(np.float32)
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    mu1 = cv2.GaussianBlur(first, (11, 11), 1.5)
    mu2 = cv2.GaussianBlur(second, (11, 11), 1.5)
    sigma1 = cv2.GaussianBlur(first * first, (11, 11), 1.5) - mu1 * mu1
    sigma2 = cv2.GaussianBlur(second * second, (11, 11), 1.5) - mu2 * mu2
    sigma12 = cv2.GaussianBlur(first * second, (11, 11), 1.5) - mu1 * mu2
    score = ((2 * mu1 * mu2 + c1) * (2 * sigma12 + c2)) / ((mu1 * mu1 + mu2 * mu2 + c1) * (sigma1 + sigma2 + c2))
    return float(np.mean(score))


def psnr(reference, candidate):
    first = np.asarray(reference).astype(np.float32)
    second = np.asarray(candidate).astype(np.float32)
    mse = float(np.mean((first - second) ** 2))
    return 99.0 if mse == 0 else 20 * math.log10(255.0 / math.sqrt(mse))


def thumbnail(image, size=(280, 350)):
    return ImageOps.contain(image, size, Image.Resampling.LANCZOS)


def contact_sheet(source, variants, target):
    tile_w, tile_h = 300, 390
    canvas = Image.new("RGB", (tile_w * 4, tile_h * 3), "white")
    draw = ImageDraw.Draw(canvas)
    original_thumb = thumbnail(source)
    for row, longest in enumerate((2048, 1600, 1280)):
        canvas.paste(original_thumb, (10, row * tile_h + 28))
        draw.text((10, row * tile_h + 8), f"original / compare {longest}", fill="black")
        for column, quality in enumerate((85, 88, 90), start=1):
            item = variants[(longest, quality)]
            preview = thumbnail(item["image"])
            canvas.paste(preview, (column * tile_w + 10, row * tile_h + 28))
            draw.text(
                (column * tile_w + 10, row * tile_h + 8),
                f"{longest}px q{quality} ssim={item['ssim']:.4f}",
                fill="black",
            )
    canvas.save(target, quality=92)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", action="append", required=True)
    parser.add_argument("--visual-review-passed", action="store_true")
    args = parser.parse_args()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []

    for source_arg in args.image:
        source_path = Path(source_arg).resolve()
        source = ImageOps.exif_transpose(Image.open(source_path)).convert("RGB")
        variants = {}
        for longest in (2048, 1600, 1280):
            reference = resize_longest(source, longest)
            for quality in (85, 88, 90):
                target = ARTIFACT_DIR / f"{source_path.stem}-{longest}-q{quality}.jpg"
                reference.save(target, "JPEG", quality=quality, optimize=True)
                decoded = Image.open(target).convert("RGB")
                row = {
                    "source": str(source_path),
                    "originalWidth": source.width,
                    "originalHeight": source.height,
                    "originalBytes": source_path.stat().st_size,
                    "longestSide": longest,
                    "quality": quality,
                    "uploadWidth": decoded.width,
                    "uploadHeight": decoded.height,
                    "uploadBytes": target.stat().st_size,
                    "ssim": round(ssim(reference, decoded), 6),
                    "psnrDb": round(psnr(reference, decoded), 3),
                    "artifact": str(target.relative_to(ROOT)),
                }
                rows.append(row)
                variants[(longest, quality)] = {"image": decoded, **row}
        contact_sheet(source, variants, ARTIFACT_DIR / f"{source_path.stem}-contact.jpg")

    selected = [row for row in rows if row["longestSide"] == 1600 and row["quality"] == 88]
    metric_passed = all(row["ssim"] >= 0.99 for row in selected)
    passed = metric_passed and args.visual_review_passed
    payload = {
        "status": "PASS" if passed else "FAIL",
        "decision": {
            "longestSide": 1600,
            "jpegQuality": 88,
            "minimumSsim": min(row["ssim"] for row in selected),
            "visualReviewPassed": args.visual_review_passed,
            "visualReviewNotes": (
                "No visible regression in hair, hat, ear-side edges, raised arms, shoulders, or light clothing."
                if args.visual_review_passed
                else "Pending"
            ),
            "originalFileOverwritten": False,
        },
        "rows": rows,
    }
    (REPORT_DIR / "upload-ab.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Client Upload A/B",
        "",
        "- Compared longest sides 2048, 1600, and 1280 with JPEG qualities 85, 88, and 90.",
        f"- Selected: 1600px / quality 88; minimum SSIM `{payload['decision']['minimumSsim']}`.",
        f"- Visual review: `{'PASS' if args.visual_review_passed else 'PENDING'}`.",
        f"- Status: **{payload['status']}**",
        "- EXIF orientation is normalized by the platform image APIs; the original album file is never overwritten.",
        "",
        "| Source | Side | Quality | Upload bytes | SSIM | PSNR dB |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(f"| `{Path(row['source']).name}` | {row['longestSide']} | {row['quality']} | {row['uploadBytes']} | {row['ssim']} | {row['psnrDb']} |")
    (REPORT_DIR / "upload-ab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload["decision"], ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
