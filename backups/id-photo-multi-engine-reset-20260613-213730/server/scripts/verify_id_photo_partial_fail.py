from __future__ import annotations

import argparse
import json
import mimetypes
import shutil
import sys
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "current-fixes"
FINAL_DIR = REPORT_ROOT / "final"
SOURCE_DIR = REPORT_ROOT / "id-photo-samples" / "source"
OUTPUT_DIR = REPORT_ROOT / "id-photo-samples" / "output"
NEGATIVE_DIR = REPORT_ROOT / "id-photo-samples" / "negative"
FAIL_SAMPLE_DIR = Path(r"C:\Users\zyu33\Desktop\idphoto-fail-samples")

BG_COLORS = {
    "blue": "#2F80ED",
    "white": "#FFFFFF",
    "red": "#D9001B",
    "lightBlue": "#8FD3FF",
    "gray": "#BFC3CA",
}

FALLBACK_CANDIDATES = [
    Path(r"C:\Users\zyu33\Desktop\b9fcfc995c64135f4be13197c85a96f0.jpg"),
    Path(r"C:\Users\zyu33\Desktop\cs.jpeg"),
]


def _json_response(res: requests.Response) -> dict[str, Any]:
    try:
        data = res.json()
    except Exception:
        data = {"raw": res.text[:500]}
    data["_statusCode"] = res.status_code
    return data


def _image_meta(path: Path) -> dict[str, Any]:
    with Image.open(path) as img:
        exif = img.getexif()
        orientation = exif.get(274, "")
        normalized = ImageOps.exif_transpose(img)
        return {
            "filename": path.name,
            "format": img.format,
            "size": f"{img.width}x{img.height}",
            "fileSize": path.stat().st_size,
            "mime": mimetypes.guess_type(str(path))[0] or "unknown",
            "mode": img.mode,
            "exifOrientation": orientation,
            "normalizedMode": normalized.convert("RGB").mode,
            "normalizedSize": f"{normalized.width}x{normalized.height}",
            "hasAlpha": img.mode in {"RGBA", "LA"} or ("transparency" in img.info),
        }


def _copy_sample(path: Path, label: str) -> Path:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    target = SOURCE_DIR / f"{label}-{path.name}"
    if path.resolve() != target.resolve():
        shutil.copy2(path, target)
    return target


def _prepare(base_url: str, image_path: Path) -> dict[str, Any]:
    with image_path.open("rb") as f:
        res = requests.post(
            base_url.rstrip("/") + "/api/id-photo/prepare",
            files={"image": (image_path.name, f, mimetypes.guess_type(str(image_path))[0] or "image/jpeg")},
            data={
                "purpose": "official_id_photo",
                "specId": "yicun",
                "widthPx": "295",
                "heightPx": "413",
                "widthMm": "25",
                "heightMm": "35",
                "mode": "official",
                "composition": "head_shoulder",
            },
            timeout=45,
        )
    return _json_response(res)


def _compose(base_url: str, prepared_id: str, bg_name: str, bg_hex: str) -> dict[str, Any]:
    res = requests.post(
        base_url.rstrip("/") + "/api/id-photo/compose",
        data={
            "preparedId": prepared_id,
            "bgColor": bg_hex,
            "bgColorName": bg_name,
            "outputType": "jpg",
        },
        timeout=35,
    )
    return _json_response(res)


def _download(base_url: str, image_url: str, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    url = image_url if image_url.startswith("http") else base_url.rstrip("/") + image_url
    res = requests.get(url, timeout=30)
    target.write_bytes(res.content)
    ok = res.status_code == 200 and target.exists() and target.stat().st_size > 0
    info: dict[str, Any] = {"url": url, "path": str(target), "statusCode": res.status_code, "exists": ok}
    if ok:
        with Image.open(target) as img:
            info["size"] = f"{img.width}x{img.height}"
            info["sizePassed"] = img.size == (295, 413)
    return info


def _make_negative() -> Path:
    NEGATIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = NEGATIVE_DIR / "negative-landscape-solid.png"
    img = Image.new("RGB", (640, 420), "#8ecae6")
    img.save(path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    for directory in (FINAL_DIR, SOURCE_DIR, OUTPUT_DIR, NEGATIVE_DIR):
      directory.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "baseUrl": base_url,
        "rawFailSampleDir": str(FAIL_SAMPLE_DIR),
        "rawFailSamplesMissing": False,
        "samples": [],
        "negative": {},
        "health": {},
        "passed": False,
    }

    try:
        health = requests.get(base_url + "/api/health", timeout=10)
        report["health"] = _json_response(health)
    except Exception as exc:
        report["health"] = {"success": False, "error": str(exc)}
        _write_reports(report)
        return 1
    if not report["health"].get("success"):
        _write_reports(report)
        return 1

    raw_samples = []
    if FAIL_SAMPLE_DIR.exists():
        raw_samples = [p for p in FAIL_SAMPLE_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    if not raw_samples:
        report["rawFailSamplesMissing"] = True
        raw_samples = [p for p in FALLBACK_CANDIDATES if p.exists()]

    if not raw_samples:
        report["missingReason"] = "缺少原始失败样本，当前只能根据截图定位现象"
        _write_reports(report)
        return 1

    total_color_checks = 0
    passed_color_checks = 0
    failures: list[str] = []

    for idx, sample in enumerate(raw_samples):
        purpose = "fallback_real_sample" if report["rawFailSamplesMissing"] else "failed_sample"
        copied = _copy_sample(sample, f"{idx+1:02d}-{purpose}")
        row: dict[str, Any] = {
            "filename": sample.name,
            "purpose": "失败样本" if not report["rawFailSamplesMissing"] else "本地 fallback 真人样本",
            "sourcePath": str(sample),
            "localSourceCopy": str(copied),
            "image_load": _image_meta(sample),
            "normalize": {"usedImageOpsExifTranspose": True, "convertedToRGB": True},
            "prepare": {},
            "compose": {},
        }
        prepare = _prepare(base_url, sample)
        row["prepare"] = prepare
        if not (prepare.get("_statusCode") == 200 and prepare.get("success") and prepare.get("preparedId")):
            failures.append(f"{sample.name}: prepare failed {prepare.get('code')}")
            report["samples"].append(row)
            continue
        prepared_id = prepare["preparedId"]
        for bg_name, bg_hex in BG_COLORS.items():
            total_color_checks += 1
            compose = _compose(base_url, prepared_id, bg_name, bg_hex)
            out_name = f"{sample.stem}-{bg_name}.jpg"
            download = {}
            if compose.get("success") and (compose.get("finalImageUrl") or compose.get("imageUrl")):
                download = _download(base_url, compose.get("finalImageUrl") or compose.get("imageUrl"), OUTPUT_DIR / out_name)
            ok = bool(
                compose.get("_statusCode") == 200
                and compose.get("success")
                and download.get("exists")
                and download.get("sizePassed")
            )
            if ok:
                passed_color_checks += 1
            else:
                failures.append(f"{sample.name}:{bg_name}: compose/download/size failed")
            row["compose"][bg_name] = {
                "request": {"bgColor": bg_hex, "bgColorName": bg_name},
                "response": compose,
                "download": download,
                "passed": ok,
            }
        report["samples"].append(row)

    neg = _make_negative()
    negative_prepare = _prepare(base_url, neg)
    report["negative"] = {
        "filename": neg.name,
        "purpose": "负样本",
        "prepare": negative_prepare,
        "rejected": not bool(negative_prepare.get("success")),
    }
    if negative_prepare.get("success"):
        failures.append("negative sample was accepted")

    pass_rate = passed_color_checks / max(1, total_color_checks)
    report["totalColorChecks"] = total_color_checks
    report["passedColorChecks"] = passed_color_checks
    report["passRate"] = round(pass_rate, 4)
    report["failures"] = failures
    report["passed"] = not failures and pass_rate >= 0.95
    _write_reports(report)
    return 0 if report["passed"] else 1


def _write_reports(report: dict[str, Any]) -> None:
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    json_path = FINAL_DIR / "id-photo-sample-validation-report.json"
    md_path = FINAL_DIR / "id-photo-sample-validation-report.md"
    root_path = FINAL_DIR / "id-photo-root-cause.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# ID Photo Partial Fail Validation",
        "",
        f"- Base URL: `{report.get('baseUrl')}`",
        f"- Health: `{report.get('health', {}).get('success')}`",
        f"- Raw fail sample dir: `{report.get('rawFailSampleDir')}`",
        f"- Raw fail samples missing: `{report.get('rawFailSamplesMissing')}`",
    ]
    if report.get("rawFailSamplesMissing"):
        lines.append("- 缺少原始失败样本，当前只能根据截图定位现象；本轮使用本地 fallback 真人样本验证接口链路。")
    lines += [
        f"- Total color checks: `{report.get('totalColorChecks', 0)}`",
        f"- Passed color checks: `{report.get('passedColorChecks', 0)}`",
        f"- Pass rate: `{report.get('passRate', 0)}`",
        f"- Negative rejected: `{report.get('negative', {}).get('rejected')}`",
        f"- Passed: `{report.get('passed')}`",
        "",
        "## Samples",
    ]
    for sample in report.get("samples", []):
        lines.append(f"- `{sample.get('filename')}` | purpose={sample.get('purpose')} | prepare={sample.get('prepare', {}).get('success')}")
        for bg, info in (sample.get("compose") or {}).items():
            lines.append(f"  - {bg}: passed={info.get('passed')} output={info.get('download', {}).get('path', '')}")
    lines += ["", "## Failures", *(f"- {item}" for item in report.get("failures", []))]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    root_lines = [
        "# ID Photo Root Cause",
        "",
        "- 现象截图显示底色页在 compose 阶段失败，而非上传入口完全不可用。",
        "- 后端 compose 原超时为 5 秒，前端 request 原超时为 8 秒；部分图片预处理成功但合成耗时稍长时，会被前端直接判定为底色生成失败。",
        "- 本轮修复：统一本地/云端 API 地址选择、后端 compose 超时提升至 20 秒、前端 compose 超时提升至 25 秒，并对 compose 做一次重试且保留 prepared foreground。",
    ]
    root_path.write_text("\n".join(root_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
