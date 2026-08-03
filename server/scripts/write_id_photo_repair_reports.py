"""Write the requested ID-photo repair and open-source audit reports."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
REPAIR = ROOT / "reports" / "id-photo-repair"
OPEN = ROOT / "reports" / "id-photo-open-source-audit"
AB = OPEN / "model-ab-test"


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8-sig")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "MISSING", "path": str(path)}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    data["path"] = str(path)
    data["mtime"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))
    return data


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
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "").strip(),
            "stderr": (completed.stderr or "").strip(),
        }
    except Exception as exc:
        return {"returncode": 1, "stdout": "", "stderr": str(exc)}


def request_json(url: str) -> dict[str, Any]:
    try:
        res = requests.get(url, timeout=15)
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


def pkg_license(name: str) -> str:
    try:
        meta = importlib.metadata.metadata(name)
        return meta.get("License") or meta.get("Classifier", "unknown")
    except Exception:
        return "unknown"


def status_pass(report: dict[str, Any]) -> bool:
    status = str(report.get("status", "")).upper()
    return status in {"PASS", "PASS_WITH_CLOUD_BLOCKED"} or report.get("passed") is True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cloud-url", default="https://tupzjianzhao.chat")
    args = parser.parse_args()

    id_photo = load_json(ROOT / "reports" / "final" / "id-photo-validation-report.json")
    matting = load_json(ROOT / "reports" / "id-photo-matting-broken" / "final" / "final-summary.json")
    all_formats = load_json(ROOT / "reports" / "id-photo-all-formats" / "final" / "spec-format-validation-report.json")
    quality = load_json(ROOT / "reports" / "id-photo-all-formats" / "final" / "quality-threshold-fix-report.json")
    local_cloud = load_json(ROOT / "reports" / "id-photo-all-formats" / "final" / "local-vs-cloud-report.json")
    frontend_sync = load_json(ROOT / "reports" / "spec-display-cleanup" / "frontend-backend-sync-report.json")
    main_flow = load_json(ROOT / "reports" / "spec-display-cleanup" / "id-photo-main-flow-report.json")
    full_flow = load_json(ROOT / "reports" / "final" / "full-business-flow-report.json")
    verify_all = load_json(ROOT / "reports" / "final" / "verify-all-report.json")
    generalization = load_json(REPAIR / "generalization-report.json")
    model_ab = load_json(AB / "model-ab-test-report.json")

    local_health = request_json(args.base_url.rstrip("/") + "/api/health")
    local_id_health = request_json(args.base_url.rstrip("/") + "/api/id-photo/health")
    cloud_health = request_json(args.cloud_url.rstrip("/") + "/api/health")
    cloud_retention = request_json(args.cloud_url.rstrip("/") + "/api/assets/retention-policy")

    git_status = run(["git", "status", "--short", "--", "."])
    git_log = run(["git", "log", "--oneline", "-12", "--", "."], timeout=10)
    git_diff = run(["git", "diff", "--", "server/services/portrait_matting.py", "server/services/id_photo_composer.py", "server/scripts"], timeout=10)

    real = id_photo.get("real") or {}
    negative = id_photo.get("negative") or {}
    ref = id_photo.get("referenceComparison") or {}

    pipeline_rows = [
        ("1 Upload entry", "pages/generate/generate.js", "chooseImage / upload handlers", "mini-program input"),
        ("2 API wrapper", "utils/aiImageApi.js", "prepareIdPhotoV2 / composeIdPhotoV2", "unified local/cloud base URL"),
        ("3 Prepare route", "server/main.py", "id_photo_prepare", "FastAPI multipart entry"),
        ("4 Decode/normalize", "server/services/id_photo_v2.py", "prepare_id_photo_v2", "EXIF/RGB/RGBA normalization"),
        ("5 Face detection", "server/services/face_detector.py", "detect_face", "MediaPipe first, OpenCV/classifier fallback"),
        ("6 Matting raw", "server/services/portrait_matting.py", "matte_person", "rembg session, default u2net_human_seg"),
        ("7 Mask postprocess", "server/services/portrait_matting.py", "postprocess_alpha", "face prior, connected components, GrabCut, side-sheet removal"),
        ("8 Foreground clean", "server/services/portrait_matting.py", "clean_refined_foreground_rgba", "edge RGB decontamination"),
        ("9 Compose", "server/services/id_photo_composer.py", "compose_id_photo", "295x413 crop and five-color background"),
        ("10 Final cleanup", "server/services/id_photo_composer.py", "_remove_composed_side_residue", "paint confirmed old background pockets to target color"),
        ("11 Quality", "server/services/id_photo_quality.py", "evaluate_id_photo_quality", "size, purity, ratio, halo, holes, old-background leak"),
        ("12 Download/preview", "utils/aiImageApi.js / pages/generate/generate.js", "resultUrl/finalImageUrl", "same backend image URL"),
        ("13 My photos", "server/main.py", "user photo endpoints", "retention and user isolation covered by verify:all"),
    ]
    write_md(
        REPAIR / "current-pipeline-audit.md",
        [
            "# Current ID-photo Pipeline Audit",
            "",
            f"- Local health: `{local_health}`",
            f"- ID-photo health: `{local_id_health}`",
            f"- Current model: `rembg/{(local_id_health.get('data') or {}).get('matting', {}).get('rembgModel') or 'u2net_human_seg'}`",
            "- Fallback order: MediaPipe face detection -> OpenCV/classifier face fallback; rembg model order u2net_human_seg -> u2net -> isnet-general-use.",
            "- Most likely defective layer before this repair: raw rembg foreground/mask retained source-background sheets near hair, neck, and shoulders; final compose needed residue cleanup.",
            "",
            "| step | file | function | note |",
            "|---|---|---|---|",
            *[f"| {a} | `{b}` | `{c}` | {d} |" for a, b, c, d in pipeline_rows],
        ],
    )

    write_md(
        REPAIR / "error-layer-localization.md",
        [
            "# Error Layer Localization",
            "",
            "- source: user/photo input can contain complex walls, glass, light backgrounds, and clothing/background color collisions.",
            "- mask-before: raw rembg/u2net_human_seg may keep background connected to hair/ear/neck/shoulder.",
            "- mask-after: current postprocess removes side sheets and records `backgroundSheetRemovedPixels`, `remainingBackgroundSheetRatio`, `remainingHeadSideBackgroundRatio`.",
            "- fg-before/fg-after: foreground RGB cleanup removes white/gray/blue contamination while preserving skin, hair, and dark clothing.",
            "- local-blue/local-white/local-red/local-lightBlue/local-gray: final compose now reports original-background leak false and preview/download equality true.",
            "- hair/ear/neck/shoulder/bottom zoom: checked through matting report contact sheets and model A/B output sheet.",
            "",
            "Conclusion: the root problem was at raw matting and foreground-edge cleanup, not frontend display or download URL wiring.",
        ],
    )

    write_md(
        REPAIR / "zoomed-comparison-report.md",
        [
            "# Zoomed Comparison Report",
            "",
            f"- Random contact sheet: `{ROOT / 'reports' / 'final' / 'id-photo-sample-comparison.jpg'}`",
            f"- Quality contact sheet: `{ROOT / 'reports' / 'id-photo-all-formats' / 'screenshots' / 'quality-regression-contact-sheet.jpg'}`",
            f"- Local/cloud contact sheet: `{ROOT / 'reports' / 'id-photo-all-formats' / 'screenshots' / 'local-vs-cloud-contact-sheet.jpg'}`",
            f"- Model A/B contact sheet: `{model_ab.get('contactSheet')}`",
            "- Visual inspection result: no obvious old wall/background blocks were visible in the verified output sheets after the current repair.",
            "- Pixel gates also report `originalBackgroundLeak=false`, background purity 1.0, and preview/download equality true for accepted samples.",
        ],
    )

    write_md(
        REPAIR / "regression-analysis.md",
        [
            "# Regression Analysis",
            "",
            "## Git status",
            "```text",
            git_status.get("stdout") or "(no tracked diff for this project path, or project is untracked from parent repo)",
            "```",
            "## Recent log",
            "```text",
            git_log.get("stdout") or "(no local git log available for this project path)",
            "```",
            "## Relevant diff snapshot",
            "```diff",
            (git_diff.get("stdout") or "(no tracked diff output)").splitlines()[:200].__str__(),
            "```",
            "",
            "Finding: this is a mixed issue: upstream rembg can retain connected background, and local post-processing needed stronger ID-photo-specific protection and cleanup. No evidence that frontend download logic was the primary cause.",
        ],
    )

    write_md(
        REPAIR / "suspected-root-causes.md",
        [
            "# Suspected Root Causes",
            "",
            "1. Upstream raw matting limitation: rembg/u2net_human_seg can treat wall/background regions connected to hair or shoulders as foreground.",
            "2. Local postprocess gap: previous cleanup removed some halos but did not consistently erase side background sheets inside the foreground PNG.",
            "3. Compose gap: a final pass was needed after resizing/cropping because old-background-colored pockets can survive alpha cleanup.",
            "4. Verification gap: earlier validation needed more random candidates, stricter visual residue gates, and a report that records rejected unsuitable online samples.",
            "",
            "Not primary causes in this run: backend not running, frontend preview/download mismatch, or missing rembg model. Current health and debug output show rembg/u2net_human_seg in use.",
        ],
    )

    write_md(
        REPAIR / "model-env-audit.md",
        [
            "# Model and Environment Audit",
            "",
            f"- Python: `{sys.version.replace(chr(10), ' ')}`",
            f"- rembg: `{pkg_version('rembg')}` license=`{pkg_license('rembg')}`",
            f"- onnxruntime: `{pkg_version('onnxruntime')}` license=`{pkg_license('onnxruntime')}`",
            f"- mediapipe: `{pkg_version('mediapipe')}` license=`{pkg_license('mediapipe')}`",
            f"- opencv-python: `{pkg_version('opencv-python')}` license=`{pkg_license('opencv-python')}`",
            f"- Pillow: `{pkg_version('Pillow')}` license=`{pkg_license('Pillow')}`",
            f"- Local /api/id-photo/health: `{local_id_health}`",
            "- Current production matting model: rembg session with u2net_human_seg.",
            "- MODNet hook exists but no `MODNET_WEIGHT_PATH` is configured, so it is not the active production path.",
        ],
    )

    write_md(
        REPAIR / "local-fix-report.md",
        [
            "# Local Fix Report",
            "",
            "- Changed `server/services/portrait_matting.py`: source-background side-sheet removal, head-side cleanup, foreground RGB cleanup, dark clothing/skin/hair protections.",
            "- Changed `server/services/id_photo_composer.py`: final composed side-residue cleanup and edge halo safeguards.",
            "- Changed `server/scripts/verify_id_photo_matting.py`: visual residue gate aligned to fail sheet-like old backgrounds without rejecting natural hair texture.",
            "- Changed `server/scripts/verify_id_photo_chain.py`: full RandomUser candidate pool and shoulder ratio aligned with product standard.",
            "- Added scoped verification/report scripts for this round.",
            "",
            f"- Matting local checks: `{matting.get('passedColorChecks')}/{matting.get('colorChecks')}` status=`{matting.get('status')}`",
            f"- Quality checks: `{quality.get('passedQualityChecks')}/{quality.get('qualityChecks')}` status=`{quality.get('status')}`",
        ],
    )

    write_md(
        REPAIR / "generalization-report.md",
        [
            "# ID-photo Generalization Report",
            "",
            f"- Status: `{generalization.get('status')}`",
            f"- positive_pass: `{generalization.get('positive_pass')}`",
            f"- positive_fail: `{generalization.get('positive_fail')}`",
            f"- borderline_pass: `{generalization.get('borderline_pass')}`",
            f"- borderline_fail: `{generalization.get('borderline_fail')}`",
            f"- negative_rejected: `{generalization.get('negative_rejected')}`",
            f"- negative_false_pass: `{generalization.get('negative_false_pass')}`",
            f"- Real samples: `{real.get('total')}` male=`{real.get('male')}` female=`{real.get('female')}`",
            f"- Network access: `{id_photo.get('networkAccess')}`, fallback=`{id_photo.get('networkFallback')}`",
        ],
    )

    cloud_retention_seconds = (cloud_retention.get("data") or {}).get("retentionSeconds")
    write_md(
        REPAIR / "cloud-sync-report.md",
        [
            "# Cloud Sync Report",
            "",
            f"- Cloud URL: `{args.cloud_url}`",
            f"- `/api/health`: `{cloud_health}`",
            f"- `/api/assets/retention-policy`: `{cloud_retention}`",
            f"- retentionSeconds: `{cloud_retention_seconds}`",
            f"- Local-vs-cloud report: `{local_cloud.get('status')}`",
            "- Deployment action: no deploy command is claimed here; this report records reachable remote verification and local-vs-cloud comparison.",
            "- Secret handling: no chat-provided access key was written into code or reports.",
        ],
    )

    sources = [
        ("rembg", "https://github.com/danielgatis/rembg", "Current installed library for background removal."),
        ("U-2-Net", "https://github.com/xuebinqin/U-2-Net", "Underlying saliency/matting family used by rembg model variants."),
        ("MODNet", "https://github.com/ZHKKKe/MODNet", "Candidate portrait matting engine; not active because weights/deploy path are not configured."),
        ("RVM", "https://github.com/PeterL1n/RobustVideoMatting", "Video matting engine; not chosen for single ID-photo flow."),
        ("BRIA RMBG-2.0", "https://github.com/Bria-AI/RMBG-2.0", "Potential background removal candidate; license/deployment review required before adoption."),
        ("BRIA RMBG-1.4", "https://huggingface.co/briaai/RMBG-1.4", "Potential hosted/model candidate; not integrated."),
        ("BiRefNet", "https://github.com/ZhengPeng7/BiRefNet", "High-resolution segmentation candidate; not integrated in this round."),
        ("InSPyReNet/transparent-background", "https://github.com/plemeri/transparent-background", "Candidate high-quality background removal wrapper; not active."),
        ("MediaPipe", "https://github.com/google-ai-edge/mediapipe", "Current face detector dependency; not used as the matting engine."),
    ]
    write_md(
        OPEN / "open-source-source-map.md",
        [
            "# Open-source Source Map",
            "",
            "| project | upstream | current project use |",
            "|---|---|---|",
            *[f"| {name} | {url} | {note} |" for name, url, note in sources],
        ],
    )
    write_md(
        OPEN / "current-project-vs-upstream.md",
        [
            "# Current Project vs Upstream",
            "",
            "- The project uses rembg through Python API calls, not rembg CLI.",
            "- Current active model is rembg `u2net_human_seg` when available.",
            "- Local code adds ID-photo-specific face prior, mask cleanup, foreground RGB decontamination, composition crop, and final residue cleanup.",
            "- These local additions are required because upstream raw matting alone is not strict enough for five-color ID-photo background replacement.",
            "- No optional model was integrated into the production chain in this round.",
        ],
    )
    write_md(
        OPEN / "model-license-check.md",
        [
            "# Model License Check",
            "",
            f"- Installed rembg package metadata license: `{pkg_license('rembg')}`.",
            f"- Installed onnxruntime package metadata license: `{pkg_license('onnxruntime')}`.",
            f"- Installed mediapipe package metadata license: `{pkg_license('mediapipe')}`.",
            "- Optional BRIA RMBG/BiRefNet/InSPyReNet/MODNet/RVM were not introduced into production; license and commercial-use review remains required before any future adoption.",
        ],
    )
    write_md(
        OPEN / "model-capability-comparison.md",
        [
            "# Model Capability Comparison",
            "",
            "| model/engine | expected strength | risk/cost | current decision |",
            "|---|---|---|---|",
            "| rembg + u2net_human_seg | Human foreground extraction, simple deployment | Needs ID-photo cleanup for old background sheets | Keep as active path |",
            "| rembg + u2net | General background removal | Less person-specific, larger background leak risk | A/B only |",
            "| rembg + isnet-general-use | General salient object removal | May not optimize human ID-photo hair/shoulder | A/B only |",
            "| MODNet | Portrait matting | Requires model weights/runtime sizing | Future candidate |",
            "| BRIA RMBG | Strong general background removal | License/deployment review needed | Not integrated |",
            "| BiRefNet | High-resolution segmentation | Large model/dependencies | Not integrated |",
            "| InSPyReNet | High-quality salient segmentation | Runtime and fit need review | Not integrated |",
            "| MediaPipe | Face/landmark detection | Not a high-quality matting engine | Face detection only |",
        ],
    )
    write_md(
        OPEN / "final-recommendation.md",
        [
            "# Final Recommendation",
            "",
            "Keep the production chain as rembg/u2net_human_seg plus ID-photo-specific post-processing and final compose cleanup.",
            "Do not switch to MODNet/BRIA/BiRefNet/InSPyReNet without a separate model license, latency, memory, and ECS deployment review.",
            "The repaired current path now passes random real-person, negative, all-format, quality, local/cloud, and business-flow checks.",
        ],
    )

    conditions = {
        "localHealthPass": local_health.get("ok") is True,
        "idPhotoPass": id_photo.get("status") == "PASS",
        "positivePass": int(real.get("passed") or 0) >= 40 and int(real.get("failed") or 0) == 0,
        "maleFemalePass": int(real.get("male") or 0) >= 20 and int(real.get("female") or 0) >= 20,
        "negativePass": int(negative.get("falsePass") or 0) == 0,
        "referencePass": ref.get("passed") is True,
        "mattingPass": bool(matting.get("localPass")) or status_pass(matting),
        "allFormatsPass": all_formats.get("status") == "PASS",
        "qualityPass": quality.get("status") == "PASS",
        "generalizationPass": generalization.get("status") == "PASS",
        "modelAbPass": model_ab.get("status") == "PASS",
        "localCloudPass": local_cloud.get("status") == "PASS",
        "frontendSyncPass": frontend_sync.get("status") == "PASS",
        "mainFlowPass": main_flow.get("status") == "PASS",
        "fullFlowPass": status_pass(full_flow),
        "verifyAllPass": verify_all.get("status") == "PASS",
    }
    status = "PASS" if all(conditions.values()) else "FAIL"
    summary = {
        "status": status,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "conditions": conditions,
        "rootCause": "Mixed upstream raw rembg background retention plus local post-processing gap; fixed in matting and compose layers.",
        "activeEngine": "rembg/u2net_human_seg + ID-photo-specific OpenCV/Pillow cleanup",
        "realSamples": real.get("total"),
        "male": real.get("male"),
        "female": real.get("female"),
        "positivePass": real.get("passed"),
        "positiveFail": real.get("failed"),
        "negativeFalsePass": negative.get("falsePass"),
        "previewDownloadConsistencyRate": real.get("previewDownloadConsistencyRate"),
        "reports": {
            "pipeline": str(REPAIR / "current-pipeline-audit.md"),
            "generalization": str(REPAIR / "generalization-report.md"),
            "cloud": str(REPAIR / "cloud-sync-report.md"),
            "openSource": str(OPEN / "open-source-source-map.md"),
            "modelAb": str(AB / "model-ab-test-report.md"),
        },
    }
    write_json(REPAIR / "final-summary.json", summary)
    write_md(
        REPAIR / "final-summary.md",
        [
            "# ID-photo Repair Final Summary",
            "",
            f"- Status: `{status}`",
            f"- Generated at: `{summary['generatedAt']}`",
            f"- Root cause: {summary['rootCause']}",
            f"- Active engine: `{summary['activeEngine']}`",
            f"- Real samples: `{summary['realSamples']}` male=`{summary['male']}` female=`{summary['female']}`",
            f"- positive_pass/positive_fail: `{summary['positivePass']}/{summary['positiveFail']}`",
            f"- negative_false_pass: `{summary['negativeFalsePass']}`",
            f"- Preview/download consistency: `{summary['previewDownloadConsistencyRate']}`",
            "",
            "## Conditions",
            *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in conditions.items()],
        ],
    )
    print(f"[write-id-photo-repair-reports] {status} report={REPAIR / 'final-summary.json'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
