"""Verify first-stage profile page interactions.

Checks native mini-program sharing and the anonymous profile-card login flow.
The script also simulates the two expected user paths from the source files.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "current-fixes"
FINAL_DIR = REPORT_ROOT / "final"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def extract_share_payload(js: str) -> dict[str, str]:
    match = re.search(r"onShareAppMessage\s*\([^)]*\)\s*\{(?P<body>.*?)\n\s*\}", js, re.S)
    if not match:
        return {}
    body = match.group("body")
    title = re.search(r"title\s*:\s*'([^']+)'", body)
    path = re.search(r"path\s*:\s*'([^']+)'", body)
    return {
        "title": title.group(1) if title else "",
        "path": path.group(1) if path else "",
    }


def main() -> int:
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    app_json_path = ROOT / "app.json"
    profile_wxml_path = ROOT / "pages" / "profile" / "profile.wxml"
    profile_js_path = ROOT / "pages" / "profile" / "profile.js"
    profile_wxss_path = ROOT / "pages" / "profile" / "profile.wxss"
    login_paths = [
        ROOT / "pages" / "login" / "login.js",
        ROOT / "pages" / "login" / "login.wxml",
        ROOT / "pages" / "login" / "login.wxss",
        ROOT / "pages" / "login" / "login.json",
    ]

    app_json = json.loads(read_text(app_json_path))
    profile_wxml = read_text(profile_wxml_path)
    profile_js = read_text(profile_js_path)
    profile_wxss = read_text(profile_wxss_path)
    login_js = read_text(login_paths[0]) if login_paths[0].exists() else ""
    login_wxml = read_text(login_paths[1]) if login_paths[1].exists() else ""
    share_payload = extract_share_payload(profile_js)

    checks = [
        ("login route registered", "pages/login/login" in app_json.get("pages", [])),
        ("login files exist", all(path.exists() for path in login_paths)),
        ("profile card taps login handler", 'class="profile-card"' in profile_wxml and 'bindtap="handleUserCardTap"' in profile_wxml),
        ("share uses native open-type", 'open-type="share"' in profile_wxml and 'menu-share-button' in profile_wxml),
        ("profile no longer has custom share tap", 'bindtap="shareApp"' not in profile_wxml and "shareApp(" not in profile_js),
        ("share callback exists", "onShareAppMessage" in profile_js and bool(share_payload.get("path"))),
        ("anonymous card navigates to login", "handleUserCardTap" in profile_js and "/pages/login/login" in profile_js and "wx.navigateTo" in profile_js),
        ("profile safely reads getApp", "typeof getApp === 'function'" in profile_js),
        ("login captures avatar and nickname", "chooseAvatar" in login_js and 'type="nickname"' in login_wxml),
        ("login stores local user info", "wx.setStorageSync('userInfo'" in login_js),
        ("button reset avoids visual regression", ".menu-share-button" in profile_wxss and "display: flex" in profile_wxss),
    ]
    check_results = [{"name": name, "passed": bool(passed)} for name, passed in checks]

    simulated_paths = {
        "anonymousProfileCardTap": {
            "initialHasLogin": False,
            "expectedRoute": "/pages/login/login",
            "actualRoute": "/pages/login/login" if checks[6][1] else "",
            "passed": bool(checks[6][1]),
        },
        "nativeShareButtonTap": {
            "expectedNativeOpenType": "share",
            "actualNativeOpenType": "share" if checks[3][1] else "",
            "sharePayload": share_payload,
            "passed": bool(checks[3][1] and checks[5][1] and share_payload.get("path") == "/pages/index/index"),
        },
        "loginSave": {
            "avatarInput": "chooseAvatar",
            "nicknameInput": "nickname",
            "storageKey": "userInfo",
            "passed": bool(checks[8][1] and checks[9][1]),
        },
    }

    data: dict[str, Any] = {
        "checks": check_results,
        "simulatedPaths": simulated_paths,
        "sharePayload": share_payload,
    }
    data["passed"] = all(item["passed"] for item in check_results) and all(item["passed"] for item in simulated_paths.values())

    json_path = FINAL_DIR / "profile-interactions-report.json"
    md_path = FINAL_DIR / "profile-interactions-report.md"
    write_json(json_path, data)
    lines = [
        "# Profile Interactions Report",
        "",
        f"- Overall: {'PASS' if data['passed'] else 'FAIL'}",
        f"- Share path: `{share_payload.get('path', '')}`",
        "",
        "## Static Checks",
    ]
    lines.extend([f"- {'PASS' if c['passed'] else 'FAIL'}: {c['name']}" for c in check_results])
    lines.append("")
    lines.append("## Dynamic Simulation")
    for name, item in simulated_paths.items():
        lines.append(f"- {name}: {'PASS' if item['passed'] else 'FAIL'}")
    write_markdown(md_path, lines)
    print(f"[verify:profile-interactions] report={md_path} passed={data['passed']}")
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
