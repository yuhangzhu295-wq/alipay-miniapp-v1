"""Verify backend user isolation for "我的电子照" records."""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "user-photo-isolation"
FINAL = REPORT_ROOT / "final"
AUDIT = REPORT_ROOT / "audit"
VERSION = "20260609-user-photo-isolation-v1"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def req_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        res = requests.request(method, url, timeout=kwargs.pop("timeout", 30), **kwargs)
        try:
            data = res.json()
        except Exception:
            data = {"raw": res.text[:300]}
        return {"statusCode": res.status_code, "data": data, "ok": res.ok}
    except Exception as exc:
        return {"statusCode": 0, "data": {"error": str(exc)}, "ok": False}


def make_sample(path: Path, label: str, color: tuple[int, int, int]) -> None:
    img = Image.new("RGB", (295, 413), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([78, 58, 217, 198], fill=(245, 224, 205))
    draw.rectangle([58, 210, 237, 360], fill=(28, 48, 88))
    draw.text((92, 25), label, fill=(20, 35, 60))
    img.save(path, "JPEG", quality=92)


def login(base_url: str, client_user_id: str, nick: str) -> dict[str, Any]:
    res = req_json(
        "POST",
        f"{base_url}/api/auth/login",
        json={
            "clientUserId": client_user_id,
            "userInfo": {"nickName": nick, "avatarUrl": ""},
        },
    )
    data = res["data"]
    token = data.get("token") if isinstance(data, dict) else ""
    return {
        "passed": res["statusCode"] == 200 and bool(data.get("success")) and bool(token) and bool(data.get("userId")),
        "response": res,
        "token": token,
        "userId": data.get("userId") if isinstance(data, dict) else "",
        "headers": {"Authorization": f"Bearer {token}", "X-User-Token": token} if token else {},
    }


def create_asset(base_url: str, label: str, color: tuple[int, int, int]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{label}.jpg"
        make_sample(path, label, color)
        with path.open("rb") as f:
            try:
                res = requests.post(
                    f"{base_url}/api/compress",
                    files={"file": (path.name, f, "image/jpeg")},
                    data={"targetKB": "200"},
                    timeout=45,
                )
                data = res.json()
            except Exception as exc:
                return {"passed": False, "statusCode": 0, "data": {"error": str(exc)}}
    image_url = data.get("imageUrl") if isinstance(data, dict) else ""
    return {
        "passed": res.status_code == 200 and bool(data.get("success")) and bool(image_url),
        "statusCode": res.status_code,
        "data": data,
        "imageUrl": image_url,
    }


def create_photo(base_url: str, headers: dict[str, str], image_url: str, spec_name: str) -> dict[str, Any]:
    payload = {
        "imageUrl": image_url,
        "thumbnailUrl": image_url,
        "specId": "one-inch",
        "specName": spec_name,
        "widthPx": 295,
        "heightPx": 413,
        "backgroundColor": "blue",
        "source": "verify_user_photo_isolation",
        "type": "idPhoto",
        "sizeText": "25x35mm | 295x413px",
    }
    res = req_json("POST", f"{base_url}/api/user/photos", headers=headers, json=payload)
    data = res["data"]
    photo = data.get("photo") if isinstance(data, dict) else None
    return {
        "passed": res["statusCode"] == 200 and bool(data.get("success")) and bool(photo and photo.get("id")),
        "response": res,
        "photo": photo or {},
        "photoId": (photo or {}).get("id", ""),
    }


def list_photos(base_url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    res = req_json("GET", f"{base_url}/api/user/photos", headers=headers or {})
    data = res["data"]
    photos = data.get("photos") if isinstance(data, dict) else None
    return {
        "statusCode": res["statusCode"],
        "data": data,
        "photos": photos if isinstance(photos, list) else [],
    }


def photo_ids(result: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in result.get("photos", []) if item.get("id")}


def permission_call(method: str, base_url: str, photo_id: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    endpoint = f"{base_url}/api/user/photos/{photo_id}"
    if method == "download":
        endpoint += "/download"
        res = requests.get(endpoint, headers=headers or {}, timeout=30)
        return {"statusCode": res.status_code, "passed": res.status_code == 200, "contentType": res.headers.get("content-type", "")}
    res = requests.delete(endpoint, headers=headers or {}, timeout=30)
    try:
        data = res.json()
    except Exception:
        data = {"raw": res.text[:200]}
    return {"statusCode": res.status_code, "passed": res.status_code == 200, "data": data}


def run(base_url: str, target: str) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    run_id = f"user-photo-isolation-{target}-{int(time.time())}"
    health = req_json("GET", f"{base_url}/api/health")
    retention = req_json("GET", f"{base_url}/api/assets/retention-policy")
    status = req_json("GET", f"{base_url}/api/user/photos/isolation-status")

    user_a = login(base_url, f"test-user-a-{run_id}", "User A")
    user_b = login(base_url, f"test-user-b-{run_id}", "User B")
    asset_a = create_asset(base_url, "user-a", (210, 230, 255))
    asset_b = create_asset(base_url, "user-b", (235, 245, 220))

    photo_a = create_photo(base_url, user_a["headers"], asset_a.get("imageUrl", ""), "A 用户一寸照") if user_a["passed"] and asset_a["passed"] else {"passed": False, "photoId": ""}
    list_a_after_a = list_photos(base_url, user_a["headers"]) if user_a["passed"] else {"photos": [], "statusCode": 0}
    list_b_before_b = list_photos(base_url, user_b["headers"]) if user_b["passed"] else {"photos": [], "statusCode": 0}

    photo_b = create_photo(base_url, user_b["headers"], asset_b.get("imageUrl", ""), "B 用户一寸照") if user_b["passed"] and asset_b["passed"] else {"passed": False, "photoId": ""}
    list_b_after_b = list_photos(base_url, user_b["headers"]) if user_b["passed"] else {"photos": [], "statusCode": 0}
    list_a_after_b = list_photos(base_url, user_a["headers"]) if user_a["passed"] else {"photos": [], "statusCode": 0}
    unauth_list = list_photos(base_url)

    a_id = photo_a.get("photoId", "")
    b_id = photo_b.get("photoId", "")
    a_ids_after_a = photo_ids(list_a_after_a)
    b_ids_before_b = photo_ids(list_b_before_b)
    b_ids_after_b = photo_ids(list_b_after_b)
    a_ids_after_b = photo_ids(list_a_after_b)

    delete_a_by_b = permission_call("delete", base_url, a_id, user_b["headers"]) if a_id and user_b["passed"] else {"statusCode": 0}
    delete_b_by_a = permission_call("delete", base_url, b_id, user_a["headers"]) if b_id and user_a["passed"] else {"statusCode": 0}
    download_a_by_b = permission_call("download", base_url, a_id, user_b["headers"]) if a_id and user_b["passed"] else {"statusCode": 0}
    download_b_by_a = permission_call("download", base_url, b_id, user_a["headers"]) if b_id and user_a["passed"] else {"statusCode": 0}
    download_a_by_a = permission_call("download", base_url, a_id, user_a["headers"]) if a_id and user_a["passed"] else {"statusCode": 0}
    delete_unauth = permission_call("delete", base_url, a_id, {}) if a_id else {"statusCode": 0}
    download_unauth = permission_call("download", base_url, a_id, {}) if a_id else {"statusCode": 0}

    cleanup = req_json("POST", f"{base_url}/api/assets/cleanup-expired")
    list_a_after_cleanup = list_photos(base_url, user_a["headers"]) if user_a["passed"] else {"photos": [], "statusCode": 0}
    list_b_after_cleanup = list_photos(base_url, user_b["headers"]) if user_b["passed"] else {"photos": [], "statusCode": 0}

    checks = {
        "healthPass": health["statusCode"] == 200 and bool(health["data"].get("success")),
        "retentionSeconds86400": retention["statusCode"] == 200 and retention["data"].get("retentionSeconds") == 86400,
        "isolationStatusLatest": status["statusCode"] == 200 and status["data"].get("version") == VERSION,
        "userALoginPass": user_a["passed"],
        "userBLoginPass": user_b["passed"],
        "userACreatePass": photo_a.get("passed") is True,
        "userBCreatePass": photo_b.get("passed") is True,
        "userASeesOwnPhoto": bool(a_id and a_id in a_ids_after_a),
        "userBDoesNotSeeUserA": bool(a_id and a_id not in b_ids_before_b),
        "userBSeesOwnOnly": bool(b_id and b_id in b_ids_after_b and a_id not in b_ids_after_b),
        "userADoesNotSeeUserB": bool(a_id and b_id and a_id in a_ids_after_b and b_id not in a_ids_after_b),
        "deleteUserAByUserBRejected": delete_a_by_b.get("statusCode") == 403,
        "deleteUserBByUserARejected": delete_b_by_a.get("statusCode") == 403,
        "downloadUserAByUserBRejected": download_a_by_b.get("statusCode") == 403,
        "downloadUserBByUserARejected": download_b_by_a.get("statusCode") == 403,
        "ownerDownloadPass": download_a_by_a.get("statusCode") == 200,
        "unauthListSafe": unauth_list["statusCode"] in (401, 403) and len(unauth_list.get("photos", [])) == 0,
        "unauthDeleteRejected": delete_unauth.get("statusCode") in (401, 403),
        "unauthDownloadRejected": download_unauth.get("statusCode") in (401, 403),
        "cleanupKeepsCurrentUserPhotos": bool(
            a_id in photo_ids(list_a_after_cleanup) and b_id in photo_ids(list_b_after_cleanup)
        ),
    }

    # Remove verification records after permission checks.
    cleanup_delete_a = permission_call("delete", base_url, a_id, user_a["headers"]) if a_id and user_a["passed"] else {"statusCode": 0}
    cleanup_delete_b = permission_call("delete", base_url, b_id, user_b["headers"]) if b_id and user_b["passed"] else {"statusCode": 0}
    checks["ownerDeletePass"] = cleanup_delete_a.get("statusCode") == 200 and cleanup_delete_b.get("statusCode") == 200

    passed = all(checks.values())
    payload = {
        "status": "PASS" if passed else "FAIL",
        "target": target,
        "baseUrl": base_url,
        "runId": run_id,
        "checks": checks,
        "health": health,
        "retention": retention,
        "isolationStatus": status,
        "userA": {"login": user_a["passed"], "userId": user_a.get("userId"), "photoId": a_id, "listAfterB": list_a_after_b},
        "userB": {"login": user_b["passed"], "userId": user_b.get("userId"), "photoId": b_id, "listBeforeB": list_b_before_b, "listAfterB": list_b_after_b},
        "permissions": {
            "deleteAByB": delete_a_by_b,
            "deleteBByA": delete_b_by_a,
            "downloadAByB": download_a_by_b,
            "downloadBByA": download_b_by_a,
            "downloadAByA": download_a_by_a,
            "deleteUnauth": delete_unauth,
            "downloadUnauth": download_unauth,
        },
        "cleanup": cleanup,
        "cleanupDelete": {"userA": cleanup_delete_a, "userB": cleanup_delete_b},
    }

    write_json(FINAL / f"{target}-user-photo-isolation-report.json", payload)
    scenario_ran = bool(
        checks["isolationStatusLatest"]
        and checks["userALoginPass"]
        and checks["userBLoginPass"]
        and checks["userACreatePass"]
        and checks["userBCreatePass"]
    )
    user_a_can_see_b = "NOT_VERIFIED" if not scenario_ran else str(not checks["userADoesNotSeeUserB"])
    user_b_can_see_a = "NOT_VERIFIED" if not scenario_ran else str(not checks["userBDoesNotSeeUserA"])
    ownership_delete = "NOT_VERIFIED" if not scenario_ran else str(checks["deleteUserAByUserBRejected"] and checks["deleteUserBByUserARejected"])
    ownership_download = "NOT_VERIFIED" if not scenario_ran else str(checks["downloadUserAByUserBRejected"] and checks["downloadUserBByUserARejected"])
    unauth_safe = "NOT_VERIFIED" if not scenario_ran else str(checks["unauthListSafe"])
    cleanup_safe = "NOT_VERIFIED" if not scenario_ran else str(checks["cleanupKeepsCurrentUserPhotos"])
    title = "本地" if target == "local" else "云端"
    lines = [
        f"# {title}用户电子照隔离验证",
        "",
        f"- Status: `{payload['status']}`",
        f"- Base URL: `{base_url}`",
        f"- Run ID: `{run_id}`",
        f"- Retention seconds: `{retention['data'].get('retentionSeconds')}`",
        f"- Isolation version: `{status['data'].get('version')}`",
        "",
        "## 核心结论",
        f"- userA can see userB data: `{user_a_can_see_b}`",
        f"- userB can see userA data: `{user_b_can_see_a}`",
        f"- Delete ownership check: `{ownership_delete}`",
        f"- Download ownership check: `{ownership_download}`",
        f"- Unauthenticated list safe: `{unauth_safe}`",
        f"- Cleanup kept non-expired records: `{cleanup_safe}`",
        "",
        "## 检查项",
    ]
    lines += [f"- {key}: `{value}`" for key, value in checks.items()]
    if target == "local":
        write_md(FINAL / "user-photo-isolation-report.md", lines)
        write_md(FINAL / "delete-download-permission-report.md", [
            "# 删除与下载权限验证",
            "",
            f"- Status: `{payload['status']}`",
            f"- userB delete userA: `{delete_a_by_b.get('statusCode')}`",
            f"- userA delete userB: `{delete_b_by_a.get('statusCode')}`",
            f"- userB download userA: `{download_a_by_b.get('statusCode')}`",
            f"- userA download userB: `{download_b_by_a.get('statusCode')}`",
            f"- unauth delete: `{delete_unauth.get('statusCode')}`",
            f"- unauth download: `{download_unauth.get('statusCode')}`",
        ])
        write_md(FINAL / "local-business-flow-report.md", lines)
    else:
        write_md(FINAL / "cloud-user-photo-isolation-report.md", lines)
        write_md(FINAL / "cloud-business-flow-report.md", lines)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--target", choices=["local", "cloud"], default="local")
    args = parser.parse_args()
    payload = run(args.base_url, args.target)
    print(f"[verify-user-photo-isolation] {payload['status']} target={args.target} base={args.base_url}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
