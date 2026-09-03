"""Deterministic HD-watermark ROI, call-count, and frontend contract checks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np


SERVER_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SERVER_ROOT.parent
REPORT_DIR = PROJECT_ROOT / "reports" / "watermark-hd-speed"
sys.path.insert(0, str(SERVER_ROOT))

import services.hd_inpaint as hd_inpaint


def _encode(image):
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise AssertionError("fixture encoding failed")
    return encoded.tobytes()


def _fake_single(calls):
    def run(image_bytes, mask_bytes, **kwargs):
        image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        mask = cv2.imdecode(np.frombuffer(mask_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
        calls.append({"size": f"{image.shape[1]}x{image.shape[0]}", "kwargs": kwargs})
        output = image.copy()
        output[mask > 0] = (17, 31, 47)
        return {
            "bytes": _encode(output),
            "suffix": ".png",
            "backendMode": "LaMa/IOPaint 高清修复",
            "mode": "hd",
            "engine": "lama",
            "fallbackUsed": False,
            "message": "ok",
            "debug": {
                "engine": "lama",
                "lamaCallCount": 1,
                "firstLamaMs": 7,
                "retryLamaMs": 0,
                "lamaMs": 7,
                "lamaInferenceMs": 5,
                "iopaintConnectMs": 0,
                "iopaintRequestEncodeMs": 1,
                "iopaintHttpMs": 6,
                "iopaintResponseDecodeMs": 0,
                "iopaintOutputEncodeMs": 1,
                "iopaintTotalMs": 6,
                "roiOriginalSize": f"{image.shape[1]}x{image.shape[0]}",
                "roiInferenceSize": f"{image.shape[1]}x{image.shape[0]}",
                "roiScale": 1.0,
                "modelLoaded": True,
                "modelWarm": True,
                "processUptimeSeconds": 100,
                "modelLoadMs": 0,
                "torchThreads": 4,
                "interopThreads": 1,
                "retryReason": "",
            },
        }

    return run


def _mask(width, height, boxes):
    result = np.zeros((height, width), dtype=np.uint8)
    for x, y, box_width, box_height in boxes:
        cv2.rectangle(result, (x, y), (x + box_width - 1, y + box_height - 1), 255, thickness=-1)
    return result


def _run_case(name, boxes, expected_rois, expect_capped=False):
    width, height = 1200, 800
    image = np.full((height, width, 3), 212, dtype=np.uint8)
    cv2.line(image, (0, height // 2), (width - 1, height // 2), (80, 80, 80), 2)
    cv2.putText(image, "INVOICE 2026", (80, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (45, 45, 45), 2)
    mask = _mask(width, height, boxes)
    calls = []
    original_single = hd_inpaint._do_hd_inpaint_single
    hd_inpaint._do_hd_inpaint_single = _fake_single(calls)
    try:
        result = hd_inpaint.do_hd_inpaint(_encode(image), _encode(mask), request_id=f"unit-{name}")
    finally:
        hd_inpaint._do_hd_inpaint_single = original_single
    output = cv2.imdecode(np.frombuffer(result["bytes"], np.uint8), cv2.IMREAD_COLOR)
    debug = result["debug"]
    checks = {
        "roiCount": debug["mergedRoiCount"] == expected_rois,
        "callCountBounded": debug["lamaCallCount"] <= 2 and len(calls) <= 2,
        "outputSizePreserved": output.shape == image.shape,
        "outsideRoiUnchanged": debug["outsideRoiChangedPixels"] == 0,
        "realEngineContract": result["engine"] == "lama" and result["fallbackUsed"] is False,
        "cappedAsExpected": bool(debug["roiGroupingCapped"]) is expect_capped,
    }
    return {
        "name": name,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "componentCount": debug["componentCount"],
        "mergedRoiCount": debug["mergedRoiCount"],
        "roiBoxes": debug["eachRoiBox"],
        "roiPaddings": debug["eachRoiPadding"],
        "callSizes": [item["size"] for item in calls],
        "lamaCallCount": debug["lamaCallCount"],
    }


def main():
    cases = [
        _run_case("single-small", [(520, 360, 90, 45)], 1),
        _run_case("two-near", [(420, 330, 70, 45), (505, 335, 70, 45)], 1),
        _run_case("two-far", [(70, 80, 70, 45), (1040, 680, 80, 50)], 2),
        _run_case("top-bottom", [(520, 15, 80, 40), (520, 745, 80, 40)], 2),
        _run_case("many-small", [(50, 60, 40, 30), (250, 180, 40, 30), (470, 300, 40, 30), (700, 430, 40, 30), (1040, 690, 40, 30)], 2, True),
        _run_case("one-large", [(220, 180, 760, 430)], 1),
    ]
    api_source = (PROJECT_ROOT / "utils" / "watermarkApi.js").read_text(encoding="utf-8")
    page_source = (PROJECT_ROOT / "pages" / "tool-detail" / "tool-detail.js").read_text(encoding="utf-8")
    main_source = (SERVER_ROOT / "main.py").read_text(encoding="utf-8")
    static_checks = {
        "normalizedStrokeTransportRetained": "strokesJson" in api_source and "maskBase64" not in api_source,
        "realStageLabelsPresent": all(label in api_source for label in (
            "正在上传图片", "正在分析涂抹区域", "正在进行高清修复", "正在合成处理结果", "正在加载预览"
        )),
        "elapsedWithoutFakePercent": "已等待" in api_source and "fakePercent" not in api_source,
        "duplicateHdSubmissionGuard": "activeHdRequests" in api_source and "HD_REQUEST_ACTIVE" in main_source,
        "progressEndpointPresent": "/api/watermark/hd-progress/{request_id}" in main_source,
        "pageReceivesHdStatus": "onStatus: quality === 'hd'" in page_source,
        "quickQualityMappingUnchanged": "params.quality === 'manual' ? 'manual' : 'quick'" in api_source,
    }
    payload = {
        "status": "PASS" if all(item["status"] == "PASS" for item in cases) and all(static_checks.values()) else "FAIL",
        "cases": cases,
        "staticChecks": static_checks,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "roi-components-unit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 高清 ROI 单元验证", "", f"- 状态：{payload['status']}", ""]
    for case in cases:
        lines.append(
            f"- {case['name']}: {case['status']}; components={case['componentCount']}; "
            f"rois={case['mergedRoiCount']}; calls={case['lamaCallCount']}; sizes={case['callSizes']}"
        )
    lines.extend(["", "## 静态契约"] + [f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in static_checks.items()])
    (REPORT_DIR / "roi-components-unit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
