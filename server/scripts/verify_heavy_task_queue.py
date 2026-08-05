"""Verify FAST isolation and serialized BiRefNet/LaMa heavy-task scheduling."""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from pathlib import Path
from typing import Any

import requests

try:
    import psutil
except ImportError:  # Resource sampling remains optional on lean cloud clients.
    psutil = None


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "id-photo-real-speed"
PREPARE_DATA = {
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
    "hairRetouch": "false",
}


def percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int((len(ordered) - 1) * ratio + 0.5)))]


def timing(values: list[int]) -> dict[str, int]:
    return {
        "count": len(values),
        "p50Ms": int(statistics.median(values)) if values else 0,
        "p95Ms": percentile(values, 0.95),
        "maxMs": max(values, default=0),
    }


def post_fast(base_url: str, image_path: Path, timeout: int = 35) -> dict[str, Any]:
    started = time.perf_counter()
    with image_path.open("rb") as fh:
        response = requests.post(
            base_url + "/api/id-photo/prepare",
            files={"image": (image_path.name, fh, "image/jpeg")},
            data=PREPARE_DATA,
            timeout=timeout,
        )
    elapsed = int((time.perf_counter() - started) * 1000)
    try:
        data = response.json()
    except Exception:
        data = {"text": response.text[:500]}
    return {
        "statusCode": response.status_code,
        "durationMs": elapsed,
        "requestId": data.get("requestId"),
        "sourceId": data.get("sourceId"),
        "preparedId": data.get("preparedId"),
        "fastQualityStatus": data.get("fastQualityStatus"),
        "selectedModel": data.get("selectedModel"),
        "detailFallbackUsed": data.get("detailFallbackUsed"),
        "performance": data.get("performance") or {},
        "success": data.get("success") is True,
        "clearResult": response.status_code in {200, 400, 422},
    }


def create_detail(base_url: str, fast: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    response = requests.post(
        base_url + "/api/id-photo/detail-jobs",
        data={
            "sourceId": fast.get("sourceId") or "",
            "preparedId": fast.get("preparedId") or "",
            "fastPreviewUrl": "",
        },
        timeout=15,
    )
    elapsed = int((time.perf_counter() - started) * 1000)
    data = response.json()
    data.update({"statusCode": response.status_code, "createMs": elapsed})
    return data


def poll_detail(base_url: str, job_id: str, timeout: int = 360) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = requests.get(base_url + "/api/id-photo/detail-jobs/" + job_id, timeout=15)
        data = response.json()
        history.append({
            "at": time.time(),
            "status": data.get("status"),
            "queue": data.get("queue"),
        })
        if data.get("status") in {"completed", "failed", "cancelled"}:
            data["history"] = history
            return data
        time.sleep(1)
    return {"status": "timeout", "history": history}


def post_lama(base_url: str, image_path: Path, mask_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    with image_path.open("rb") as image_fh, mask_path.open("rb") as mask_fh:
        response = requests.post(
            base_url + "/api/watermark/hd-remove",
            files={
                "image": (image_path.name, image_fh, "image/jpeg"),
                "mask": (mask_path.name, mask_fh, "image/png"),
            },
            data={"strength": "medium", "preserveDetail": "true"},
            timeout=360,
        )
    elapsed = int((time.perf_counter() - started) * 1000)
    try:
        data = response.json()
    except Exception:
        data = {"text": response.text[:500]}
    return {
        "statusCode": response.status_code,
        "durationMs": elapsed,
        "success": data.get("success") is True,
        "engine": data.get("engine"),
        "fallbackUsed": data.get("fallbackUsed"),
        "queueWaitMs": (data.get("debug") or {}).get("queueWaitMs"),
        "code": data.get("code"),
    }


class ResourceSampler:
    def __init__(self, process_pids: list[int] | None = None, enabled: bool = True) -> None:
        self.enabled = enabled
        self.rows: list[dict[str, Any]] = []
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.processes: list[Any] = []
        if enabled and psutil is not None:
            if process_pids:
                self.processes = [psutil.Process(pid) for pid in process_pids]
            else:
                for process in psutil.process_iter(["cmdline"]):
                    try:
                        command = " ".join(process.info.get("cmdline") or [])
                        if "uvicorn" in command and any(port in command for port in ("8000", "8081", "8091")):
                            self.processes.append(process)
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        continue

    def start(self) -> None:
        if not self.enabled or psutil is None:
            return
        psutil.cpu_percent(interval=None)
        for process in self.processes:
            try:
                process.cpu_percent(interval=None)
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

        def run() -> None:
            while not self.stop_event.wait(0.5):
                memory = psutil.virtual_memory()
                swap = psutil.swap_memory()
                process_cpu = 0.0
                process_rss = 0
                live_pids: list[int] = []
                for process in self.processes:
                    try:
                        process_cpu += process.cpu_percent(interval=None)
                        process_rss += process.memory_info().rss
                        live_pids.append(process.pid)
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        continue
                self.rows.append({
                    "systemCpuPercent": psutil.cpu_percent(interval=None),
                    "processCpuPercent": round(process_cpu, 1),
                    "processRssMb": round(process_rss / 1024 / 1024, 1),
                    "systemMemoryUsedMb": round(memory.used / 1024 / 1024, 1),
                    "swapUsedMb": round(swap.used / 1024 / 1024, 1),
                    "pids": live_pids,
                })

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def stop(self) -> dict[str, Any]:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        return {
            "available": self.enabled and psutil is not None,
            "samples": len(self.rows),
            "processPids": sorted({pid for row in self.rows for pid in row.get("pids", [])}),
            "maxSystemCpuPercent": max((r["systemCpuPercent"] for r in self.rows), default=None),
            "maxProcessCpuPercent": max((r["processCpuPercent"] for r in self.rows), default=None),
            "maxProcessRssMb": max((r["processRssMb"] for r in self.rows), default=None),
            "maxSystemMemoryUsedMb": max((r["systemMemoryUsedMb"] for r in self.rows), default=None),
            "maxSwapUsedMb": max((r["swapUsedMb"] for r in self.rows), default=None),
        }


def wait_until_running(base_url: str, job_id: str, timeout: int = 20) -> dict[str, Any]:
    deadline = time.time() + timeout
    latest: dict[str, Any] = {}
    while time.time() < deadline:
        latest = requests.get(base_url + "/api/id-photo/detail-jobs/" + job_id, timeout=10).json()
        if latest.get("status") in {"running", "completed", "failed", "cancelled"}:
            return latest
        time.sleep(0.25)
    return latest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--fast-image", required=True)
    parser.add_argument("--detail-image", default="")
    parser.add_argument("--watermark-image", default="")
    parser.add_argument("--watermark-mask", default="")
    parser.add_argument("--include-lama", action="store_true")
    parser.add_argument("--process-pid", action="append", type=int, default=[])
    parser.add_argument("--disable-resource-sampling", action="store_true")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    fast_image = Path(args.fast_image)
    detail_image = Path(args.detail_image or args.fast_image)

    sampler = ResourceSampler(args.process_pid, enabled=not args.disable_resource_sampling)
    sampler.start()
    fast_rows = [post_fast(base_url, fast_image) for _ in range(10)]

    detail_seed = post_fast(base_url, detail_image)
    detail_create = create_detail(base_url, detail_seed)
    detail_state = wait_until_running(base_url, detail_create.get("jobId", "")) if detail_create.get("jobId") else detail_create
    fast_during_detail = post_fast(base_url, fast_image)
    detail_final = poll_detail(base_url, detail_create["jobId"]) if detail_create.get("jobId") else detail_create

    lama_sections: dict[str, Any] = {"tested": False, "reason": "--include-lama not supplied"}
    if args.include_lama:
        watermark_image = Path(args.watermark_image)
        watermark_mask = Path(args.watermark_mask)
        lama_sections = {"tested": True}

        lama_holder: dict[str, Any] = {}
        lama_thread = threading.Thread(target=lambda: lama_holder.update(post_lama(base_url, watermark_image, watermark_mask)))
        lama_thread.start()
        time.sleep(0.5)
        lama_sections["fastDuringLama"] = post_fast(base_url, fast_image)
        lama_thread.join()
        lama_sections["lamaWithFast"] = lama_holder

        detail_seed_2 = post_fast(base_url, detail_image)
        detail_create_2 = create_detail(base_url, detail_seed_2)
        if detail_create_2.get("jobId"):
            wait_until_running(base_url, detail_create_2["jobId"])
            lama_sections["lamaDuringDetail"] = post_lama(base_url, watermark_image, watermark_mask)
            lama_sections["detailWithLama"] = poll_detail(base_url, detail_create_2["jobId"])
        else:
            lama_sections["detailCreate"] = detail_create_2

    resource_usage = sampler.stop()
    fast_durations = [row["durationMs"] for row in fast_rows]
    checks = {
        "tenFastReturnedClearly": len(fast_rows) == 10 and all(row["clearResult"] for row in fast_rows),
        "tenFastNoSyncDetail": all(row.get("detailFallbackUsed") is False for row in fast_rows),
        "tenFastModnetOnly": all(row.get("selectedModel") == "hivision_modnet" for row in fast_rows),
        "tenFastUnder30Seconds": max(fast_durations, default=30001) < 30000,
        "fastDuringDetailUnder30Seconds": fast_during_detail.get("durationMs", 30001) < 30000,
        "detailIsAsync": detail_create.get("createMs", 30001) < 10000,
        "detailUsesBirefnet": detail_final.get("selectedModel") == "birefnet-v1-lite",
    }
    if args.include_lama:
        checks.update({
            "fastDuringLamaUnder30Seconds": (lama_sections.get("fastDuringLama") or {}).get("durationMs", 30001) < 30000,
            "lamaWithFastSucceeded": (lama_sections.get("lamaWithFast") or {}).get("success") is True,
            "lamaDuringDetailSucceeded": (lama_sections.get("lamaDuringDetail") or {}).get("success") is True,
            "detailWithLamaCompleted": (lama_sections.get("detailWithLama") or {}).get("status") == "completed",
        })

    payload = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "baseUrl": base_url,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fastImage": str(fast_image.resolve()),
        "detailImage": str(detail_image.resolve()),
        "tenFast": {"timing": timing(fast_durations), "rows": fast_rows},
        "fastWithDetail": {
            "detailCreate": detail_create,
            "detailInitialState": detail_state,
            "fast": fast_during_detail,
            "detailFinal": detail_final,
        },
        "lamaScenarios": lama_sections,
        "resourceUsage": resource_usage,
        "checks": checks,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "heavy-task-queue.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Heavy Task Queue",
        "",
        f"- Status: {payload['status']}",
        f"- Base URL: `{base_url}`",
        f"- Ten FAST: P50 {payload['tenFast']['timing']['p50Ms']} ms, P95 {payload['tenFast']['timing']['p95Ms']} ms, max {payload['tenFast']['timing']['maxMs']} ms",
        f"- FAST during DETAIL: {fast_during_detail.get('durationMs')} ms",
        f"- DETAIL create: {detail_create.get('createMs')} ms; final state: {detail_final.get('status')}",
        f"- Resource sample: process CPU max {resource_usage.get('maxProcessCpuPercent')}%, process RSS max {resource_usage.get('maxProcessRssMb')} MB, system CPU max {resource_usage.get('maxSystemCpuPercent')}%, Swap used max {resource_usage.get('maxSwapUsedMb')} MB",
        f"- LaMa scenarios: {'tested' if lama_sections.get('tested') else 'not tested on this target'}",
        "",
        "## Checks",
    ]
    lines.extend(f"- {key}: {'PASS' if value else 'FAIL'}" for key, value in checks.items())
    (REPORT_DIR / "heavy-task-queue.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[heavy-task-queue] {payload['status']} report={REPORT_DIR / 'heavy-task-queue.json'}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
