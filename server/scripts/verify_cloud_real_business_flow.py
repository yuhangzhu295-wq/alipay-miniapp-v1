from __future__ import annotations

import argparse
import hashlib
import json
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageChops, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_URL = "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/lena.jpg"
BG_COLORS = {
    "blue": "#1a73e8",
    "white": "#ffffff",
    "red": "#e53935",
    "lightBlue": "#81d4fa",
    "gray": "#9e9e9e",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def request_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        res = requests.request(method, url, **kwargs)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:800]}
        return {
            "passed": 200 <= res.status_code < 300,
            "statusCode": res.status_code,
            "durationMs": int((time.perf_counter() - started) * 1000),
            "data": data,
        }
    except Exception as exc:
        return {
            "passed": False,
            "statusCode": 0,
            "durationMs": int((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }


def full_url(base_url: str, image_url: str) -> str:
    if image_url.startswith(("http://", "https://")):
        return image_url
    return base_url.rstrip("/") + "/" + image_url.lstrip("/")


def download_image(base_url: str, image_url: str, target: Path) -> dict[str, Any]:
    url = full_url(base_url, image_url)
    started = time.perf_counter()
    try:
        res = requests.get(url, timeout=60)
        data = res.content
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        img = Image.open(BytesIO(data)).convert("RGB")
        return {
            "passed": res.status_code == 200 and len(data) > 0,
            "url": url,
            "statusCode": res.status_code,
            "durationMs": int((time.perf_counter() - started) * 1000),
            "bytes": len(data),
            "sha256": sha256_bytes(data),
            "path": str(target),
            "size": {"width": img.width, "height": img.height},
        }
    except Exception as exc:
        return {"passed": False, "url": url, "error": str(exc)}


def prepare_source_image(source_url: str, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    res = requests.get(
        source_url,
        timeout=60,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; id-photo-cloud-e2e/1.0)",
            "Referer": "https://commons.wikimedia.org/wiki/File:Passport_Pic.jpg",
        },
    )
    res.raise_for_status()
    target.write_bytes(res.content)
    img = Image.open(target).convert("RGB")
    return {
        "sourceUrl": source_url,
        "path": str(target),
        "bytes": len(res.content),
        "sha256": sha256_file(target),
        "size": {"width": img.width, "height": img.height},
    }


def prepare_source_file(source_file: Path, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    data = source_file.read_bytes()
    target.write_bytes(data)
    img = Image.open(target).convert("RGB")
    return {
        "sourceFile": str(source_file),
        "path": str(target),
        "bytes": len(data),
        "sha256": sha256_file(target),
        "size": {"width": img.width, "height": img.height},
    }


def make_watermark_sample(image_path: Path, mask_path: Path) -> dict[str, Any]:
    image_path.parent.mkdir(parents=True, exist_ok=True)
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = 640, 420
    image = Image.new("RGB", (w, h), (235, 241, 248))
    draw = ImageDraw.Draw(image, "RGBA")
    for y in range(h):
        shade = int(245 - 42 * y / h)
        draw.line([(0, y), (w, y)], fill=(shade, shade + 2, min(255, shade + 8)))
    draw.rounded_rectangle([72, 76, 560, 338], radius=18, fill=(255, 255, 255, 180), outline=(158, 174, 192), width=3)
    draw.ellipse([110, 116, 250, 256], fill=(120, 164, 208, 210))
    draw.rectangle([292, 126, 516, 158], fill=(126, 147, 170, 180))
    draw.rectangle([292, 188, 500, 216], fill=(151, 167, 188, 150))
    mask = Image.new("L", (w, h), 0)
    mask_draw = ImageDraw.Draw(mask)
    for x in range(-80, w + 80, 210):
        for y in range(20, h + 80, 120):
            draw.line([(x, y), (x + 160, y + 82)], fill=(95, 95, 95, 110), width=5)
            draw.text((x + 58, y + 28), "WATERMARK", fill=(92, 92, 92, 126))
            mask_draw.line([(x, y), (x + 160, y + 82)], fill=255, width=18)
            mask_draw.rectangle([x + 52, y + 22, x + 168, y + 50], fill=255)
    image.save(image_path, quality=94)
    mask.save(mask_path)
    return {
        "image": str(image_path),
        "mask": str(mask_path),
        "imageSha256": sha256_file(image_path),
        "maskSha256": sha256_file(mask_path),
    }


def post_file(base_url: str, endpoint: str, image_path: Path, extra: dict[str, str] | None = None, timeout: int = 180) -> dict[str, Any]:
    with image_path.open("rb") as fh:
        return request_json(
            "POST",
            base_url.rstrip("/") + endpoint,
            files={"image": (image_path.name, fh, "image/jpeg")},
            data=extra or {},
            timeout=timeout,
        )


def run_id_photo(base_url: str, source_path: Path, artifacts: Path, screenshots: Path) -> dict[str, Any]:
    prepare_attempts: list[dict[str, Any]] = []
    prepare_data = {
        "purpose": "official_id_photo",
        "specId": "yicun",
        "widthPx": "295",
        "heightPx": "413",
        "widthMm": "25",
        "heightMm": "35",
        "imageType": "real_person",
        "mode": "official",
        "composition": "head_shoulder",
        "outfit": "preserve_original",
    }
    prepared_id = ""
    for attempt in range(1, 4):
        with source_path.open("rb") as fh:
            result = request_json(
                "POST",
                base_url.rstrip() + "/api/id-photo/prepare",
                files={"image": (source_path.name, fh, "image/jpeg")},
                data=prepare_data,
                timeout=180,
            )
        result["attempt"] = attempt
        prepare_attempts.append(result)
        data = result.get("data") or {}
        if result["passed"] and data.get("success") and data.get("preparedId"):
            prepared_id = data["preparedId"]
            break
        time.sleep(8)

    compose_rows: list[dict[str, Any]] = []
    if prepared_id:
        for color_id, hex_value in BG_COLORS.items():
            attempts: list[dict[str, Any]] = []
            result: dict[str, Any] = {"passed": False, "statusCode": 0, "error": "not attempted"}
            for attempt in range(1, 4):
                result = request_json(
                    "POST",
                    base_url.rstrip() + "/api/id-photo/compose",
                    data={"preparedId": prepared_id, "bgColor": hex_value, "bgColorName": color_id, "outputType": "jpg"},
                    timeout=180,
                )
                result["attempt"] = attempt
                attempts.append(result)
                data = result.get("data") or {}
                if result.get("passed") and data.get("success"):
                    break
                time.sleep(5)
            data = result.get("data") or {}
            image_url = data.get("resultUrl") or data.get("imageUrl") or ""
            download = {"passed": False, "error": "missing result url"}
            if image_url:
                download = download_image(base_url, image_url, artifacts / f"id-photo-{color_id}.jpg")
            size_ok = bool(download.get("passed")) and download.get("size") == {"width": 295, "height": 413}
            compose_rows.append({"color": color_id, "request": result, "attempts": attempts, "download": download, "sizeOk": size_ok})

    sheet_path = screenshots / "id-photo-cloud-flow.jpg"
    make_contact_sheet(
        [source_path] + [Path(row["download"]["path"]) for row in compose_rows if row["download"].get("passed")],
        sheet_path,
        labels=["source"] + [row["color"] for row in compose_rows if row["download"].get("passed")],
    )
    checks = {
        "preparePassed": bool(prepared_id),
        "fiveBackgroundsComposed": len(compose_rows) == 5 and all(row["request"].get("passed") for row in compose_rows),
        "fiveImagesDownloaded": len(compose_rows) == 5 and all(row["download"].get("passed") for row in compose_rows),
        "allOutputSizes295x413": len(compose_rows) == 5 and all(row["sizeOk"] for row in compose_rows),
        "contactSheetSaved": sheet_path.exists(),
    }
    return {"passed": all(checks.values()), "checks": checks, "preparedId": prepared_id, "prepareAttempts": prepare_attempts, "compose": compose_rows, "screenshot": str(sheet_path)}


def run_watermark(base_url: str, image_path: Path, mask_path: Path, artifacts: Path, screenshots: Path, include_hd: bool) -> dict[str, Any]:
    modes = ["manual", "quick"] + (["hd"] if include_hd else [])
    endpoints = {
        "manual": "/api/watermark/manual-remove",
        "quick": "/api/watermark/quick-remove",
        "hd": "/api/watermark/hd-remove",
    }
    rows: list[dict[str, Any]] = []
    for mode in modes:
        with image_path.open("rb") as image_fh, mask_path.open("rb") as mask_fh:
            result = request_json(
                "POST",
                base_url.rstrip() + endpoints[mode],
                files={
                    "image": (image_path.name, image_fh, "image/jpeg"),
                    "mask": (mask_path.name, mask_fh, "image/png"),
                },
                data={"strength": "medium", "preserveDetail": "true"},
                timeout=240 if mode == "hd" else 120,
            )
        data = result.get("data") or {}
        image_url = data.get("resultUrl") or data.get("imageUrl") or ""
        download = {"passed": False, "error": "missing result url"}
        if image_url:
            download = download_image(base_url, image_url, artifacts / f"watermark-{mode}.jpg")
        changed = False
        if download.get("passed"):
            changed = image_changed(image_path, Path(download["path"]))
        rows.append({"mode": mode, "request": result, "download": download, "changedFromSource": changed})

    sheet_path = screenshots / ("watermark-cloud-flow-hd.jpg" if include_hd else "watermark-cloud-flow-basic.jpg")
    make_contact_sheet(
        [image_path, mask_path] + [Path(row["download"]["path"]) for row in rows if row["download"].get("passed")],
        sheet_path,
        labels=["source", "mask"] + [row["mode"] for row in rows if row["download"].get("passed")],
    )
    checks = {
        "allEndpointsPassed": all(row["request"].get("passed") and (row["request"].get("data") or {}).get("success") for row in rows),
        "allImagesDownloaded": all(row["download"].get("passed") for row in rows),
        "allImagesChanged": all(row["changedFromSource"] for row in rows),
        "contactSheetSaved": sheet_path.exists(),
    }
    if include_hd:
        hd = next((row for row in rows if row["mode"] == "hd"), None)
        hd_data = ((hd or {}).get("request") or {}).get("data") or {}
        checks["hdRealEngine"] = bool(hd_data.get("engine")) and hd_data.get("engine") not in {"opencv_hd_fallback", "not_ready", "opencv_manual", "opencv_quick"}
        checks["hdFallbackNotUsed"] = hd_data.get("fallbackUsed") is False
    return {"passed": all(checks.values()), "checks": checks, "rows": rows, "screenshot": str(sheet_path)}


def run_compress(base_url: str, image_path: Path, artifacts: Path) -> dict[str, Any]:
    with image_path.open("rb") as fh:
        result = request_json(
            "POST",
            base_url.rstrip() + "/api/compress",
            files={"file": (image_path.name, fh, "image/jpeg")},
            data={"targetKb": "80"},
            timeout=90,
        )
    data = result.get("data") or {}
    image_url = data.get("resultUrl") or data.get("imageUrl") or ""
    download = {"passed": False, "error": "missing result url"}
    if image_url:
        download = download_image(base_url, image_url, artifacts / "compressed-output.jpg")
    return {"passed": result.get("passed") and download.get("passed"), "request": result, "download": download}


def image_changed(source: Path, output: Path) -> bool:
    a = Image.open(source).convert("RGB")
    b = Image.open(output).convert("RGB")
    if a.size != b.size:
        b = b.resize(a.size)
    return ImageChops.difference(a, b).getbbox() is not None


def make_contact_sheet(paths: list[Path], target: Path, labels: list[str]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    thumbs: list[Image.Image] = []
    for path in paths:
        img = Image.open(path).convert("RGB")
        img.thumbnail((180, 180))
        thumbs.append(img)
    width = max(1, len(thumbs)) * 210 + 20
    height = 250
    sheet = Image.new("RGB", (width, height), (246, 248, 251))
    draw = ImageDraw.Draw(sheet)
    for idx, img in enumerate(thumbs):
        x = 20 + idx * 210
        sheet.paste(img, (x + (180 - img.width) // 2, 36 + (180 - img.height) // 2))
        draw.text((x, 214), labels[idx][:24], fill=(30, 41, 59))
    sheet.save(target, quality=92)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--source-file", default="")
    parser.add_argument("--include-hd", action="store_true")
    args = parser.parse_args()

    run_root = ROOT / "reports" / "cloud-deploy-e2e" / args.run_id
    cloud_tests = run_root / "cloud-tests"
    screenshots = cloud_tests / "screenshots"
    artifacts = run_root / "cloud-artifacts"
    cloud_tests.mkdir(parents=True, exist_ok=True)
    screenshots.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)

    if args.source_file:
        source = prepare_source_file(Path(args.source_file), cloud_tests / "input-id-photo-source.jpg")
    else:
        source = prepare_source_image(args.source_url, cloud_tests / "input-id-photo-source.jpg")
    watermark = make_watermark_sample(cloud_tests / "input-watermark-source.jpg", cloud_tests / "input-watermark-mask.png")
    health = {
        "api": request_json("GET", args.base_url.rstrip() + "/api/health", timeout=30),
        "watermark": request_json("GET", args.base_url.rstrip() + "/api/watermark/health", timeout=30),
        "retention": request_json("GET", args.base_url.rstrip() + "/api/assets/retention-policy", timeout=30),
        "capabilities": request_json("GET", args.base_url.rstrip() + "/api/id-photo/capabilities", timeout=30),
    }
    id_photo = run_id_photo(args.base_url, Path(source["path"]), artifacts, screenshots)
    watermark_flow = run_watermark(args.base_url, Path(watermark["image"]), Path(watermark["mask"]), artifacts, screenshots, args.include_hd)
    compress = run_compress(args.base_url, Path(watermark["image"]), artifacts)
    cleanup = request_json("POST", args.base_url.rstrip() + "/api/assets/cleanup-expired", timeout=30)

    checks = {
        "healthPassed": all(item.get("passed") for item in health.values()),
        "retentionIs24h": ((health["retention"].get("data") or {}).get("retentionSeconds") == 86400),
        "idPhotoPassed": id_photo["passed"],
        "watermarkPassed": watermark_flow["passed"],
        "compressPassed": bool(compress.get("passed")),
        "cleanupEndpointPassed": cleanup.get("passed") and (cleanup.get("data") or {}).get("success") is True,
    }
    if args.include_hd:
        wm_health = health["watermark"].get("data") or {}
        checks["hdHealthReady"] = wm_health.get("hdAvailable") is True and wm_health.get("hdRealModelLoaded") is True and wm_health.get("fallbackUsed") is False

    payload = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "baseUrl": args.base_url,
        "runId": args.run_id,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source,
        "watermarkInput": watermark,
        "health": health,
        "idPhoto": id_photo,
        "watermark": watermark_flow,
        "compress": compress,
        "cleanup": cleanup,
        "checks": checks,
        "artifactDir": str(artifacts),
        "screenshotDir": str(screenshots),
    }
    suffix = "hd" if args.include_hd else "basic"
    report_json = cloud_tests / f"cloud-real-business-flow-{suffix}.json"
    report_md = cloud_tests / f"cloud-real-business-flow-{suffix}.md"
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    source_label = source.get("sourceUrl") or source.get("sourceFile") or ""
    lines = [
        f"# Cloud Real Business Flow ({suffix})",
        "",
        f"- Status: {payload['status']}",
        f"- Base URL: `{args.base_url}`",
        f"- Source: `{source_label}`",
        f"- Artifact dir: `{artifacts}`",
        "",
        "## Checks",
    ]
    lines.extend([f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items()])
    lines.extend(["", "## Screenshots", f"- ID photo: `{id_photo['screenshot']}`", f"- Watermark: `{watermark_flow['screenshot']}`"])
    report_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"[cloud-real-business-flow] {payload['status']} report={report_json}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
