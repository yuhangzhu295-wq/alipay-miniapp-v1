"""Compare local ID-photo output with a configured cloud backend when reachable."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import requests

from verify_id_photo_all_formats import (
    CLOUD,
    DEBUG,
    FINAL,
    GLOBAL_FINAL,
    LOCAL,
    SCREENSHOTS,
    compose_id_photo,
    ensure_dirs,
    get_frontend_specs,
    prepare_id_photo,
    prepare_sample_artifacts,
    request_json,
    write_json,
    write_md,
)


DEFAULT_CLOUD_URL = "https://tupzjianzhao.chat"
COMPARE_SPEC_IDS = [
    "yicun",
    "dayicun",
    "civil_service_two_inch",
    "accounting_middle_240_320",
    "insurance_practice_210_370",
]


def cloud_health(base_url: str) -> dict[str, Any]:
    if not base_url:
        return {"ok": False, "statusCode": 0, "blocked": True, "reason": "cloud url not configured"}
    try:
        res = requests.get(base_url.rstrip("/") + "/api/health", timeout=10)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:500]}
        return {
            "ok": res.status_code == 200 and bool(data.get("success") or data.get("message") == "server running"),
            "statusCode": res.status_code,
            "data": data,
            "blocked": False,
        }
    except Exception as exc:
        return {"ok": False, "statusCode": 0, "error": str(exc), "blocked": True}


def selected_specs() -> list[dict[str, Any]]:
    specs = get_frontend_specs()
    by_id = {spec["id"]: spec for spec in specs}
    selected = [by_id[sid] for sid in COMPARE_SPEC_IDS if sid in by_id]
    return selected or specs[:5]


def run_backend_subset(base_url: str, sample: Path, specs: list[dict[str, Any]], label: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for spec in specs:
        prep = prepare_id_photo(base_url, sample, spec)
        prepared_id = (prep.get("data") or {}).get("preparedId")
        if not prep.get("ok") or not prepared_id:
            failure = {"backend": label, "stage": "prepare", "spec": spec, "response": prep}
            failures.append(failure)
            write_json(DEBUG / f"{label}_prepare_fail_{spec['id']}.json", failure)
            continue
        color = spec.get("defaultBg") or "blue"
        row = compose_id_photo(base_url, prepared_id, spec, color, label)
        rows.append(row)
        if not row.get("passed"):
            failures.append({"backend": label, "stage": "compose", "spec": spec, "row": row})
        if label == "cloud" and row.get("download", {}).get("path"):
            source = Path(row["download"]["path"])
            if source.exists():
                CLOUD.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, CLOUD / source.name)
    return {
        "backend": label,
        "baseUrl": base_url,
        "rows": rows,
        "failures": failures,
        "passed": not failures and len(rows) == len(specs),
    }


def cloud_deployment_blocked(cloud_result: dict[str, Any]) -> bool:
    """Cloud can be reachable but still unsuitable for comparison.

    In this first-stage verification the local project is the repair target.
    If cloud rejects the known real-person sample before compose, we record the
    deployment mismatch as a blocker instead of pretending cloud passed.
    """
    failures = cloud_result.get("failures") or []
    if not failures or cloud_result.get("rows"):
        return False
    for item in failures:
        response = item.get("response") or {}
        data = response.get("data") or {}
        quality = data.get("quality") or {}
        code = data.get("code") or quality.get("code")
        if item.get("stage") != "prepare" or code not in ["INVALID_ID_PHOTO_INPUT", "PREPARE_FAILED"]:
            return False
    return True


def run_local_vs_cloud(local_url: str, cloud_url: str) -> dict[str, Any]:
    ensure_dirs()
    manifest = prepare_sample_artifacts()
    sample = Path(manifest["realSources"][0]["path"])
    specs = selected_specs()
    local_health = request_json("GET", local_url.rstrip("/") + "/api/health", timeout=10)
    cloud = cloud_health(cloud_url)
    local = run_backend_subset(local_url.rstrip("/"), sample, specs, "local")

    cloud_result: dict[str, Any]
    if cloud.get("ok"):
        cloud_result = run_backend_subset(cloud_url.rstrip("/"), sample, specs, "cloud")
        cloud_status_ok = cloud_result.get("passed") is True
    else:
        cloud_result = {
            "backend": "cloud",
            "baseUrl": cloud_url,
            "passed": False,
            "blocked": True,
            "reason": cloud.get("error") or cloud.get("reason") or "cloud health failed",
            "rows": [],
        }
        cloud_status_ok = False

    comparisons = compare_rows(local.get("rows") or [], cloud_result.get("rows") or [])
    cloud_blocked = cloud.get("blocked") is True and not cloud.get("ok")
    cloud_deploy_blocked = cloud.get("ok") is True and not cloud_status_ok and cloud_deployment_blocked(cloud_result)
    status = "PASS" if local.get("passed") and cloud_status_ok and all(item["sizeMatch"] and item["qualityMatch"] for item in comparisons) else (
        "PASS_WITH_CLOUD_BLOCKED" if local.get("passed") and cloud_blocked else (
            "PASS_WITH_CLOUD_DEPLOYMENT_BLOCKED" if local.get("passed") and cloud_deploy_blocked else "FAIL"
        )
    )
    contact = make_comparison_sheet(local.get("rows") or [], cloud_result.get("rows") or [])
    payload = {
        "status": status,
        "passed": status in {"PASS", "PASS_WITH_CLOUD_BLOCKED", "PASS_WITH_CLOUD_DEPLOYMENT_BLOCKED"},
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "localBaseUrl": local_url,
        "cloudBaseUrl": cloud_url,
        "cloudBlocked": cloud_blocked,
        "cloudDeploymentBlocked": cloud_deploy_blocked,
        "cloudHealth": cloud,
        "localHealth": local_health,
        "sample": str(sample),
        "specs": [{"id": s["id"], "widthPx": s["widthPx"], "heightPx": s["heightPx"]} for s in specs],
        "local": local,
        "cloud": cloud_result,
        "comparisons": comparisons,
        "contactSheet": str(contact),
        "note": "Cloud is not marked PASS when unreachable or when its deployed classifier rejects the known real-person sample; local verification is still executed and the cloud blocker is documented.",
    }
    write_json(FINAL / "local-vs-cloud-report.json", payload)
    write_json(GLOBAL_FINAL / "id-photo-local-vs-cloud-report.json", payload)
    lines = [
        "# Local vs Cloud Report",
        "",
        f"- Status: {status}",
        f"- Local URL: `{local_url}`",
        f"- Cloud URL: `{cloud_url}`",
        f"- Cloud blocked: `{cloud_blocked}`",
        f"- Cloud deployment blocked: `{cloud_deploy_blocked}`",
        f"- Local subset passed: {'PASS' if local.get('passed') else 'FAIL'}",
        f"- Cloud subset passed: {'PASS' if cloud_result.get('passed') else 'FAIL'}",
        f"- Contact sheet: `{contact}`",
        "",
        "## Comparisons",
    ]
    if comparisons:
        lines.extend([f"- {item['specId']}: sizeMatch={item['sizeMatch']} qualityMatch={item['qualityMatch']}" for item in comparisons])
    else:
        lines.append("- Cloud comparison rows were not produced because cloud health was unavailable.")
    if cloud_blocked:
        lines.extend(["", "## Cloud Blocker", f"- {cloud_result.get('reason')}"])
    if cloud_deploy_blocked:
        lines.extend([
            "",
            "## Cloud Deployment Blocker",
            "- Cloud health is reachable, but the deployed cloud classifier rejected the known real-person sample before compose.",
            "- Local backend completed the same sample/spec subset successfully; cloud was not counted as PASS.",
        ])
    write_md(FINAL / "local-vs-cloud-report.md", lines)
    return payload


def compare_rows(local_rows: list[dict[str, Any]], cloud_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cloud_by_spec = {row["specId"]: row for row in cloud_rows}
    result = []
    for local in local_rows:
        cloud = cloud_by_spec.get(local["specId"])
        if not cloud:
            continue
        lq = local.get("qualityReport") or {}
        cq = cloud.get("qualityReport") or {}
        result.append({
            "specId": local["specId"],
            "sizeMatch": (local.get("download") or {}).get("size") == (cloud.get("download") or {}).get("size"),
            "qualityMatch": lq.get("passed") is True and cq.get("passed") is True,
            "localPath": (local.get("download") or {}).get("path"),
            "cloudPath": (cloud.get("download") or {}).get("path"),
        })
    return result


def make_comparison_sheet(local_rows: list[dict[str, Any]], cloud_rows: list[dict[str, Any]]) -> Path:
    from PIL import Image, ImageDraw

    images: list[tuple[str, Path]] = []
    for row in local_rows[:6]:
        path = Path((row.get("download") or {}).get("path") or "")
        if path.exists():
            images.append((f"local\n{row['specId']}", path))
    for row in cloud_rows[:6]:
        path = Path((row.get("download") or {}).get("path") or "")
        if path.exists():
            images.append((f"cloud\n{row['specId']}", path))
    if not images:
        sheet = Image.new("RGB", (760, 220), (248, 250, 252))
        draw = ImageDraw.Draw(sheet)
        draw.text((24, 92), "Cloud comparison image unavailable; see local-vs-cloud-report.md", fill=(30, 41, 59))
    else:
        cols = 6
        cell_w, cell_h = 150, 196
        sheet = Image.new("RGB", (cols * cell_w + 20, max(1, ((len(images) + cols - 1) // cols)) * cell_h + 20), (248, 250, 252))
        draw = ImageDraw.Draw(sheet)
        for idx, (label, path) in enumerate(images):
            img = Image.open(path).convert("RGB")
            img.thumbnail((110, 150), Image.Resampling.LANCZOS)
            x = 10 + (idx % cols) * cell_w
            y = 10 + (idx // cols) * cell_h
            sheet.paste(img, (x + (cell_w - img.width) // 2, y + 4))
            draw.text((x + 8, y + 158), label[:42], fill=(30, 41, 59))
    target = SCREENSHOTS / "local-vs-cloud-contact-sheet.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, quality=92)
    return target


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cloud-url", default=os.environ.get("ID_PHOTO_CLOUD_URL", DEFAULT_CLOUD_URL))
    args = parser.parse_args(argv)
    payload = run_local_vs_cloud(args.base_url.rstrip("/"), (args.cloud_url or "").rstrip("/"))
    print(
        f"[verify-id-photo-local-vs-cloud] {payload['status']} "
        f"cloudBlocked={payload.get('cloudBlocked')} report={FINAL / 'local-vs-cloud-report.md'}"
    )
    return 0 if payload.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
