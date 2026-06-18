from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "id-photo-multi-engine-reset"
ARTIFACT_DIR = REPORT_DIR / "negative-samples"
REPORT_JSON = REPORT_DIR / "negative-samples-report.json"
REPORT_MD = REPORT_DIR / "negative-samples-report.md"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def save_image(name: str, image: Image.Image) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / f"{name}.jpg"
    image.convert("RGB").save(path, quality=92)
    return path


def make_samples() -> list[tuple[str, Path]]:
    samples: list[tuple[str, Path]] = []

    img = Image.new("RGB", (600, 800), "#dfe7ff")
    d = ImageDraw.Draw(img)
    d.ellipse((210, 120, 390, 300), fill="#ffd3bd", outline="#2b2b2b", width=5)
    d.rectangle((160, 310, 440, 620), fill="#6aa7ff")
    d.ellipse((250, 190, 275, 215), fill="#111")
    d.ellipse((325, 190, 350, 215), fill="#111")
    d.arc((260, 215, 340, 265), 0, 180, fill="#111", width=4)
    samples.append(("anime_cartoon", save_image("anime_cartoon", img)))

    img = Image.new("RGB", (600, 800), "#f4ead8")
    d = ImageDraw.Draw(img)
    d.ellipse((160, 180, 440, 520), fill="#9a6b3d")
    d.ellipse((120, 140, 230, 260), fill="#9a6b3d")
    d.ellipse((370, 140, 480, 260), fill="#9a6b3d")
    d.ellipse((230, 300, 260, 330), fill="#111")
    d.ellipse((340, 300, 370, 330), fill="#111")
    samples.append(("animal_pet", save_image("animal_pet", img)))

    img = Image.new("RGB", (800, 500), "#cbe9ff")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 290, 800, 500), fill="#62a85e")
    d.polygon([(0, 300), (220, 80), (440, 300)], fill="#9d9d9d")
    d.polygon([(320, 300), (560, 70), (800, 300)], fill="#8d8d8d")
    samples.append(("landscape", save_image("landscape", img)))

    img = Image.new("RGB", (600, 800), "#f7f7f7")
    d = ImageDraw.Draw(img)
    d.rectangle((160, 180, 440, 560), fill="#1e293b")
    d.rectangle((220, 240, 380, 500), fill="#f59e0b")
    samples.append(("object_only", save_image("object_only", img)))

    img = Image.new("RGB", (900, 600), "#ececec")
    d = ImageDraw.Draw(img)
    for offset in [160, 360, 560]:
        d.ellipse((offset, 120, offset + 120, 240), fill="#f4c7b5")
        d.rectangle((offset - 20, 250, offset + 140, 470), fill="#334155")
    samples.append(("multi_people_schematic", save_image("multi_people_schematic", img)))

    img = Image.new("RGB", (600, 800), "#e2e8f0")
    d = ImageDraw.Draw(img)
    d.ellipse((240, 150, 420, 340), fill="#f2c6ad")
    d.polygon([(280, 160), (420, 250), (300, 350)], fill="#d3a087")
    d.rectangle((210, 360, 450, 650), fill="#475569")
    samples.append(("side_face_schematic", save_image("side_face_schematic", img)))

    img = Image.new("RGB", (600, 800), "#f1f5f9")
    d = ImageDraw.Draw(img)
    d.ellipse((200, 130, 400, 330), fill="#f2c6ad")
    d.rectangle((190, 165, 410, 250), fill="#111827")
    d.rectangle((160, 350, 440, 650), fill="#2563eb")
    samples.append(("face_occluded", save_image("face_occluded", img)))

    img = Image.new("RGB", (600, 800), "#ffffff")
    d = ImageDraw.Draw(img)
    d.ellipse((270, 250, 330, 310), fill="#f2c6ad")
    d.rectangle((250, 315, 350, 460), fill="#334155")
    samples.append(("face_too_small", save_image("face_too_small", img)))

    img = Image.new("RGB", (600, 800), "#e5e7eb")
    d = ImageDraw.Draw(img)
    d.ellipse((170, 120, 430, 380), fill="#f2c6ad")
    d.rectangle((0, 360, 600, 800), fill="#64748b")
    samples.append(("missing_shoulders", save_image("missing_shoulders", img)))

    img = Image.new("RGB", (600, 800), "#dedede")
    d = ImageDraw.Draw(img)
    d.ellipse((190, 140, 410, 360), fill="#f2c6ad")
    d.rectangle((150, 370, 450, 650), fill="#0f172a")
    img = img.filter(ImageFilter.GaussianBlur(radius=9))
    samples.append(("blurred_input", save_image("blurred_input", img)))

    return samples


def call_prepare(base_url: str, sample_path: Path) -> tuple[int, dict[str, Any]]:
    with sample_path.open("rb") as handle:
        files = {"image": (sample_path.name, handle, "image/jpeg")}
        data = {"purpose": "official_id_photo", "specId": "one_inch", "widthPx": "295", "heightPx": "413"}
        response = requests.post(base_url.rstrip("/") + "/api/id-photo/prepare", files=files, data=data, timeout=45)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text[:1000]}
    return response.status_code, payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    rows = []
    false_pass = 0
    for name, path in make_samples():
        status, payload = call_prepare(args.base_url, path)
        passed = bool(payload.get("success") and payload.get("preparedId"))
        if passed:
            false_pass += 1
        rows.append({
            "name": name,
            "path": str(path),
            "status": status,
            "falsePass": passed,
            "code": payload.get("code"),
            "message": payload.get("message"),
            "requestId": payload.get("requestId"),
        })

    report = {
        "status": "PASS" if false_pass == 0 else "FAIL",
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "baseUrl": args.base_url,
        "total": len(rows),
        "falsePass": false_pass,
        "samples": rows,
    }
    write_json(REPORT_JSON, report)

    lines = [
        "# ID Photo Negative Samples Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Base URL: `{args.base_url}`",
        f"- Total negative samples: `{report['total']}`",
        f"- False pass: `{false_pass}`",
        "",
        "## Samples",
    ]
    for row in rows:
        lines.append(f"- [{' ' if row['falsePass'] else 'x'}] {row['name']}: status `{row['status']}`, code `{row.get('code')}`, message `{row.get('message')}`")
    write_md(REPORT_MD, lines)
    print(f"[verify-id-photo-negative-samples] {report['status']} falsePass={false_pass}")
    return 0 if false_pass == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
