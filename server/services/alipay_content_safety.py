"""Alibaba Cloud image moderation provider for Alipay Mini Program uploads.

This provider is deliberately fail-closed: an unknown upstream result,
credential issue, or transport issue never turns into a local PASS.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict
from types import SimpleNamespace


STATUS_PASS = "PASS"
STATUS_REJECT = "REJECT"


class AlipayContentSafetyError(RuntimeError):
    """Alibaba Cloud moderation could not supply a trusted decision."""


class AlipayContentSafetyConfigurationError(AlipayContentSafetyError):
    """Server-only Alibaba Cloud moderation configuration is incomplete."""


class AliyunGreenContentSafetyService:
    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        region_id: str = "cn-shanghai",
        endpoint: str = "green-cip.cn-shanghai.aliyuncs.com",
        service: str = "baselineCheck",
        client: Any = None,
    ) -> None:
        self.access_key_id = str(access_key_id or "").strip()
        self.access_key_secret = str(access_key_secret or "").strip()
        self.region_id = str(region_id or "cn-shanghai").strip()
        self.endpoint = str(endpoint or "green-cip.cn-shanghai.aliyuncs.com").strip()
        self.service = str(service or "baselineCheck").strip()
        self.client = client

    @classmethod
    def from_env(cls) -> "AliyunGreenContentSafetyService":
        access_key_id = (
            os.environ.get("ALIYUN_GREEN_ACCESS_KEY_ID")
            or os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID")
            or ""
        ).strip()
        access_key_secret = (
            os.environ.get("ALIYUN_GREEN_ACCESS_KEY_SECRET")
            or os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
            or ""
        ).strip()
        print(
            "[alipay-content-safety-config] "
            f"accessKeyIdConfigured={str(bool(access_key_id)).lower()} "
            f"accessKeySecretConfigured={str(bool(access_key_secret)).lower()}",
            flush=True,
        )
        return cls(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region_id=os.environ.get("ALIYUN_GREEN_REGION_ID") or "cn-shanghai",
            endpoint=os.environ.get("ALIYUN_GREEN_ENDPOINT") or "green-cip.cn-shanghai.aliyuncs.com",
            service=os.environ.get("ALIYUN_GREEN_IMAGE_SERVICE") or "baselineCheck",
        )

    def configuration_errors(self) -> list[str]:
        errors = []
        if not self.access_key_id:
            errors.append("ALIYUN_GREEN_ACCESS_KEY_ID")
        if not self.access_key_secret:
            errors.append("ALIYUN_GREEN_ACCESS_KEY_SECRET")
        return errors

    def ensure_configured(self) -> None:
        missing = self.configuration_errors()
        if missing:
            raise AlipayContentSafetyConfigurationError(
                "Missing server-only Alibaba Cloud moderation configuration: " + ", ".join(missing)
            )

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        try:
            from alibabacloud_green20220302.client import Client
            from alibabacloud_tea_openapi.models import Config
        except Exception as exc:
            raise AlipayContentSafetyConfigurationError(
                "alibabacloud-green20220302 dependency is unavailable"
            ) from exc
        return Client(Config(
            access_key_id=self.access_key_id,
            access_key_secret=self.access_key_secret,
            region_id=self.region_id,
            endpoint=self.endpoint,
            connect_timeout=10000,
            read_timeout=6000,
        ))

    @staticmethod
    def _value(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    def check_image(self, media_url: str, data_id: str) -> Dict[str, Any]:
        self.ensure_configured()
        if not str(media_url or "").startswith("https://"):
            raise AlipayContentSafetyConfigurationError("media_url must use a public HTTPS URL")
        try:
            request_payload = {
                "service": self.service,
                "service_parameters": json.dumps({"imageUrl": media_url, "dataId": data_id}),
            }
            if self.client is None:
                from alibabacloud_green20220302 import models
                request = models.ImageModerationRequest(**request_payload)
            else:
                # Tests may inject a client without installing the production SDK.
                request = SimpleNamespace(**request_payload)
            response = self._client().image_moderation(request)
        except AlipayContentSafetyError:
            raise
        except Exception as exc:
            raise AlipayContentSafetyError("Alibaba Cloud image moderation request failed") from exc

        if int(self._value(response, "status_code", 0) or 0) != 200:
            raise AlipayContentSafetyError("Alibaba Cloud image moderation returned a non-200 response")
        body = self._value(response, "body", {})
        if int(self._value(body, "code", 0) or 0) != 200:
            raise AlipayContentSafetyError("Alibaba Cloud image moderation rejected the request")
        data = self._value(body, "data", {})
        risk_level = str(self._value(data, "risk_level", "")).strip().lower()
        results = self._value(data, "result", []) or []
        labels = [str(self._value(item, "label", "")).strip() for item in results]
        request_id = str(self._value(body, "request_id", "")).strip()
        if risk_level == "none":
            return {"traceId": request_id or data_id, "status": STATUS_PASS, "reason": "PASS", "labels": labels}
        if risk_level in {"low", "medium", "high"}:
            return {"traceId": request_id or data_id, "status": STATUS_REJECT, "reason": risk_level.upper(), "labels": labels}
        raise AlipayContentSafetyError("Alibaba Cloud image moderation returned an unknown risk level")
