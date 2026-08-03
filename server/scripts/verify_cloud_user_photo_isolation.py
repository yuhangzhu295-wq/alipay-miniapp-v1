"""Verify live cloud user-photo isolation. This never uses localhost."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "server" / "scripts" / "verify_user_photo_isolation.py"


def load_verify():
    spec = importlib.util.spec_from_file_location("verify_user_photo_isolation", VERIFY)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://tupzjianzhao.chat")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    if "127.0.0.1" in base or "localhost" in base:
        print("[verify-cloud-user-photo-isolation] FAIL cloud base-url must not be localhost")
        return 1
    module = load_verify()
    payload = module.run(base, "cloud")
    print(f"[verify-cloud-user-photo-isolation] {payload['status']} base={base}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
