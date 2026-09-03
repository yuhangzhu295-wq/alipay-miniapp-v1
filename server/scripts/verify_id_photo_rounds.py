"""Run the ID-photo verifier for multiple checkpointed rounds."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
CHECKPOINTS = REPORTS / "checkpoints"


def _copy_round_artifacts(round_index: int) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    src_json = REPORTS / "final-validation-report.json"
    src_md = REPORTS / "final-validation-report.md"
    if src_json.exists():
        shutil.copy2(src_json, CHECKPOINTS / f"verify-round-{round_index}.json")
    if src_md.exists():
        shutil.copy2(src_md, CHECKPOINTS / f"verify-round-{round_index}.md")


def _write_summary(rounds: int, exit_codes: list[int]) -> None:
    payload = {
        "rounds": rounds,
        "exitCodes": exit_codes,
        "passed": all(code == 0 for code in exit_codes),
        "artifacts": [str(CHECKPOINTS / f"verify-round-{idx}.md") for idx in range(1, rounds + 1)],
    }
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / "verify-rounds-summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md = [
        "# ID Photo Verification Rounds",
        "",
        f"- Rounds: {rounds}",
        f"- Passed: {'YES' if payload['passed'] else 'NO'}",
        "",
        "## Round Exit Codes",
        *[f"- Round {idx}: {code}" for idx, code in enumerate(exit_codes, start=1)],
        "",
        "## Artifacts",
        *[f"- `{path}`" for path in payload["artifacts"]],
        "",
    ]
    (CHECKPOINTS / "verify-rounds-summary.md").write_text("\n".join(md), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--real-count", type=int, default=40)
    parser.add_argument("--min-pass-rate", type=float, default=95.0)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--no-network", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    exit_codes: list[int] = []
    verifier = ROOT / "server" / "scripts" / "verify_id_photo_chain.py"
    for round_index in range(1, args.rounds + 1):
        cmd = [
            sys.executable,
            str(verifier),
            "--base-url",
            args.base_url,
            "--real-count",
            str(args.real_count),
            "--min-pass-rate",
            str(args.min_pass_rate),
        ]
        if args.quick:
            cmd.append("--quick")
        if args.no_network:
            cmd.append("--no-network")
        print(f"[verify-rounds] round {round_index}/{args.rounds}: {' '.join(cmd)}")
        completed = subprocess.run(cmd, cwd=str(ROOT))
        exit_codes.append(completed.returncode)
        _copy_round_artifacts(round_index)
        if completed.returncode != 0:
            break
    _write_summary(args.rounds, exit_codes)
    return 0 if all(code == 0 for code in exit_codes) and len(exit_codes) == args.rounds else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
