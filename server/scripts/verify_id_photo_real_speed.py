from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import requests
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "id-photo-real-speed"


def percentile(values, ratio):
    ordered = sorted(values)
    if not ordered:
        return 0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def prepare(base_url, image_path, timeout):
    form = {
        "purpose": "official_id_photo",
        "specId": "one-inch",
        "widthPx": "295",
        "heightPx": "413",
        "mode": "official",
        "composition": "head_shoulder",
        "outfit": "preserve_original",
        "hairRetouch": "false",
    }
    started = time.perf_counter()
    with image_path.open("rb") as handle:
        response = requests.post(
            base_url.rstrip("/") + "/api/id-photo/prepare",
            files={"image": (image_path.name, handle, "image/jpeg")},
            data=form,
            timeout=timeout,
        )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    data = response.json()
    quality = data.get("quality") or {}
    performance = data.get("performance") or {}
    worker_metrics = quality.get("fastWorkerMetrics") or {}
    return {
        "path": str(image_path),
        "width": Image.open(image_path).width,
        "height": Image.open(image_path).height,
        "bytes": image_path.stat().st_size,
        "httpStatus": response.status_code,
        "success": bool(data.get("success")),
        "code": data.get("code"),
        "requestId": data.get("requestId"),
        "sourceId": data.get("sourceId") or "",
        "selectedModel": data.get("selectedModel") or quality.get("finalSelectedModel"),
        "fastQualityStatus": data.get("fastQualityStatus"),
        "fastAStatus": quality.get("fastAStatus"),
        "fastAScore": quality.get("fastAScore"),
        "fastBTriggered": bool(quality.get("fastBTriggered")),
        "fastBStatus": quality.get("fastBStatus"),
        "fastBScore": quality.get("fastBScore"),
        "fastBDurationMs": quality.get("fastBDurationMs"),
        "sessionReused": bool(worker_metrics.get("sessionReused")),
        "fastResultUsable": bool(data.get("fastResultUsable")),
        "mattingPass": bool(data.get("mattingPass")),
        "cropPass": bool(data.get("cropPass")),
        "detailRecommended": bool(data.get("detailRecommended")),
        "detailReasons": data.get("detailReasons") or [],
        "detailFallbackUsed": bool(data.get("detailFallbackUsed")),
        "detailFallbackReasons": quality.get("detailFallbackReasons") or [],
        "queueWaitMs": performance.get("queueWaitMs"),
        "uploadMs": performance.get("saveUploadMs"),
        "imageDecodeMs": performance.get("imageDecodeMs"),
        "modelLoadMs": performance.get("modelLoadMs"),
        "fastInferenceMs": performance.get("fastInferenceMs"),
        "qualityGateMs": performance.get("qualityGateMs"),
        "cropMs": performance.get("cropMs"),
        "prepareCacheWriteMs": performance.get("prepareCacheWriteMs"),
        "totalServerMs": performance.get("totalServerMs") or performance.get("totalMs"),
        "totalClientMs": elapsed_ms,
        "timestamps": {
            key: data.get(key)
            for key in (
                "requestReceivedAt",
                "uploadSavedAt",
                "decodeFinishedAt",
                "fastInferenceFinishedAt",
                "qualityGateFinishedAt",
                "cropFinishedAt",
                "prepareFinishedAt",
                "composeFinishedAt",
            )
        },
    }


def run_async_detail(base_url, row, timeout):
    started = time.perf_counter()
    response = requests.post(
        base_url.rstrip("/") + "/api/id-photo/detail-jobs",
        data={"sourceId": row["sourceId"], "fastPreviewUrl": ""},
        timeout=10,
    )
    created_ms = int((time.perf_counter() - started) * 1000)
    job = response.json()
    history = [{"status": job.get("status"), "atMs": created_ms}]
    deadline = time.monotonic() + timeout
    current = job
    while current.get("status") in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(2.5)
        current = requests.get(
            base_url.rstrip("/") + "/api/id-photo/detail-jobs/" + job["jobId"],
            timeout=10,
        ).json()
        if history[-1]["status"] != current.get("status"):
            history.append({"status": current.get("status"), "atMs": int((time.perf_counter() - started) * 1000)})
    return {
        "createHttpStatus": response.status_code,
        "createMs": created_ms,
        "jobId": job.get("jobId"),
        "requestId": job.get("requestId"),
        "detailModel": job.get("detailModel"),
        "history": history,
        "status": current.get("status"),
        "preparedId": current.get("preparedId"),
        "selectedModel": current.get("selectedModel"),
        "performance": current.get("performance") or {},
        "message": current.get("message"),
    }


def write_reports(payload):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "fast-no-detail.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = payload["summary"]
    lines = [
        "# FAST Without Synchronous DETAIL",
        "",
        f"- Base URL: `{payload['baseUrl']}`",
        f"- Runs: {summary['runs']}",
        f"- P50: {summary['p50Ms']}ms",
        f"- P95: {summary['p95Ms']}ms",
        f"- Maximum: {summary['maxMs']}ms",
        f"- Synchronous DETAIL count: {summary['synchronousDetailCount']}",
        f"- Over 30 seconds: {summary['over30Seconds']}",
        f"- Status: **{payload['status']}**",
        "",
        "| File | HTTP | Client ms | Model | FAST status | DETAIL fallback |",
        "| --- | ---: | ---: | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| `{Path(row['path']).name}` | {row['httpStatus']} | {row['totalClientMs']} | "
            f"{row['selectedModel']} | {row['fastQualityStatus']} | {row['detailFallbackUsed']} |"
        )
    (REPORT_DIR / "fast-no-detail.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if payload.get("asyncDetail"):
        detail = payload["asyncDetail"]
        (REPORT_DIR / "async-detail.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
        (REPORT_DIR / "async-detail.md").write_text(
            "\n".join([
                "# Async DETAIL",
                "",
                f"- Create response: {detail['createMs']}ms",
                f"- Model: `{detail['detailModel']}`",
                f"- Status history: `{detail['history']}`",
                f"- Final status: **{detail['status']}**",
                f"- Queue wait: {detail['performance'].get('queueWaitMs', 0)}ms",
                "- The HTTP create call returns before BiRefNet inference.",
            ]) + "\n",
            encoding="utf-8",
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--image", action="append", required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=35)
    parser.add_argument("--verify-async-detail", action="store_true")
    args = parser.parse_args()

    images = [Path(item).resolve() for item in args.image]
    for image in images:
        if not image.exists():
            raise SystemExit(f"missing image: {image}")

    rows = []
    for _ in range(max(1, args.repeats)):
        rows.extend(prepare(args.base_url, image, args.timeout) for image in images)
    durations = [row["totalClientMs"] for row in rows]
    summary = {
        "runs": len(rows),
        "successCount": sum(bool(row["success"]) for row in rows),
        "successRatePercent": round(100.0 * sum(bool(row["success"]) for row in rows) / max(1, len(rows)), 2),
        "fastASelectedCount": sum(row["selectedModel"] == "hivision_modnet" for row in rows),
        "fastBSelectedCount": sum(row["selectedModel"] == "modnet_photographic_portrait_matting" for row in rows),
        "fastBTriggeredCount": sum(bool(row["fastBTriggered"]) for row in rows),
        "fastBlockCount": sum(row["fastQualityStatus"] == "FAST_BLOCK" for row in rows),
        "sessionReusedCount": sum(bool(row["sessionReused"]) for row in rows),
        "p50Ms": int(statistics.median(durations)),
        "p95Ms": percentile(durations, 0.95),
        "maxMs": max(durations),
        "synchronousDetailCount": sum(row["detailFallbackUsed"] for row in rows),
        "over30Seconds": sum(value > 30000 for value in durations),
    }
    passed = (
        summary["synchronousDetailCount"] == 0
        and summary["over30Seconds"] == 0
        and all(row["httpStatus"] == 200 and row["success"] for row in rows)
        and all(row["selectedModel"] in {"hivision_modnet", "modnet_photographic_portrait_matting"} for row in rows)
        and all(row["fastQualityStatus"] in {"FAST_PASS", "FAST_REPAIRABLE", "FAST_WARNING"} for row in rows)
    )
    payload = {"status": "PASS" if passed else "FAIL", "baseUrl": args.base_url, "summary": summary, "rows": rows}
    if args.verify_async_detail:
        candidate = next((row for row in rows if row["sourceId"]), None)
        if candidate:
            payload["asyncDetail"] = run_async_detail(args.base_url, candidate, timeout=300)
            passed = passed and payload["asyncDetail"]["createMs"] < 10000 and payload["asyncDetail"]["detailModel"] == "birefnet-v1-lite"
            payload["status"] = "PASS" if passed else "FAIL"
    write_reports(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
