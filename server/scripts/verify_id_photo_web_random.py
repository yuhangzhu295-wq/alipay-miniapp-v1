"""Run fresh web-random ID-photo validation and write generalization output."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cloud-url", default="https://tupzjianzhao.chat")
    parser.add_argument("--real-count", type=int, default=40)
    parser.add_argument("--min-pass-rate", type=float, default=95)
    args = parser.parse_args()

    chain_cmd = [
        sys.executable,
        str(ROOT / "server" / "scripts" / "verify_id_photo_chain.py"),
        "--base-url",
        args.base_url,
        "--real-count",
        str(args.real_count),
        "--min-pass-rate",
        str(args.min_pass_rate),
    ]
    chain = subprocess.run(chain_cmd, cwd=str(ROOT))
    if chain.returncode != 0:
        return chain.returncode

    gen_cmd = [
        sys.executable,
        str(ROOT / "server" / "scripts" / "verify_id_photo_generalization.py"),
        "--base-url",
        args.base_url,
        "--cloud-url",
        args.cloud_url,
    ]
    generalization = subprocess.run(gen_cmd, cwd=str(ROOT))
    return generalization.returncode


if __name__ == "__main__":
    raise SystemExit(main())
