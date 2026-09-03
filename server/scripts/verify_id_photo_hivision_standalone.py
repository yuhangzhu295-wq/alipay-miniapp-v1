from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "id-photo-multi-engine-reset"
OUTPUT_DIR = REPORT_DIR / "hivision-standalone-test"
REPORT_JSON = REPORT_DIR / "hivision-standalone-test-report.json"
REPORT_MD = REPORT_DIR / "hivision-standalone-test-report.md"
HIVISION_ROOT = ROOT / "third_party" / "HivisionIDPhotos"
WINDOWS_VENV_PYTHON = HIVISION_ROOT / ".venv" / "Scripts" / "python.exe"
OVERRIDE_PYTHON = os.environ.get("ID_PHOTO_HIVISION_PYTHON", "").strip()
VENV_PYTHON = Path(OVERRIDE_PYTHON) if OVERRIDE_PYTHON else (WINDOWS_VENV_PYTHON if platform.system() == "Windows" else Path(sys.executable))
ASCII_BASE = Path(tempfile.gettempdir()) / "idphoto_hivision_ascii"
ASCII_ROOT = ASCII_BASE / "HivisionIDPhotos"
ASCII_OUTPUT_DIR = ASCII_BASE / "standalone-output"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_command(cmd: list[str], cwd: Path, timeout: int = 900) -> dict[str, Any]:
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


def prepare_ascii_root() -> dict[str, Any]:
    ASCII_BASE.mkdir(parents=True, exist_ok=True)
    if ASCII_ROOT.exists():
        return {"path": str(ASCII_ROOT), "created": False, "returncode": 0, "outputTail": "existing"}
    cmd = (
        ["cmd", "/c", "mklink", "/J", str(ASCII_ROOT), str(HIVISION_ROOT)]
        if platform.system() == "Windows"
        else ["ln", "-s", str(HIVISION_ROOT), str(ASCII_ROOT)]
    )
    proc = subprocess.run(
        cmd,
        cwd=str(ASCII_BASE),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
    )
    return {
        "path": str(ASCII_ROOT),
        "created": proc.returncode == 0,
        "returncode": proc.returncode,
        "outputTail": proc.stdout[-4000:],
    }


def find_demo_image(run_root: Path) -> Path | None:
    candidates = [
        run_root / "demo" / "images" / "test0.jpg",
        run_root / "demo" / "images" / "test0.png",
        run_root / "demo" / "test0.jpg",
    ]
    for item in candidates:
        if item.exists():
            return item
    for pattern in ["*.jpg", "*.jpeg", "*.png"]:
        found = list((run_root / "demo").rglob(pattern)) if (run_root / "demo").exists() else []
        if found:
            return found[0]
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matting-model", default="hivision_modnet")
    parser.add_argument("--input", type=Path)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "path": str(HIVISION_ROOT),
        "venvPython": str(VENV_PYTHON),
        "asciiRoot": str(ASCII_ROOT),
        "commands": [],
        "outputs": {},
        "passed": False,
        "blockedReason": "",
    }

    if not (HIVISION_ROOT / "inference.py").exists():
        report["blockedReason"] = "inference.py not found; run verify:id-photo-hivision-install first"
    elif not VENV_PYTHON.exists():
        report["blockedReason"] = "Hivision venv python not found"
    else:
        ascii_state = prepare_ascii_root()
        report["asciiRootState"] = ascii_state
        run_root = ASCII_ROOT if ASCII_ROOT.exists() else HIVISION_ROOT
        ASCII_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for old in ASCII_OUTPUT_DIR.glob("test_*"):
            if old.is_file():
                old.unlink()
        demo = args.input.resolve() if args.input and args.input.exists() else find_demo_image(run_root)
        report["demoImage"] = str(demo) if demo else ""
        if demo is None:
            report["blockedReason"] = "No demo image found in HivisionIDPhotos"
        else:
            out_matting = ASCII_OUTPUT_DIR / "test_matting.png"
            out_blue = ASCII_OUTPUT_DIR / "test_blue.jpg"
            commands = [
                [str(VENV_PYTHON), "inference.py", "-t", "human_matting", "-i", str(demo), "-o", str(out_matting), "--matting_model", args.matting_model],
                [str(VENV_PYTHON), "inference.py", "-t", "add_background", "-i", str(out_matting), "-o", str(out_blue), "-c", "438edb", "-k", "30", "-r", "1"],
            ]
            for cmd in commands:
                report["commands"].append(run_command(cmd, run_root, timeout=1200))
            if out_matting.exists():
                shutil.copy2(out_matting, OUTPUT_DIR / out_matting.name)
            if out_blue.exists():
                shutil.copy2(out_blue, OUTPUT_DIR / out_blue.name)
            report["outputs"] = {
                "matting": str(OUTPUT_DIR / out_matting.name),
                "blue": str(OUTPUT_DIR / out_blue.name),
                "asciiMatting": str(out_matting),
                "asciiBlue": str(out_blue),
                "mattingExists": (OUTPUT_DIR / out_matting.name).exists(),
                "blueExists": (OUTPUT_DIR / out_blue.name).exists(),
            }

    failing = [cmd for cmd in report["commands"] if cmd.get("returncode") not in (0, None)]
    outputs = report.get("outputs") or {}
    report["passed"] = not report["blockedReason"] and not failing and all(
        outputs.get(key) for key in ["mattingExists", "blueExists"]
    )
    if failing and not report["blockedReason"]:
        report["blockedReason"] = "one or more official Hivision inference commands failed"

    write_json(REPORT_JSON, report)
    if report["passed"]:
        write_json(REPORT_DIR / "hivision-standalone-ready.json", {
            "ready": True,
            "note": "Production human-matting and add-background commands passed with the routed model.",
            "model": args.matting_model,
            "outputs": report["outputs"],
        })

    lines = [
        "# HivisionIDPhotos Standalone Test Report",
        "",
        f"- Result: {'PASS' if report['passed'] else 'BLOCKED'}",
        f"- Hivision path: `{HIVISION_ROOT}`",
        f"- ASCII run path: `{report.get('asciiRoot')}`",
        f"- Venv Python: `{VENV_PYTHON}`",
        f"- Demo image: `{report.get('demoImage', '')}`",
        f"- Blocked reason: {report.get('blockedReason') or 'none'}",
        "",
        "## Outputs",
    ]
    for key, value in (report.get("outputs") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Commands"])
    for item in report["commands"]:
        status = "PASS" if item.get("returncode") == 0 else "FAIL"
        lines.append(f"- {status} `{ ' '.join(item.get('cmd', [])) }` ({item.get('seconds')}s)")
        tail = (item.get("outputTail") or "").strip()
        if tail:
            lines.append("  ```text")
            lines.extend(("  " + line) for line in tail.splitlines()[-40:])
            lines.append("  ```")
    write_md(REPORT_MD, lines)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
