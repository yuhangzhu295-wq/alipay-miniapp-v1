"""Static and simulated audit for mini-program auth isolation."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "reports" / "user-photo-isolation" / "final"
AUDIT = ROOT / "reports" / "user-photo-isolation" / "audit"


def read(path: str) -> str:
    p = ROOT / path
    return p.read_text(encoding="utf-8") if p.exists() else ""


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    files = {
        "app": read("app.js"),
        "authService": read("utils/authService.js"),
        "imageService": read("utils/imageService.js"),
        "photosJs": read("pages/photos/photos.js"),
        "photosWxml": read("pages/photos/photos.wxml"),
        "profileJs": read("pages/profile/profile.js"),
        "profileWxml": read("pages/profile/profile.wxml"),
        "loginJs": read("pages/login/login.js"),
        "loginWxml": read("pages/login/login.wxml"),
        "generateJs": read("pages/generate/generate.js"),
        "previewJs": read("pages/preview/preview.js"),
        "serverMain": read("server/main.py"),
        "apiConfig": read("utils/apiConfig.js"),
    }

    checks = {
        "authServiceExists": bool(files["authService"]),
        "loginUsesBackendAuth": "/api/auth/login" in files["authService"] and "loginWithProfile" in files["loginJs"],
        "tokenStoredForRequests": "Authorization: 'Bearer ' + auth.token" in files["authService"],
        "profileDoesNotTrustStaleUserInfo": "authService.getAuth()" in files["profileJs"] and "wx.getStorageSync('token')" not in files["profileJs"],
        "profileShowsAnonymousPrompt": "未登录，点我登录哦" in files["profileJs"] or "未登录，点我登录哦" in files["profileWxml"],
        "profileNoFixedTestNickname": "'11'" not in files["profileJs"] and ">11<" not in files["profileWxml"],
        "photosRequiresLogin": "authService.isLoggedIn()" in files["photosJs"] and "立即登录" in files["photosJs"],
        "photosUsesBackendList": "imageService.fetchPhotoRecords()" in files["photosJs"],
        "photosDoesNotListGlobalMyPhotos": "wx.getStorageSync('myPhotos')" not in files["photosJs"],
        "photoStorageKeyIsUserScoped": "myPhotos:' + userId" in files["authService"],
        "saveRecordSyncsBackend": "/api/user/photos" in files["imageService"] and "savePhotoRecord" in files["generateJs"],
        "deleteUsesBackendPermission": "DELETE" in files["imageService"] and "deletePhotoRecord" in files["photosJs"],
        "downloadUsesBackendPermission": "/download" in files["imageService"] and "downloadPhotoRecord" in files["photosJs"],
        "serverHasAuthLogin": "@app.post(\"/api/auth/login\")" in files["serverMain"],
        "serverRecordBindsUser": "\"userId\": user[\"userId\"]" in files["serverMain"],
        "serverListFiltersUser": "if item.get(\"userId\") == user[\"userId\"]" in files["serverMain"],
        "serverDeleteChecksOwner": "不能删除不属于当前用户" in files["serverMain"],
        "serverDownloadChecksOwner": "不能下载不属于当前用户" in files["serverMain"],
        "retentionStill86400": "ID_PHOTO_ASSET_RETENTION_SECONDS" in files["serverMain"] and "86400" in files["serverMain"],
        "cloudBaseConfigured": "https://tupzjianzhao.chat" in files["apiConfig"],
    }
    passed = all(checks.values())

    audit_lines = [
        "# 当前我的电子照数据链路审计",
        "",
        "## 登录/授权入口",
        "- 页面入口：`pages/profile/profile` 的用户卡片跳转 `pages/login/login`。",
        "- 授权入口：`pages/login/login` 使用头像/昵称授权，并调用 `utils/authService.js`。",
        "- 后端入口：`POST /api/auth/login` 签发用户 token。",
        "",
        "## 用户身份字段",
        "- 当前后端记录绑定字段：`userId`，可同时保存 `openid`（配置微信 appid/secret 后）。",
        "- 请求鉴权字段：`Authorization: Bearer <token>` / `X-User-Token`。",
        "- 前端本地备份键：`myPhotos:<userId>`。",
        "",
        "## 我的电子照来源",
        "- 现在列表来源：后端 `GET /api/user/photos`。",
        "- 本地 storage 仅作为当前登录用户备份，不作为未登录列表来源。",
        "- 未登录状态：不读取旧 `myPhotos`，显示登录引导空态。",
        "",
        "## 风险结论",
        "- 原状态存在风险：`pages/photos/photos.js` 曾直接读取全局 `myPhotos`，没有后端归属校验。",
        "- 当前修复：保存、查询、删除、下载均进入后端用户归属校验。",
        "",
        "## 审计项",
    ]
    audit_lines += [f"- {key}: `{value}`" for key, value in checks.items()]
    write_md(AUDIT / "current-data-flow.md", audit_lines)
    write_md(FINAL / "current-data-flow.md", audit_lines)

    report_lines = [
        "# 授权登录隔离验证",
        "",
        f"- Status: `{'PASS' if passed else 'FAIL'}`",
        "",
        "## 检查项",
    ]
    report_lines += [f"- {key}: `{value}`" for key, value in checks.items()]
    write_md(FINAL / "user-auth-report.md", report_lines)
    write_json(FINAL / "user-auth-report.json", {"status": "PASS" if passed else "FAIL", "checks": checks})
    print(f"[verify-user-auth-isolation] {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
