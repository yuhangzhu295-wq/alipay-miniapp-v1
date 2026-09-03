"""Deterministic verification for the Alipay identity and safety providers.

This test intentionally uses generated credentials and fake upstream objects.
It proves the adapter's fail-closed behavior without making a production
Alipay or Alibaba Cloud request, and prints a machine-readable report.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from services.alipay_auth import (
    AlipayAuthConfigurationError,
    AlipayAuthError,
    AlipayAuthService,
)
from services.alipay_content_safety import (
    AlipayContentSafetyConfigurationError,
    AlipayContentSafetyError,
    AliyunGreenContentSafetyService,
    STATUS_PASS,
    STATUS_REJECT,
)


class _HttpResponse:
    status_code = 200

    def json(self):
        return {
            "alipay_system_oauth_token_response": {
                "user_id": "2088_test_user",
                "access_token": "not-reported",
            }
        }


class _HttpClient:
    def __init__(self):
        self.calls = []

    def post(self, url, data, timeout):
        self.calls.append({"url": url, "data": dict(data), "timeout": timeout})
        return _HttpResponse()


class _GreenClient:
    def __init__(self, risk_level):
        self.risk_level = risk_level
        self.calls = []

    def image_moderation(self, request):
        self.calls.append(request)
        return SimpleNamespace(
            status_code=200,
            body=SimpleNamespace(
                code=200,
                request_id="green_test_request",
                data=SimpleNamespace(
                    risk_level=self.risk_level,
                    result=[SimpleNamespace(label="fixture")],
                ),
            ),
        )


def _expect_error(expected, callback):
    try:
        callback()
    except expected:
        return True
    return False


def _private_key_pem(private_format=serialization.PrivateFormat.PKCS8):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        private_format,
        serialization.NoEncryption(),
    ).decode("utf-8")


def main():
    report = {
        "kind": "deterministic-provider-verification",
        "externalCalls": False,
        "tests": {},
        "pass": False,
    }

    report["tests"]["authMissingConfigurationFailsClosed"] = _expect_error(
        AlipayAuthConfigurationError,
        lambda: AlipayAuthService("", "").exchange_auth_code("test-code"),
    )

    http_client = _HttpClient()
    auth_service = AlipayAuthService(
        app_id="2021000000000000",
        app_private_key=_private_key_pem(),
        http_client=http_client,
    )
    exchange = auth_service.exchange_auth_code("test-code")
    request_data = http_client.calls[0]["data"] if http_client.calls else {}
    report["tests"]["authExchangeRequiresSignedCode"] = bool(
        exchange.get("userId") == "2088_test_user"
        and request_data.get("method") == "alipay.system.oauth.token"
        and request_data.get("grant_type") == "authorization_code"
        and request_data.get("code") == "test-code"
        and request_data.get("sign_type") == "RSA2"
        and request_data.get("sign")
    )
    report["tests"]["authEmptyCodeFailsClosed"] = _expect_error(
        AlipayAuthError,
        lambda: auth_service.exchange_auth_code(""),
    )
    pkcs1_http_client = _HttpClient()
    pkcs1_exchange = AlipayAuthService(
        app_id="2021000000000000",
        app_private_key=_private_key_pem(serialization.PrivateFormat.TraditionalOpenSSL)
            .replace("-----BEGIN RSA PRIVATE KEY-----", "")
            .replace("-----END RSA PRIVATE KEY-----", "")
            .replace("\n", ""),
        http_client=pkcs1_http_client,
    ).exchange_auth_code("test-code-pkcs1")
    report["tests"]["authAcceptsRawPkcs1MerchantKey"] = bool(
        pkcs1_exchange.get("userId") == "2088_test_user" and pkcs1_http_client.calls
    )

    report["tests"]["safetyMissingConfigurationFailsClosed"] = _expect_error(
        AlipayContentSafetyConfigurationError,
        lambda: AliyunGreenContentSafetyService("", "").check_image("https://example.test/image.jpg", "check"),
    )
    report["tests"]["safetyRejectsNonHttpsMedia"] = _expect_error(
        AlipayContentSafetyConfigurationError,
        lambda: AliyunGreenContentSafetyService("id", "secret").check_image("http://example.test/image.jpg", "check"),
    )

    pass_client = _GreenClient("none")
    pass_result = AliyunGreenContentSafetyService("id", "secret", client=pass_client).check_image(
        "https://example.test/image.jpg", "safety-test-pass"
    )
    report["tests"]["safetyExplicitLowRiskPasses"] = (
        pass_result.get("status") == STATUS_PASS and len(pass_client.calls) == 1
    )

    reject_client = _GreenClient("high")
    reject_result = AliyunGreenContentSafetyService("id", "secret", client=reject_client).check_image(
        "https://example.test/image.jpg", "safety-test-reject"
    )
    report["tests"]["safetyHighRiskRejects"] = (
        reject_result.get("status") == STATUS_REJECT and len(reject_client.calls) == 1
    )

    report["tests"]["safetyUnknownResultFailsClosed"] = _expect_error(
        AlipayContentSafetyError,
        lambda: AliyunGreenContentSafetyService("id", "secret", client=_GreenClient("unknown")).check_image(
            "https://example.test/image.jpg", "safety-test-unknown"
        ),
    )

    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    auth_source = (ROOT.parent / "alipay" / "utils" / "authService.js").read_text(encoding="utf-8")
    safety_source = (ROOT.parent / "alipay" / "utils" / "imageSafetyApi.js").read_text(encoding="utf-8")
    report["tests"]["serverRouteAndProviderDispatchPresent"] = all([
        '@app.post("/api/auth/alipay/login")' in main_source,
        'provider == "alipay_user_id"' in main_source,
        'alipay_content_safety_service.check_image' in main_source,
        'CONTENT_SAFETY_PLATFORM_UNSUPPORTED' in main_source,
    ])
    report["tests"]["clientRequiresBoundAlipayIdentity"] = all([
        "/api/auth/alipay/login" in auth_source,
        "identityBound: !!data.identityBound" in auth_source,
        "_ensureSafetyIdentity" in safety_source,
        "auth.identityBound === true" in safety_source,
    ])

    report["pass"] = all(report["tests"].values())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
