"""Server-side Alipay Mini Program identity exchange.

The client only forwards the one-time code returned by ``my.getAuthCode``.
This module keeps the application private key exclusively on the server and
returns a stable Alipay user identifier only after the official OpenAPI
exchange succeeds.
"""
from __future__ import annotations

import base64
import datetime as dt
import os
from typing import Any, Dict

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class AlipayAuthError(RuntimeError):
    """An Alipay authorization code could not be trusted."""


class AlipayAuthConfigurationError(AlipayAuthError):
    """Required server-only Alipay authorization settings are missing."""


def _private_key_candidates(value: str) -> list[bytes]:
    value = str(value or "").strip().replace("\\n", "\n")
    if not value:
        return []
    if "-----BEGIN" in value:
        return [value.encode("utf-8")]
    # Alipay consoles commonly expose raw Base64 text. Support the two PEM
    # encodings used by RSA merchant keys without recording the key itself.
    return [
        ("-----BEGIN PRIVATE KEY-----\n" + value + "\n-----END PRIVATE KEY-----\n").encode("utf-8"),
        ("-----BEGIN RSA PRIVATE KEY-----\n" + value + "\n-----END RSA PRIVATE KEY-----\n").encode("utf-8"),
    ]


class AlipayAuthService:
    GATEWAY_URL = "https://openapi.alipay.com/gateway.do"

    def __init__(
        self,
        app_id: str,
        app_private_key: str,
        gateway_url: str = "",
        request_timeout_seconds: float = 10.0,
        http_client: Any = None,
    ) -> None:
        self.app_id = str(app_id or "").strip()
        self.app_private_key = str(app_private_key or "").strip()
        self.gateway_url = str(gateway_url or self.GATEWAY_URL).strip()
        self.request_timeout_seconds = float(request_timeout_seconds)
        self.http_client = http_client or requests

    @classmethod
    def from_env(cls) -> "AlipayAuthService":
        app_id = (os.environ.get("ALIPAY_APP_ID") or "").strip()
        app_private_key = (
            os.environ.get("ALIPAY_APP_PRIVATE_KEY")
            or os.environ.get("ALIPAY_PRIVATE_KEY")
            or ""
        ).strip()
        print(
            "[alipay-config] "
            f"alipayAppIdConfigured={str(bool(app_id)).lower()} "
            f"alipayPrivateKeyConfigured={str(bool(app_private_key)).lower()}",
            flush=True,
        )
        return cls(
            app_id=app_id,
            app_private_key=app_private_key,
            gateway_url=os.environ.get("ALIPAY_GATEWAY_URL") or cls.GATEWAY_URL,
            request_timeout_seconds=float(os.environ.get("ALIPAY_AUTH_TIMEOUT_SECONDS", "10") or 10),
        )

    def configuration_errors(self) -> list[str]:
        errors = []
        if not self.app_id:
            errors.append("ALIPAY_APP_ID")
        if not self.app_private_key:
            errors.append("ALIPAY_APP_PRIVATE_KEY")
        return errors

    def ensure_configured(self) -> None:
        missing = self.configuration_errors()
        if missing:
            raise AlipayAuthConfigurationError(
                "Missing server-only Alipay authorization configuration: " + ", ".join(missing)
            )

    def _sign(self, parameters: Dict[str, str]) -> str:
        try:
            private_key = None
            for candidate in _private_key_candidates(self.app_private_key):
                try:
                    private_key = serialization.load_pem_private_key(candidate, password=None)
                    break
                except Exception:
                    continue
            if private_key is None:
                raise ValueError("unsupported key encoding")
            content = "&".join(
                f"{key}={parameters[key]}"
                for key in sorted(parameters)
                if key != "sign" and parameters[key] is not None
            ).encode("utf-8")
            signature = private_key.sign(content, padding.PKCS1v15(), hashes.SHA256())
            return base64.b64encode(signature).decode("ascii")
        except Exception as exc:
            raise AlipayAuthConfigurationError("Invalid ALIPAY_APP_PRIVATE_KEY") from exc

    def exchange_auth_code(self, auth_code: str) -> Dict[str, str]:
        self.ensure_configured()
        auth_code = str(auth_code or "").strip()
        if not auth_code:
            raise AlipayAuthError("Alipay auth code is required")
        timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parameters = {
            "app_id": self.app_id,
            "method": "alipay.system.oauth.token",
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": timestamp,
            "version": "1.0",
            "grant_type": "authorization_code",
            "code": auth_code,
        }
        parameters["sign"] = self._sign(parameters)
        try:
            response = self.http_client.post(
                self.gateway_url,
                data=parameters,
                timeout=self.request_timeout_seconds,
            )
            payload = response.json() if getattr(response, "status_code", 0) == 200 else {}
        except Exception as exc:
            raise AlipayAuthError("Alipay authorization exchange request failed") from exc

        result = payload.get("alipay_system_oauth_token_response") if isinstance(payload, dict) else None
        user_id = str((result or {}).get("user_id") or "").strip()
        if not user_id:
            raise AlipayAuthError("Alipay authorization exchange did not return a user identifier")
        return {"userId": user_id, "accessToken": str((result or {}).get("access_token") or "")}
