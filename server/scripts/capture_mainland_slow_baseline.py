from __future__ import annotations

import json
import time
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "mainland-fast-repair"
SOURCE = ROOT / "reports" / "20260804-performance" / "S01-reconstructed-source.jpg"
BASE_URL = "https://tupzjianzhao.chat"


def write(rows):
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "baselineSha": "35dc6d7754eec5fc69337367bbd30ed5052238fb",
        "baseUrl": BASE_URL,
        "hairRetouch": False,
        "rows": rows,
    }
    (OUT / "slow-request-root-cause.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8"
    )


def flatten(width, response, elapsed_ms):
    data = response.json()
    quality = data.get("quality") or {}
    probe = quality.get("fastQualityProbe") or {}
    fast_ms = int(quality.get("fastDurationMs") or 0)
    detail_ms = int(quality.get("detailDurationMs") or 0)
    return {
        "requestId": data.get("requestId"),
        "specId": "one-inch",
        "controlledOutputSize": f"{width}x413",
        "requestedModel": "hivision_modnet",
        "fastModel": quality.get("fastModel"),
        "fastDurationMs": fast_ms,
        "fastQualityReport": probe,
        "rawFailReasons": probe.get("rawFailReasons") or [],
        "cropFailReasons": [
            code
            for code in (probe.get("rawFailReasons") or [])
            if code.startswith("ID_PHOTO_HEAD_")
            or code.startswith("ID_PHOTO_TOP_")
            or code.startswith("ID_PHOTO_BOTTOM_")
            or code.startswith("ID_PHOTO_SHOULDER_")
            or code in {"ID_PHOTO_FACE_NOT_CENTERED", "ID_PHOTO_BODY_TOO_MUCH"}
        ],
        "mattingFailReasons": [],
        "detailFallbackUsed": bool(quality.get("detailFallbackUsed")),
        "detailFallbackReasons": quality.get("fastFailReasons") or [],
        "detailDurationMs": detail_ms,
        "finalSelectedModel": quality.get("finalSelectedModel") or data.get("engineModel"),
        "totalServerMs": fast_ms + detail_ms,
        "totalServerMsBasis": "known matting stages; face/IO excluded",
        "totalClientMs": elapsed_ms,
        "statusCode": response.status_code,
        "success": bool(data.get("success")),
    }


def main():
    rows = [
        {
            "requestId": "ca2729a12a",
            "specId": "one-inch",
            "controlledOutputSize": "800x413",
            "requestedModel": "hivision_modnet",
            "fastModel": "hivision_modnet",
            "fastDurationMs": 1671,
            "fastQualityReport": {
                "rawFailReasons": [
                    "ID_PHOTO_HEAD_WIDTH_BAD",
                    "ID_PHOTO_SHOULDER_WIDTH_BAD",
                    "ID_PHOTO_SHOULDER_TOO_NARROW",
                ]
            },
            "rawFailReasons": [
                "ID_PHOTO_HEAD_WIDTH_BAD",
                "ID_PHOTO_SHOULDER_WIDTH_BAD",
                "ID_PHOTO_SHOULDER_TOO_NARROW",
            ],
            "cropFailReasons": [
                "ID_PHOTO_HEAD_WIDTH_BAD",
                "ID_PHOTO_SHOULDER_WIDTH_BAD",
                "ID_PHOTO_SHOULDER_TOO_NARROW",
            ],
            "mattingFailReasons": [],
            "detailFallbackUsed": True,
            "detailFallbackReasons": ["shoulderAlphaMissing"],
            "detailDurationMs": 158404,
            "finalSelectedModel": "birefnet-v1-lite",
            "totalServerMs": 160075,
            "totalServerMsBasis": "known matting stages; face/IO excluded",
            "totalClientMs": 162087,
            "statusCode": 200,
            "success": True,
        }
    ]
    write(rows)
    for width in (850, 900, 950, 1000):
        form = {
            "purpose": "official_id_photo",
            "specId": "one-inch",
            "widthPx": str(width),
            "heightPx": "413",
            "mode": "official",
            "composition": "head_shoulder",
            "outfit": "preserve_original",
            "hairRetouch": "false",
        }
        started = time.perf_counter()
        with SOURCE.open("rb") as handle:
            response = requests.post(
                BASE_URL + "/api/id-photo/prepare",
                files={"image": (SOURCE.name, handle, "image/jpeg")},
                data=form,
                timeout=240,
            )
        rows.append(flatten(width, response, int((time.perf_counter() - started) * 1000)))
        write(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
