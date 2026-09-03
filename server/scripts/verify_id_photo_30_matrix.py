"""Run the 30-real-image async DETAIL, mainland-spec, color, and download matrix."""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "id-photo-real-speed"
SPECS = [
    ("one-inch", "official_id_photo", 295, 413, 25, 35),
    ("id-card-cn", "id_card", 358, 441, 26, 32),
    ("passport-cn", "passport", 390, 567, 33, 48),
    ("driver-license-cn", "driver_license", 260, 378, 22, 32),
]
COLORS = {
    "blue": "#1a73e8",
    "white": "#ffffff",
    "red": "#e53935",
    "lightBlue": "#81d4fa",
    "gray": "#9e9e9e",
}


def post_prepare(base_url: str, image_path: Path, spec: tuple[str, str, int, int, int, int]) -> dict[str, Any]:
    spec_id, purpose, width_px, height_px, width_mm, height_mm = spec
    started = time.perf_counter()
    with image_path.open("rb") as fh:
        response = requests.post(
            base_url + "/api/id-photo/prepare",
            files={"image": (image_path.name, fh, "image/jpeg")},
            data={
                "purpose": purpose,
                "specId": spec_id,
                "widthPx": str(width_px),
                "heightPx": str(height_px),
                "widthMm": str(width_mm),
                "heightMm": str(height_mm),
                "imageType": "real_person",
                "mode": "official",
                "composition": "head_shoulder",
                "outfit": "preserve_original",
                "hairRetouch": "false",
            },
            timeout=35,
        )
    duration_ms = int((time.perf_counter() - started) * 1000)
    try:
        data = response.json()
    except Exception:
        data = {"text": response.text[:500]}
    return {
        "specId": spec_id,
        "statusCode": response.status_code,
        "durationMs": duration_ms,
        "success": data.get("success") is True,
        "code": data.get("code"),
        "requestId": data.get("requestId"),
        "preparedId": data.get("preparedId") or "",
        "sourceId": data.get("sourceId") or "",
        "fastQualityStatus": data.get("fastQualityStatus"),
        "selectedModel": data.get("selectedModel"),
        "detailFallbackUsed": data.get("detailFallbackUsed"),
        "clearResult": response.status_code in {200, 400, 422},
    }


def create_detail(base_url: str, source_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    response = requests.post(
        base_url + "/api/id-photo/detail-jobs",
        data={"sourceId": source_id, "fastPreviewUrl": ""},
        timeout=15,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    try:
        data = response.json()
    except Exception:
        data = {"text": response.text[:500]}
    return {
        "statusCode": response.status_code,
        "createMs": duration_ms,
        "jobId": data.get("jobId") or "",
        "requestId": data.get("requestId"),
        "status": data.get("status"),
        "detailModel": data.get("detailModel"),
        "code": data.get("code"),
    }


def poll_batch(base_url: str, rows: list[dict[str, Any]], timeout: int = 420) -> None:
    pending = {row["jobId"]: row for row in rows if row.get("jobId")}
    deadline = time.time() + timeout
    while pending and time.time() < deadline:
        time.sleep(2)
        for job_id, row in list(pending.items()):
            try:
                data = requests.get(base_url + "/api/id-photo/detail-jobs/" + job_id, timeout=15).json()
            except Exception as exc:
                row["pollError"] = str(exc)
                continue
            row["status"] = data.get("status")
            row["selectedModel"] = data.get("selectedModel")
            row["preparedId"] = data.get("preparedId") or ""
            row["performance"] = data.get("performance") or {}
            row["message"] = data.get("message")
            if row["status"] in {"completed", "failed", "cancelled"}:
                pending.pop(job_id, None)
    for row in pending.values():
        row["status"] = "timeout"


def compose_and_download(base_url: str, prepared_id: str, color_name: str, color_hex: str) -> dict[str, Any]:
    started = time.perf_counter()
    response = requests.post(
        base_url + "/api/id-photo/compose",
        data={"preparedId": prepared_id, "bgColor": color_hex, "bgColorName": color_name, "outputType": "jpg"},
        timeout=35,
    )
    compose_ms = int((time.perf_counter() - started) * 1000)
    try:
        data = response.json()
    except Exception:
        data = {"text": response.text[:500]}
    result_url = data.get("resultUrl") or data.get("imageUrl") or ""
    download_status = 0
    download_ms = 0
    downloaded_bytes = 0
    if result_url:
        url = result_url if result_url.startswith(("http://", "https://")) else base_url + "/" + result_url.lstrip("/")
        download_started = time.perf_counter()
        download = requests.get(url, timeout=35)
        download_ms = int((time.perf_counter() - download_started) * 1000)
        download_status = download.status_code
        downloaded_bytes = len(download.content)
    return {
        "color": color_name,
        "statusCode": response.status_code,
        "success": data.get("success") is True,
        "code": data.get("code"),
        "message": data.get("message"),
        "composeMs": compose_ms,
        "resultUrl": result_url,
        "downloadStatusCode": download_status,
        "downloadMs": download_ms,
        "downloadedBytes": downloaded_bytes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--fast-report", default=str(REPORT_DIR / "fast-no-detail.json"))
    parser.add_argument("--reuse-detail", action="store_true")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    fast_report = json.loads(Path(args.fast_report).read_text(encoding="utf-8"))
    source_rows = fast_report.get("rows") or []
    if len(source_rows) < 30:
        raise SystemExit(f"expected at least 30 source rows, found {len(source_rows)}")

    prior_details: dict[str, dict[str, Any]] = {}
    prior_report = REPORT_DIR / "thirty-image-matrix.json"
    if args.reuse_detail and prior_report.exists():
        prior_payload = json.loads(prior_report.read_text(encoding="utf-8"))
        prior_details = {row.get("path", ""): row.get("detail") or {} for row in prior_payload.get("rows") or []}

    matrix: list[dict[str, Any]] = []
    for index, source in enumerate(source_rows[:30], 1):
        image_path = Path(source["path"])
        spec_rows = [post_prepare(base_url, image_path, spec) for spec in SPECS]
        one_inch = spec_rows[0]
        colors = []
        if one_inch["preparedId"]:
            colors = [compose_and_download(base_url, one_inch["preparedId"], name, value) for name, value in COLORS.items()]
        matrix.append({
            "index": index,
            "path": str(image_path),
            "sourceKind": "current-user-original" if index <= 3 else "archived-real-person-source-or-normalized",
            "width": source.get("width"),
            "height": source.get("height"),
            "bytes": source.get("bytes"),
            "ordinary": source,
            "specs": spec_rows,
            "fiveColors": colors,
            "detail": prior_details.get(str(image_path), {}),
        })

    detail_pending = [row for row in matrix if row["detail"].get("status") not in {"completed", "failed", "cancelled"}]
    for start in range(0, len(detail_pending), 2):
        batch = detail_pending[start:start + 2]
        created = []
        for row in batch:
            source_id = row["ordinary"].get("sourceId") or row["specs"][0].get("sourceId")
            detail = create_detail(base_url, source_id) if source_id else {
                "statusCode": 0,
                "createMs": 0,
                "status": "not-created",
                "detailModel": None,
                "code": "DETAIL_SOURCE_NOT_FOUND",
            }
            row["detail"] = detail
            created.append(detail)
        poll_batch(base_url, created)

    ordinary_times = [row["ordinary"]["totalClientMs"] for row in matrix]
    all_spec_rows = [spec for row in matrix for spec in row["specs"]]
    all_color_rows = [color for row in matrix for color in row["fiveColors"]]
    detail_rows = [row["detail"] for row in matrix]
    matting_spec_rows = [row for row in all_spec_rows if row.get("code") != "TEMPLATE_NOT_AVAILABLE"]
    successful_color_rows = [row for row in all_color_rows if row.get("success")]
    checks = {
        "thirtyRealImages": len(matrix) == 30,
        "currentThreeOriginalsIncluded": sum(row["sourceKind"] == "current-user-original" for row in matrix) == 3,
        "ordinaryNoSyncDetail": all(row["ordinary"].get("detailFallbackUsed") is False for row in matrix),
        "ordinaryUnder30Seconds": max(ordinary_times, default=30001) < 30000,
        "allFourSpecsReturnedClearly": len(all_spec_rows) == 120 and all(row["clearResult"] for row in all_spec_rows),
        "allMattingSpecRunsFastOnly": all(
            row["selectedModel"] in {"hivision_modnet", "modnet_photographic_portrait_matting"}
            for row in matting_spec_rows
        ),
        "allMattingSpecRunsNoSyncDetail": all(row["detailFallbackUsed"] is False for row in matting_spec_rows),
        "allDetailCreatesImmediate": all(row.get("createMs", 10001) < 10000 for row in detail_rows),
        "allDetailJobsUseBirefnet": all(row.get("detailModel") == "birefnet-v1-lite" for row in detail_rows),
        "allDetailJobsTerminal": all(row.get("status") in {"completed", "failed", "cancelled"} for row in detail_rows),
        "usableImagesHaveFiveColorAttempts": all(len(row["fiveColors"]) == 5 for row in matrix if row["specs"][0]["success"]),
        "allColorAttemptsReturnClearly": all(row["statusCode"] in {200, 400, 422} for row in all_color_rows),
        "allSuccessfulColorsDownload": all(row["downloadStatusCode"] == 200 and row["downloadedBytes"] > 0 for row in successful_color_rows),
    }
    detail_statuses: dict[str, int] = {}
    for row in detail_rows:
        detail_statuses[row.get("status") or "unknown"] = detail_statuses.get(row.get("status") or "unknown", 0) + 1
    payload = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "baseUrl": base_url,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": {
            "images": len(matrix),
            "ordinaryP50Ms": int(statistics.median(ordinary_times)),
            "ordinaryP95Ms": sorted(ordinary_times)[min(len(ordinary_times) - 1, round((len(ordinary_times) - 1) * 0.95))],
            "ordinaryMaxMs": max(ordinary_times),
            "ordinarySynchronousDetailCount": sum(bool(row["ordinary"].get("detailFallbackUsed")) for row in matrix),
            "specRequests": len(all_spec_rows),
            "driverTemplateExistingIssueCount": sum(row.get("code") == "TEMPLATE_NOT_AVAILABLE" for row in all_spec_rows),
            "detailJobs": len(detail_rows),
            "detailStatuses": detail_statuses,
            "colorAttempts": len(all_color_rows),
            "colorOutputs": len(successful_color_rows),
        },
        "checks": checks,
        "rows": matrix,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "thirty-image-matrix.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Thirty Real Image Matrix",
        "",
        f"- Status: {payload['status']}",
        "- Sources: 3 current user originals plus 27 archived real-person source/normalized regression images.",
        "- Archived normalized images are disclosed as normalized regression inputs, not phone-camera originals.",
        f"- Ordinary P50/P95/max: {payload['summary']['ordinaryP50Ms']}/{payload['summary']['ordinaryP95Ms']}/{payload['summary']['ordinaryMaxMs']} ms",
        f"- Ordinary synchronous DETAIL count: {payload['summary']['ordinarySynchronousDetailCount']}",
        f"- Spec requests: {payload['summary']['specRequests']}",
        f"- Async DETAIL statuses: `{payload['summary']['detailStatuses']}`",
        f"- Five-color attempts / generated downloads: {payload['summary']['colorAttempts']} / {payload['summary']['colorOutputs']}",
        f"- Existing driver-template purpose mismatch responses: {payload['summary']['driverTemplateExistingIssueCount']} (recorded, not changed in this performance scope)",
        "",
        "## Checks",
    ]
    lines.extend(f"- {key}: {'PASS' if value else 'FAIL'}" for key, value in checks.items())
    (REPORT_DIR / "thirty-image-matrix.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[id-photo-30-matrix] {payload['status']} report={REPORT_DIR / 'thirty-image-matrix.json'}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
