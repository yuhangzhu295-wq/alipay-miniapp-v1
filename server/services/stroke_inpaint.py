"""Rebuild watermark masks from compact normalized strokes and process only their ROI."""
from __future__ import annotations

import json
import time
from typing import Any

import cv2
import numpy as np

from services.hd_inpaint import do_hd_inpaint
from services.manual_inpaint import ManualInpaintError, do_manual_inpaint, do_quick_inpaint


MAX_STROKES = 500
MAX_POINTS = 100_000


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalized(value: Any) -> float:
    return max(0.0, min(1.0, _number(value)))


def parse_strokes_payload(strokes_json: str) -> dict[str, Any]:
    if not strokes_json or len(strokes_json.encode("utf-8")) > 2 * 1024 * 1024:
        raise ManualInpaintError("笔迹数据为空或过大，请重新涂抹水印区域")
    try:
        payload = json.loads(strokes_json)
    except json.JSONDecodeError as exc:
        raise ManualInpaintError("笔迹数据格式错误，请重新涂抹水印区域") from exc
    if not isinstance(payload, dict) or payload.get("coordinateSpace") != "normalized":
        raise ManualInpaintError("笔迹坐标格式不受支持，请更新小程序后重试")
    strokes = payload.get("strokes")
    if not isinstance(strokes, list) or not strokes or len(strokes) > MAX_STROKES:
        raise ManualInpaintError("笔迹数量为空或超出限制，请分区域处理")
    return payload


def build_mask_from_strokes(payload: dict[str, Any], image_width: int, image_height: int) -> tuple[np.ndarray, dict[str, Any]]:
    mask = np.zeros((image_height, image_width), dtype=np.uint8)
    point_count = 0
    accepted = 0

    for stroke in payload.get("strokes") or []:
        if not isinstance(stroke, dict):
            continue
        stroke_type = str(stroke.get("type") or "brush")
        if stroke_type == "maskRect":
            x1 = int(round(_normalized(stroke.get("x")) * image_width))
            y1 = int(round(_normalized(stroke.get("y")) * image_height))
            x2 = int(round(_normalized(_number(stroke.get("x")) + _number(stroke.get("w"))) * image_width))
            y2 = int(round(_normalized(_number(stroke.get("y")) + _number(stroke.get("h"))) * image_height))
            x1, x2 = sorted((max(0, min(image_width - 1, x1)), max(0, min(image_width, x2))))
            y1, y2 = sorted((max(0, min(image_height - 1, y1)), max(0, min(image_height, y2))))
            if x2 > x1 and y2 > y1:
                cv2.rectangle(mask, (x1, y1), (x2 - 1, y2 - 1), 255, thickness=-1)
                accepted += 1
            continue

        points = stroke.get("points")
        if not isinstance(points, list) or not points:
            continue
        point_count += len(points)
        if point_count > MAX_POINTS:
            raise ManualInpaintError("笔迹点数超出限制，请分区域处理")
        mapped = [
            (
                int(round(_normalized(point.get("x")) * (image_width - 1))),
                int(round(_normalized(point.get("y")) * (image_height - 1))),
            )
            for point in points
            if isinstance(point, dict)
        ]
        if not mapped:
            continue
        brush_size = max(1, int(round(_number(stroke.get("brushSizeRatio"), 0.01) * image_width)))
        brush_size = min(brush_size, max(8, int(min(image_width, image_height) * 0.25)))
        if len(mapped) == 1:
            cv2.circle(mask, mapped[0], max(1, brush_size // 2), 255, thickness=-1, lineType=cv2.LINE_8)
        else:
            for start, end in zip(mapped, mapped[1:]):
                cv2.line(mask, start, end, 255, thickness=brush_size, lineType=cv2.LINE_8)
            cv2.circle(mask, mapped[0], max(1, brush_size // 2), 255, thickness=-1, lineType=cv2.LINE_8)
            cv2.circle(mask, mapped[-1], max(1, brush_size // 2), 255, thickness=-1, lineType=cv2.LINE_8)
        accepted += 1

    non_zero = int(cv2.countNonZero(mask))
    if accepted <= 0 or non_zero <= 0:
        raise ManualInpaintError("遮罩为空，请重新涂抹水印区域")

    x, y, width, height = cv2.boundingRect(cv2.findNonZero(mask))
    return mask, {
        "strokeCount": accepted,
        "pointCount": point_count,
        "maskNonZeroPixels": non_zero,
        "maskRatio": round(non_zero / float(max(1, image_width * image_height)), 6),
        "maskBoundingBox": {"x": x, "y": y, "width": width, "height": height},
    }


def _encode_png(image: np.ndarray, label: str) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ManualInpaintError(f"{label}编码失败")
    return encoded.tobytes()


def process_stroke_inpaint(
    image_bytes: bytes,
    strokes_json: str,
    quality: str = "quick",
    strength: str = "medium",
    preserve_detail: bool = True,
    request_id: str = "",
    progress_callback=None,
    smart_expand: bool = False,
    mask_dilation_px: int = 5,
) -> dict[str, Any]:
    started = time.perf_counter()
    decode_started = time.perf_counter()
    image_arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(image_arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ManualInpaintError("原图读取失败，请重新上传图片")
    image_height, image_width = image.shape[:2]
    image_decode_ms = int((time.perf_counter() - decode_started) * 1000)

    parse_started = time.perf_counter()
    payload = parse_strokes_payload(strokes_json)
    stroke_parse_ms = int((time.perf_counter() - parse_started) * 1000)
    declared_width = int(_number(payload.get("originalWidth")))
    declared_height = int(_number(payload.get("originalHeight")))
    if declared_width != image_width or declared_height != image_height:
        raise ManualInpaintError(
            f"笔迹原图尺寸 {declared_width}x{declared_height} 与上传图片 {image_width}x{image_height} 不一致"
        )

    mask_started = time.perf_counter()
    mask, mask_debug = build_mask_from_strokes(payload, image_width, image_height)
    mask_build_ms = int((time.perf_counter() - mask_started) * 1000)
    mode = str(quality or "quick").lower()
    if mode in {"hd", "high", "high_quality"}:
        box = mask_debug["maskBoundingBox"]
        base_padding = int(round(min(image_width, image_height) * 0.04))
        stroke_span = max(int(box["width"]), int(box["height"]))
        adaptive_padding = max(base_padding, int(round(stroke_span * 0.08)))
        padding = max(32, min(128, adaptive_padding))
        x1 = max(0, box["x"] - padding)
        y1 = max(0, box["y"] - padding)
        x2 = min(image_width, box["x"] + box["width"] + padding)
        y2 = min(image_height, box["y"] + box["height"] + padding)
        roi_image = image[y1:y2, x1:x2].copy()
        roi_mask = mask[y1:y2, x1:x2].copy()

        border_left = max(0, padding - box["x"])
        border_top = max(0, padding - box["y"])
        border_right = max(0, box["x"] + box["width"] + padding - image_width)
        border_bottom = max(0, box["y"] + box["height"] + padding - image_height)
        if border_left or border_top or border_right or border_bottom:
            roi_image_for_engine = cv2.copyMakeBorder(
                roi_image,
                border_top,
                border_bottom,
                border_left,
                border_right,
                cv2.BORDER_REFLECT_101,
            )
            roi_mask_for_engine = cv2.copyMakeBorder(
                roi_mask,
                border_top,
                border_bottom,
                border_left,
                border_right,
                cv2.BORDER_REFLECT_101,
            )
        else:
            roi_image_for_engine = roi_image
            roi_mask_for_engine = roi_mask

        mask_encode_started = time.perf_counter()
        mask_png = _encode_png(roi_mask_for_engine, "ROI mask")
        mask_encode_ms = int((time.perf_counter() - mask_encode_started) * 1000)
        result = do_hd_inpaint(
            _encode_png(roi_image_for_engine, "ROI image"),
            mask_png,
            strength=strength,
            preserve_detail=preserve_detail,
            request_id=request_id,
            progress_callback=progress_callback,
            smart_expand=smart_expand,
            mask_dilation_px=mask_dilation_px,
        )

        repaired_arr = np.frombuffer(result["bytes"], dtype=np.uint8)
        repaired_roi = cv2.imdecode(repaired_arr, cv2.IMREAD_COLOR)
        if repaired_roi is None:
            raise ManualInpaintError("HD ROI result decode failed")
        if repaired_roi.shape[:2] != roi_image_for_engine.shape[:2]:
            repaired_roi = cv2.resize(
                repaired_roi,
                (roi_image_for_engine.shape[1], roi_image_for_engine.shape[0]),
                interpolation=cv2.INTER_LINEAR,
            )
        repaired_roi = repaired_roi[
            border_top:border_top + roi_image.shape[0],
            border_left:border_left + roi_image.shape[1],
        ]

        dilation_px = max(3, min(12, int(mask_dilation_px or 5)))
        roi_allowed_mask = cv2.dilate(
            roi_mask,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilation_px * 2 + 1, dilation_px * 2 + 1)),
            iterations=1,
        )
        output = image.copy()
        output[y1:y2, x1:x2] = np.where(
            roi_allowed_mask[:, :, None] > 0,
            repaired_roi,
            roi_image,
        )
        allowed_mask = np.zeros_like(mask)
        allowed_mask[y1:y2, x1:x2] = roi_allowed_mask
        unchanged_outside_roi = output.copy()
        unchanged_outside_roi[y1:y2, x1:x2] = image[y1:y2, x1:x2]
        outside_changed = int(np.count_nonzero(np.any(unchanged_outside_roi != image, axis=2)))
        output_bytes = _encode_png(output, "HD ROI output")
        engine_debug = result.get("debug") or {}
        debug = {
            **engine_debug,
            **mask_debug,
            "transport": "normalized_strokes_json",
            "strokesPayloadBytes": len(strokes_json.encode("utf-8")),
            "imageUploadBytes": len(image_bytes),
            "originalSize": f"{image_width}x{image_height}",
            "roiOriginalSize": f"{roi_image_for_engine.shape[1]}x{roi_image_for_engine.shape[0]}",
            "roi": {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1, "padding": padding},
            "roiReflectBorder": {
                "left": border_left,
                "top": border_top,
                "right": border_right,
                "bottom": border_bottom,
            },
            "roiPixelRatio": round(((x2 - x1) * (y2 - y1)) / float(image_width * image_height), 6),
            "outsideRoiChangedPixels": outside_changed,
            "outsideAllowedMaskChangedPixels": int(
                np.count_nonzero(np.any(output[allowed_mask == 0] != image[allowed_mask == 0], axis=1))
            ),
            "maskPolicy": "strict_local",
            "smartExpand": False,
            "maskDilationPx": dilation_px,
            "outputSize": f"{image_width}x{image_height}",
            "outputBytes": len(output_bytes),
            "durationMs": int((time.perf_counter() - started) * 1000),
            "totalDurationMs": int((time.perf_counter() - started) * 1000),
        }
        return {
            "bytes": output_bytes,
            "suffix": ".png",
            "mode": "hd",
            "engine": result.get("engine") or "lama",
            "fallbackUsed": bool(result.get("fallbackUsed")),
            "backendMode": result.get("backendMode") or "hd",
            "message": result.get("message") or "processed",
            "debug": debug,
        }

    box = mask_debug["maskBoundingBox"]
    base_padding = int(round(min(image_width, image_height) * 0.04))
    stroke_span = max(int(box["width"]), int(box["height"]))
    adaptive_padding = max(base_padding, int(round(stroke_span * 0.08)))
    padding = max(32, min(128, adaptive_padding))
    x1 = max(0, box["x"] - padding)
    y1 = max(0, box["y"] - padding)
    x2 = min(image_width, box["x"] + box["width"] + padding)
    y2 = min(image_height, box["y"] + box["height"] + padding)
    roi_image = image[y1:y2, x1:x2].copy()
    roi_mask = mask[y1:y2, x1:x2].copy()

    border_left = max(0, padding - box["x"])
    border_top = max(0, padding - box["y"])
    border_right = max(0, box["x"] + box["width"] + padding - image_width)
    border_bottom = max(0, box["y"] + box["height"] + padding - image_height)
    if border_left or border_top or border_right or border_bottom:
        roi_image_for_engine = cv2.copyMakeBorder(
            roi_image,
            border_top,
            border_bottom,
            border_left,
            border_right,
            cv2.BORDER_REFLECT_101,
        )
        roi_mask_for_engine = cv2.copyMakeBorder(
            roi_mask,
            border_top,
            border_bottom,
            border_left,
            border_right,
            cv2.BORDER_REFLECT_101,
        )
    else:
        roi_image_for_engine = roi_image
        roi_mask_for_engine = roi_mask

    image_png = _encode_png(roi_image_for_engine, "ROI 原图")
    mask_png = _encode_png(roi_mask_for_engine, "ROI 遮罩")
    if mode in {"manual"}:
        result = do_manual_inpaint(image_png, mask_png, strength=strength)
        mode = "manual"
    else:
        result = do_quick_inpaint(image_png, mask_png, strength=strength)
        mode = "quick"

    repaired_arr = np.frombuffer(result["bytes"], dtype=np.uint8)
    repaired_roi = cv2.imdecode(repaired_arr, cv2.IMREAD_COLOR)
    if repaired_roi is None:
        raise ManualInpaintError("修复结果读取失败")
    if repaired_roi.shape[:2] != roi_image_for_engine.shape[:2]:
        repaired_roi = cv2.resize(
            repaired_roi,
            (roi_image_for_engine.shape[1], roi_image_for_engine.shape[0]),
            interpolation=cv2.INTER_LINEAR,
        )
    repaired_roi = repaired_roi[
        border_top:border_top + roi_image.shape[0],
        border_left:border_left + roi_image.shape[1],
    ]

    dilation_px = max(3, min(12, int(mask_dilation_px or 5)))
    roi_allowed_mask = cv2.dilate(
        roi_mask,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilation_px * 2 + 1, dilation_px * 2 + 1)),
        iterations=1,
    )
    output = image.copy()
    output[y1:y2, x1:x2] = np.where(
        roi_allowed_mask[:, :, None] > 0,
        repaired_roi,
        roi_image,
    )
    allowed_mask = np.zeros_like(mask)
    allowed_mask[y1:y2, x1:x2] = roi_allowed_mask
    unchanged_outside_roi = output.copy()
    unchanged_outside_roi[y1:y2, x1:x2] = image[y1:y2, x1:x2]
    outside_changed = int(np.count_nonzero(np.any(unchanged_outside_roi != image, axis=2)))
    output_bytes = _encode_png(output, "修复结果")
    engine_debug = result.get("debug") or {}
    debug = {
        **engine_debug,
        **mask_debug,
        "transport": "normalized_strokes_json",
        "strokesPayloadBytes": len(strokes_json.encode("utf-8")),
        "imageUploadBytes": len(image_bytes),
        "originalSize": f"{image_width}x{image_height}",
        "roiOriginalSize": f"{roi_image_for_engine.shape[1]}x{roi_image_for_engine.shape[0]}",
        "roi": {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1, "padding": padding},
        "roiReflectBorder": {
            "left": border_left,
            "top": border_top,
            "right": border_right,
            "bottom": border_bottom,
        },
        "roiPixelRatio": round(((x2 - x1) * (y2 - y1)) / float(image_width * image_height), 6),
        "outsideRoiChangedPixels": outside_changed,
        "outsideAllowedMaskChangedPixels": int(
            np.count_nonzero(np.any(output[allowed_mask == 0] != image[allowed_mask == 0], axis=1))
        ),
        "maskPolicy": "strict_local",
        "smartExpand": False,
        "maskDilationPx": dilation_px,
        "outputSize": f"{image_width}x{image_height}",
        "outputBytes": len(output_bytes),
        "durationMs": int((time.perf_counter() - started) * 1000),
        "totalDurationMs": int((time.perf_counter() - started) * 1000),
    }
    return {
        "bytes": output_bytes,
        "suffix": ".png",
        "mode": mode,
        "engine": result.get("engine") or ("lama" if mode == "hd" else f"opencv_{mode}"),
        "fallbackUsed": bool(result.get("fallbackUsed")),
        "backendMode": result.get("backendMode") or mode,
        "message": result.get("message") or "处理成功",
        "debug": debug,
    }
