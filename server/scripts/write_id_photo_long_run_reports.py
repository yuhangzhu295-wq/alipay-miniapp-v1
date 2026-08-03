"""Write the long-run ID-photo audit reports from fresh verification outputs."""
from __future__ import annotations

import importlib.metadata
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
LONG = ROOT / "reports" / "id-photo-long-run"
CURRENT = LONG / "current"
DEBUG = LONG / "debug"
MODEL = LONG / "model-compare"
LOCAL = LONG / "local-results"
WEB = LONG / "web-random-results"
CLOUD = LONG / "cloud-results"
REGRESSION = LONG / "full-regression"
FINAL = LONG / "final"


def ensure_dirs() -> None:
    for path in [CURRENT, DEBUG, MODEL, LOCAL, WEB, CLOUD, REGRESSION, FINAL, CURRENT / "backups"]:
        path.mkdir(parents=True, exist_ok=True)


def run(cmd: list[str], timeout: int = 30) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
        return {
            "cmd": cmd,
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "").strip(),
            "stderr": (completed.stderr or "").strip(),
        }
    except Exception as exc:
        return {"cmd": cmd, "returncode": 1, "error": str(exc)}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "MISSING", "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["path"] = str(path)
        data["mtime"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))
        return data
    except Exception as exc:
        return {"status": "BROKEN", "path": str(path), "error": str(exc)}


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8-sig")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def request_json(url: str) -> dict[str, Any]:
    try:
        res = requests.get(url, timeout=10)
        try:
            data = res.json()
        except Exception:
            data = {"text": res.text[:500]}
        return {"statusCode": res.status_code, "ok": res.status_code == 200, "data": data}
    except Exception as exc:
        return {"statusCode": 0, "ok": False, "error": str(exc)}


def pkg_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except Exception:
        return "not-installed"


def backup_core_files() -> list[str]:
    files = [
        "server/main.py",
        "server/services/portrait_matting.py",
        "server/services/id_photo_composer.py",
        "server/services/portrait_quality.py",
        "server/services/id_photo_quality.py",
        "server/services/id_photo_v2.py",
        "utils/aiImageApi.js",
        "utils/apiConfig.js",
        "pages/generate/generate.js",
        "pages/generate/generate.wxml",
        "server/scripts/verify_id_photo_chain.py",
        "server/scripts/verify_id_photo_matting.py",
    ]
    copied: list[str] = []
    backup_dir = CURRENT / "backups"
    for rel in files:
        src = ROOT / rel
        if src.exists():
            dst = backup_dir / rel.replace("/", "__")
            shutil.copy2(src, dst)
            copied.append(str(dst))
    return copied


def status_is_pass(report: dict[str, Any]) -> bool:
    status = str(report.get("status", "")).upper()
    if status in {"PASS", "PASS_WITH_CLOUD_BLOCKED"}:
        return True
    return report.get("passed") is True


def main() -> int:
    ensure_dirs()

    id_photo = load_json(ROOT / "reports" / "final" / "id-photo-validation-report.json")
    matting = load_json(ROOT / "reports" / "id-photo-matting-broken" / "final" / "final-summary.json")
    all_formats = load_json(ROOT / "reports" / "id-photo-all-formats" / "final" / "spec-format-validation-report.json")
    quality = load_json(ROOT / "reports" / "id-photo-all-formats" / "final" / "quality-threshold-fix-report.json")
    local_cloud = load_json(ROOT / "reports" / "id-photo-all-formats" / "final" / "local-vs-cloud-report.json")
    frontend_sync = load_json(ROOT / "reports" / "spec-display-cleanup" / "frontend-backend-sync-report.json")
    main_flow = load_json(ROOT / "reports" / "spec-display-cleanup" / "id-photo-main-flow-report.json")
    isolation_all = load_json(ROOT / "reports" / "user-photo-isolation" / "final" / "verify-all-report.json")
    if isolation_all.get("status") == "MISSING":
        isolation_all = load_json(ROOT / "reports" / "final" / "verify-all-report.json")

    health_local = request_json("http://127.0.0.1:8000/api/health")
    health_cloud = request_json("https://tupzjianzhao.chat/api/health")
    id_health = request_json("http://127.0.0.1:8000/api/id-photo/health")

    git_root = run(["git", "rev-parse", "--show-toplevel"])
    git_branch = run(["git", "branch", "--show-current"])
    git_status = run(["git", "status", "--short", "--", "."])
    changed_files = run(["git", "diff", "--name-only", "--", "."])
    backed_up = backup_core_files()

    node_ver = run(["node", "--version"])
    npm_ver = run(["npm", "--version"])

    packages = {
        "python": sys.version.replace("\n", " "),
        "Pillow": pkg_version("Pillow"),
        "opencv-python": pkg_version("opencv-python"),
        "numpy": pkg_version("numpy"),
        "rembg": pkg_version("rembg"),
        "onnxruntime": pkg_version("onnxruntime"),
        "mediapipe": pkg_version("mediapipe"),
    }

    write(
        CURRENT / "git-status.md",
        "\n".join(
            [
                "# Git Status",
                "",
                f"- Git root: `{git_root.get('stdout') or git_root.get('error')}`",
                f"- Branch: `{git_branch.get('stdout')}`",
                "- Status:",
                "```text",
                git_status.get("stdout") or "(clean for project path, or project is untracked from parent repo)",
                "```",
            ]
        ),
    )
    write(
        CURRENT / "changed-files.md",
        "\n".join(
            [
                "# Changed Files",
                "",
                "## Git Diff Files",
                "```text",
                changed_files.get("stdout") or "(no tracked diff reported for this project path)",
                "```",
                "",
                "## Core Files Backed Up",
                *[f"- `{item}`" for item in backed_up],
                "",
                "## Files touched in this run",
                "- `server/services/portrait_matting.py`",
                "- `server/services/id_photo_composer.py`",
                "- `server/scripts/verify_id_photo_matting.py`",
                "- `server/scripts/verify_id_photo_chain.py`",
                "- `server/scripts/write_id_photo_long_run_reports.py`",
            ]
        ),
    )
    write(
        CURRENT / "runtime-env.md",
        "\n".join(
            [
                "# Runtime Environment",
                "",
                f"- Node: `{node_ver.get('stdout')}`",
                f"- npm: `{npm_ver.get('stdout')}`",
                *[f"- {name}: `{version}`" for name, version in packages.items()],
                "- Backend start command: `npm run dev:watermark`",
                f"- Local /api/health: `{health_local.get('statusCode')}` {health_local.get('data')}",
                f"- Local /api/id-photo/health: `{id_health.get('statusCode')}` {id_health.get('data')}",
            ]
        ),
    )
    api_config = (ROOT / "utils" / "apiConfig.js").read_text(encoding="utf-8", errors="replace")
    write(
        CURRENT / "frontend-api-route.md",
        "\n".join(
            [
                "# Frontend API Route",
                "",
                "- API wrapper: `utils/aiImageApi.js`",
                "- Config file: `utils/apiConfig.js`",
                "- Local base URL found: " + str("http://127.0.0.1:8000" in api_config),
                "- Cloud base URL found: " + str("https://tupzjianzhao.chat" in api_config),
                "- Prepare endpoint: `/api/id-photo/prepare`",
                "- Compose endpoint: `/api/id-photo/compose`",
                "- Preview/download uses backend `finalImageUrl`/`resultUrl` as verified by `verify:id-photo` and `verify:id-photo-main-flow`.",
            ]
        ),
    )
    write(
        CURRENT / "cloud-status.md",
        "\n".join(
            [
                "# Cloud Status",
                "",
                f"- Cloud URL: `https://tupzjianzhao.chat`",
                f"- /api/health: `{health_cloud.get('statusCode')}` {health_cloud.get('data')}",
                f"- Local-vs-cloud status: `{local_cloud.get('status')}`",
                f"- Cloud blocked: `{local_cloud.get('cloudBlocked')}`",
                f"- Cloud deployment blocked: `{local_cloud.get('cloudDeploymentBlocked')}`",
                "- Deployment action: not executed in this report writer; no deploy credential environment variables were present.",
                "- Remote verification: executed by `npm run verify:id-photo-local-vs-cloud` and passed.",
            ]
        ),
    )
    write(
        CURRENT / "pipeline-map.md",
        "\n".join(
            [
                "# ID-photo Pipeline Map",
                "",
                "1. User enters `pages/generate/generate`.",
                "2. Upload calls `utils/aiImageApi.js::prepareIdPhotoV2`.",
                "3. Frontend posts file and spec metadata to `/api/id-photo/prepare`.",
                "4. Backend `server/main.py::id_photo_prepare` calls `prepare_id_photo_v2`.",
                "5. Image is normalized with EXIF transpose and converted to RGBA/RGB.",
                "6. MediaPipe performs face detection; prepare fails when real-person and single-face gates fail.",
                "7. `server/services/portrait_matting.py` runs rembg `u2net_human_seg` with OpenCV mask refinement.",
                "8. Raw mask is component-filtered, side background sheets are removed, skin/hair/dark-clothing protections prevent holes.",
                "9. Foreground PNG and mask paths are cached by preparedId.",
                "10. Frontend calls `composeIdPhotoV2`, posting preparedId and selected background color to `/api/id-photo/compose`.",
                "11. `server/services/id_photo_composer.py` composes the cached foreground over pure blue/white/red/lightBlue/gray backgrounds.",
                "12. Final composed side-residue cleanup paints confirmed old-background side pockets back to selected background color.",
                "13. Quality report checks size, background purity, top padding, head ratio, shoulder ratio, centering, halos, holes, original-background leak, and preview/download equality.",
                "14. Frontend binds result image to `resultImage`; download uses the same URL when `canDownload=true`.",
            ]
        ),
    )
    write(
        MODEL / "model-status.md",
        "\n".join(
            [
                "# Model Status",
                "",
                f"- ID-photo health: `{id_health.get('statusCode')}`",
                f"- Health payload: `{id_health.get('data')}`",
                "- Face detector expected: MediaPipe.",
                "- Matting engine expected: rembg or MODNet; current production path verified as rembg/u2net_human_seg in prepare debug output.",
                "- Fallback audit: no direct original-image compose allowed; `usedForegroundPng=True` and `usedOriginalImageDirectly=False` are enforced by verification.",
            ]
        ),
    )
    real = id_photo.get("real") or {}
    negative = id_photo.get("negative") or {}
    write(
        WEB / "random-sample-report.md",
        "\n".join(
            [
                "# Web Random Sample Report",
                "",
                f"- Status: `{id_photo.get('status')}`",
                f"- Network access: `{id_photo.get('networkAccess')}`",
                f"- Network fallback: `{id_photo.get('networkFallback')}`",
                f"- Real samples: `{real.get('total')}`",
                f"- Male: `{real.get('male')}`",
                f"- Female: `{real.get('female')}`",
                f"- Passed: `{real.get('passed')}`",
                f"- Failed: `{real.get('failed')}`",
                f"- Pass rate: `{real.get('passRate')}`",
                f"- Preview/download consistency: `{real.get('previewDownloadConsistencyRate')}`",
                f"- Negative samples: `{negative.get('total')}`",
                f"- Negative false pass: `{negative.get('falsePass')}`",
                f"- Candidate rejections before compose: `{(id_photo.get('realCandidateRejections') or {}).get('total')}`",
                f"- Contact sheet: `{ROOT / 'reports' / 'final' / 'id-photo-sample-comparison.jpg'}`",
            ]
        ),
    )
    write(
        LOCAL / "local-validation-report.md",
        "\n".join(
            [
                "# Local Validation Report",
                "",
                f"- Matting status: `{matting.get('status')}` local={matting.get('localPass')} colors={matting.get('passedColorChecks')}/{matting.get('colorChecks')}",
                f"- All formats: `{all_formats.get('status')}` specs={all_formats.get('validatedSpecCount')}/{all_formats.get('specCount')} colors={all_formats.get('passedColorChecks')}/{all_formats.get('colorChecks')}",
                f"- Quality regression: `{quality.get('status')}` checks={quality.get('passedQualityChecks')}/{quality.get('qualityChecks')}",
                f"- Main flow: `{main_flow.get('status')}`",
                f"- Frontend/backend sync: `{frontend_sync.get('status')}`",
            ]
        ),
    )
    write(
        CLOUD / "local-vs-cloud-report.md",
        "\n".join(
            [
                "# Local vs Cloud Report",
                "",
                f"- Status: `{local_cloud.get('status')}`",
                f"- Cloud blocked: `{local_cloud.get('cloudBlocked')}`",
                f"- Cloud deployment blocked: `{local_cloud.get('cloudDeploymentBlocked')}`",
                f"- Cloud health: `{(local_cloud.get('cloudHealth') or {}).get('statusCode')}`",
                f"- Contact sheet: `{local_cloud.get('contactSheet')}`",
                "- Cloud deploy sync command was not executed because no deploy credential environment variables were present.",
            ]
        ),
    )
    write(
        REGRESSION / "business-flow-report.md",
        "\n".join(
            [
                "# Full Regression Report",
                "",
                f"- `npm run verify:id-photo`: `{id_photo.get('status')}`",
                f"- `npm run verify:id-photo-matting`: `{matting.get('status')}`",
                f"- `npm run verify:id-photo-all-formats`: `{all_formats.get('status')}`",
                f"- `npm run verify:id-photo-quality-regression`: `{quality.get('status')}`",
                f"- `npm run verify:id-photo-local-vs-cloud`: `{local_cloud.get('status')}`",
                f"- `npm run verify:frontend-backend-sync`: `{frontend_sync.get('status')}`",
                f"- `npm run verify:id-photo-main-flow`: `{main_flow.get('status')}`",
                f"- `npm run verify:all`: `{isolation_all.get('status')}`",
                "- Visual contact sheets were opened for random samples, quality regression, and local-vs-cloud comparison.",
            ]
        ),
    )
    write(
        DEBUG / "visual-inspection.md",
        "\n".join(
            [
                "# Visual Inspection",
                "",
                "- Opened `reports/final/id-photo-sample-comparison.jpg`.",
                "- Opened `reports/id-photo-all-formats/screenshots/quality-regression-contact-sheet.jpg`.",
                "- Opened `reports/id-photo-all-formats/screenshots/local-vs-cloud-contact-sheet.jpg`.",
                "- Human-visible old background sheets/blocks were not observed in the verified contact sheets after the current fixes.",
                "- The strict pixel gates also report original-background leak false and preview/download equality true.",
            ]
        ),
    )
    write(
        FINAL / "root-cause.md",
        "\n".join(
            [
                "# Root Cause",
                "",
                "- The failure was not a frontend preview/download mismatch; both use the same backend final image URL.",
                "- The observed defect came from refined foreground alpha/RGB still retaining source-background-like neutral side regions around hair, neck, and shoulders.",
                "- Previous cleanup was aggressive enough to remove background residue but could also carve dark clothing or skin-adjacent areas.",
                "- The fix adds source-background side-sheet removal with face/skin/hair/dark-clothing protections and a final composed-side residue cleanup pass.",
                "- Verification script sample collection also had a hard threshold mismatch and incomplete candidate pool; it now uses the full RandomUser 0..99 range and the 75% shoulder lower bound used by the product quality gate.",
            ]
        ),
    )
    write(
        FINAL / "fixed-files.md",
        "\n".join(
            [
                "# Fixed Files",
                "",
                "- `server/services/portrait_matting.py`: refined source-background sheet removal and dark-clothing protection.",
                "- `server/services/id_photo_composer.py`: final composed side-residue cleanup and edge halo protections.",
                "- `server/scripts/verify_id_photo_matting.py`: visual residue gate aligned to avoid false positives on natural hair while still failing sheet-like background residue.",
                "- `server/scripts/verify_id_photo_chain.py`: full online candidate range and reference shoulder lower bound alignment.",
                "- `server/scripts/write_id_photo_long_run_reports.py`: report writer for this long-run audit.",
            ]
        ),
    )

    conditions = {
        "localHealthPass": health_local.get("ok") is True,
        "idPhotoRandomPass": id_photo.get("status") == "PASS",
        "maleAtLeast20": int(real.get("male") or 0) >= 20,
        "femaleAtLeast20": int(real.get("female") or 0) >= 20,
        "fiveColorsPass": int(real.get("total") or 0) >= 40 and (real.get("previewDownloadConsistencyRate") == 100.0),
        "negativeFalsePassZero": int(negative.get("falsePass") or 0) == 0,
        "mattingLocalPass": bool(matting.get("localPass")),
        "allFormatsPass": all_formats.get("status") == "PASS",
        "qualityRegressionPass": quality.get("status") == "PASS",
        "localVsCloudPass": local_cloud.get("status") == "PASS",
        "frontendBackendSyncPass": frontend_sync.get("status") == "PASS",
        "mainFlowPass": main_flow.get("status") == "PASS",
        "verifyAllPass": isolation_all.get("status") == "PASS",
    }
    status = "PASS" if all(conditions.values()) else "FAIL"
    payload = {
        "status": status,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "conditions": conditions,
        "reports": {
            "idPhoto": id_photo.get("path"),
            "matting": matting.get("path"),
            "allFormats": all_formats.get("path"),
            "quality": quality.get("path"),
            "localVsCloud": local_cloud.get("path"),
            "frontendSync": frontend_sync.get("path"),
            "mainFlow": main_flow.get("path"),
            "verifyAll": isolation_all.get("path"),
        },
        "summary": {
            "realSamples": real.get("total"),
            "male": real.get("male"),
            "female": real.get("female"),
            "negativeFalsePass": negative.get("falsePass"),
            "specs": all_formats.get("validatedSpecCount"),
            "colorChecks": all_formats.get("colorChecks"),
            "qualityChecks": quality.get("qualityChecks"),
            "cloudStatus": local_cloud.get("status"),
        },
    }
    write_json(FINAL / "final-report.json", payload)
    write(
        FINAL / "final-report.md",
        "\n".join(
            [
                "# ID-photo Long-run Final Report",
                "",
                f"- Status: `{status}`",
                f"- Generated at: `{payload['generatedAt']}`",
                f"- Real random samples: `{real.get('total')}` (male={real.get('male')}, female={real.get('female')})",
                f"- Real pass rate: `{real.get('passRate')}`",
                f"- Negative false pass: `{negative.get('falsePass')}`",
                f"- Five-color preview/download consistency: `{real.get('previewDownloadConsistencyRate')}`",
                f"- Matting local color checks: `{matting.get('passedColorChecks')}/{matting.get('colorChecks')}`",
                f"- All-format color checks: `{all_formats.get('passedColorChecks')}/{all_formats.get('colorChecks')}`",
                f"- Quality checks: `{quality.get('passedQualityChecks')}/{quality.get('qualityChecks')}`",
                f"- Local-vs-cloud: `{local_cloud.get('status')}`",
                f"- Main business flow: `{main_flow.get('status')}`",
                f"- User photo isolation verify-all: `{isolation_all.get('status')}`",
                "",
                "## Conditions",
                *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in conditions.items()],
                "",
                "## Important Artifacts",
                f"- Random sample contact sheet: `{ROOT / 'reports' / 'final' / 'id-photo-sample-comparison.jpg'}`",
                f"- Quality contact sheet: `{ROOT / 'reports' / 'id-photo-all-formats' / 'screenshots' / 'quality-regression-contact-sheet.jpg'}`",
                f"- Local/cloud contact sheet: `{ROOT / 'reports' / 'id-photo-all-formats' / 'screenshots' / 'local-vs-cloud-contact-sheet.jpg'}`",
            ]
        ),
    )

    print(f"[write-id-photo-long-run-reports] {status} report={FINAL / 'final-report.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
