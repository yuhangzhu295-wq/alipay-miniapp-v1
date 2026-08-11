"""Exercise the WeChat image-content safety Gate without invoking image models.

The script uses the real FastAPI routes, real request signing, real asynchronous
state store and real backend Gate.  It replaces only the outbound WeChat HTTP
transport and image-model functions so it can deterministically verify PASS,
PENDING and REJECT behavior in an isolated runtime directory.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import base64
import struct
import sys
import tempfile
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_ROOT = PROJECT_ROOT / "server"
REPORT_DIR = PROJECT_ROOT / "reports" / "wechat-content-security"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def make_jpeg(rgb: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (96, 128), rgb)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return dict(self._payload)


class FakeWeChatHttp:
    """Records the exact server-side WeChat API contract used by the service."""

    def __init__(self) -> None:
        self.token_requests: list[dict[str, Any]] = []
        self.media_requests: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any], timeout: float) -> FakeResponse:
        self.token_requests.append({"url": url, "params": dict(params), "timeout": timeout})
        return FakeResponse({"access_token": "test-server-token", "expires_in": 7200})

    def post(self, url: str, params: dict[str, Any], json: dict[str, Any], timeout: float) -> FakeResponse:
        self.media_requests.append({"url": url, "params": dict(params), "json": dict(json), "timeout": timeout})
        return FakeResponse({"errcode": 0, "errmsg": "ok", "trace_id": "trace-" + str(len(self.media_requests))})


def callback_signature(token: str, timestamp: str, nonce: str, encrypted: str = "") -> str:
    values = [token, timestamp, nonce]
    if encrypted:
        values.append(encrypted)
    return hashlib.sha1("".join(sorted(values)).encode("utf-8")).hexdigest()


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def install_model_import_stubs() -> None:
    """Keep this security-route test independent from local AI model packages.

    ``main.py`` imports its model services at module import time. The Gate tests
    replace those model callables anyway, so lightweight placeholders let the
    real HTTP routes load without installing OpenCV, rembg, MediaPipe or models.
    The real ``services.wechat_security`` module is deliberately not stubbed.
    """
    services = types.ModuleType("services")
    services.__path__ = [str(SERVER_ROOT / "services")]
    sys.modules["services"] = services

    def add_module(name: str, **attributes: Any) -> None:
        module = types.ModuleType(name)
        for key, value in attributes.items():
            setattr(module, key, value)
        sys.modules[name] = module

    class TemplateError(Exception):
        def __init__(self, message: str = "template error", status_code: int = 400, code: str = "TEMPLATE_ERROR", template_id: str = "") -> None:
            super().__init__(message)
            self.status_code = status_code
            self.code = code
            self.template_id = template_id

    class PortraitQualityError(Exception):
        def __init__(self, message: str = "portrait quality error", status_code: int = 400, code: str = "PORTRAIT_ERROR", quality: dict[str, Any] | None = None) -> None:
            super().__init__(message)
            self.status_code = status_code
            self.code = code
            self.quality = quality or {}

    class HdInpaintError(Exception):
        def __init__(self, message: str = "hd inpaint error", status_code: int = 400, fallback_available: bool = False, debug: dict[str, Any] | None = None) -> None:
            super().__init__(message)
            self.status_code = status_code
            self.fallback_available = fallback_available
            self.debug = debug or {}

    class HeavyTaskBusyError(Exception):
        pass

    class QueueStub:
        def run(self, _task_type: str, task: Any) -> tuple[Any, int]:
            return task(), 0

        def snapshot(self) -> dict[str, Any]:
            return {}

    add_module("services.remove_bg", do_remove_bg=lambda *_args, **_kwargs: "")
    add_module("services.change_bg", do_change_bg=lambda *_args, **_kwargs: {})
    add_module("services.inpaint", do_inpaint=lambda *_args, **_kwargs: "")
    add_module("services.compress", do_compress=lambda *_args, **_kwargs: ("", 0))
    add_module("services.professional", do_professional_photo=lambda *_args, **_kwargs: {})
    add_module("services.manual_inpaint", do_manual_inpaint=lambda *_args, **_kwargs: {}, do_quick_inpaint=lambda *_args, **_kwargs: {})
    add_module("services.scan_template", do_scan_template=lambda *_args, **_kwargs: (b"", []))
    add_module("services.hd_inpaint", HdInpaintError=HdInpaintError, do_hd_inpaint=lambda *_args, **_kwargs: {}, get_hd_status=lambda: {})
    add_module("services.stroke_inpaint", process_stroke_inpaint=lambda *_args, **_kwargs: {})
    add_module(
        "services.id_photo_v2",
        TemplateError=TemplateError,
        compose_prepared_id_photo=lambda *_args, **_kwargs: {},
        cleanup_prepare_cache=lambda: None,
        generate_id_photo_v2=lambda *_args, **_kwargs: {},
        get_capabilities=lambda: {"templates": []},
        get_detail_source=lambda *_args, **_kwargs: None,
        prepare_detail_id_photo=lambda *_args, **_kwargs: {},
        prepare_id_photo_v2=lambda *_args, **_kwargs: ({}, {}),
    )
    add_module("services.heavy_task_queue", HeavyTaskBusyError=HeavyTaskBusyError, heavy_task_queue=QueueStub())
    add_module(
        "services.hd_progress",
        begin_request=lambda *_args, **_kwargs: True,
        finish_request=lambda *_args, **_kwargs: None,
        get_request=lambda *_args, **_kwargs: {},
        normalize_request_id=lambda value: str(value or "test-request"),
        update_request=lambda *_args, **_kwargs: None,
    )
    add_module("services.face_detector", get_face_detector_status=lambda: {"opencvAvailable": True})
    add_module("services.portrait_matting", matting_status=lambda: {"rembgAvailable": True})
    add_module(
        "services.portrait_quality",
        PortraitQualityError=PortraitQualityError,
        classify_image_type=lambda *_args, **_kwargs: {"imageType": "real_person"},
        validate_portrait_input=lambda *_args, **_kwargs: {},
    )
    add_module(
        "id_photo_engines",
        get_engine_info=lambda: {},
        get_engine_runtime_tags=lambda: {"engine": "test", "engineVersion": "test", "engineModel": "test"},
    )


def main() -> int:
    runtime_dir = Path(tempfile.mkdtemp(prefix="wechat-content-security-"))
    report: dict[str, Any] = {
        "generatedAt": utc_now(),
        "runtime": "isolated FastAPI TestClient",
        "liveWeChatCallVerified": False,
        "liveWeChatCallReason": "The test deliberately substitutes only outbound WeChat HTTP; no production AppSecret or callback endpoint is available in the local workspace.",
        "tests": [],
    }
    try:
        os.environ.update({
            "ID_PHOTO_RUNTIME_DIR": str(runtime_dir),
            "ID_PHOTO_AUTH_SECRET": "content-security-test-auth-secret",
            "WECHAT_APPID": "wx_content_security_test",
            "WECHAT_APP_SECRET": "server-only-test-secret",
            "WECHAT_CONTENT_SECURITY_CALLBACK_TOKEN": "content-security-callback-token",
            "WECHAT_CONTENT_SECURITY_PUBLIC_BASE_URL": "https://tupzjianzhao.chat",
            "WECHAT_CONTENT_SECURITY_RETENTION_SECONDS": "1800",
            "WECHAT_CONTENT_SECURITY_PENDING_TIMEOUT_SECONDS": "1800",
        })
        sys.path.insert(0, str(SERVER_ROOT))
        install_model_import_stubs()
        from fastapi.testclient import TestClient
        import main as server_main

        fake_http = FakeWeChatHttp()
        server_main.wechat_security_service = server_main.WeChatSecurityService(
            app_id="wx_content_security_test",
            app_secret="server-only-test-secret",
            callback_token="content-security-callback-token",
            scene=4,
            http_client=fake_http,
        )

        normal_image = make_jpeg((48, 122, 206))
        rejected_image = make_jpeg((212, 82, 76))
        model_calls = {"prepare": 0, "compose": 0, "watermarkQuick": 0, "watermarkHd": 0}

        def fake_prepare(image_bytes: bytes, **_: Any) -> tuple[dict[str, Any], dict[str, int]]:
            model_calls["prepare"] += 1
            assert_true(bool(image_bytes), "prepare must receive verified image bytes")
            return ({
                "preparedId": "prepared_security_case",
                "sourceId": "source_security_case",
                "imageType": "real_person",
                "mode": "official",
                "spec": {"id": "one-inch", "width": 295, "height": 413},
                "compositionVersion": "content-security-test",
                "quality": {
                    "fastResultUsable": True,
                    "mattingPass": True,
                    "cropPass": True,
                    "detailRecommended": False,
                },
                "debug": {"faceDetector": "test", "faceCount": 1},
                "performance": {},
                "performanceTimestamps": {},
            }, {})

        def fake_compose(prepared_id: str, **kwargs: Any) -> dict[str, Any]:
            model_calls["compose"] += 1
            assert_true(prepared_id == "prepared_security_case", "compose must reuse prepare result")
            path = runtime_dir / ("compose_" + str(model_calls["compose"]) + ".jpg")
            path.write_bytes(normal_image)
            return {
                "path": str(path),
                "mode": "official",
                "imageType": "real_person",
                "spec": {"id": "one-inch", "width": 295, "height": 413},
                "bgColor": kwargs.get("bg_color") or "#438EDB",
                "outfit": {},
                "warnings": [],
                "quality": {"mattingPass": True, "cropPass": True},
                "debug": {},
            }

        def fake_stroke_inpaint(
            image_bytes: bytes,
            _strokes_json: str,
            quality: str,
            _strength: str,
            _preserve_detail: bool,
            **_: Any,
        ) -> dict[str, Any]:
            assert_true(bool(image_bytes), "watermark model must receive verified image bytes")
            if quality == "hd":
                model_calls["watermarkHd"] += 1
                engine = "lama"
            else:
                model_calls["watermarkQuick"] += 1
                engine = "opencv_quick"
            return {
                "bytes": image_bytes,
                "mode": quality,
                "engine": engine,
                "fallbackUsed": False,
                "backendMode": "content-security-test",
                "message": "处理成功",
                "debug": {},
                "suffix": ".jpg",
            }

        server_main.prepare_id_photo_v2 = fake_prepare
        server_main.compose_prepared_id_photo = fake_compose
        server_main.process_stroke_inpaint = fake_stroke_inpaint
        server_main.get_engine_runtime_tags = lambda: {
            "engine": "content-security-test",
            "engineVersion": "test",
            "engineModel": "test",
        }
        server_main.heavy_task_queue.run = lambda _task_type, task: (task(), 0)
        server_main.heavy_task_queue.snapshot = lambda: {}

        token = server_main._issue_user_token("content-security-user", openid="openid-content-security", provider="wechat")
        headers = {"Authorization": "Bearer " + token}
        client = TestClient(server_main.app)

        def add_test(name: str, passed: bool, **detail: Any) -> None:
            report["tests"].append({"name": name, "passed": bool(passed), **detail})

        def submit(image_bytes: bytes, purpose: str) -> dict[str, Any]:
            response = client.post(
                "/api/content-security/images",
                headers=headers,
                data={"purpose": purpose},
                files={"image": ("input.jpg", image_bytes, "image/jpeg")},
            )
            assert_true(response.status_code in {200, 202}, "security submission must return 200/202")
            payload = response.json()
            assert_true(payload.get("securityCheckId"), "security submission must return securityCheckId")
            return {"httpStatus": response.status_code, **payload}

        def deliver_callback(trace_id: str, suggest: str) -> None:
            timestamp, nonce = "1700000000", "nonce-content-security"
            signature = callback_signature("content-security-callback-token", timestamp, nonce)
            payload = {
                "Event": "wxa_media_check",
                "appid": "wx_content_security_test",
                "trace_id": trace_id,
                "status_code": 0,
                "result": {"suggest": suggest, "label": 100},
            }
            response = client.post(
                "/api/content-security/callback",
                params={"signature": signature, "timestamp": timestamp, "nonce": nonce},
                content=json.dumps(payload),
                headers={"content-type": "application/json"},
            )
            assert_true(response.status_code == 200 and response.text == "success", "callback must be accepted")

        normal_submission = submit(normal_image, "id_photo")
        assert_true(normal_submission["status"] == "PENDING", "accepted async submission must remain PENDING")
        pending_prepare = client.post(
            "/api/id-photo/prepare",
            headers=headers,
            data={"securityCheckId": normal_submission["securityCheckId"], "specId": "one-inch"},
            files={"image": ("normal.jpg", normal_image, "image/jpeg")},
        )
        pending_payload = pending_prepare.json()
        assert_true(pending_prepare.status_code == 503, "PENDING image must not enter prepare")
        assert_true(pending_payload.get("code") == "CONTENT_SAFETY_PENDING", "PENDING response code must be explicit")
        assert_true(model_calls["prepare"] == 0, "model must not run while PENDING")
        add_test("async_submission_is_not_pass", True, status=normal_submission["status"], blockedStatus=pending_prepare.status_code)

        deliver_callback("trace-1", "pass")
        status_response = client.get("/api/content-security/images/" + normal_submission["securityCheckId"], headers=headers)
        pass_status = status_response.json()
        assert_true(status_response.status_code == 200 and pass_status.get("status") == "PASS", "callback PASS must be persisted")
        add_test("callback_pass_transitions_to_pass", True, status=pass_status.get("status"))

        model_calls_before_duplicate = dict(model_calls)
        deliver_callback("trace-1", "pass")
        duplicate_status = client.get(
            "/api/content-security/images/" + normal_submission["securityCheckId"],
            headers=headers,
        ).json()
        assert_true(duplicate_status.get("status") == "PASS", "duplicate callback must preserve terminal status")
        assert_true(model_calls == model_calls_before_duplicate, "duplicate callback must not invoke downstream models")
        add_test("duplicate_callback_is_idempotent", True, status=duplicate_status.get("status"), downstreamCalls=0)

        prepare_response = client.post(
            "/api/id-photo/prepare",
            headers=headers,
            data={"securityCheckId": normal_submission["securityCheckId"], "specId": "one-inch", "widthPx": "295", "heightPx": "413"},
            files={"image": ("normal.jpg", normal_image, "image/jpeg")},
        )
        prepare_payload = prepare_response.json()
        assert_true(prepare_response.status_code == 200 and prepare_payload.get("success"), "PASS image must reach prepare")
        assert_true(model_calls["prepare"] == 1, "prepare model must run exactly once after PASS")

        colors = ["#438EDB", "#FFFFFF", "#FF0000", "#7EC8E3", "#BFC5D0"]
        compose_results = []
        for color in colors:
            response = client.post(
                "/api/id-photo/compose",
                data={"preparedId": prepare_payload["preparedId"], "bgColor": color, "bgColorName": color, "outputType": "jpg"},
            )
            compose_results.append({"status": response.status_code, "success": bool(response.json().get("success"))})
            assert_true(response.status_code == 200 and response.json().get("success"), "compose must work after PASS")
        assert_true(model_calls["compose"] == 5, "five color outputs must reuse one prepared input")
        assert_true(len(fake_http.media_requests) == 1, "five color switches must not resubmit media security")
        add_test("normal_id_photo_prepare_and_five_color_compose", True, composeCount=len(compose_results), mediaCheckCalls=len(fake_http.media_requests))

        strokes = json.dumps({
            "coordinateSpace": "normalized",
            "strokes": [{"type": "maskRect", "x": 0.2, "y": 0.2, "w": 0.1, "h": 0.1}],
        })
        watermark_common = {
            "securityCheckId": normal_submission["securityCheckId"],
            "strokesJson": strokes,
            "originalWidth": "96",
            "originalHeight": "128",
            "displayWidth": "96",
            "displayHeight": "128",
            "strength": "medium",
        }
        quick_response = client.post(
            "/api/watermark/remove-v2",
            headers=headers,
            data={**watermark_common, "quality": "quick"},
            files={"image": ("normal.jpg", normal_image, "image/jpeg")},
        )
        hd_response = client.post(
            "/api/watermark/remove-v2",
            headers=headers,
            data={**watermark_common, "quality": "hd", "requestId": "content-security-hd"},
            files={"image": ("normal.jpg", normal_image, "image/jpeg")},
        )
        assert_true(quick_response.status_code == 200 and quick_response.json().get("success"), "PASS image must enter quick watermark flow")
        assert_true(hd_response.status_code == 200 and hd_response.json().get("success"), "PASS image must enter HD watermark flow")
        assert_true(model_calls["watermarkQuick"] == 1 and model_calls["watermarkHd"] == 1, "both watermark modes must run only after PASS")
        assert_true(hd_response.json().get("engine") == "lama", "HD flow test must preserve the HD model contract")
        add_test("normal_image_watermark_quick_and_hd", True, quickEngine=quick_response.json().get("engine"), hdEngine=hd_response.json().get("engine"))

        repeated_submissions = [submit(normal_image, "id_photo") for _ in range(5)]
        assert_true(all(item.get("status") == "PASS" and item.get("reused") is True for item in repeated_submissions), "same PASS image must be reused")
        assert_true(len(fake_http.media_requests) == 1, "repeated same-image submissions must not repeat media security")
        add_test("same_image_security_deduplication", True, repeatedSubmissions=len(repeated_submissions), mediaCheckCalls=len(fake_http.media_requests))

        rejected_submission = submit(rejected_image, "watermark_removal")
        deliver_callback("trace-2", "risky")
        rejected_prepare_before = model_calls["prepare"]
        rejected_prepare = client.post(
            "/api/id-photo/prepare",
            headers=headers,
            data={"securityCheckId": rejected_submission["securityCheckId"], "specId": "one-inch"},
            files={"image": ("rejected.jpg", rejected_image, "image/jpeg")},
        )
        rejected_payload = rejected_prepare.json()
        assert_true(rejected_prepare.status_code == 403, "REJECT image must be blocked from prepare")
        assert_true(rejected_payload.get("code") == "CONTENT_SAFETY_REJECTED", "REJECT code must be explicit")
        assert_true(rejected_payload.get("message") == "图片内容不符合平台规范，请更换图片后重试。", "REJECT message must be user-safe")
        assert_true(model_calls["prepare"] == rejected_prepare_before, "rejected image must not call prepare model")
        rejected_watermark_before = model_calls["watermarkQuick"]
        rejected_watermark = client.post(
            "/api/watermark/remove-v2",
            headers=headers,
            data={**watermark_common, "securityCheckId": rejected_submission["securityCheckId"], "quality": "quick"},
            files={"image": ("rejected.jpg", rejected_image, "image/jpeg")},
        )
        assert_true(rejected_watermark.status_code == 403, "REJECT image must be blocked from watermark")
        assert_true(model_calls["watermarkQuick"] == rejected_watermark_before, "rejected image must not call watermark model")
        add_test("rejected_image_blocks_models", True, prepareModelCalls=model_calls["prepare"], watermarkQuickCalls=model_calls["watermarkQuick"])

        no_openid_token = server_main._issue_user_token("content-security-no-openid", openid="", provider="local_profile")
        no_openid_response = client.post(
            "/api/content-security/images",
            headers={"Authorization": "Bearer " + no_openid_token},
            data={"purpose": "id_photo"},
            files={"image": ("normal.jpg", normal_image, "image/jpeg")},
        )
        assert_true(no_openid_response.status_code == 403, "security submission without OpenID must fail closed")
        assert_true(no_openid_response.json().get("code") == "CONTENT_SAFETY_OPENID_REQUIRED", "OpenID failure code must be explicit")
        add_test("openid_is_required_for_wechat_media_check", True, status=no_openid_response.status_code)

        first_request = fake_http.media_requests[0]
        media_body = first_request["json"]
        assert_true(first_request["url"] == server_main.WeChatSecurityService.MEDIA_CHECK_URL, "must use mediaCheckAsync")
        assert_true(media_body.get("media_type") == 2 and media_body.get("version") == 2, "must use mediaCheckAsync v2 image payload")
        assert_true(media_body.get("openid") == "openid-content-security", "media check must include user OpenID")
        assert_true(media_body.get("scene") == 4 and str(media_body.get("media_url", "")).startswith("https://"), "media check must include scene and public HTTPS URL")
        add_test("server_side_media_check_async_contract", True, mediaCheckUrl=first_request["url"], requestBody={
            "media_url": media_body.get("media_url"),
            "media_type": media_body.get("media_type"),
            "version": media_body.get("version"),
            "scene": media_body.get("scene"),
            "openidPresent": bool(media_body.get("openid")),
        })

        registry = json.loads((runtime_dir / "content_security_registry.json").read_text(encoding="utf-8"))
        records = registry.get("records") or []
        assert_true(all(not record.get("stagingPath") for record in records), "terminal PASS/REJECT records must remove staged files")
        add_test("terminal_security_assets_are_deleted", True, recordCount=len(records))

        forbidden = client.post(
            "/api/content-security/callback",
            params={"signature": "bad", "timestamp": "1", "nonce": "2"},
            content="{}",
            headers={"content-type": "application/json"},
        )
        assert_true(forbidden.status_code == 403, "callback must verify WeChat signature")
        add_test("callback_signature_is_verified", True, status=forbidden.status_code)

        handshake_timestamp, handshake_nonce = "1700000001", "nonce-handshake"
        handshake = client.get(
            "/api/content-security/callback",
            params={
                "signature": callback_signature("content-security-callback-token", handshake_timestamp, handshake_nonce),
                "timestamp": handshake_timestamp,
                "nonce": handshake_nonce,
                "echostr": "wechat-handshake-ok",
            },
        )
        assert_true(handshake.status_code == 200 and handshake.text == "wechat-handshake-ok", "plain callback handshake must echo only after signature validation")
        add_test("plain_callback_handshake_is_verified", True, status=handshake.status_code)

        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        aes_key = bytes(range(32))
        encoding_aes_key = base64.b64encode(aes_key).decode("ascii").rstrip("=")
        encrypted_service = server_main.WeChatSecurityService(
            app_id="wx_content_security_test",
            app_secret="server-only-test-secret",
            callback_token="content-security-callback-token",
            encoding_aes_key=encoding_aes_key,
            http_client=fake_http,
        )
        encrypted_message = b"wechat-encrypted-handshake"
        encrypted_plain = os.urandom(16) + struct.pack("!I", len(encrypted_message)) + encrypted_message + b"wx_content_security_test"
        padding = 32 - (len(encrypted_plain) % 32)
        encrypted_plain += bytes([padding]) * padding
        encryptor = Cipher(algorithms.AES(aes_key), modes.CBC(aes_key[:16])).encryptor()
        encrypted_echo = base64.b64encode(encryptor.update(encrypted_plain) + encryptor.finalize()).decode("ascii")
        original_service = server_main.wechat_security_service
        server_main.wechat_security_service = encrypted_service
        try:
            encrypted_timestamp, encrypted_nonce = "1700000002", "nonce-encrypted-handshake"
            encrypted_handshake = client.get(
                "/api/content-security/callback",
                params={
                    "msg_signature": callback_signature("content-security-callback-token", encrypted_timestamp, encrypted_nonce, encrypted_echo),
                    "timestamp": encrypted_timestamp,
                    "nonce": encrypted_nonce,
                    "echostr": encrypted_echo,
                },
            )
            assert_true(encrypted_handshake.status_code == 200 and encrypted_handshake.text == encrypted_message.decode("utf-8"), "AES callback handshake must be signature-checked and decrypted")
        finally:
            server_main.wechat_security_service = original_service
        add_test("encrypted_callback_handshake_is_verified", True, status=encrypted_handshake.status_code)

        client_roots = [PROJECT_ROOT / "pages", PROJECT_ROOT / "utils", PROJECT_ROOT / "project.config.json"]
        forbidden_secret_markers = ("WECHAT_APP_SECRET", "WECHAT_SECRET", "AppSecret", "appSecret")
        secret_hits: list[str] = []
        for root in client_roots:
            paths = root.rglob("*") if root.is_dir() else [root]
            for path in paths:
                if not path.is_file() or path.suffix not in {".js", ".json", ".wxml", ".wxss"}:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                if any(marker in text for marker in forbidden_secret_markers):
                    secret_hits.append(str(path.relative_to(PROJECT_ROOT)))
        assert_true(not secret_hits, "frontend must not contain an AppSecret marker")
        add_test("app_secret_is_server_only", True, clientSecretHits=secret_hits)

        report["modelCalls"] = model_calls
        report["wechatTransport"] = {
            "tokenRequests": len(fake_http.token_requests),
            "mediaCheckRequests": len(fake_http.media_requests),
            "deduplicatedNormalImageCalls": 1,
        }
        report["summary"] = {
            "passed": sum(1 for item in report["tests"] if item["passed"]),
            "total": len(report["tests"]),
            "allPassed": all(item["passed"] for item in report["tests"]),
        }
        assert_true(report["summary"]["allPassed"], "all content-security tests must pass")

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        write_json(REPORT_DIR / "security-api-test.json", report)
        write_text(REPORT_DIR / "normal-image-flow.md", "\n".join([
            "# 正常图片链路验证",
            "",
            "- 测试方式：隔离 FastAPI TestClient，保留真实安全状态机、路由和 Gate；仅替换外部微信 HTTP 与图片模型。",
            "- 正常图提交后初始状态为 `PENDING`，此时 `/api/id-photo/prepare` 返回 `CONTENT_SAFETY_PENDING`，模型调用数为 0。",
            "- 模拟经过签名验证的微信 `wxa_media_check` 回调 `suggest=pass` 后，状态变为 `PASS`。",
            "- `prepare` 成功，随后五种底色 `compose` 均成功；同一图 `mediaCheckAsync` 调用数仍为 1。",
            "- 同一张 `PASS` 图分别进入快速与高清去水印，均成功进入原有处理链路；高清测试仍要求引擎标识为 `lama`。",
            "",
            "详细数据见 `security-api-test.json`。",
        ]) + "\n")
        write_text(REPORT_DIR / "rejected-image-flow.md", "\n".join([
            "# 拒绝图片链路验证",
            "",
            "- 为第二张独立图片提交异步审核，模拟已签名微信回调 `suggest=risky`。",
            "- 状态变为 `REJECT`，临时安全目录文件被删除。",
            "- 对证件照 `prepare` 与去水印 `remove-v2` 的后续请求均返回 HTTP 403。",
            "- 用户可见提示固定为：`图片内容不符合平台规范，请更换图片后重试。`",
            "- 准备模型与快速去水印模型调用计数在拒绝请求前后未增加。",
        ]) + "\n")
        print(json.dumps(report["summary"], ensure_ascii=False))
        return 0
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        report["summary"] = {
            "passed": sum(1 for item in report["tests"] if item.get("passed")),
            "total": len(report["tests"]),
            "allPassed": False,
        }
        write_json(REPORT_DIR / "security-api-test.json", report)
        print(json.dumps(report["error"], ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
