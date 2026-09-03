"""Aggregate verifier for the user-photo isolation repair scope."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "reports" / "user-photo-isolation" / "final"
RUN_PYTHON = ROOT / "server" / "scripts" / "run_python.js"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_step(name: str, script: str, args: list[str]) -> dict[str, Any]:
    cmd = ["node", str(RUN_PYTHON), f"server/scripts/{script}", *args]
    started = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {
        "name": name,
        "script": script,
        "cmd": cmd,
        "exitCode": proc.returncode,
        "passed": proc.returncode == 0,
        "durationSeconds": round(time.time() - started, 2),
        "outputTail": proc.stdout[-4000:],
    }


def get_json(url: str) -> dict[str, Any]:
    last_error = ""
    for attempt in range(1, 4):
        try:
            res = requests.get(url, timeout=20)
            try:
                data = res.json()
            except Exception:
                data = {"raw": res.text[:300]}
            return {"statusCode": res.status_code, "data": data, "ok": res.ok, "attempts": attempt}
        except Exception as exc:
            last_error = str(exc)
            if attempt < 3:
                time.sleep(2)
    return {"statusCode": 0, "data": {"error": last_error}, "ok": False, "attempts": 3}


def read_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cloud-url", default="https://tupzjianzhao.chat")
    args = parser.parse_args()
    local = args.base_url.rstrip("/")
    cloud = args.cloud_url.rstrip("/")
    FINAL.mkdir(parents=True, exist_ok=True)

    steps = [
        run_step("user-auth-isolation", "verify_user_auth_isolation.py", []),
        run_step("local-user-photo-isolation", "verify_user_photo_isolation.py", ["--base-url", local, "--target", "local"]),
        run_step("cloud-user-photo-isolation", "verify_cloud_user_photo_isolation.py", ["--base-url", cloud]),
    ]

    local_report = read_report(FINAL / "local-user-photo-isolation-report.json")
    cloud_report = read_report(FINAL / "cloud-user-photo-isolation-report.json")
    auth_report = read_report(FINAL / "user-auth-report.json")
    cloud_health = get_json(f"{cloud}/api/health")
    cloud_retention = get_json(f"{cloud}/api/assets/retention-policy")
    cloud_status = get_json(f"{cloud}/api/user/photos/isolation-status")
    credential_name_markers = ("ALIYUN", "ALICLOUD", "AWS", "AZURE", "SSH", "WINRM", "ECS", "DEPLOY")
    credential_sensitive_markers = ("ACCESS", "SECRET", "PASSWORD", "TOKEN")
    credential_env_names = sorted(
        name
        for name in os.environ
        if any(marker in name.upper() for marker in credential_name_markers)
        or any(marker in name.upper() for marker in credential_sensitive_markers)
    )

    fixed_files = [
        "server/main.py",
        "utils/authService.js",
        "utils/imageService.js",
        "app.js",
        "pages/login/login.js",
        "pages/login/login.wxml",
        "pages/profile/profile.js",
        "pages/profile/profile.wxml",
        "pages/photos/photos.js",
        "pages/photos/photos.wxml",
        "pages/photos/photos.wxss",
        "pages/generate/generate.js",
        "pages/preview/preview.js",
        "server/scripts/verify_user_auth_isolation.py",
        "server/scripts/verify_user_photo_isolation.py",
        "server/scripts/verify_cloud_user_photo_isolation.py",
        "server/scripts/verify_user_photo_isolation_all.py",
        "server/scripts/verify_frontend_ui.py",
        "server/scripts/verify_id_photo_full_business_flow.py",
        "package.json",
    ]
    write_md(FINAL / "fixed-files.md", ["# 修改文件清单", ""] + [f"- `{item}`" for item in fixed_files])

    cloud_sync = {
        "status": "PASS" if cloud_status["statusCode"] == 200 and cloud_status["data"].get("version") == "20260609-user-photo-isolation-v1" else "FAIL",
        "cloudUrl": cloud,
        "health": cloud_health,
        "retention": cloud_retention,
        "isolationStatus": cloud_status,
        "frontendCloudBaseConfigured": "https://tupzjianzhao.chat" in (ROOT / "utils" / "apiConfig.js").read_text(encoding="utf-8"),
        "localNotUsedForCloudVerification": "127.0.0.1" not in cloud and "localhost" not in cloud,
        "deploymentChannelAudit": {
            "repositoryDeployScriptsPresent": (ROOT / "deploy" / "cloud" / "activate-release.ps1").exists()
            and (ROOT / "deploy" / "cloud" / "install-release.ps1").exists(),
            "credentialEnvironmentVariablesPresent": bool(credential_env_names),
            "credentialEnvironmentVariableNamesOnly": credential_env_names,
            "remoteIsolationEndpointStatus": cloud_status["statusCode"],
            "blocker": "cloud endpoint /api/user/photos/isolation-status returned non-200; current release is not synchronized"
            if cloud_status["statusCode"] != 200
            else "",
        },
    }
    write_json(FINAL / "cloud-sync-report.json", cloud_sync)
    write_md(FINAL / "cloud-sync-report.md", [
        "# 云端同步验证",
        "",
        f"- Status: `{cloud_sync['status']}`",
        f"- Cloud URL: `{cloud}`",
        f"- Health status: `{cloud_health['statusCode']}`",
        f"- Retention seconds: `{cloud_retention['data'].get('retentionSeconds')}`",
        f"- Isolation version: `{cloud_status['data'].get('version')}`",
        f"- Frontend cloud base configured: `{cloud_sync['frontendCloudBaseConfigured']}`",
        f"- Localhost not used for cloud verification: `{cloud_sync['localNotUsedForCloudVerification']}`",
        f"- Deploy scripts present: `{cloud_sync['deploymentChannelAudit']['repositoryDeployScriptsPresent']}`",
        f"- Deploy credential env vars present: `{cloud_sync['deploymentChannelAudit']['credentialEnvironmentVariablesPresent']}`",
        f"- Remote isolation endpoint status: `{cloud_sync['deploymentChannelAudit']['remoteIsolationEndpointStatus']}`",
        f"- Blocker: `{cloud_sync['deploymentChannelAudit']['blocker']}`",
    ])

    conditions = {
        "authStaticPass": auth_report.get("status") == "PASS",
        "localUserPhotoIsolationPass": local_report.get("status") == "PASS",
        "cloudUserPhotoIsolationPass": cloud_report.get("status") == "PASS",
        "cloudSyncPass": cloud_sync["status"] == "PASS",
        "localUserAUserBSeparated": bool((local_report.get("checks") or {}).get("userADoesNotSeeUserB") and (local_report.get("checks") or {}).get("userBDoesNotSeeUserA")),
        "cloudUserAUserBSeparated": bool((cloud_report.get("checks") or {}).get("userADoesNotSeeUserB") and (cloud_report.get("checks") or {}).get("userBDoesNotSeeUserA")),
        "deletePermissionChecked": bool((local_report.get("checks") or {}).get("deleteUserAByUserBRejected") and (cloud_report.get("checks") or {}).get("deleteUserAByUserBRejected")),
        "downloadPermissionChecked": bool((local_report.get("checks") or {}).get("downloadUserAByUserBRejected") and (cloud_report.get("checks") or {}).get("downloadUserAByUserBRejected")),
        "unauthSafe": bool((local_report.get("checks") or {}).get("unauthListSafe") and (cloud_report.get("checks") or {}).get("unauthListSafe")),
        "retentionSeconds86400": cloud_retention["data"].get("retentionSeconds") == 86400,
        "reportsGenerated": all((FINAL / name).exists() for name in [
            "current-data-flow.md",
            "user-auth-report.md",
            "user-photo-isolation-report.md",
            "delete-download-permission-report.md",
            "local-business-flow-report.md",
            "cloud-user-photo-isolation-report.md",
            "cloud-business-flow-report.md",
            "cloud-sync-report.md",
            "fixed-files.md",
        ]),
    }
    passed = all(step["passed"] for step in steps) and all(conditions.values())
    summary = {
        "status": "PASS" if passed else "FAIL",
        "localUrl": local,
        "cloudUrl": cloud,
        "steps": steps,
        "conditions": conditions,
        "manualRealDeviceItems": [
            "真实微信 appid/secret 配置后，用两台真机微信账号确认 openid 绑定。",
            "微信正式版发布 current release 状态需在微信公众平台后台确认。",
        ],
    }
    write_json(FINAL / "final-summary.json", summary)
    (ROOT / "reports" / "final").mkdir(parents=True, exist_ok=True)
    write_json(ROOT / "reports" / "final" / "verify-all-report.json", summary)
    write_md(FINAL / "verify-all-report.md", [
        "# 用户电子照隔离最终验证",
        "",
        f"- Status: `{summary['status']}`",
        f"- Local URL: `{local}`",
        f"- Cloud URL: `{cloud}`",
        "",
        "## 停止条件",
        *[f"- {key}: `{value}`" for key, value in conditions.items()],
        "",
        "## 命令",
        *[f"- {step['name']}: exit `{step['exitCode']}`" for step in steps],
    ])
    shutil.copyfile(FINAL / "verify-all-report.md", ROOT / "reports" / "final" / "verify-all-report.md")
    print(f"[verify-user-photo-isolation-all] {summary['status']}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
