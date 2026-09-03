from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "id-photo-multi-engine-reset"
REPORT_JSON = REPORT_DIR / "hivision-install-report.json"
REPORT_MD = REPORT_DIR / "hivision-install-report.md"
THIRD_PARTY = ROOT / "third_party"
HIVISION_ROOT = THIRD_PARTY / "HivisionIDPhotos"
REPO_URL = "https://github.com/Zeyi-Lin/HivisionIDPhotos.git"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_command(cmd: list[str], cwd: Path, timeout: int = 600) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            shell=False,
        )
        return {
            "cmd": cmd,
            "cwd": str(cwd),
            "returncode": proc.returncode,
            "seconds": round(time.time() - started, 2),
            "outputTail": proc.stdout[-12000:],
        }
    except Exception as exc:
        return {
            "cmd": cmd,
            "cwd": str(cwd),
            "returncode": -1,
            "seconds": round(time.time() - started, 2),
            "outputTail": repr(exc),
        }


def find_python() -> str:
    override = os.environ.get("ID_PHOTO_HIVISION_PYTHON")
    if override:
        return override
    return sys.executable


def venv_python() -> Path:
    return HIVISION_ROOT / ".venv" / "Scripts" / "python.exe"


def list_models() -> list[str]:
    patterns = ["*.onnx", "*.pth", "*.pt", "*.safetensors", "*.ckpt"]
    found: list[str] = []
    if not HIVISION_ROOT.exists():
        return found
    for pattern in patterns:
        for path in HIVISION_ROOT.rglob(pattern):
            if ".venv" not in path.parts:
                found.append(str(path.relative_to(HIVISION_ROOT)))
    return sorted(found)[:200]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-model-download", action="store_true")
    args = parser.parse_args()

    report: dict[str, Any] = {
        "repository": REPO_URL,
        "path": str(HIVISION_ROOT),
        "python": find_python(),
        "venvPython": str(venv_python()),
        "commands": [],
        "models": [],
        "passed": False,
        "blockedReason": "",
    }

    THIRD_PARTY.mkdir(parents=True, exist_ok=True)

    if not HIVISION_ROOT.exists():
        report["commands"].append(run_command(["git", "clone", REPO_URL, str(HIVISION_ROOT)], THIRD_PARTY, timeout=900))
    elif (HIVISION_ROOT / ".git").exists():
        report["commands"].append(run_command(["git", "rev-parse", "--is-inside-work-tree"], HIVISION_ROOT, timeout=60))
    else:
        report["blockedReason"] = "HivisionIDPhotos directory exists but is not a git repository"

    if HIVISION_ROOT.exists() and (HIVISION_ROOT / ".git").exists():
        commit = run_command(["git", "rev-parse", "HEAD"], HIVISION_ROOT, timeout=60)
        report["commands"].append(commit)
        report["commit"] = (commit.get("outputTail") or "").strip().splitlines()[-1:] or [""]
        report["commit"] = report["commit"][0]

    if not (HIVISION_ROOT / "inference.py").exists():
        report["blockedReason"] = report["blockedReason"] or "inference.py not found after clone/check"
    else:
        if not venv_python().exists():
            report["commands"].append(run_command([find_python(), "-m", "venv", str(HIVISION_ROOT / ".venv")], HIVISION_ROOT, timeout=600))
        if venv_python().exists():
            report["commands"].append(run_command([str(venv_python()), "-m", "pip", "install", "--upgrade", "pip"], HIVISION_ROOT, timeout=600))
            for req_name in ["requirements.txt", "requirements-app.txt"]:
                req = HIVISION_ROOT / req_name
                if req.exists():
                    report["commands"].append(run_command([str(venv_python()), "-m", "pip", "install", "-r", str(req)], HIVISION_ROOT, timeout=1800))
                else:
                    report["commands"].append({
                        "cmd": ["skip", req_name],
                        "cwd": str(HIVISION_ROOT),
                        "returncode": 0,
                        "seconds": 0,
                        "outputTail": f"{req_name} not found",
                    })
            compat_deps = [
                "opencv-python>=4.8.1.78",
                "onnxruntime>=1.15.0",
                "requests",
                "mtcnn-runtime",
                "tqdm",
                "starlette",
            ]
            report["commands"].append(
                run_command([str(venv_python()), "-m", "pip", "install", *compat_deps], HIVISION_ROOT, timeout=1800)
            )
            import_check = (
                "import cv2,numpy,onnxruntime,requests,tqdm;"
                "from mtcnnruntime import MTCNN;"
                "print('hivision core imports ok')"
            )
            report["commands"].append(run_command([str(venv_python()), "-c", import_check], HIVISION_ROOT, timeout=120))
            downloader = HIVISION_ROOT / "scripts" / "download_model.py"
            if downloader.exists() and not args.skip_model_download:
                report["commands"].append(run_command([str(venv_python()), str(downloader), "--models", "all"], HIVISION_ROOT, timeout=1800))
            elif downloader.exists():
                report["commands"].append({
                    "cmd": ["skip", "scripts/download_model.py --models all"],
                    "cwd": str(HIVISION_ROOT),
                    "returncode": 0,
                    "seconds": 0,
                    "outputTail": "skipped by --skip-model-download",
                })
            else:
                report["commands"].append({
                    "cmd": ["skip", "scripts/download_model.py"],
                    "cwd": str(HIVISION_ROOT),
                    "returncode": 0,
                    "seconds": 0,
                    "outputTail": "download_model.py not found",
                })
        else:
            report["blockedReason"] = report["blockedReason"] or "venv python was not created"

    report["models"] = list_models()
    compat_ok = any(
        cmd.get("returncode") == 0 and "hivision core imports ok" in str(cmd.get("outputTail", ""))
        for cmd in report["commands"]
    )

    def ignored_failure(cmd: dict[str, Any]) -> bool:
        text = " ".join(cmd.get("cmd", []))
        return bool(compat_ok and "requirements.txt" in text and cmd.get("returncode") != 0)

    failing = [
        cmd
        for cmd in report["commands"]
        if cmd.get("returncode") not in (0, None) and not ignored_failure(cmd)
    ]
    report["compatibilityFallbackUsed"] = compat_ok
    report["passed"] = bool((HIVISION_ROOT / "inference.py").exists() and venv_python().exists() and compat_ok and not failing and not report["blockedReason"])
    if failing and not report["blockedReason"]:
        report["blockedReason"] = "one or more Hivision install commands failed"

    write_json(REPORT_JSON, report)

    lines = [
        "# HivisionIDPhotos Install Report",
        "",
        f"- Result: {'PASS' if report['passed'] else 'BLOCKED'}",
        f"- Repository: {REPO_URL}",
        f"- Install path: `{HIVISION_ROOT}`",
        f"- Commit: `{report.get('commit', '')}`",
        f"- Python: `{report['python']}`",
        f"- Venv Python: `{report['venvPython']}`",
        f"- Blocked reason: {report.get('blockedReason') or 'none'}",
        f"- Model files found: {len(report['models'])}",
        "",
        "## Commands",
    ]
    for item in report["commands"]:
        status = "PASS" if item.get("returncode") == 0 else "FAIL"
        lines.append(f"- {status} `{ ' '.join(item.get('cmd', [])) }` ({item.get('seconds')}s)")
        tail = (item.get("outputTail") or "").strip()
        if tail:
            lines.append("  ```text")
            lines.extend(("  " + line) for line in tail.splitlines()[-40:])
            lines.append("  ```")
    if report["models"]:
        lines.extend(["", "## Model Files"])
        for item in report["models"][:50]:
            lines.append(f"- `{item}`")
    write_md(REPORT_MD, lines)

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
