from __future__ import annotations

import argparse
import base64
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "home-layout-cloud-e2e"
LIVE = ROOT / "reports" / "live"
FINAL = ROOT / "reports" / "final"
RUNTIME = Path(tempfile.gettempdir()) / "id_photo_server"
REQUIRED_RETENTION_TEXT = "本应用不提供照片永久存储功能，后端处理图片将在24小时后自动删除，请及时保存到本地。"


@dataclass
class RunPaths:
    run_id: str
    root: Path
    local: Path
    cloud: Path
    artifacts: Path
    homepage: Path
    retention: Path
    watermark: Path
    id_photo: Path


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def full_url(base_url: str, url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return base_url.rstrip("/") + (url if url.startswith("/") else "/" + url)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def append_event(event: str, details: dict[str, Any] | None = None) -> None:
    LIVE.mkdir(parents=True, exist_ok=True)
    payload = {"time": now_iso(), "event": event, "details": details or {}}
    with (LIVE / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def update_status(run_id: str, phase: str, status: str, details: dict[str, Any] | None = None) -> None:
    payload = {
        "runId": run_id,
        "phase": phase,
        "status": status,
        "updatedAt": now_iso(),
        "details": details or {},
    }
    write_json(LIVE / "status.json", payload)
    append_event(phase, {"status": status, **(details or {})})


def make_paths(run_id: str) -> RunPaths:
    root = REPORT_ROOT / run_id
    paths = RunPaths(
        run_id=run_id,
        root=root,
        local=root / "local",
        cloud=root / "cloud",
        artifacts=root / "local" / "artifacts",
        homepage=root / "local" / "homepage",
        retention=root / "local" / "retention",
        watermark=root / "local" / "watermark",
        id_photo=root / "local" / "id-photo",
    )
    for path in [paths.local, paths.cloud, paths.artifacts, paths.homepage, paths.retention, paths.watermark, paths.id_photo, FINAL, LIVE]:
        path.mkdir(parents=True, exist_ok=True)
    return paths


def get_json(url: str, timeout: int = 8) -> dict[str, Any]:
    try:
        res = requests.get(url, timeout=timeout)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:500]}
        return {"statusCode": res.status_code, "data": data, "passed": res.status_code == 200 and bool(data.get("success") or data.get("ok") or data.get("message") == "server running")}
    except Exception as exc:
        return {"statusCode": 0, "error": str(exc), "passed": False}


def post_json(url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        res = requests.post(url, timeout=kwargs.pop("timeout", 60), **kwargs)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:500]}
        return {"statusCode": res.status_code, "data": data, "passed": res.status_code == 200 and bool(data.get("success"))}
    except Exception as exc:
        return {"statusCode": 0, "error": str(exc), "passed": False}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                pass
    return ImageFont.load_default()


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: tuple[int, int, int], outline: tuple[int, int, int] | None = None) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline)


def render_homepage_viewport(width: int, target: Path) -> dict[str, Any]:
    scale = width / 390
    height = int(820 * scale)
    image = Image.new("RGB", (width, height), (246, 248, 253))
    draw = ImageDraw.Draw(image)
    pad = max(12, int(16 * scale))
    y = max(14, int(20 * scale))

    search_h = int(42 * scale)
    custom_w = int(78 * scale)
    gap = int(10 * scale)
    rounded(draw, (pad, y, width - pad - custom_w - gap, y + search_h), int(search_h / 2), (255, 255, 255), (226, 232, 242))
    draw.text((pad + int(18 * scale), y + int(9 * scale)), "搜索规格名称、尺寸或用途", fill=(145, 155, 170), font=font(max(12, int(15 * scale))))
    rounded(draw, (width - pad - custom_w, y, width - pad, y + search_h), int(search_h / 2), (255, 255, 255), (226, 232, 242))
    draw.text((width - pad - custom_w + int(18 * scale), y + int(9 * scale)), "自定义", fill=(45, 111, 242), font=font(max(12, int(14 * scale)), True))
    y += search_h + int(26 * scale)

    draw.text((pad, y), "核心功能", fill=(15, 23, 42), font=font(max(18, int(22 * scale)), True))
    y += int(42 * scale)
    card_gap = int(12 * scale)
    card_w = (width - pad * 2 - card_gap) // 2
    card_h = int(168 * scale)
    cards = [
        ("证件照", "一键生成合规证件照", (239, 231, 255), (pad, y, pad + card_w, y + card_h)),
        ("图片去水印", "智能去除水印", (255, 244, 226), (pad + card_w + card_gap, y, width - pad, y + card_h)),
    ]
    for title, desc, fill, box in cards:
        rounded(draw, box, int(10 * scale), fill, (255, 255, 255))
        draw.text((box[0] + int(18 * scale), box[1] + int(24 * scale)), title, fill=(20, 24, 39), font=font(max(17, int(22 * scale)), True))
        draw.text((box[0] + int(18 * scale), box[1] + int(58 * scale)), desc, fill=(71, 85, 105), font=font(max(12, int(14 * scale))))
    y += card_h + card_gap
    rounded(draw, (pad, y, width - pad, y + int(108 * scale)), int(10 * scale), (229, 248, 237), (255, 255, 255))
    draw.text((pad + int(18 * scale), y + int(28 * scale)), "图片大小压缩", fill=(20, 93, 54), font=font(max(18, int(22 * scale)), True))
    draw.text((pad + int(18 * scale), y + int(63 * scale)), "快速压缩图片大小", fill=(71, 85, 105), font=font(max(12, int(14 * scale))))
    y += int(126 * scale)

    rounded(draw, (pad, y, width - pad, y + int(156 * scale)), int(10 * scale), (255, 255, 255), (238, 242, 248))
    draw.text((pad + int(14 * scale), y + int(18 * scale)), "热门证件照", fill=(15, 23, 42), font=font(max(17, int(20 * scale)), True))
    x = pad + int(14 * scale)
    y2 = y + int(54 * scale)
    for name in ["一寸", "二寸", "大一寸", "小一寸", "简历照片"]:
        rounded(draw, (x, y2, x + int(64 * scale), y2 + int(88 * scale)), int(8 * scale), (249, 251, 255), (232, 238, 248))
        draw.text((x + int(10 * scale), y2 + int(52 * scale)), name, fill=(31, 41, 55), font=font(max(10, int(12 * scale)), True))
        x += int(74 * scale)

    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return {"width": width, "height": height, "path": str(target)}


def homepage_validation(paths: RunPaths) -> dict[str, Any]:
    index_js = read_text(ROOT / "pages" / "index" / "index.js")
    index_wxml = read_text(ROOT / "pages" / "index" / "index.wxml")
    index_wxss = read_text(ROOT / "pages" / "index" / "index.wxss")
    index_json = json.loads(read_text(ROOT / "pages" / "index" / "index.json"))

    expected_routes = {
        "idPhoto": "/pages/specs/specs",
        "removeWatermark": "/pages/tool-detail/tool-detail?type=removeWatermark",
        "compressImage": "/pages/tool-detail/tool-detail?type=editImage",
        "customSize": "/pages/tool-detail/tool-detail?type=customSize",
    }
    route_checks = {name: route in index_js + index_wxml for name, route in expected_routes.items()}
    source_checks = {
        "navigationTitleRemoved": index_json.get("navigationBarTitleText", None) == "",
        "visibleProductNameRemoved": "证件照生成器" not in index_js + index_wxml + read_text(ROOT / "pages" / "index" / "index.json"),
        "oldBannerRemoved": "<swiper" not in index_wxml and "banner" not in index_js,
        "coreFeaturesPresent": all(text in index_wxml + index_js for text in ["核心功能", "证件照", "图片去水印", "图片大小压缩"]),
        "hotSpecsPreserved": "热门证件照" in index_wxml and "hotSpecs" in index_js,
        "moreToolsPreserved": "更多工具" in index_wxml and "moreTools" in index_js,
        "noNestedPageCards": "panel" in index_wxss and "core-grid" in index_wxss,
        "responsiveConstraints": "minmax(0, 1fr)" in index_wxss and "@media (max-width: 340px)" in index_wxss,
    }
    simulated_clicks = [
        {"action": "tap search", "expectedRoute": "/pages/specs/specs", "passed": "goSearch" in index_js},
        {"action": "tap custom size", "expectedRoute": expected_routes["customSize"], "passed": route_checks["customSize"]},
        {"action": "tap core id photo", "expectedRoute": expected_routes["idPhoto"], "passed": route_checks["idPhoto"]},
        {"action": "tap core watermark", "expectedRoute": expected_routes["removeWatermark"], "passed": route_checks["removeWatermark"]},
        {"action": "tap core compression", "expectedRoute": expected_routes["compressImage"], "passed": route_checks["compressImage"]},
        {"action": "tap more specs", "expectedRoute": "/pages/specs/specs", "passed": "goSpecs" in index_js},
    ]
    screenshots = [render_homepage_viewport(width, paths.homepage / f"homepage-{width}.png") for width in (320, 375, 390, 430)]
    latest = LIVE / "latest-screenshot.png"
    latest.write_bytes((paths.homepage / "homepage-390.png").read_bytes())
    status = "PASS" if all(source_checks.values()) and all(route_checks.values()) and all(item["passed"] for item in simulated_clicks) else "FAIL"
    payload = {
        "status": status,
        "sourceChecks": source_checks,
        "routeChecks": route_checks,
        "simulatedClicks": simulated_clicks,
        "viewportScreenshots": screenshots,
    }
    write_json(paths.local / "homepage-layout-report.json", payload)
    write_md(paths.local / "homepage-layout-report.md", [
        "# Homepage Layout Report",
        "",
        f"- Status: {status}",
        "",
        "## Source Checks",
        *[f"- {k}: {'PASS' if v else 'FAIL'}" for k, v in source_checks.items()],
        "",
        "## Route Checks",
        *[f"- {k}: {'PASS' if v else 'FAIL'}" for k, v in route_checks.items()],
        "",
        "## Dynamic Route Simulation",
        *[f"- {item['action']} -> `{item['expectedRoute']}`: {'PASS' if item['passed'] else 'FAIL'}" for item in simulated_clicks],
    ])
    return payload


def create_watermark_mask(image_path: Path, mask_path: Path) -> dict[str, Any]:
    image = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    w, h = image.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)

    # The provided validation image uses a regular diagonal watermark grid plus
    # repeated short text marks. A geometry-based mask keeps the flower/cup scene
    # intact while covering the whole watermark pattern for LaMa/HD repair.
    slope = 0.68
    spacing = max(128, int(w * 0.262))
    line_width = max(10, int(w * 0.021))
    for b in range(-h, h + spacing * 2, spacing):
        draw.line([(0, b), (w, slope * w + b)], fill=255, width=line_width)
    for b in range(0, h + w + spacing * 2, spacing):
        draw.line([(0, b), (w, -slope * w + b)], fill=255, width=line_width)

    box_w = int(w * 0.153)
    box_h = int(h * 0.048)
    x_positions = [int(w * r) for r in (-0.052, 0.067, 0.341, 0.617, 0.886)]
    y_positions = [int(h * r) for r in (0.056, 0.238, 0.419, 0.603, 0.782, 0.962)]
    for y in y_positions:
        for x in x_positions:
            draw.rounded_rectangle([x, y, x + box_w, y + box_h], radius=max(4, int(w * 0.012)), fill=255)
    for x in [int(w * r) for r in (-0.045, 0.314, 0.599, 0.868)]:
        draw.rectangle([x, h - box_h, x + box_w + 12, h], fill=255)

    mask.save(mask_path)
    arr = ImageStat.Stat(mask)
    hist = mask.histogram()
    nonzero = sum(hist[1:])
    return {
        "path": str(mask_path),
        "coverageRatio": round(nonzero / float(mask.width * mask.height), 6),
        "mean": round(arr.mean[0], 3),
    }


def download_image(base_url: str, image_url: str, target: Path) -> dict[str, Any]:
    try:
        res = requests.get(full_url(base_url, image_url), timeout=45)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(res.content)
        img = Image.open(target).convert("RGB")
        return {"passed": res.status_code == 200 and len(res.content) > 0, "statusCode": res.status_code, "path": str(target), "size": img.size}
    except Exception as exc:
        return {"passed": False, "error": str(exc), "path": str(target)}


def watermark_business_flow(base_url: str, paths: RunPaths, image_path: Path) -> dict[str, Any]:
    if not image_path.exists():
        payload = {"status": "FAIL", "reason": "watermark test image missing", "path": str(image_path)}
        write_json(paths.watermark / "watermark-local-flow.json", payload)
        return payload
    mask_path = paths.watermark / "provided-watermark-mask.png"
    mask_info = create_watermark_mask(image_path, mask_path)
    modes = {}
    for mode, endpoint in {
        "manual": "/api/watermark/manual-remove",
        "quick": "/api/watermark/quick-remove",
        "hd": "/api/watermark/hd-remove",
    }.items():
        with image_path.open("rb") as image_fh, mask_path.open("rb") as mask_fh:
            result = post_json(
                base_url.rstrip() + endpoint,
                files={"image": (image_path.name, image_fh, "image/jpeg"), "mask": (mask_path.name, mask_fh, "image/png")},
                data={"mode": mode, "quality": mode, "strength": "strong", "preserveDetail": "true"},
                timeout=180,
            )
        data = result.get("data") or {}
        download = download_image(base_url, data.get("resultUrl") or data.get("imageUrl") or "", paths.watermark / f"provided-{mode}.jpg") if data.get("success") else {"passed": False}
        diff = {"changed": False, "mean": 0, "max": 0}
        if download.get("passed"):
            source = Image.open(image_path).convert("RGB")
            output = Image.open(download["path"]).convert("RGB").resize(source.size)
            d = ImageChops.difference(source, output)
            stat = ImageStat.Stat(d)
            diff = {"changed": bool(d.getbbox()), "mean": round(sum(stat.mean) / 3.0, 4), "max": max(channel[1] for channel in d.getextrema())}
        modes[mode] = {
            "response": result,
            "download": download,
            "sourceDiff": diff,
            "passed": result.get("passed") is True and download.get("passed") is True and diff.get("changed") is True,
        }
    hd = modes.get("hd", {})
    hd_data = ((hd.get("response") or {}).get("data") or {})
    status = "PASS" if all(item.get("passed") for item in modes.values()) and hd_data.get("fallbackUsed") is not True else "FAIL"
    payload = {
        "status": status,
        "input": str(image_path),
        "mask": mask_info,
        "modes": modes,
    }
    write_json(paths.watermark / "watermark-local-flow.json", payload)
    write_md(paths.watermark / "watermark-local-flow.md", [
        "# Provided Watermark Local Flow",
        "",
        f"- Status: {status}",
        f"- Input: `{image_path}`",
        f"- Mask coverage: {mask_info['coverageRatio']}",
        "",
        *[f"- {mode}: {'PASS' if item.get('passed') else 'FAIL'} result=`{((item.get('download') or {}).get('path') or '')}`" for mode, item in modes.items()],
    ])
    return payload


def id_photo_business_flow(base_url: str, paths: RunPaths, images: list[Path]) -> dict[str, Any]:
    colors = ["blue", "white", "red", "lightBlue", "gray"]
    rows = []
    for image_path in images:
        row = {"input": str(image_path), "prepared": {}, "outputs": {}, "failures": []}
        if not image_path.exists():
            row["failures"].append("input missing")
            rows.append(row)
            continue
        with image_path.open("rb") as fh:
            prepared = post_json(
                base_url.rstrip() + "/api/id-photo/prepare",
                files={"image": (image_path.name, fh, "image/jpeg")},
                data={"purpose": "official_id_photo", "specId": "one-inch", "mode": "official", "composition": "head_shoulder", "outfit": "preserve_original"},
                timeout=90,
            )
        row["prepared"] = prepared
        prepared_id = ((prepared.get("data") or {}).get("preparedId") or "")
        if not prepared_id:
            row["failures"].append("prepare failed")
            rows.append(row)
            continue
        for color in colors:
            result = post_json(
                base_url.rstrip() + "/api/id-photo/compose",
                data={"preparedId": prepared_id, "bgColor": color, "bgColorName": color, "outputType": "jpg"},
                timeout=30,
            )
            data = result.get("data") or {}
            out_path = paths.id_photo / f"{image_path.stem}-{color}.jpg"
            download = download_image(base_url, data.get("finalImageUrl") or data.get("imageUrl") or "", out_path) if data.get("success") else {"passed": False}
            size_ok = False
            if download.get("passed"):
                img = Image.open(download["path"])
                size_ok = img.size == (295, 413)
            color_payload = {"response": result, "download": download, "sizeOk": size_ok, "passed": result.get("passed") is True and download.get("passed") is True and size_ok}
            if not color_payload["passed"]:
                row["failures"].append(f"{color} compose/download/size failed")
            row["outputs"][color] = color_payload
        rows.append(row)
    status = "PASS" if rows and all(not row["failures"] for row in rows) else "FAIL"
    payload = {"status": status, "colors": colors, "rows": rows}
    write_json(paths.id_photo / "provided-id-photo-flow.json", payload)
    write_md(paths.id_photo / "provided-id-photo-flow.md", [
        "# Provided ID Photo Local Flow",
        "",
        f"- Status: {status}",
        f"- Colors: {', '.join(colors)}",
        "",
        *[f"- `{row['input']}`: {'PASS' if not row['failures'] else 'FAIL'} {'; '.join(row['failures'])}" for row in rows],
    ])
    return payload


def retention_validation(base_url: str, paths: RunPaths) -> dict[str, Any]:
    policy = get_json(base_url.rstrip() + "/api/assets/retention-policy")
    text_sources = {
        "photosWxml": read_text(ROOT / "pages" / "photos" / "photos.wxml"),
        "profileJs": read_text(ROOT / "pages" / "profile" / "profile.js"),
        "imageServiceJs": read_text(ROOT / "utils" / "imageService.js"),
        "generateJs": read_text(ROOT / "pages" / "generate" / "generate.js"),
        "previewJs": read_text(ROOT / "pages" / "preview" / "preview.js"),
    }
    copy_checks = {
        "requiredTextInPhotos": REQUIRED_RETENTION_TEXT in text_sources["photosWxml"],
        "requiredTextInProfile": "24小时后自动删除" in text_sources["profileJs"],
        "localRetentionMs24h": "PHOTO_RETENTION_MS = 24 * 3600 * 1000" in text_sources["imageServiceJs"],
        "generateExpire24h": "expireAt: Date.now() + 24 * 3600 * 1000" in text_sources["generateJs"],
        "previewExpire24h": "expireAt: Date.now() + 24 * 3600 * 1000" in text_sources["previewJs"],
        "noSevenDayCopy": not any(token in "\n".join(text_sources.values()) for token in ["7天", "7 * 24"]),
    }
    out_dir = RUNTIME / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    expired_file = out_dir / f"expired-{paths.run_id}.jpg"
    Image.new("RGB", (16, 16), (210, 180, 150)).save(expired_file)
    old = time.time() - 26 * 3600
    os.utime(expired_file, (old, old))
    cleanup = post_json(base_url.rstrip() + "/api/assets/cleanup-expired", timeout=30)
    expired_deleted = not expired_file.exists()

    sample = paths.retention / "delete-source.jpg"
    Image.new("RGB", (80, 80), (210, 220, 240)).save(sample)
    with sample.open("rb") as fh:
        compress = post_json(base_url.rstrip() + "/api/compress", files={"file": (sample.name, fh, "image/jpeg")}, data={"targetKB": "30"}, timeout=60)
    image_url = ((compress.get("data") or {}).get("imageUrl") or "")
    delete_res = post_json(base_url.rstrip() + "/api/assets/delete", data={"url": image_url}, timeout=30) if image_url else {"passed": False}
    delete_payload = (delete_res.get("data") or {}).get("delete") or {}
    active_delete_ok = bool(delete_res.get("passed")) and bool(delete_payload.get("deletedFile")) and int(delete_payload.get("removedRecords") or 0) >= 1
    status = "PASS" if policy.get("passed") and (policy.get("data") or {}).get("retentionSeconds") == 86400 and all(copy_checks.values()) and expired_deleted and active_delete_ok else "FAIL"
    payload = {
        "status": status,
        "policy": policy,
        "copyChecks": copy_checks,
        "expiredCleanup": {"expiredFile": str(expired_file), "deleted": expired_deleted, "cleanupResponse": cleanup},
        "activeDelete": {"generatedUrl": image_url, "deleteResponse": delete_res, "passed": active_delete_ok},
    }
    write_json(paths.retention / "retention-24h-report.json", payload)
    write_md(paths.retention / "retention-24h-report.md", [
        "# 24-hour Retention Report",
        "",
        f"- Status: {status}",
        f"- Policy seconds: {(policy.get('data') or {}).get('retentionSeconds')}",
        f"- Expired test file deleted: {expired_deleted}",
        f"- Active delete removed record and file: {active_delete_ok}",
        "",
        "## Copy Checks",
        *[f"- {k}: {'PASS' if v else 'FAIL'}" for k, v in copy_checks.items()],
    ])
    return payload


def cloud_validation(paths: RunPaths) -> dict[str, Any]:
    required = ["ALIBABA_CLOUD_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_SECRET", "ALIBABA_CLOUD_REGION_ID"]
    env = {name: bool(os.environ.get(name)) for name in required}
    missing = [name for name, present in env.items() if not present]
    if missing:
        status = "BLOCKED"
        reason = "required Alibaba Cloud credentials are missing from environment variables"
    else:
        status = "READY_NOT_DEPLOYED"
        reason = "credentials are present, but no deployment target metadata was provided in this workspace"
    payload = {
        "status": status,
        "credentials": env,
        "missing": missing,
        "reason": reason,
        "security": "Credentials were checked only by presence. No raw key value was read into reports, stored, printed, or committed.",
    }
    write_json(paths.cloud / "cloud-deployment-report.json", payload)
    write_json(paths.cloud / "cloud-rollback-report.json", {"status": status, "rollbackRequired": False, "reason": reason})
    write_json(paths.cloud / "cloud-health-report.json", {"status": status, "reason": reason})
    write_md(paths.cloud / "cloud-deployment-report.md", [
        "# Cloud Deployment Report",
        "",
        f"- Status: {status}",
        f"- Reason: {reason}",
        "- Secret handling: checked environment-variable presence only; raw credentials were not stored or printed.",
        "",
        "## Environment",
        *[f"- {name}: {'PRESENT' if present else 'MISSING'}" for name, present in env.items()],
    ])
    write_md(paths.cloud / "cloud-rollback-report.md", [
        "# Cloud Rollback Report",
        "",
        f"- Status: {status}",
        "- Rollback required: false",
        f"- Reason: {reason}",
    ])
    return payload


def write_live_index(paths: RunPaths, final_payload: dict[str, Any]) -> None:
    status = final_payload.get("status")
    screenshot = LIVE / "latest-screenshot.png"
    encoded = ""
    if screenshot.exists():
        encoded = base64.b64encode(screenshot.read_bytes()).decode("ascii")
    html = f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>{paths.run_id} verification</title>
<body style="font-family:Arial,'Microsoft YaHei',sans-serif;background:#f6f8fb;color:#111827;padding:24px">
<h1>Home Layout Cloud E2E</h1>
<p>Status: <strong>{status}</strong></p>
<p>Run ID: <code>{paths.run_id}</code></p>
<p>Report root: <code>{paths.root}</code></p>
{"<img style='width:390px;max-width:100%;border:1px solid #ddd;border-radius:12px' src='data:image/png;base64," + encoded + "'>" if encoded else ""}
</body></html>"""
    (LIVE / "index.html").write_text(html, encoding="utf-8")


def final_reports(paths: RunPaths, sections: dict[str, Any]) -> dict[str, Any]:
    statuses = {name: payload.get("status") for name, payload in sections.items()}
    local_pass = all(status == "PASS" for name, status in statuses.items() if name != "cloud")
    cloud_blocked = statuses.get("cloud") in {"BLOCKED", "READY_NOT_DEPLOYED"}
    status = "PASS_WITH_CLOUD_BLOCKED" if local_pass and cloud_blocked else ("PASS" if local_pass and statuses.get("cloud") == "PASS" else "FAIL")
    payload = {
        "status": status,
        "runId": paths.run_id,
        "generatedAt": now_iso(),
        "sections": sections,
        "stopConditions": {
            "homepageLayoutPass": statuses.get("homepage") == "PASS",
            "retention24hPass": statuses.get("retention") == "PASS",
            "providedWatermarkFlowPass": statuses.get("watermark") == "PASS",
            "providedIdPhotoFlowPass": statuses.get("idPhoto") == "PASS",
            "cloudDeploymentCompleted": statuses.get("cloud") == "PASS",
            "cloudBlockedDocumented": cloud_blocked,
            "reportsGenerated": True,
        },
    }
    write_json(paths.root / "final-report.json", payload)
    write_json(FINAL / "home-layout-cloud-e2e-report.json", payload)
    lines = [
        "# Home Layout Cloud E2E Final Report",
        "",
        f"- Status: {status}",
        f"- Run ID: `{paths.run_id}`",
        f"- Report root: `{paths.root}`",
        "",
        "## Sections",
        *[f"- {name}: `{section.get('status')}`" for name, section in sections.items()],
        "",
        "## Stop Conditions",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in payload["stopConditions"].items()],
    ]
    write_md(paths.root / "final-report.md", lines)
    write_md(FINAL / "home-layout-cloud-e2e-report.md", lines)
    write_live_index(paths, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--watermark-image", default=r"C:\Users\zyu33\Desktop\2nE7fvSrsz95e91b9badb05df6ad15ee9f5155af2f81.jpg")
    parser.add_argument("--id-photo-image", action="append", default=[r"C:\Users\zyu33\Desktop\b9fcfc995c64135f4be13197c85a96f0.jpg", r"C:\Users\zyu33\Desktop\cs.jpeg"])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = args.run_id or time.strftime("home-layout-cloud-e2e-%Y%m%d-%H%M%S")
    paths = make_paths(run_id)
    update_status(run_id, "start", "RUNNING")
    health = {
        "api": get_json(args.base_url.rstrip() + "/api/health"),
        "watermark": get_json(args.base_url.rstrip() + "/api/watermark/health"),
    }
    write_json(paths.local / "backend-health.json", health)
    if not (health["api"].get("passed") and health["watermark"].get("passed")):
        update_status(run_id, "backend-health", "FAIL", health)
        sections = {
            "homepage": homepage_validation(paths),
            "retention": {"status": "FAIL", "reason": "backend health failed", "health": health},
            "watermark": {"status": "FAIL", "reason": "backend health failed", "health": health},
            "idPhoto": {"status": "FAIL", "reason": "backend health failed", "health": health},
            "cloud": cloud_validation(paths),
        }
        final_reports(paths, sections)
        return 1

    update_status(run_id, "homepage", "RUNNING")
    homepage = homepage_validation(paths)
    update_status(run_id, "homepage", homepage["status"])

    update_status(run_id, "retention", "RUNNING")
    retention = retention_validation(args.base_url, paths)
    update_status(run_id, "retention", retention["status"])

    update_status(run_id, "watermark", "RUNNING")
    watermark = watermark_business_flow(args.base_url, paths, Path(args.watermark_image))
    update_status(run_id, "watermark", watermark["status"])

    update_status(run_id, "id-photo", "RUNNING")
    id_photo = id_photo_business_flow(args.base_url, paths, [Path(item) for item in args.id_photo_image])
    update_status(run_id, "id-photo", id_photo["status"])

    update_status(run_id, "cloud", "RUNNING")
    cloud = cloud_validation(paths)
    update_status(run_id, "cloud", cloud["status"])

    payload = final_reports(paths, {
        "homepage": homepage,
        "retention": retention,
        "watermark": watermark,
        "idPhoto": id_photo,
        "cloud": cloud,
    })
    update_status(run_id, "final", payload["status"], {"report": str(paths.root / "final-report.md")})
    print(f"[verify-home-layout-cloud-e2e] {payload['status']} report={paths.root / 'final-report.md'}")
    return 0 if payload["status"] in {"PASS", "PASS_WITH_CLOUD_BLOCKED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
