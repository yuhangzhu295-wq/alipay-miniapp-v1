"""Benchmark the two resident FAST sessions with explicit ORT thread counts."""
from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
REPORT_DIR = ROOT / "reports" / "id-photo-under-10s"
MODELS = ("hivision_modnet", "modnet_photographic_portrait_matting")
DEFAULT_SOURCES = (
    Path(r"C:\Users\zyu33\Desktop\6a83d1e010f6e9ed8c35af94f0c33936.jpg"),
    Path(r"C:\Users\zyu33\Desktop\610a7b3fadac6b4452736f72b8f3a492.jpg"),
    Path(r"C:\Users\zyu33\Desktop\217139c99959fa2888673f2100612b8f.jpg"),
)


def percentile(values: list[float], percentage: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentage + 0.999999)))
    return round(float(ordered[index]), 3)


def decode_metrics(header: str) -> dict[str, Any]:
    if not header:
        return {}
    padded = header + "=" * (-len(header) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


def wait_for_worker(base_url: str, process: subprocess.Popen[Any], timeout: int = 180) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"worker exited before health check: {process.returncode}")
        try:
            health = requests.get(base_url + "/health", timeout=3).json()
            if health.get("ready"):
                return health
        except Exception as exc:
            last_error = repr(exc)
        time.sleep(0.5)
    raise RuntimeError(f"worker did not become ready: {last_error}")


def request_matting(base_url: str, image_path: Path, model: str, phase: str) -> dict[str, Any]:
    started = time.perf_counter()
    response = requests.post(
        base_url + "/matting",
        params={"model": model},
        data=image_path.read_bytes(),
        headers={"Content-Type": "application/octet-stream"},
        timeout=60,
    )
    client_ms = round((time.perf_counter() - started) * 1000.0, 3)
    metrics = decode_metrics(response.headers.get("X-Hivision-Metrics", ""))
    return {
        "phase": phase,
        "source": str(image_path),
        "model": model,
        "statusCode": response.status_code,
        "clientMs": client_ms,
        "outputBytes": len(response.content),
        "metrics": metrics,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    client = [float(row["clientMs"]) for row in rows]
    inference = [float(row["metrics"].get("inferenceMs") or 0) for row in rows]
    rss = [float(row["metrics"].get("processRssMb") or 0) for row in rows]
    swap = [float(row["metrics"].get("swapUsedMb") or 0) for row in rows]
    return {
        "count": len(rows),
        "successCount": sum(row["statusCode"] == 200 for row in rows),
        "sessionReuseCount": sum(bool(row["metrics"].get("sessionReused")) for row in rows),
        "clientP50Ms": round(statistics.median(client), 3) if client else 0,
        "clientP95Ms": percentile(client, 0.95),
        "clientMaxMs": round(max(client), 3) if client else 0,
        "inferenceP50Ms": round(statistics.median(inference), 3) if inference else 0,
        "inferenceP95Ms": percentile(inference, 0.95),
        "maxRssMb": round(max(rss), 1) if rss else 0,
        "minSwapUsedMb": round(min(swap), 1) if swap else 0,
        "maxSwapUsedMb": round(max(swap), 1) if swap else 0,
    }


def run_configuration(
    intra_threads: int,
    port: int,
    target_sources: list[Path],
    ordinary_sources: list[Path],
) -> dict[str, Any]:
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(
        {
            "ID_PHOTO_ONNX_INTRA_OP_THREADS": str(intra_threads),
            "ID_PHOTO_ONNX_INTER_OP_THREADS": "1",
            "ID_PHOTO_HIVISION_STANDARD_MODEL": MODELS[0],
            "ID_PHOTO_HIVISION_FAST_B_MODEL": MODELS[1],
            "PYTHONUNBUFFERED": "1",
        }
    )
    stdout_path = REPORT_DIR / f"onnx-runtime-intra-{intra_threads}.out.log"
    stderr_path = REPORT_DIR / f"onnx-runtime-intra-{intra_threads}.err.log"
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "id_photo_engines.hivision.worker:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            cwd=SERVER,
            env=env,
            stdout=stdout,
            stderr=stderr,
        )
        try:
            startup = wait_for_worker(base_url, process)
            released = requests.post(base_url + "/release", timeout=30).json()
            cold = [
                request_matting(base_url, target_sources[index % len(target_sources)], model, "cold")
                for index, model in enumerate(MODELS)
            ]
            warm = [
                request_matting(
                    base_url,
                    target_sources[index % len(target_sources)],
                    MODELS[index % len(MODELS)],
                    "warm",
                )
                for index in range(20)
            ]
            ordinary = [
                request_matting(base_url, image_path, model, "ordinary")
                for image_path in ordinary_sources
                for model in MODELS
            ]
            final_health = requests.get(base_url + "/health", timeout=10).json()
        finally:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

    workload = warm + ordinary
    return {
        "intraOpThreads": intra_threads,
        "interOpThreads": 1,
        "startup": startup,
        "released": released,
        "cold": cold,
        "warm": warm,
        "ordinary": ordinary,
        "coldSummary": summarize(cold),
        "warmSummary": summarize(warm),
        "ordinarySummary": summarize(ordinary),
        "workloadSummary": summarize(workload),
        "finalHealth": final_health,
        "logs": {"stdout": str(stdout_path), "stderr": str(stderr_path)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", action="append")
    parser.add_argument("--ordinary-dir", default=str(ROOT / "reports" / "id-photo-samples" / "input"))
    parser.add_argument("--ordinary-count", type=int, default=20)
    parser.add_argument("--base-port", type=int, default=18091)
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    target_sources = [Path(item).resolve() for item in (args.image or DEFAULT_SOURCES)]
    ordinary_sources = sorted(Path(args.ordinary_dir).resolve().glob("*.jpg"))[: args.ordinary_count]
    missing = [str(path) for path in target_sources if not path.is_file()]
    if missing:
        raise SystemExit(f"missing target images: {missing}")
    if len(ordinary_sources) < args.ordinary_count:
        raise SystemExit(f"expected {args.ordinary_count} ordinary images, found {len(ordinary_sources)}")

    configurations = [
        run_configuration(1, args.base_port, target_sources, ordinary_sources),
        run_configuration(2, args.base_port + 1, target_sources, ordinary_sources),
    ]
    ranked = sorted(
        configurations,
        key=lambda item: (
            item["workloadSummary"]["clientP95Ms"],
            item["workloadSummary"]["maxRssMb"],
        ),
    )
    selected = ranked[0]
    passed = all(
        config["workloadSummary"]["successCount"] == config["workloadSummary"]["count"]
        and config["workloadSummary"]["sessionReuseCount"] == config["workloadSummary"]["count"]
        and len(config["finalHealth"].get("loadedSessions") or []) == 2
        for config in configurations
    )
    payload = {
        "status": "PASS" if passed else "FAIL",
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "environment": {
            "scope": "local-isolated-worker",
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "processor": platform.processor(),
        },
        "targetSources": [str(path) for path in target_sources],
        "ordinarySources": [str(path) for path in ordinary_sources],
        "configurations": configurations,
        "decision": {
            "intraOpThreads": selected["intraOpThreads"],
            "interOpThreads": 1,
            "basis": "lowest warm-plus-ordinary client P95, then lowest peak RSS",
            "requiresCloudConfirmation": True,
        },
    }
    json_path = REPORT_DIR / "onnx-runtime-local.json"
    md_path = REPORT_DIR / "onnx-runtime-local.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# ONNX Runtime Local A/B",
        "",
        "- Scope: isolated local worker; production AMD result must be confirmed after deployment.",
        f"- Status: **{payload['status']}**",
        f"- Preliminary selection: intra-op `{payload['decision']['intraOpThreads']}`, inter-op `1`.",
        "",
        "| Intra | Cold P95 | Warm P95 | Workload P95 | Inference P95 | Peak RSS | Swap delta |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for config in configurations:
        cold = config["coldSummary"]
        warm = config["warmSummary"]
        workload = config["workloadSummary"]
        lines.append(
            f"| {config['intraOpThreads']} | {cold['clientP95Ms']} ms | {warm['clientP95Ms']} ms | "
            f"{workload['clientP95Ms']} ms | {workload['inferenceP95Ms']} ms | {workload['maxRssMb']} MB | "
            f"{round(workload['maxSwapUsedMb'] - workload['minSwapUsedMb'], 1)} MB |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "decision": payload["decision"]}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
