"""Server-side WeChat content-security primitives for image-processing flows.

This module intentionally contains no mini-program credentials.  All WeChat
credentials are read from the server environment at runtime and access tokens
are kept only in process memory.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import requests

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except Exception:  # pragma: no cover - surfaced as a configuration error when needed
    Cipher = None
    algorithms = None
    modes = None


STATUS_PENDING = "PENDING"
STATUS_PASS = "PASS"
STATUS_REJECT = "REJECT"
STATUS_ERROR = "ERROR"
STATUS_TIMEOUT = "TIMEOUT"


def utc_iso(epoch: Optional[float] = None) -> str:
    value = time.time() if epoch is None else float(epoch)
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


class WeChatSecurityError(RuntimeError):
    """An upstream WeChat security API request could not be trusted."""


class WeChatSecurityConfigurationError(WeChatSecurityError):
    """Required server-only WeChat security settings are absent."""


class ContentSafetyGateError(RuntimeError):
    """Raised when an image is not allowed to reach an image-processing model."""

    def __init__(self, code: str, message: str, status_code: int, status: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.status = status


class WeChatSecurityService:
    """Obtains server-only access tokens and submits WeChat security checks."""

    ACCESS_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
    MEDIA_CHECK_URL = "https://api.weixin.qq.com/wxa/media_check_async"
    TEXT_CHECK_URL = "https://api.weixin.qq.com/wxa/msg_sec_check"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        callback_token: str,
        encoding_aes_key: str = "",
        scene: int = 4,
        request_timeout_seconds: float = 12.0,
        http_client: Any = None,
    ) -> None:
        self.app_id = (app_id or "").strip()
        self.app_secret = (app_secret or "").strip()
        self.callback_token = (callback_token or "").strip()
        self.encoding_aes_key = (encoding_aes_key or "").strip()
        self.scene = int(scene or 4)
        self.request_timeout_seconds = float(request_timeout_seconds)
        self.http_client = http_client or requests
        self._access_token = ""
        self._access_token_expires_at = 0.0
        self._token_lock = threading.RLock()

    @classmethod
    def from_env(cls) -> "WeChatSecurityService":
        app_id = (os.environ.get("WECHAT_APP_ID") or "").strip()
        app_secret = (os.environ.get("WECHAT_APP_SECRET") or "").strip()
        if not app_id:
            app_id = (os.environ.get("WECHAT_APPID") or "").strip()
            if app_id:
                print(
                    "[wechat-config] deprecated WECHAT_APPID is in use; "
                    "canonicalAppIdEnv=WECHAT_APP_ID",
                    flush=True,
                )
        if not app_secret:
            app_secret = (os.environ.get("WECHAT_SECRET") or "").strip()
            if app_secret:
                print(
                    "[wechat-config] deprecated WECHAT_SECRET is in use; "
                    "canonicalSecretEnv=WECHAT_APP_SECRET",
                    flush=True,
                )
        print(
            "[wechat-config] "
            f"wechatAppIdConfigured={str(bool(app_id)).lower()} "
            f"wechatSecretConfigured={str(bool(app_secret)).lower()}",
            flush=True,
        )
        return cls(
            app_id=app_id,
            app_secret=app_secret,
            callback_token=os.environ.get("WECHAT_CONTENT_SECURITY_CALLBACK_TOKEN") or "",
            encoding_aes_key=os.environ.get("WECHAT_CONTENT_SECURITY_ENCODING_AES_KEY") or "",
            scene=int(os.environ.get("WECHAT_CONTENT_SECURITY_SCENE", "4") or 4),
            request_timeout_seconds=float(os.environ.get("WECHAT_CONTENT_SECURITY_TIMEOUT_SECONDS", "12") or 12),
        )

    def configuration_errors(self, require_callback: bool = True) -> list[str]:
        errors = []
        if not self.app_id:
            errors.append("WECHAT_APP_ID")
        if not self.app_secret:
            errors.append("WECHAT_APP_SECRET")
        if require_callback and not self.callback_token:
            errors.append("WECHAT_CONTENT_SECURITY_CALLBACK_TOKEN")
        if self.encoding_aes_key and len(self.encoding_aes_key) != 43:
            errors.append("WECHAT_CONTENT_SECURITY_ENCODING_AES_KEY")
        return errors

    def ensure_configured(self, require_callback: bool = True) -> None:
        missing = self.configuration_errors(require_callback=require_callback)
        if missing:
            raise WeChatSecurityConfigurationError(
                "Missing server-only content-security configuration: " + ", ".join(missing)
            )

    def get_access_token(self) -> str:
        self.ensure_configured(require_callback=False)
        now = time.time()
        with self._token_lock:
            if self._access_token and now < self._access_token_expires_at - 120:
                return self._access_token
            try:
                response = self.http_client.get(
                    self.ACCESS_TOKEN_URL,
                    params={
                        "grant_type": "client_credential",
                        "appid": self.app_id,
                        "secret": self.app_secret,
                    },
                    timeout=self.request_timeout_seconds,
                )
                payload = response.json() if getattr(response, "status_code", 0) == 200 else {}
            except Exception as exc:
                raise WeChatSecurityError("WeChat access token request failed") from exc

            token = str(payload.get("access_token") or "").strip()
            if not token:
                raise WeChatSecurityError(
                    "WeChat access token response rejected: " + str(payload.get("errcode") or "unknown")
                )
            expires_in = max(300, int(payload.get("expires_in") or 7200))
            self._access_token = token
            self._access_token_expires_at = now + expires_in
            return token

    def check_image(self, media_url: str, openid: str, scene: Optional[int] = None) -> Dict[str, Any]:
        self.ensure_configured(require_callback=True)
        if not media_url.startswith("https://"):
            raise WeChatSecurityConfigurationError("media_url must use a public HTTPS URL")
        if not openid:
            raise WeChatSecurityError("openid is required for WeChat media security checks")

        token = self.get_access_token()
        body = {
            "media_url": media_url,
            "media_type": 2,
            "version": 2,
            "scene": int(scene or self.scene),
            "openid": openid,
        }
        try:
            response = self.http_client.post(
                self.MEDIA_CHECK_URL,
                params={"access_token": token},
                json=body,
                timeout=self.request_timeout_seconds,
            )
            payload = response.json() if getattr(response, "status_code", 0) == 200 else {}
        except Exception as exc:
            raise WeChatSecurityError("WeChat media security request failed") from exc

        if int(payload.get("errcode") or 0) != 0:
            raise WeChatSecurityError(
                "WeChat media security request rejected: " + str(payload.get("errcode"))
            )
        trace_id = str(payload.get("trace_id") or "").strip()
        if not trace_id:
            raise WeChatSecurityError("WeChat media security response omitted trace_id")
        return {"traceId": trace_id, "raw": payload, "request": body}

    def check_text(self, content: str, openid: str, scene: Optional[int] = None) -> Dict[str, Any]:
        """Reserved for a future public-text UGC flow; not used by this product today."""
        self.ensure_configured(require_callback=False)
        if not openid:
            raise WeChatSecurityError("openid is required for WeChat text security checks")
        token = self.get_access_token()
        body = {"content": str(content or ""), "version": 2, "scene": int(scene or self.scene), "openid": openid}
        try:
            response = self.http_client.post(
                self.TEXT_CHECK_URL,
                params={"access_token": token},
                json=body,
                timeout=self.request_timeout_seconds,
            )
            payload = response.json() if getattr(response, "status_code", 0) == 200 else {}
        except Exception as exc:
            raise WeChatSecurityError("WeChat text security request failed") from exc
        if int(payload.get("errcode") or 0) != 0:
            raise WeChatSecurityError(
                "WeChat text security request rejected: " + str(payload.get("errcode"))
            )
        return payload

    def verify_callback_signature(self, signature: str, timestamp: str, nonce: str, encrypted: str = "") -> bool:
        if not self.callback_token or not signature or not timestamp or not nonce:
            return False
        values = [self.callback_token, str(timestamp), str(nonce)]
        if encrypted:
            values.append(encrypted)
        digest = hashlib.sha1("".join(sorted(values)).encode("utf-8")).hexdigest()
        return hmac.compare_digest(digest, str(signature))

    def parse_callback_payload(self, raw_body: bytes) -> Dict[str, Any]:
        payload = self.parse_callback_envelope(raw_body)
        encrypted = str(payload.get("Encrypt") or payload.get("encrypt") or "").strip()
        if not encrypted:
            return payload
        decrypted = self._decrypt_callback(encrypted)
        return _parse_callback_mapping(decrypted)

    def parse_callback_envelope(self, raw_body: bytes) -> Dict[str, Any]:
        return _parse_callback_mapping(raw_body)

    def _decrypt_callback(self, encrypted: str) -> bytes:
        if not self.encoding_aes_key:
            raise WeChatSecurityConfigurationError("Encrypted callback requires WECHAT_CONTENT_SECURITY_ENCODING_AES_KEY")
        if Cipher is None:
            raise WeChatSecurityConfigurationError("Encrypted callback requires the cryptography package")
        try:
            key = base64.b64decode(self.encoding_aes_key + "=")
            cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16]))
            decrypted = cipher.decryptor().update(base64.b64decode(encrypted))
            padding = decrypted[-1]
            if not 1 <= padding <= 32:
                raise ValueError("invalid PKCS#7 padding")
            plain = decrypted[:-padding]
            message_length = struct.unpack("!I", plain[16:20])[0]
            message = plain[20:20 + message_length]
            callback_app_id = plain[20 + message_length:].decode("utf-8")
            if self.app_id and callback_app_id != self.app_id:
                raise ValueError("callback appid mismatch")
            return message
        except Exception as exc:
            raise WeChatSecurityError("Unable to decrypt WeChat security callback") from exc


def _parse_callback_mapping(raw_body: bytes) -> Dict[str, Any]:
    text = raw_body.decode("utf-8", errors="replace").strip()
    if not text:
        raise WeChatSecurityError("Empty WeChat security callback")
    try:
        decoded = json.loads(text)
        if isinstance(decoded, dict):
            return decoded
    except json.JSONDecodeError:
        pass
    try:
        root = ET.fromstring(text)
        return {child.tag: child.text or "" for child in root}
    except Exception as exc:
        raise WeChatSecurityError("Unrecognized WeChat security callback payload") from exc


def evaluate_media_check_callback(payload: Dict[str, Any]) -> Tuple[str, str]:
    """Return a fail-closed local state from WeChat's async callback payload."""
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    event = str(payload.get("Event") or payload.get("event") or "").strip().lower()
    if event != "wxa_media_check":
        return STATUS_ERROR, "UNEXPECTED_EVENT"

    try:
        callback_status = int(payload.get("status_code") or payload.get("statusCode") or 0)
    except (TypeError, ValueError):
        callback_status = -1
    try:
        error_code = int(payload.get("errcode") or 0)
    except (TypeError, ValueError):
        error_code = -1
    if callback_status != 0 or error_code != 0:
        return STATUS_ERROR, "WECHAT_CALLBACK_ERROR"

    suggest = str(result.get("suggest") or payload.get("suggest") or "").strip().lower()
    if suggest == "pass":
        return STATUS_PASS, "PASS"
    if suggest in {"risky", "review", "reject"}:
        return STATUS_REJECT, suggest.upper()

    risky_value = payload.get("isrisky")
    if risky_value is not None and str(risky_value).strip() != "":
        try:
            return (STATUS_REJECT, "RISKY") if int(risky_value) else (STATUS_PASS, "PASS")
        except (TypeError, ValueError):
            return STATUS_ERROR, "INVALID_RISK_FLAG"
    return STATUS_ERROR, "UNKNOWN_CALLBACK_RESULT"


class ContentSafetyStore:
    """Small private registry for asynchronous security tasks and short-lived assets."""

    def __init__(self, registry_path: str, staging_dir: str, retention_seconds: int, pending_timeout_seconds: int) -> None:
        self.registry_path = Path(registry_path)
        self.staging_dir = Path(staging_dir)
        self.retention_seconds = max(60, int(retention_seconds))
        self.pending_timeout_seconds = max(10, int(pending_timeout_seconds))
        self._lock = threading.RLock()
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def cleanup(self, now: Optional[float] = None) -> Dict[str, int]:
        current = time.time() if now is None else float(now)
        stats = {"timedOut": 0, "expired": 0, "deletedFiles": 0}
        with self._lock:
            records = self._load_unlocked()
            kept = []
            changed = False
            for record in records:
                status = record.get("status")
                created = float(record.get("createdAtEpoch") or current)
                expires = float(record.get("expiresAtEpoch") or created + self.retention_seconds)
                if status == STATUS_PENDING and created + self.pending_timeout_seconds <= current:
                    record.update({"status": STATUS_TIMEOUT, "updatedAt": utc_iso(current), "updatedAtEpoch": current})
                    stats["timedOut"] += 1
                    stats["deletedFiles"] += int(self._delete_staging_file(record))
                    changed = True
                if expires <= current:
                    stats["expired"] += 1
                    stats["deletedFiles"] += int(self._delete_staging_file(record))
                    changed = True
                    continue
                kept.append(record)
            if changed:
                self._save_unlocked(kept)
        return stats

    def find_reusable(self, user_id: str, image_sha256: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        self.cleanup(now)
        current = time.time() if now is None else float(now)
        with self._lock:
            for record in reversed(self._load_unlocked()):
                if (
                    record.get("userId") == user_id
                    and record.get("sha256") == image_sha256
                    and record.get("status") in {STATUS_PENDING, STATUS_PASS}
                    and float(record.get("expiresAtEpoch") or 0) > current
                ):
                    return dict(record)
        return None

    def create_pending(
        self,
        user_id: str,
        user_openid: str,
        image_sha256: str,
        image_size: int,
        image_id: str,
        staging_path: str,
        media_url: str,
        purpose: str,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        current = time.time() if now is None else float(now)
        check_id = "safety_" + secrets.token_urlsafe(24)
        record = {
            "securityCheckId": check_id,
            "safeAssetId": check_id,
            "imageId": image_id,
            "userId": user_id,
            "userOpenId": user_openid,
            "sha256": image_sha256,
            "imageBytes": int(image_size),
            "purpose": str(purpose or "image_processing"),
            "mediaUrl": media_url,
            "stagingPath": str(staging_path),
            "status": STATUS_PENDING,
            "traceId": "",
            "createdAt": utc_iso(current),
            "createdAtEpoch": current,
            "updatedAt": utc_iso(current),
            "updatedAtEpoch": current,
            "expiresAtEpoch": current + self.retention_seconds,
        }
        with self._lock:
            records = self._load_unlocked()
            records.append(record)
            self._save_unlocked(records)
        return dict(record)

    def mark_submitted(self, check_id: str, trace_id: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        return self._update_record(check_id, {"traceId": trace_id}, now=now)

    def mark_terminal(self, check_id: str, status: str, reason: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        current = time.time() if now is None else float(now)
        with self._lock:
            records = self._load_unlocked()
            for record in records:
                if record.get("securityCheckId") != check_id:
                    continue
                record.update({
                    "status": status,
                    "statusReason": reason,
                    "updatedAt": utc_iso(current),
                    "updatedAtEpoch": current,
                })
                if status != STATUS_PENDING:
                    self._delete_staging_file(record)
                self._save_unlocked(records)
                return dict(record)
        return None

    def get_owned(self, check_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        self.cleanup()
        with self._lock:
            for record in self._load_unlocked():
                if record.get("securityCheckId") == check_id and record.get("userId") == user_id:
                    return dict(record)
        return None

    def get_by_trace_id(self, trace_id: str) -> Optional[Dict[str, Any]]:
        if not trace_id:
            return None
        with self._lock:
            for record in self._load_unlocked():
                if record.get("traceId") == trace_id:
                    return dict(record)
        return None

    def apply_callback(self, trace_id: str, status: str, reason: str, payload: Dict[str, Any], now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        current = time.time() if now is None else float(now)
        with self._lock:
            records = self._load_unlocked()
            for record in records:
                if record.get("traceId") != trace_id:
                    continue
                if record.get("status") != STATUS_PENDING:
                    return dict(record)
                record.update({
                    "status": status,
                    "statusReason": reason,
                    "callbackReceivedAt": utc_iso(current),
                    "callbackReceivedAtEpoch": current,
                    "updatedAt": utc_iso(current),
                    "updatedAtEpoch": current,
                    "callbackSummary": _safe_callback_summary(payload),
                })
                self._delete_staging_file(record)
                self._save_unlocked(records)
                return dict(record)
        return None

    def public_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "securityCheckId": record.get("securityCheckId"),
            "safeAssetId": record.get("safeAssetId") if record.get("status") == STATUS_PASS else "",
            "status": record.get("status"),
            "createdAt": record.get("createdAt"),
            "updatedAt": record.get("updatedAt"),
        }

    def _update_record(self, check_id: str, changes: Dict[str, Any], now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        current = time.time() if now is None else float(now)
        with self._lock:
            records = self._load_unlocked()
            for record in records:
                if record.get("securityCheckId") != check_id:
                    continue
                record.update(changes)
                record.update({"updatedAt": utc_iso(current), "updatedAtEpoch": current})
                self._save_unlocked(records)
                return dict(record)
        return None

    def _load_unlocked(self) -> list[Dict[str, Any]]:
        if not self.registry_path.exists():
            return []
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload = payload.get("records") or []
            return payload if isinstance(payload, list) else []
        except Exception:
            return []

    def _save_unlocked(self, records: Iterable[Dict[str, Any]]) -> None:
        payload = {"records": list(records)}
        temp_path = self.registry_path.with_suffix(self.registry_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, self.registry_path)

    def _delete_staging_file(self, record: Dict[str, Any]) -> bool:
        path_text = str(record.get("stagingPath") or "")
        if not path_text:
            return False
        try:
            path = Path(path_text).resolve()
            root = self.staging_dir.resolve()
            if root not in path.parents or not path.exists():
                record["stagingPath"] = ""
                return False
            path.unlink()
            record["stagingPath"] = ""
            return True
        except Exception:
            return False


def _safe_callback_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return {
        "event": str(payload.get("Event") or payload.get("event") or ""),
        "statusCode": payload.get("status_code") or payload.get("statusCode") or 0,
        "errcode": payload.get("errcode") or 0,
        "suggest": result.get("suggest") or payload.get("suggest") or "",
        "label": result.get("label") or payload.get("label") or "",
    }
