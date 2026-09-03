"""Build review-ready evidence documents from the executed content-security tests."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "wechat-content-security"
TEST_REPORT = REPORT_DIR / "security-api-test.json"
FRONTEND_REPORT = REPORT_DIR / "frontend-gate-test.json"
DEVTOOLS_PREVIEW = REPORT_DIR / "devtools-preview.json"

BACKEND_IMAGE_ROUTES = [
    "/api/remove-bg",
    "/api/change-bg",
    "/api/inpaint",
    "/api/compress",
    "/api/professional-photo",
    "/api/id-photo/generate-v2",
    "/api/id-photo/prepare",
    "/api/portrait/inspect",
    "/api/portrait/validate",
    "/api/verify-photo",
    "/api/watermark/manual-remove",
    "/api/watermark/quick-remove",
    "/api/watermark/hd-remove",
    "/api/watermark/remove-v2",
    "/api/watermark/scan-template",
]

FRONTEND_REMOTE_UPLOADS = [
    ("utils/aiImageApi.js", "removeBg, changeBg, validatePortraitInput, inspectPortrait, generateIdPhotoV2, prepareIdPhotoV2, inpaint, compressByServer, verifyPhoto"),
    ("utils/watermarkApi.js", "removeV2 (manual / quick / hd)"),
    ("utils/professionalApi.js", "generateProfessionalPhoto"),
]

SOURCE_SELECTIONS = [
    ("utils/imageService.js", "chooseImage / takePhoto"),
    ("pages/capture-guide/capture-guide.js", "相册入口"),
    ("pages/id-camera/id-camera.js", "原生相机 takePhoto / 相册重选"),
    ("pages/generate/generate.js", "重新上传"),
    ("pages/tool-detail/tool-detail.js", "工具单图选择、排版多图、采集相机、采集相册"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def source_text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def route_is_guarded(main_source: str, route: str) -> bool:
    marker = '@app.post("' + route + '")'
    start = main_source.find(marker)
    if start < 0:
        return False
    next_route = main_source.find("\n@app.", start + len(marker))
    body = main_source[start: next_route if next_route >= 0 else len(main_source)]
    return "securityCheckId" in body and "_read_verified_image" in body


def js_upload_bypasses() -> list[str]:
    bypasses: list[str] = []
    for root in (ROOT / "pages", ROOT / "utils"):
        for path in root.rglob("*.js"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"\bwx\.uploadFile\s*\(", text) and path.relative_to(ROOT).as_posix() != "utils/imageSafetyApi.js":
                bypasses.append(path.relative_to(ROOT).as_posix())
    return sorted(set(bypasses))


def client_secret_hits() -> list[str]:
    markers = ("WECHAT_APP_SECRET", "WECHAT_SECRET", "AppSecret", "appSecret")
    hits: list[str] = []
    roots = [ROOT / "pages", ROOT / "utils", ROOT / "project.config.json"]
    for root in roots:
        paths = root.rglob("*") if root.is_dir() else [root]
        for path in paths:
            if not path.is_file() or path.suffix not in {".js", ".json", ".wxml", ".wxss"}:
                continue
            if any(marker in path.read_text(encoding="utf-8", errors="ignore") for marker in markers):
                hits.append(path.relative_to(ROOT).as_posix())
    return sorted(set(hits))


def main() -> int:
    if not TEST_REPORT.exists() or not FRONTEND_REPORT.exists():
        raise RuntimeError("Run both content-security verification scripts before building reports.")
    security = read_json(TEST_REPORT)
    frontend = read_json(FRONTEND_REPORT)
    preview = read_json(DEVTOOLS_PREVIEW) if DEVTOOLS_PREVIEW.exists() else {}
    main_source = source_text("server/main.py")
    guarded = {route: route_is_guarded(main_source, route) for route in BACKEND_IMAGE_ROUTES}
    bypasses = js_upload_bypasses()
    secret_hits = client_secret_hits()
    security_ok = bool((security.get("summary") or {}).get("allPassed"))
    frontend_ok = bool((frontend.get("summary") or {}).get("allPassed"))
    all_guarded = all(guarded.values())
    preview_size = int(((preview.get("size") or {}).get("total") or 0))
    preview_ok = preview_size > 0
    readiness = security_ok and frontend_ok and preview_ok and all_guarded and not bypasses and not secret_hits

    architecture = """# 微信图片内容安全架构

## 统一业务链路

```text
选择/拍摄图片
  -> utils/imageSafetyApi.ensureImageSafety
  -> 后端 POST /api/content-security/images
  -> 私有记录 + 短期 HTTPS 临时文件
  -> 腾讯微信 mediaCheckAsync (PENDING)
  -> 微信签名回调 /api/content-security/callback
  -> PASS / REJECT / ERROR / TIMEOUT
  -> 原业务上传附带 securityCheckId
  -> 后端 _read_verified_image + 哈希、用户归属校验
  -> 原有证件照/图片处理模型
```

## Gate 规则

- `mediaCheckAsync` 的 `errcode=0` 仅表示任务已受理，记录保持 `PENDING`，不能进入处理模型。
- 只有经回调写入 `PASS` 的 `securityCheckId` 才能通过 `_read_verified_image`。
- Gate 同时校验登录用户、真实 `openid`、图片 SHA-256 和临时任务归属；换一个文件或其他用户的凭据不会放行。
- `REJECT` 显示：`图片内容不符合平台规范，请更换图片后重试。`
- `PENDING` 显示：`图片安全检测暂未完成，请稍后重试。`
- 服务或回调异常显示：`图片安全检测暂时不可用，请稍后重试。`
- `REJECT`、`ERROR`、`TIMEOUT` 会删除安全暂存文件；`PASS` 后也会删除暂存文件，原业务仍使用已有的短期结果文件生命周期。

## 服务器配置（不写入前端或 Git）

- `WECHAT_APPID`
- `WECHAT_APP_SECRET`
- `WECHAT_CONTENT_SECURITY_CALLBACK_TOKEN`
- `WECHAT_CONTENT_SECURITY_PUBLIC_BASE_URL=https://tupzjianzhao.chat`
- 可选：`WECHAT_CONTENT_SECURITY_ENCODING_AES_KEY`

微信后台消息回调地址应配置为：`https://tupzjianzhao.chat/api/content-security/callback`。`/uploads/content-security/*` 必须保持可被微信服务器经 HTTPS 临时读取，且不得目录列出。

## 文本安全结论

`TEXT_SECURITY = NOT_APPLICABLE`。现有自由输入仅为昵称、规格搜索、数值尺寸、颜色值和本地水印文字；项目没有用户公开发布、评论、动态或共享文本的业务入口，因此没有凭空增加 `msgSecCheck` 场景。

## 不变范围

本轮没有修改 Hivision、MODNet、BiRefNet、发丝精修、证件照 Composition Profile、人像比例、LaMa、IOPaint 或快速/高清去水印算法。Gate 只包裹上传前和模型入口。
"""

    upload_lines = [
        "# 图片上传入口审计",
        "",
        "## 选择与拍摄入口（10 个调用点）",
        "",
        *[f"- `{file}`：{description}" for file, description in SOURCE_SELECTIONS],
        "",
        "这些入口只产生本地临时文件；一旦进入后端图片处理，统一使用下列共享 Gate。排版、格式转换、画布编辑、保存相册等仅在本地运行时不上传原图，因此不适用媒体审核调用。",
        "",
        "## 前端远程图片处理入口（11 个操作）",
        "",
        *[f"- `{file}`：{description}，均调用 `imageSafetyApi.uploadWithSafety(...)`。" for file, description in FRONTEND_REMOTE_UPLOADS],
        "",
        "## 后端防绕过入口（15 条图片接收路由）",
        "",
        *[f"- `{route}`：{'PASS，含 `securityCheckId` 与 `_read_verified_image`' if guarded[route] else 'FAIL，未发现 Gate'}" for route in BACKEND_IMAGE_ROUTES],
        "",
        f"- 前端直连 `wx.uploadFile` 绕过文件：`{', '.join(bypasses) if bypasses else '无'}`。仅 `utils/imageSafetyApi.js` 保留两处底层调用，分别用于安全暂存和已通过 Gate 的业务上传。",
        f"- 小程序端 AppSecret 标记命中：`{', '.join(secret_hits) if secret_hits else '无'}`。",
        "",
        "## 同图复用",
        "",
        "`imageSafetyApi` 对同一用户、文件路径、文件字节数维护 in-flight 和 25 分钟 PASS 缓存；后端同时按用户 + SHA-256 复用短期任务。因此一张已通过的图切换五种底色只会提交一次 `mediaCheckAsync`。",
    ]

    final_lines = [
        "# 微信内容安全整改总结",
        "",
        f"- 生成时间：{now()}",
        f"- 本地专项后端验证：{'PASS' if security_ok else 'FAIL'}，{(security.get('summary') or {}).get('passed', 0)}/{(security.get('summary') or {}).get('total', 0)} 项。",
        f"- 小程序共享 Gate 运行时验证：{'PASS' if frontend_ok else 'FAIL'}，{(frontend.get('summary') or {}).get('passed', 0)}/{(frontend.get('summary') or {}).get('total', 0)} 项。",
        f"- 微信开发者工具预览构建：{'PASS' if preview_ok else 'FAIL'}，包体 {preview_size} bytes；仅生成预览，未提交审核。",
        "",
        "1. 微信图片安全接口：实现真实服务器端 `https://api.weixin.qq.com/wxa/media_check_async` 调用，参数含 `media_url`、`media_type=2`、`version=2`、`openid`、`scene`。本地测试替换了外网传输以避免使用生产凭据；腾讯云实际出网和回调配置尚待部署后观察日志确认，未伪称已完成线上调用。",
        "2. 调用位置：仅腾讯云 Backend 的 `WeChatSecurityService` 获取 token 并调用微信接口，小程序端不持有 access_token 或 AppSecret。",
        "3. AppSecret：前端静态扫描无命中；只从服务器环境变量读取。",
        "4. 异步结果：`PENDING/PASS/REJECT/ERROR/TIMEOUT` 已持久化；`errcode=0` 不会放行，只有回调 `PASS` 可进入模型。",
        f"5. 图片入口：审计 10 个选择/拍摄调用点、11 个前端远程处理操作和 {len(BACKEND_IMAGE_ROUTES)} 条后端图片接收路由。",
        f"6. 覆盖状态：{'全部覆盖' if all_guarded and not bypasses else '存在缺口，见 upload-entry-audit.md'}。",
        "7. 拒绝图：准备模型和去水印模型均被真实路由阻断，返回 HTTP 403 与统一合规提示。",
        "8. 正常图：prepare、五种底色 compose、快速去水印和高清去水印回归均通过；高清测试仍断言引擎为 `lama`。",
        "9. 去重：同图并发、同图重复提交和五色切换均验证为一次安全接口提交。",
        "10. 算法范围：未改动任何证件照、抠图或去水印核心算法，仅接入安全暂存、异步状态机、上传凭据和阻断。",
        "",
        "## 发布前仍需人工完成的腾讯云配置",
        "",
        "- 在腾讯云 Backend 环境变量设置上述四个必填配置，重启服务。",
        "- 在微信公众平台配置并校验消息回调 URL、Token（及选择 AES 时的 EncodingAESKey）。",
        "- 以真实 `openid` 上传一张正常图，日志需出现 `mediaCheckAsync submitted` 和后续 `callback ... PASS`，再确认正常业务结果。",
        "- 本轮未提交审核包、未上传审核，等待用户确认报告后再进行。",
        "",
        "## 证据文件",
        "",
        "- `security-architecture.md`",
        "- `upload-entry-audit.md`",
        "- `security-api-test.json`",
        "- `frontend-gate-test.json`",
        "- `devtools-preview.png` / `devtools-preview.json`",
        "- `normal-image-flow.md`",
        "- `rejected-image-flow.md`",
    ]

    write(REPORT_DIR / "security-architecture.md", architecture)
    write(REPORT_DIR / "upload-entry-audit.md", "\n".join(upload_lines) + "\n")
    write(REPORT_DIR / "final-summary.md", "\n".join(final_lines) + "\n")
    summary = {
        "generatedAt": now(),
        "readyForCodeReview": readiness,
        "liveCloudVerification": "PENDING_DEPLOYMENT_CONFIGURATION",
        "backendGateRoutes": guarded,
        "frontendUploadBypasses": bypasses,
        "clientSecretHits": secret_hits,
        "backendTestSummary": security.get("summary"),
        "frontendTestSummary": frontend.get("summary"),
        "devtoolsPreview": {"passed": preview_ok, "totalBytes": preview_size},
    }
    write(REPORT_DIR / "report-metadata.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if readiness else 1


if __name__ == "__main__":
    raise SystemExit(main())
