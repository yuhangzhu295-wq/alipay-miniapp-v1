"""高清去水印修复服务。

通过 IOPaint / LaMa 本地服务处理原图 + 黑白 mask，并只把 mask 区域合成回原图。
"""
import os
import time
import base64
import json
import threading

import cv2
import numpy as np

from services.manual_inpaint import _decode_image, _diff_debug, _mask_to_binary


_IOPAINT_SESSION = None
_IOPAINT_SESSION_LOCK = threading.Lock()
_IOPAINT_HEALTH_LOCK = threading.Lock()
_IOPAINT_HEALTH_CACHE = {"checkedAt": 0.0, "available": False, "model": ""}
_IOPAINT_RUNTIME_PATH = os.environ.get("IOPAINT_RUNTIME_PATH", "/run/iopaint-lama-runtime.json")
_IOPAINT_WARM_PATH = os.environ.get("IOPAINT_WARM_PATH", "/run/iopaint-lama-warm.json")


class HdInpaintError(ValueError):
    def __init__(self, message, debug=None, status_code=500, fallback_available=True):
        super().__init__(message)
        self.debug = debug or {}
        self.status_code = status_code
        self.fallback_available = fallback_available


def _env_enabled(name, default=True):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def get_hd_config():
    return {
        "enabled": _env_enabled("ENABLE_HD_REPAIR", True),
        "engine": os.environ.get("HD_REPAIR_ENGINE", "lama"),
        "url": os.environ.get("IOPAINT_URL", "http://127.0.0.1:8081").rstrip("/"),
    }


def _get_iopaint_session():
    global _IOPAINT_SESSION
    if _IOPAINT_SESSION is not None:
        return _IOPAINT_SESSION
    with _IOPAINT_SESSION_LOCK:
        if _IOPAINT_SESSION is None:
            import requests

            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=0)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            _IOPAINT_SESSION = session
    return _IOPAINT_SESSION


def _read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _process_uptime_seconds(pid):
    try:
        with open(f"/proc/{int(pid)}/stat", "r", encoding="utf-8") as handle:
            start_ticks = int(handle.read().split()[21])
        with open("/proc/uptime", "r", encoding="utf-8") as handle:
            system_uptime = float(handle.read().split()[0])
        return max(0, int(system_uptime - (start_ticks / float(os.sysconf("SC_CLK_TCK")))))
    except Exception:
        return 0


def _iopaint_runtime_status(available):
    runtime = _read_json_file(_IOPAINT_RUNTIME_PATH)
    warm = _read_json_file(_IOPAINT_WARM_PATH)
    pid = int(runtime.get("pid") or warm.get("pid") or 0)
    uptime = _process_uptime_seconds(pid) if pid else 0
    warm_matches = bool(pid and int(warm.get("pid") or 0) == pid and warm.get("modelWarm") is True)
    model_warm = bool(available and (warm_matches or uptime >= 60))
    return {
        "modelLoaded": bool(available),
        "modelWarm": model_warm,
        "processPid": pid,
        "processUptimeSeconds": uptime,
        "lastWarmupMs": int(warm.get("lastWarmupMs") or 0) if warm_matches else 0,
        "modelLoadMs": int(runtime.get("modelLoadMs") or 0),
        "torchThreads": int(runtime.get("torchThreads") or 0),
        "interopThreads": int(runtime.get("interopThreads") or 0),
    }


def check_hd_available(timeout=1.5, force=False):
    config = get_hd_config()
    if not config["enabled"]:
        return False
    if not config["url"]:
        return False
    now = time.monotonic()
    with _IOPAINT_HEALTH_LOCK:
        if not force and now - float(_IOPAINT_HEALTH_CACHE["checkedAt"]) <= 2.0:
            return bool(_IOPAINT_HEALTH_CACHE["available"])
    try:
        session = _get_iopaint_session()
        response = session.get(config["url"] + "/api/v1/model", timeout=timeout)
        if response.status_code == 200:
            model = response.json()
            name = str(model.get("name", "")).lower()
            available = (not config["engine"]) or config["engine"].lower() in name or bool(name)
            with _IOPAINT_HEALTH_LOCK:
                _IOPAINT_HEALTH_CACHE.update({"checkedAt": now, "available": available, "model": name})
            return available

        legacy_response = session.get(config["url"] + "/inpaint", timeout=timeout)
        available = legacy_response.status_code in (200, 204, 405)
        with _IOPAINT_HEALTH_LOCK:
            _IOPAINT_HEALTH_CACHE.update({"checkedAt": now, "available": available, "model": "legacy"})
        return available
    except Exception:
        with _IOPAINT_HEALTH_LOCK:
            _IOPAINT_HEALTH_CACHE.update({"checkedAt": now, "available": False, "model": ""})
        return False


def get_hd_status():
    config = get_hd_config()
    iopaint_available = check_hd_available()
    available = bool(config["enabled"] and iopaint_available)
    engine = config["engine"] if available else "not_ready"
    runtime = _iopaint_runtime_status(available)
    return {
        "enabled": config["enabled"],
        "engine": engine,
        "url": config["url"],
        "available": available,
        "iopaintAvailable": iopaint_available,
        "hdRealModelLoaded": iopaint_available,
        "fallbackUsed": False,
        "fallbackAvailable": True,
        "fallbackEngine": "opencv_hd_fallback",
        **runtime,
    }


def _resolve_hd_strength(strength):
    value = str(strength or "medium").lower()
    if value in ("low", "轻度", "2"):
        return 0, False, "low"
    if value in ("high", "强力", "5"):
        return 1, True, "high"
    return 1, False, "medium"


def _encode_png(image):
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise HdInpaintError("高清修复输入编码失败", status_code=500)
    return encoded.tobytes()


def _call_iopaint(image, mask_bin, feather=False, timeout=180, request_id=""):
    config = get_hd_config()
    connect_started = time.perf_counter()
    if not check_hd_available():
        raise HdInpaintError(
            "高清修复服务暂不可用，请使用快速模式或稍后重试",
            debug={"engine": config["engine"], "hdAvailable": False},
            status_code=503,
        )

    connect_ms = int((time.perf_counter() - connect_started) * 1000)
    try:
        import requests
        session = _get_iopaint_session()
    except Exception as exc:
        raise HdInpaintError(
            "高清修复服务暂不可用，请使用快速模式或稍后重试",
            debug={"engine": config["engine"], "error": str(exc)},
            status_code=503,
        )

    encode_started = time.perf_counter()
    image_png = _encode_png(image)
    mask_png = _encode_png(mask_bin)

    try:
        payload = {
            "image": base64.b64encode(image_png).decode("utf-8"),
            "mask": base64.b64encode(mask_png).decode("utf-8"),
            "hd_strategy": "CROP",
            "hd_strategy_crop_margin": 96,
            "hd_strategy_crop_trigger_size": 800,
            "sd_keep_unmasked_area": True,
            "sd_mask_blur": 5 if feather else 3,
            "sd_strength": 0.85,
            "prompt": str(request_id or ""),
            "negative_prompt": "",
        }
        request_encode_ms = int((time.perf_counter() - encode_started) * 1000)
        http_started = time.perf_counter()
        response = session.post(
            config["url"] + "/api/v1/inpaint",
            json=payload,
            timeout=timeout,
            headers={"X-Request-ID": str(request_id or "")},
        )
        http_ms = int((time.perf_counter() - http_started) * 1000)

        if response.status_code in (404, 405):
            files = {
                "image": ("image.png", image_png, "image/png"),
                "mask": ("mask.png", mask_png, "image/png"),
            }
            data = {
                "model": config["engine"],
                "sizeLimit": "0",
            }
            http_started = time.perf_counter()
            response = session.post(config["url"] + "/inpaint", files=files, data=data, timeout=timeout)
            http_ms = int((time.perf_counter() - http_started) * 1000)
    except requests.exceptions.Timeout as exc:
        raise HdInpaintError(
            "高清修复耗时较长，请稍后重试或切换快速模式",
            debug={"engine": config["engine"], "error": str(exc)},
            status_code=504,
        )
    except Exception as exc:
        raise HdInpaintError(
            "高清修复服务暂不可用，请使用快速模式或稍后重试",
            debug={"engine": config["engine"], "error": str(exc)},
            status_code=503,
        )

    if response.status_code != 200:
        raise HdInpaintError(
            "高清修复模型未就绪，请检查本地高清修复服务",
            debug={
                "engine": config["engine"],
                "statusCode": response.status_code,
                "response": response.text[:300],
            },
            status_code=503,
        )

    decode_started = time.perf_counter()
    result_arr = np.frombuffer(response.content, dtype=np.uint8)
    result = cv2.imdecode(result_arr, cv2.IMREAD_COLOR)
    response_decode_ms = int((time.perf_counter() - decode_started) * 1000)
    if result is None:
        raise HdInpaintError(
            "高清修复模型未返回有效图片",
            debug={"engine": config["engine"], "response": response.text[:300]},
            status_code=502,
        )
    runtime = _iopaint_runtime_status(True)

    def _header_int(name, default=0):
        try:
            return int(round(float(response.headers.get(name, default))))
        except (TypeError, ValueError):
            return int(default)

    inference_ms = _header_int("X-IOPaint-Inference-Ms", http_ms)
    output_encode_ms = _header_int("X-IOPaint-Output-Encode-Ms", 0)
    iopaint_total_ms = _header_int("X-IOPaint-Total-Ms", http_ms)
    return result, {
        "iopaintConnectMs": connect_ms,
        "iopaintRequestEncodeMs": request_encode_ms,
        "iopaintHttpMs": http_ms,
        "iopaintResponseDecodeMs": response_decode_ms,
        "lamaInferenceMs": inference_ms,
        "iopaintOutputEncodeMs": output_encode_ms,
        "iopaintTotalMs": iopaint_total_ms,
        "iopaintRequestBytes": len(image_png) + len(mask_png),
        "iopaintResponseBytes": len(response.content),
        "modelLoaded": runtime["modelLoaded"],
        "modelWarm": runtime["modelWarm"],
        "processUptimeSeconds": runtime["processUptimeSeconds"],
        "modelLoadMs": 0 if runtime["modelWarm"] else runtime["modelLoadMs"],
        "torchThreads": _header_int("X-IOPaint-Torch-Threads", runtime["torchThreads"]),
        "interopThreads": _header_int("X-IOPaint-Interop-Threads", runtime["interopThreads"]),
    }


def _call_iopaint_scaled(
    image,
    mask_bin,
    feather=False,
    timeout=180,
    request_id="",
    inference_max_edge=None,
):
    original_h, original_w = image.shape[:2]
    configured_max = max(768, min(1536, int(os.environ.get("HD_INPAINT_MAX_EDGE", "1536"))))
    max_edge = max(768, min(configured_max, int(inference_max_edge or configured_max)))
    scale = min(1.0, max_edge / float(max(original_w, original_h)))
    if scale < 1.0:
        inference_size = (
            max(1, int(round(original_w * scale))),
            max(1, int(round(original_h * scale))),
        )
        inference_image = cv2.resize(image, inference_size, interpolation=cv2.INTER_AREA)
        inference_mask = cv2.resize(mask_bin, inference_size, interpolation=cv2.INTER_NEAREST)
    else:
        inference_size = (original_w, original_h)
        inference_image = image
        inference_mask = mask_bin
    started = time.perf_counter()
    repaired, transport_debug = _call_iopaint(
        inference_image,
        inference_mask,
        feather=feather,
        timeout=timeout,
        request_id=request_id,
    )
    call_ms = int((time.perf_counter() - started) * 1000)
    if repaired.shape[:2] != (original_h, original_w):
        repaired = cv2.resize(repaired, (original_w, original_h), interpolation=cv2.INTER_LANCZOS4)
    return repaired, {
        **transport_debug,
        "roiOriginalSize": f"{original_w}x{original_h}",
        "roiInferenceSize": f"{inference_size[0]}x{inference_size[1]}",
        "roiScale": round(scale, 6),
        "lamaMs": call_ms,
        "inferenceMaxEdge": max_edge,
    }


def _odd_kernel(value, minimum=3, maximum=31):
    value = max(minimum, min(maximum, int(value)))
    return value if value % 2 == 1 else value + 1


def _diagonal_projection_period(signal, index_map, vector_length, min_dim):
    sums = np.bincount(index_map.ravel(), weights=signal.ravel(), minlength=vector_length)
    counts = np.bincount(index_map.ravel(), minlength=vector_length)
    projection = sums / np.maximum(counts, 1)
    projection = cv2.GaussianBlur(projection.reshape(1, -1).astype(np.float32), (0, 0), 2.0).ravel()
    projection = np.maximum(projection - np.percentile(projection, 35), 0)

    min_period = max(54, int(min_dim * 0.10))
    max_period = min(320, int(min_dim * 0.48), max(min_period + 1, vector_length // 2))
    best_period = 0
    best_score = 0.0
    norm = float(np.linalg.norm(projection))
    if norm <= 1e-6:
        return {"period": 0, "offset": 0, "score": 0.0}

    for period in range(min_period, max_period + 1):
        left = projection[:-period]
        right = projection[period:]
        denom = float(np.linalg.norm(left) * np.linalg.norm(right))
        if denom <= 1e-6:
            continue
        score = float(np.dot(left, right) / denom)
        if score > best_score:
            best_score = score
            best_period = period

    if best_period <= 0:
        return {"period": 0, "offset": 0, "score": 0.0}

    offset_scores = np.zeros(best_period, dtype=np.float32)
    for offset in range(best_period):
        offset_scores[offset] = float(np.sum(projection[offset::best_period]))
    return {
        "period": int(best_period),
        "offset": int(np.argmax(offset_scores)),
        "score": round(best_score, 6),
    }


def _detect_repeating_diagonal_grid_mask(image):
    """Detect a repeated diamond watermark without hard-coding one sample.

    Repeated diagonal watermarks produce two strong periodic projections
    (x+y and x-y). Requiring both families prevents ordinary scene edges from
    being mistaken for a tiled watermark.
    """
    image_h, image_w = image.shape[:2]
    min_dim = max(1, min(image_w, image_h))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    local_bg = cv2.medianBlur(gray, 31)
    dark = cv2.subtract(local_bg, gray).astype(np.float32)
    signal = np.clip(dark - 3.0, 0.0, 30.0)
    yy, xx = np.indices((image_h, image_w), dtype=np.int32)
    vector_length = image_w + image_h - 1

    plus = _diagonal_projection_period(signal, xx + yy, vector_length, min_dim)
    minus = _diagonal_projection_period(signal, xx - yy + image_h - 1, vector_length, min_dim)
    periods_close = (
        plus["period"] > 0
        and minus["period"] > 0
        and abs(plus["period"] - minus["period"]) <= max(5, int(max(plus["period"], minus["period"]) * 0.04))
    )
    detected = bool(periods_close and plus["score"] >= 0.72 and minus["score"] >= 0.72)
    empty = np.zeros((image_h, image_w), dtype=np.uint8)
    if not detected:
        return empty, {
            "gridDetected": False,
            "gridPlusPeriod": plus["period"],
            "gridPlusScore": plus["score"],
            "gridMinusPeriod": minus["period"],
            "gridMinusScore": minus["score"],
            "gridMaskRatio": 0.0,
        }

    period = int(round((plus["period"] + minus["period"]) / 2.0))
    half_band = max(7, min(15, int(round(min_dim * 0.0165))))
    plus_distance = np.abs(((xx + yy - plus["offset"] + period / 2.0) % period) - period / 2.0)
    minus_distance = np.abs(
        ((xx - yy + image_h - 1 - minus["offset"] + period / 2.0) % period) - period / 2.0
    )
    grid_mask = np.where((plus_distance <= half_band) | (minus_distance <= half_band), 255, 0).astype(np.uint8)
    grid_ratio = float(cv2.countNonZero(grid_mask)) / float(image_w * image_h)
    if grid_ratio > 0.36:
        return empty, {
            "gridDetected": False,
            "gridRejected": "coverage_too_large",
            "gridPlusPeriod": plus["period"],
            "gridPlusScore": plus["score"],
            "gridMinusPeriod": minus["period"],
            "gridMinusScore": minus["score"],
            "gridMaskRatio": round(grid_ratio, 6),
        }
    return grid_mask, {
        "gridDetected": True,
        "gridPeriod": period,
        "gridHalfBand": half_band,
        "gridPlusPeriod": plus["period"],
        "gridPlusOffset": plus["offset"],
        "gridPlusScore": plus["score"],
        "gridMinusPeriod": minus["period"],
        "gridMinusOffset": minus["offset"],
        "gridMinusScore": minus["score"],
        "gridMaskRatio": round(grid_ratio, 6),
    }


def _residual_quality(image, mask_bin):
    selected = mask_bin > 0
    if not np.any(selected):
        return {"mean": 0.0, "p90": 0.0, "darkRatio": 0.0}
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    local_bg = cv2.medianBlur(gray, 31)
    dark = cv2.subtract(local_bg, gray)[selected]
    return {
        "mean": round(float(np.mean(dark)), 6),
        "p90": round(float(np.percentile(dark, 90)), 6),
        "darkRatio": round(float(np.mean(dark > 8)), 6),
    }


def _residual_needs_retry(before, after):
    visible_residual = bool(
        after["mean"] > 2.5
        or after["p90"] > 8.0
        or after["darkRatio"] > 0.09
    )
    insufficient_reduction = bool(
        after["mean"] > before["mean"] * 0.40
        or after["p90"] > before["p90"] * 0.40
        or after["darkRatio"] > before["darkRatio"] * 0.42
    )
    return visible_residual and insufficient_reduction


def _build_hd_fallback_mask(mask_bin, image_w, image_h, strength_mode):
    min_dim = max(1, min(image_w, image_h))
    base = _odd_kernel(round(min_dim * 0.014), 5, 17)
    iterations = 2
    if strength_mode == "low":
        iterations = 1
    elif strength_mode == "high":
        iterations = 3

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (base, base))
    expanded = cv2.dilate(mask_bin, kernel, iterations=iterations)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_odd_kernel(base + 2, 5, 21), _odd_kernel(base + 2, 5, 21)))
    expanded = cv2.morphologyEx(expanded, cv2.MORPH_CLOSE, close_kernel, iterations=1)
    return expanded, {
        "fallbackMaskKernel": base,
        "fallbackMaskIterations": iterations,
        "fallbackMaskNonZeroPixels": int(cv2.countNonZero(expanded)),
    }


def _build_hd_translucent_mask(mask_bin):
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    refined = cv2.morphologyEx(mask_bin, cv2.MORPH_CLOSE, kernel, iterations=1)
    refined = cv2.dilate(refined, kernel, iterations=1)
    return refined, {
        "fallbackMaskKernel": 3,
        "fallbackMaskIterations": 1,
        "fallbackMaskNonZeroPixels": int(cv2.countNonZero(refined)),
        "fallbackTransparentMode": True,
    }


def _local_hd_translucent_cleanup(image, mask_bin, preserve_detail=True):
    """Fallback for tiled/semi-transparent watermark masks.

    Large tiled watermark masks are many thin strokes spread over the image; a
    huge hole-fill creates visible smears. This path keeps the mask thin and
    suppresses only the marked translucent strokes.
    """
    base = cv2.inpaint(image, mask_bin, 3, cv2.INPAINT_TELEA)
    local_smooth = cv2.bilateralFilter(base, 5, 18, 18)
    alpha = (mask_bin.astype(np.float32) / 255.0)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.75)
    alpha = np.clip(alpha * 0.24, 0.0, 0.24)[:, :, None]
    repaired = base.astype(np.float32) * (1.0 - alpha) + local_smooth.astype(np.float32) * alpha
    repaired = np.clip(repaired, 0, 255).astype(np.uint8)
    if preserve_detail:
        blur = cv2.GaussianBlur(repaired, (0, 0), 0.55)
        repaired = cv2.addWeighted(repaired, 1.08, blur, -0.08, 0)
    return repaired


def _local_hd_tiled_watermark_cleanup(image, mask_bin, preserve_detail=True):
    """Suppress thin tiled translucent watermarks without broad hole filling."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    refined = cv2.morphologyEx(mask_bin, cv2.MORPH_CLOSE, kernel, iterations=1)
    refined = cv2.dilate(refined, kernel, iterations=1)

    # Estimate the local background under dark watermark strokes. Median blur
    # removes thin text/diagonal marks while keeping broad light/shadow fields.
    bg = cv2.medianBlur(image, 31)
    bg = cv2.bilateralFilter(bg, 9, 56, 56)
    fill = cv2.inpaint(bg, refined, 3, cv2.INPAINT_TELEA)

    alpha = refined.astype(np.float32) / 255.0
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.35)
    alpha = np.clip(alpha * 1.08, 0.0, 1.0)[:, :, None]
    repaired = fill.astype(np.float32) * alpha + image.astype(np.float32) * (1.0 - alpha)
    repaired = np.clip(repaired, 0, 255).astype(np.uint8)
    if preserve_detail:
        blur = cv2.GaussianBlur(repaired, (0, 0), 0.45)
        repaired = cv2.addWeighted(repaired, 1.05, blur, -0.05, 0)
    return repaired, refined


def _build_thin_watermark_mask(image, mask_bin):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    local_bg = cv2.medianBlur(gray, 31)
    dark_thin = cv2.subtract(local_bg, gray)

    contrast = cv2.inRange(dark_thin, 7, 255)
    low_sat = cv2.inRange(sat, 0, 190)
    thin = cv2.bitwise_and(contrast, low_sat)
    thin = cv2.bitwise_and(thin, mask_bin)

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(thin, 8)
    filtered = np.zeros_like(thin)
    for index in range(1, component_count):
        x, y, w, h, area = stats[index]
        if area < 2 or area > 1200:
            continue
        if w > 120 or h > 120:
            continue
        if (w <= 3 and h > 50) or (h <= 3 and w > 80):
            continue
        filtered[labels == index] = 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    filtered = cv2.dilate(filtered, kernel, iterations=1)
    return filtered


def _build_long_structure_mask(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    dark = cv2.inRange(gray, 0, 210)
    image_h, image_w = gray.shape[:2]
    horizontal_length = max(31, min(151, int(round(image_w * 0.10))))
    vertical_length = max(31, min(151, int(round(image_h * 0.10))))
    horizontal = cv2.morphologyEx(
        dark,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (horizontal_length, 1)),
    )
    vertical = cv2.morphologyEx(
        dark,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, vertical_length)),
    )
    structure = cv2.bitwise_or(horizontal, vertical)
    return cv2.dilate(
        structure,
        cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)),
        iterations=1,
    )


def _local_hd_inpaint(image, mask_bin, feather=False, preserve_detail=True):
    """OpenCV HD fallback: stronger, multi-scale path distinct from manual.

    Manual/quick are small-radius direct inpaint. The HD fallback first creates
    a clean low-frequency background estimate, then runs TELEA and NS at a
    higher scale and blends the candidates only inside an expanded, feathered
    mask. This intentionally removes translucent watermark residue more
    aggressively than ordinary mode.
    """
    image_h, image_w = image.shape[:2]
    max_dim = max(image_h, image_w)
    scale = 2 if max_dim <= 1400 else 1

    work_img = image
    work_mask = mask_bin
    if scale > 1:
        work_img = cv2.resize(image, (image_w * scale, image_h * scale), interpolation=cv2.INTER_CUBIC)
        work_mask = cv2.resize(mask_bin, (image_w * scale, image_h * scale), interpolation=cv2.INTER_NEAREST)

    radius_telea = 9 * scale
    radius_ns = 7 * scale
    telea = cv2.inpaint(work_img, work_mask, radius_telea, cv2.INPAINT_TELEA)
    ns = cv2.inpaint(work_img, work_mask, radius_ns, cv2.INPAINT_NS)

    low_freq = cv2.bilateralFilter(work_img, 11, 72, 72)
    low_freq = cv2.GaussianBlur(low_freq, (0, 0), 1.15 * scale)
    background = cv2.inpaint(low_freq, work_mask, max(5, radius_telea + 2), cv2.INPAINT_TELEA)

    repaired = cv2.addWeighted(telea, 0.48, ns, 0.28, 0)
    repaired = cv2.addWeighted(repaired, 0.78, background, 0.22, 0)

    if preserve_detail:
        blur = cv2.GaussianBlur(repaired, (0, 0), 0.85 * scale)
        repaired = cv2.addWeighted(repaired, 1.12, blur, -0.12, 0)
        repaired = cv2.bilateralFilter(repaired, 5, 28, 28)
    else:
        repaired = cv2.bilateralFilter(repaired, 9, 58, 58)

    if scale > 1:
        repaired = cv2.resize(repaired, (image_w, image_h), interpolation=cv2.INTER_AREA)

    if feather:
        repaired = cv2.GaussianBlur(repaired, (0, 0), 0.28)
    return repaired


def _composite_mask_area(original, repaired, mask_bin, feather, sigma=1.2):
    if repaired.shape[:2] != original.shape[:2]:
        repaired = cv2.resize(repaired, (original.shape[1], original.shape[0]), interpolation=cv2.INTER_LINEAR)

    alpha = mask_bin.astype(np.float32) / 255.0
    if feather:
        alpha = cv2.GaussianBlur(alpha, (0, 0), sigma)
        alpha = np.clip(alpha, 0.0, 1.0)
    alpha = alpha[:, :, None]
    blended = repaired.astype(np.float32) * alpha + original.astype(np.float32) * (1.0 - alpha)
    return np.clip(blended, 0, 255).astype(np.uint8)


def _circular_hue_distance(hue, center):
    delta = np.abs(hue.astype(np.int16) - int(center))
    return np.minimum(delta, 180 - delta)


def _expand_chromatic_watermark_mask(image, mask_bin):
    """Extend a partial HD brush over the associated colored watermark.

    Stamps and colored watermarks are often made of disconnected rings and
    glyphs. A user stroke through their center should select the nearby pieces
    with the same dominant hue without turning the whole local rectangle into
    an inpaint hole.
    """
    input_pixels = int(cv2.countNonZero(mask_bin))
    empty = np.zeros_like(mask_bin)
    debug = {
        "chromaticMaskExpanded": False,
        "chromaticExpansionPixels": 0,
        "chromaticIntentPixels": 0,
        "chromaticComponentCount": 0,
        "chromaticComponents": [],
    }
    if input_pixels <= 0 or not _env_enabled("HD_CHROMATIC_MASK_EXPANSION", True):
        return mask_bin, empty, debug

    image_h, image_w = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask_bin, connectivity=8)
    chromatic_intent = np.zeros_like(mask_bin)
    details = []

    for label in range(1, count):
        x, y, width, height, area = [int(item) for item in stats[label]]
        if area < 16 or width <= 0 or height <= 0:
            continue
        component = labels == label
        chromatic_seed = component & (saturation >= 50) & (value >= 35)
        seed_pool_size = int(np.count_nonzero(chromatic_seed))
        min_seed_pixels = max(32, int(round(area * 0.008)))
        if seed_pool_size < min_seed_pixels:
            continue

        histogram = np.bincount(hue[chromatic_seed], minlength=180).astype(np.float32)
        smoothed = sum(np.roll(histogram, offset) for offset in range(-2, 3))
        dominant_hue = int(np.argmax(smoothed))
        hue_distance = _circular_hue_distance(hue, dominant_hue)
        focused_seed = chromatic_seed & (hue_distance <= 10)
        focused_pixels = int(np.count_nonzero(focused_seed))
        if focused_pixels < min_seed_pixels or focused_pixels / float(seed_pool_size) < 0.35:
            continue

        brush_estimate = max(2.0, min(float(min(width, height)), area / float(max(width, height))))
        search_padding = min(
            256,
            max(
                32,
                int(round(brush_estimate * 2.5)),
                int(round(max(width, height) * 0.60)),
                int(round(min(image_w, image_h) * 0.025)),
            ),
        )
        x1 = max(0, x - search_padding)
        y1 = max(0, y - search_padding)
        x2 = min(image_w, x + width + search_padding)
        y2 = min(image_h, y + height + search_padding)

        seed_saturation = saturation[focused_seed]
        saturation_floor = max(20, min(64, int(round(float(np.percentile(seed_saturation, 15)) * 0.25))))
        candidate = np.zeros_like(mask_bin)
        local_match = (
            (hue_distance[y1:y2, x1:x2] <= 10)
            & (saturation[y1:y2, x1:x2] >= saturation_floor)
            & (value[y1:y2, x1:x2] >= 35)
        )
        candidate[y1:y2, x1:x2] = np.where(local_match, 255, 0).astype(np.uint8)

        bridge_size = int(round(max(brush_estimate * 0.28, min(image_w, image_h) * 0.022)))
        bridge_size = max(5, min(31, bridge_size))
        if bridge_size % 2 == 0:
            bridge_size += 1
        bridged = cv2.dilate(
            candidate,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (bridge_size, bridge_size)),
            iterations=1,
        )
        group_count, group_labels, _group_stats, _group_centroids = cv2.connectedComponentsWithStats(
            bridged, connectivity=8
        )
        selected_labels = [
            group_label
            for group_label in range(1, group_count)
            if np.any((group_labels == group_label) & component)
        ]
        if not selected_labels:
            continue
        selected = np.isin(group_labels, selected_labels) & (candidate > 0)
        selected_pixels = int(np.count_nonzero(selected))
        max_selected_pixels = max(area * 8, int(round(image_w * image_h * 0.04)))
        if selected_pixels <= 0 or selected_pixels > max_selected_pixels:
            continue

        selected_mask = np.where(selected, 255, 0).astype(np.uint8)
        halo_radius = max(2, min(5, int(round(brush_estimate * 0.055))))
        selected_mask = cv2.dilate(
            selected_mask,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (halo_radius * 2 + 1, halo_radius * 2 + 1)),
            iterations=1,
        )
        chromatic_intent = cv2.bitwise_or(chromatic_intent, selected_mask)
        selected_box = cv2.boundingRect(cv2.findNonZero(selected_mask))
        details.append({
            "dominantHue": dominant_hue,
            "seedPixels": focused_pixels,
            "saturationFloor": saturation_floor,
            "searchPadding": search_padding,
            "bridgeSize": bridge_size,
            "haloRadius": halo_radius,
            "selectedPixels": int(cv2.countNonZero(selected_mask)),
            "selectedBox": {
                "x": int(selected_box[0]),
                "y": int(selected_box[1]),
                "width": int(selected_box[2]),
                "height": int(selected_box[3]),
            },
        })

    processing_mask = cv2.bitwise_or(mask_bin, chromatic_intent)
    processing_pixels = int(cv2.countNonZero(processing_mask))
    intent_pixels = int(cv2.countNonZero(chromatic_intent))
    expansion_pixels = max(0, processing_pixels - input_pixels)
    debug.update({
        "chromaticMaskExpanded": expansion_pixels > 0,
        "chromaticExpansionPixels": expansion_pixels,
        "chromaticIntentPixels": intent_pixels,
        "chromaticComponentCount": len(details),
        "chromaticComponents": details,
    })
    return processing_mask, chromatic_intent, debug


def _build_chromatic_residual_mask(result, chromatic_intent_mask, dominant_hues):
    intent_pixels = int(cv2.countNonZero(chromatic_intent_mask))
    debug = {
        "chromaticResidualDetected": False,
        "chromaticResidualPixels": 0,
        "chromaticResidualMaskPixels": 0,
    }
    if intent_pixels <= 0 or not dominant_hues:
        return np.zeros_like(chromatic_intent_mask), debug

    hsv = cv2.cvtColor(result, cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    hue_distance = np.full(hue.shape, 180, dtype=np.int16)
    for dominant_hue in dominant_hues:
        hue_distance = np.minimum(hue_distance, _circular_hue_distance(hue, dominant_hue))

    zone = cv2.dilate(
        chromatic_intent_mask,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)),
        iterations=1,
    )
    residual = np.where(
        (zone > 0) & (hue_distance <= 14) & (saturation >= 10) & (value >= 30),
        255,
        0,
    ).astype(np.uint8)
    residual_pixels = int(cv2.countNonZero(residual))
    min_residual_pixels = max(32, int(round(result.shape[0] * result.shape[1] * 0.0002)))
    if residual_pixels < min_residual_pixels:
        return np.zeros_like(chromatic_intent_mask), debug

    residual = cv2.dilate(
        residual,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
        iterations=1,
    )
    residual = cv2.bitwise_and(residual, zone)
    residual_mask_pixels = int(cv2.countNonZero(residual))
    debug.update({
        "chromaticResidualDetected": residual_mask_pixels > 0,
        "chromaticResidualPixels": residual_pixels,
        "chromaticResidualMaskPixels": residual_mask_pixels,
    })
    return residual, debug


def _do_hd_inpaint_single(
    img_bytes: bytes,
    mask_bytes: bytes,
    strength="medium",
    preserve_detail=True,
    request_id="",
    allow_retry=True,
    inference_max_edge=None,
) -> dict:
    started_at = time.time()
    if not img_bytes:
        raise HdInpaintError("原图数据为空", status_code=400)
    if not mask_bytes:
        raise HdInpaintError("Mask 数据为空", status_code=400)

    image = _decode_image(img_bytes, cv2.IMREAD_COLOR, "原图")
    mask_raw = _decode_image(mask_bytes, cv2.IMREAD_UNCHANGED, "遮罩")

    image_h, image_w = image.shape[:2]
    mask_h, mask_w = mask_raw.shape[:2]
    dilation_iterations, feather, strength_mode = _resolve_hd_strength(strength)
    config = get_hd_config()
    iopaint_available = check_hd_available()

    debug = {
        "engine": config["engine"] if iopaint_available else "opencv_hd_fallback",
        "iopaintAvailable": iopaint_available,
        "fallbackEngine": "opencv_hd_fallback",
        "imageWidth": image_w,
        "imageHeight": image_h,
        "maskWidth": mask_w,
        "maskHeight": mask_h,
        "imageSize": f"{image_w}x{image_h}",
        "maskSize": f"{mask_w}x{mask_h}",
        "maskInputSize": f"{mask_w}x{mask_h}",
        "maskResized": False,
        "maskNonZeroPixels": 0,
        "maskRatio": 0,
        "dilationIterations": dilation_iterations,
        "feather": bool(feather),
        "preserveDetail": bool(preserve_detail),
        "strength": strength_mode,
        "algorithm": "IOPAINT_LAMA" if iopaint_available else "OPENCV_HD_FALLBACK_MULTISCALE",
        "durationMs": 0,
        "diffMean": 0,
        "diffMax": 0,
        "resultUrl": "",
        "lamaCallCount": 0,
        "firstLamaMs": 0,
        "retryLamaMs": 0,
        "totalDurationMs": 0,
    }

    mask_bin = _mask_to_binary(mask_raw)
    if (mask_w, mask_h) != (image_w, image_h):
        print("[watermark-hd] mask size mismatch:", f"image={image_w}x{image_h}", f"mask={mask_w}x{mask_h}")
        mask_bin = cv2.resize(mask_bin, (image_w, image_h), interpolation=cv2.INTER_NEAREST)
        debug["maskResized"] = True
        debug["maskWidth"] = image_w
        debug["maskHeight"] = image_h
        debug["maskSize"] = f"{image_w}x{image_h}"

    input_non_zero = int(cv2.countNonZero(mask_bin))
    input_ratio = round(input_non_zero / float(image_w * image_h), 6)
    non_zero = input_non_zero
    debug["inputMaskNonZeroPixels"] = input_non_zero
    debug["inputMaskRatio"] = input_ratio
    debug["maskNonZeroPixels"] = input_non_zero
    debug["maskRatio"] = input_ratio
    if non_zero == 0:
        raise HdInpaintError("遮罩为空，请重新涂抹水印区域。", debug=debug, status_code=400)

    component_count = max(0, cv2.connectedComponents(mask_bin, connectivity=8)[0] - 1)
    grid_mask, grid_debug = _detect_repeating_diagonal_grid_mask(image)
    should_expand_grid = bool(grid_debug.get("gridDetected") and (input_ratio >= 0.08 or component_count >= 4))
    if should_expand_grid:
        mask_bin = cv2.bitwise_or(mask_bin, grid_mask)
    else:
        grid_mask = np.zeros_like(mask_bin)
    non_zero = int(cv2.countNonZero(mask_bin))
    debug["maskNonZeroPixels"] = non_zero
    debug["maskRatio"] = round(non_zero / float(image_w * image_h), 6)
    debug["maskComponentCount"] = component_count
    debug["gridMaskExpanded"] = should_expand_grid
    debug.update(grid_debug)

    if not iopaint_available:
        debug["engine"] = "not_ready"
        debug["algorithm"] = "IOPAINT_LAMA_NOT_READY"
        raise HdInpaintError(
            "高清修复模型未就绪，请启动本地 IOPaint/LaMa 服务后重试。当前可先使用快速模式。",
            debug=debug,
            status_code=503,
            fallback_available=True,
        )

    if dilation_iterations > 0:
        kernel = np.ones((3, 3), np.uint8)
        hd_mask = cv2.dilate(mask_bin, kernel, iterations=dilation_iterations)
    else:
        hd_mask = mask_bin

    composite_mask = hd_mask
    composite_sigma = 1.2

    if iopaint_available:
        repaired, first_lama_debug = _call_iopaint_scaled(
            image,
            hd_mask,
            feather=feather,
            request_id=request_id,
            inference_max_edge=inference_max_edge,
        )
        debug.update(first_lama_debug)
        debug["lamaCallCount"] = 1
        debug["firstLamaMs"] = first_lama_debug["lamaMs"]
        debug["backendEngine"] = "iopaint"
        # IOPaint/LaMa is the HD gate. Large tiled watermark masks need to keep
        # the model result as the primary image; heavy local smoothing makes
        # flower/table samples look repainted. Smaller tiled masks still get a
        # light local cleanup pass to suppress faint residue.
        if debug["maskRatio"] >= 0.18:
            thin_cleanup_mask = _build_thin_watermark_mask(image, mask_bin)
            thin_cleanup_ratio = round(float(cv2.countNonZero(thin_cleanup_mask)) / float(image_w * image_h), 6)
            if thin_cleanup_ratio > 0:
                line_repaired, _ = _local_hd_tiled_watermark_cleanup(repaired, thin_cleanup_mask, preserve_detail=preserve_detail)
                repaired = cv2.addWeighted(repaired, 0.62, line_repaired, 0.38, 0)
            debug.update({
                "postCleanup": "iopaint_primary_tiled_watermark_thin_cleanup",
                "backendEngine": "iopaint_lama_primary",
                "postCleanupMaskRatio": debug["maskRatio"],
                "postCleanupThinMaskRatio": thin_cleanup_ratio,
                "postCleanupMaskKernel": 2,
            })
            composite_mask = hd_mask
            composite_sigma = 0.75
        elif debug["maskRatio"] >= 0.025:
            local_repaired, cleanup_mask = _local_hd_tiled_watermark_cleanup(image, mask_bin, preserve_detail=preserve_detail)
            repaired = cv2.addWeighted(repaired, 0.78, local_repaired, 0.22, 0)
            debug.update({
                "postCleanup": "light_tiled_translucent_watermark",
                "backendEngine": "iopaint_lama_plus_light_local_cleanup",
                "postCleanupMaskRatio": round(float(cv2.countNonZero(cleanup_mask)) / float(image_w * image_h), 6),
                "postCleanupMaskKernel": 3,
            })
            composite_mask = cleanup_mask
            composite_sigma = 0.65
    else:
        if debug["maskRatio"] >= 0.18:
            fallback_mask, fallback_debug = _build_hd_translucent_mask(mask_bin)
            debug["algorithm"] = "OPENCV_HD_FALLBACK_TRANSLUCENT"
            repaired = _local_hd_translucent_cleanup(image, fallback_mask, preserve_detail=preserve_detail)
            composite_sigma = 0.85
        else:
            fallback_mask, fallback_debug = _build_hd_fallback_mask(mask_bin, image_w, image_h, strength_mode)
            debug["algorithm"] = "OPENCV_HD_FALLBACK_MULTISCALE"
            repaired = _local_hd_inpaint(image, fallback_mask, feather=True, preserve_detail=preserve_detail)
            composite_sigma = 2.2
        debug.update(fallback_debug)
        debug["fallbackMaskRatio"] = round(fallback_debug["fallbackMaskNonZeroPixels"] / float(image_w * image_h), 6)
        composite_mask = fallback_mask
        debug["backendEngine"] = "opencv_hd_fallback"
    result = _composite_mask_area(image, repaired, composite_mask, True, sigma=composite_sigma)

    quality_mask = grid_mask if should_expand_grid else composite_mask
    before_quality = _residual_quality(image, quality_mask)
    after_quality = _residual_quality(result, quality_mask)
    auto_retry_count = 0
    retry_min_pixels = max(512, int(image_w * image_h * 0.008))
    retry_eligible = int(cv2.countNonZero(quality_mask)) >= retry_min_pixels
    residual_detected = retry_eligible and _residual_needs_retry(before_quality, after_quality)
    debug["retryReason"] = "objective_residual_threshold" if residual_detected and allow_retry else ""
    debug["firstResidualScore"] = after_quality["mean"]
    while allow_retry and residual_detected and auto_retry_count < 1:
        residual_mask = _build_thin_watermark_mask(result, quality_mask)
        residual_mask = cv2.morphologyEx(
            residual_mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
            iterations=1,
        )
        residual_mask = cv2.dilate(
            residual_mask,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
            iterations=1,
        )
        if cv2.countNonZero(residual_mask) <= 0:
            break
        retry_repaired, retry_lama_debug = _call_iopaint_scaled(
            result,
            residual_mask,
            feather=False,
            request_id=request_id,
            inference_max_edge=inference_max_edge,
        )
        result = _composite_mask_area(result, retry_repaired, residual_mask, True, sigma=0.35)
        auto_retry_count += 1
        debug["lamaCallCount"] += 1
        debug["retryLamaMs"] += retry_lama_debug["lamaMs"]
        debug["secondInferenceMs"] = retry_lama_debug.get("lamaInferenceMs", retry_lama_debug["lamaMs"])
        debug["retryRoi"] = {"x": 0, "y": 0, "width": image_w, "height": image_h}
        for timing_key in (
            "lamaInferenceMs", "iopaintConnectMs", "iopaintRequestEncodeMs",
            "iopaintHttpMs", "iopaintResponseDecodeMs", "iopaintOutputEncodeMs", "iopaintTotalMs",
        ):
            debug[timing_key] = int(debug.get(timing_key) or 0) + int(retry_lama_debug.get(timing_key) or 0)
        after_quality = _residual_quality(result, quality_mask)
        residual_detected = _residual_needs_retry(before_quality, after_quality)

    debug.update({
        "residualScoreBefore": before_quality["mean"],
        "residualP90Before": before_quality["p90"],
        "residualDarkRatioBefore": before_quality["darkRatio"],
        "residualScoreAfter": after_quality["mean"],
        "residualP90After": after_quality["p90"],
        "residualDarkRatioAfter": after_quality["darkRatio"],
        "residualDetected": residual_detected,
        "autoRetryCount": auto_retry_count,
        "retryEligible": retry_eligible,
        "retryMinPixels": retry_min_pixels,
    })

    diff_mean, diff_max = _diff_debug(image, result, mask_bin)
    debug["diffMean"] = round(diff_mean, 6)
    debug["diffMax"] = diff_max
    debug["durationMs"] = int((time.time() - started_at) * 1000)
    debug["totalDurationMs"] = debug["durationMs"]

    if diff_max <= 0:
        raise HdInpaintError("高清修复未产生有效变化，请调整涂抹区域后重试。", debug=debug, status_code=422)

    result_encode_started = time.perf_counter()
    ok, encoded = cv2.imencode(".png", result, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])
    if not ok:
        raise HdInpaintError("高清修复结果编码失败", debug=debug, status_code=500)
    debug["resultEncodeMs"] = int((time.perf_counter() - result_encode_started) * 1000)

    return {
        "bytes": encoded.tobytes(),
        "suffix": ".png",
        "backendMode": "LaMa/IOPaint 高清修复" if iopaint_available else "OpenCV 高清修复",
        "mode": "hd",
        "engine": debug["engine"],
        "fallbackUsed": not iopaint_available,
        "message": "处理成功",
        "debug": debug,
    }


def _rect_distance(left, right):
    gap_x = max(left["x"] - (right["x"] + right["width"]), right["x"] - (left["x"] + left["width"]), 0)
    gap_y = max(left["y"] - (right["y"] + right["height"]), right["y"] - (left["y"] + left["height"]), 0)
    return float((gap_x * gap_x + gap_y * gap_y) ** 0.5)


def _merge_region_pair(left, right):
    x1 = min(left["x"], right["x"])
    y1 = min(left["y"], right["y"])
    x2 = max(left["x"] + left["width"], right["x"] + right["width"])
    y2 = max(left["y"] + left["height"], right["y"] + right["height"])
    return {
        "x": x1,
        "y": y1,
        "width": x2 - x1,
        "height": y2 - y1,
        "area": int(left["area"] + right["area"]),
        "brushEstimate": max(float(left["brushEstimate"]), float(right["brushEstimate"])),
        "components": list(left["components"]) + list(right["components"]),
    }


def _component_regions(mask_bin, image_width, image_height):
    started = time.perf_counter()
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask_bin, connectivity=8)
    component_count = max(0, count - 1)
    min_area = max(4, int(round(image_width * image_height * 0.000002)))
    regions = []
    for label in range(1, count):
        x, y, width, height, area = [int(value) for value in stats[label]]
        if area < min_area or width <= 0 or height <= 0:
            continue
        brush_estimate = max(2.0, min(float(min(width, height)), area / float(max(width, height))))
        regions.append({
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "area": area,
            "brushEstimate": brush_estimate,
            "components": [label],
        })
    if not regions and component_count > 0:
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        x, y, width, height, area = [int(value) for value in stats[largest]]
        regions.append({
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "area": area,
            "brushEstimate": max(2.0, area / float(max(width, height))),
            "components": [largest],
        })

    merge_floor = max(16, int(round(min(image_width, image_height) * 0.012)))
    changed = True
    while changed and len(regions) > 1:
        changed = False
        for left_index in range(len(regions)):
            if changed:
                break
            for right_index in range(left_index + 1, len(regions)):
                merge_distance = min(
                    128,
                    max(
                        merge_floor,
                        int(round(max(regions[left_index]["brushEstimate"], regions[right_index]["brushEstimate"]) * 1.75)),
                    ),
                )
                if _rect_distance(regions[left_index], regions[right_index]) <= merge_distance:
                    merged = _merge_region_pair(regions[left_index], regions[right_index])
                    regions = [item for idx, item in enumerate(regions) if idx not in (left_index, right_index)] + [merged]
                    changed = True
                    break

    capped = False
    while len(regions) > 2:
        capped = True
        best = None
        for left_index in range(len(regions)):
            for right_index in range(left_index + 1, len(regions)):
                merged = _merge_region_pair(regions[left_index], regions[right_index])
                merged_area = merged["width"] * merged["height"]
                source_area = (
                    regions[left_index]["width"] * regions[left_index]["height"]
                    + regions[right_index]["width"] * regions[right_index]["height"]
                )
                cost = merged_area - source_area
                if best is None or cost < best[0]:
                    best = (cost, left_index, right_index, merged)
        _, left_index, right_index, merged = best
        regions = [item for idx, item in enumerate(regions) if idx not in (left_index, right_index)] + [merged]

    regions.sort(key=lambda item: (item["y"], item["x"]))
    return regions, {
        "componentCount": component_count,
        "filteredComponentCount": sum(len(item["components"]) for item in regions),
        "mergedRoiCount": len(regions),
        "roiGroupingCapped": capped,
        "componentMinArea": min_area,
        "connectedComponentsMs": int((time.perf_counter() - started) * 1000),
    }


def _texture_complexity(image, box):
    margin = 16
    x1 = max(0, box["x"] - margin)
    y1 = max(0, box["y"] - margin)
    x2 = min(image.shape[1], box["x"] + box["width"] + margin)
    y2 = min(image.shape[0], box["y"] + box["height"] + margin)
    sample = image[y1:y2, x1:x2]
    if sample.size <= 0:
        return 0.0
    gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _dynamic_roi_padding(image, region):
    image_height, image_width = image.shape[:2]
    min_dim = min(image_width, image_height)
    span = max(region["width"], region["height"])
    fill_ratio = region["area"] / float(max(1, region["width"] * region["height"]))
    texture = _texture_complexity(image, region)
    padding = max(32, int(round(region["brushEstimate"] * 0.75)), int(round(span * 0.06)))
    if texture >= 400 or region["brushEstimate"] >= 24:
        padding = max(padding, 64)
    if texture >= 1800 or span >= min_dim * 0.40 or (fill_ratio >= 0.35 and span >= 320):
        padding = max(padding, 96)
    if span >= min_dim * 0.70:
        padding = max(padding, 128)
    return min(128, padding), round(texture, 3)


def _choose_inference_max_edge(width, height, texture):
    longest = max(width, height)
    if longest <= 768:
        return 768
    if longest <= 1280:
        return 1280 if texture >= 1200 else 1024
    return 1536 if texture >= 2400 else 1280


def _safe_progress(callback, stage, **details):
    if callback is None:
        return
    try:
        callback(stage, **details)
    except Exception:
        pass


def do_hd_inpaint(
    img_bytes: bytes,
    mask_bytes: bytes,
    strength="medium",
    preserve_detail=True,
    request_id="",
    progress_callback=None,
) -> dict:
    """Run LaMa on at most two mask-driven ROIs and composite losslessly."""
    started = time.perf_counter()
    decode_started = time.perf_counter()
    image = _decode_image(img_bytes, cv2.IMREAD_COLOR, "原图")
    image_decode_ms = int((time.perf_counter() - decode_started) * 1000)
    mask_decode_started = time.perf_counter()
    mask_raw = _decode_image(mask_bytes, cv2.IMREAD_UNCHANGED, "遮罩")
    mask_decode_ms = int((time.perf_counter() - mask_decode_started) * 1000)
    image_height, image_width = image.shape[:2]
    mask_bin = _mask_to_binary(mask_raw)
    mask_resized = False
    if mask_bin.shape[:2] != image.shape[:2]:
        mask_bin = cv2.resize(mask_bin, (image_width, image_height), interpolation=cv2.INTER_NEAREST)
        mask_resized = True
    input_mask_pixels = int(cv2.countNonZero(mask_bin))
    if input_mask_pixels <= 0:
        raise HdInpaintError("遮罩为空，请重新涂抹水印区域。", status_code=400)

    _safe_progress(progress_callback, "analyzing", requestId=request_id)
    mask_bin, chromatic_intent_mask, chromatic_debug = _expand_chromatic_watermark_mask(image, mask_bin)
    mask_pixels = int(cv2.countNonZero(mask_bin))
    regions, component_debug = _component_regions(mask_bin, image_width, image_height)
    roi_started = time.perf_counter()
    roi_specs = []
    for region in regions:
        padding, texture = _dynamic_roi_padding(image, region)
        x1 = max(0, region["x"] - padding)
        y1 = max(0, region["y"] - padding)
        x2 = min(image_width, region["x"] + region["width"] + padding)
        y2 = min(image_height, region["y"] + region["height"] + padding)
        borders = {
            "left": max(0, padding - region["x"]),
            "top": max(0, padding - region["y"]),
            "right": max(0, region["x"] + region["width"] + padding - image_width),
            "bottom": max(0, region["y"] + region["height"] + padding - image_height),
        }
        roi_specs.append({
            **region,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "padding": padding,
            "textureComplexity": texture,
            "borders": borders,
        })
    roi_build_ms = int((time.perf_counter() - roi_started) * 1000)

    output = image.copy()
    roi_union = np.zeros((image_height, image_width), dtype=np.uint8)
    inner_debugs = []
    result_resize_ms = 0
    result_composite_ms = 0
    for index, spec in enumerate(roi_specs):
        _safe_progress(
            progress_callback,
            "repairing",
            requestId=request_id,
            roiIndex=index + 1,
            roiCount=len(roi_specs),
        )
        roi_image = image[spec["y1"]:spec["y2"], spec["x1"]:spec["x2"]].copy()
        roi_mask = mask_bin[spec["y1"]:spec["y2"], spec["x1"]:spec["x2"]].copy()
        roi_chromatic_intent = chromatic_intent_mask[
            spec["y1"]:spec["y2"], spec["x1"]:spec["x2"]
        ].copy()
        borders = spec["borders"]
        if any(borders.values()):
            roi_image_engine = cv2.copyMakeBorder(
                roi_image,
                borders["top"], borders["bottom"], borders["left"], borders["right"],
                cv2.BORDER_REFLECT_101,
            )
            roi_mask_engine = cv2.copyMakeBorder(
                roi_mask,
                borders["top"], borders["bottom"], borders["left"], borders["right"],
                cv2.BORDER_CONSTANT,
                value=0,
            )
            roi_chromatic_intent_engine = cv2.copyMakeBorder(
                roi_chromatic_intent,
                borders["top"], borders["bottom"], borders["left"], borders["right"],
                cv2.BORDER_CONSTANT,
                value=0,
            )
        else:
            roi_image_engine = roi_image
            roi_mask_engine = roi_mask
            roi_chromatic_intent_engine = roi_chromatic_intent
        inference_max_edge = _choose_inference_max_edge(
            roi_image_engine.shape[1], roi_image_engine.shape[0], spec["textureComplexity"]
        )
        has_chromatic_intent = cv2.countNonZero(roi_chromatic_intent_engine) > 0
        single = _do_hd_inpaint_single(
            _encode_png(roi_image_engine),
            _encode_png(roi_mask_engine),
            strength=strength,
            preserve_detail=preserve_detail,
            request_id=f"{request_id}:{index + 1}" if request_id else str(index + 1),
            allow_retry=len(roi_specs) == 1 and not has_chromatic_intent,
            inference_max_edge=inference_max_edge,
        )
        repaired = cv2.imdecode(np.frombuffer(single["bytes"], dtype=np.uint8), cv2.IMREAD_COLOR)
        if repaired is None:
            raise HdInpaintError("高清修复模型未返回有效图片", status_code=502)
        resize_started = time.perf_counter()
        if repaired.shape[:2] != roi_image_engine.shape[:2]:
            repaired = cv2.resize(
                repaired,
                (roi_image_engine.shape[1], roi_image_engine.shape[0]),
                interpolation=cv2.INTER_LANCZOS4,
            )
        single_debug = dict(single.get("debug") or {})
        chromatic_retry_debug = {
            "chromaticResidualDetected": False,
            "chromaticResidualPixels": 0,
            "chromaticResidualMaskPixels": 0,
            "chromaticRetryApplied": False,
            "chromaticLuminanceCleanupApplied": False,
            "chromaticLuminanceCleanupPixels": 0,
        }
        if len(roi_specs) == 1 and has_chromatic_intent:
            dominant_hues = [
                int(item["dominantHue"])
                for item in chromatic_debug.get("chromaticComponents", [])
                if "dominantHue" in item
            ]
            residual_mask, chromatic_retry_debug = _build_chromatic_residual_mask(
                repaired,
                roi_chromatic_intent_engine,
                dominant_hues,
            )
            if cv2.countNonZero(residual_mask) > 0:
                retry_single = _do_hd_inpaint_single(
                    _encode_png(repaired),
                    _encode_png(residual_mask),
                    strength=strength,
                    preserve_detail=preserve_detail,
                    request_id=(f"{request_id}:{index + 1}:chromatic-retry" if request_id else "chromatic-retry"),
                    allow_retry=False,
                    inference_max_edge=inference_max_edge,
                )
                retry_repaired = cv2.imdecode(
                    np.frombuffer(retry_single["bytes"], dtype=np.uint8), cv2.IMREAD_COLOR
                )
                if retry_repaired is None:
                    raise HdInpaintError("Chromatic HD retry returned an invalid image", status_code=502)
                if retry_repaired.shape[:2] != roi_image_engine.shape[:2]:
                    retry_repaired = cv2.resize(
                        retry_repaired,
                        (roi_image_engine.shape[1], roi_image_engine.shape[0]),
                        interpolation=cv2.INTER_LANCZOS4,
                    )
                repaired = retry_repaired
                retry_debug = dict(retry_single.get("debug") or {})
                retry_sum_keys = (
                    "lamaMs", "lamaInferenceMs", "iopaintConnectMs", "iopaintRequestEncodeMs",
                    "iopaintHttpMs", "iopaintResponseDecodeMs", "iopaintOutputEncodeMs", "iopaintTotalMs",
                )
                single_debug["lamaCallCount"] = min(
                    2,
                    int(single_debug.get("lamaCallCount") or 0) + int(retry_debug.get("lamaCallCount") or 0),
                )
                single_debug["retryLamaMs"] = int(single_debug.get("retryLamaMs") or 0) + int(
                    retry_debug.get("firstLamaMs") or retry_debug.get("lamaMs") or 0
                )
                for timing_key in retry_sum_keys:
                    single_debug[timing_key] = int(single_debug.get(timing_key) or 0) + int(
                        retry_debug.get(timing_key) or 0
                    )
                single_debug["totalDurationMs"] = int(single_debug.get("totalDurationMs") or 0) + int(
                    retry_debug.get("totalDurationMs") or 0
                )
                single_debug["retryReason"] = "chromatic_watermark_residual"
                chromatic_retry_debug["chromaticRetryApplied"] = True
            luminance_cleanup_mask = _build_thin_watermark_mask(repaired, roi_chromatic_intent_engine)
            luminance_cleanup_mask = cv2.dilate(
                luminance_cleanup_mask,
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
                iterations=1,
            )
            protected_structure = _build_long_structure_mask(roi_image_engine)
            luminance_cleanup_mask = cv2.bitwise_and(
                luminance_cleanup_mask,
                cv2.bitwise_not(protected_structure),
            )
            luminance_cleanup_pixels = int(cv2.countNonZero(luminance_cleanup_mask))
            if luminance_cleanup_pixels > 0:
                repaired = cv2.inpaint(repaired, luminance_cleanup_mask, 3, cv2.INPAINT_TELEA)
                chromatic_retry_debug["chromaticLuminanceCleanupApplied"] = True
                chromatic_retry_debug["chromaticLuminanceCleanupPixels"] = luminance_cleanup_pixels
        repaired = repaired[
            borders["top"]:borders["top"] + roi_image.shape[0],
            borders["left"]:borders["left"] + roi_image.shape[1],
        ]
        result_resize_ms += int((time.perf_counter() - resize_started) * 1000)
        composite_started = time.perf_counter()
        output[spec["y1"]:spec["y2"], spec["x1"]:spec["x2"]] = repaired
        roi_union[spec["y1"]:spec["y2"], spec["x1"]:spec["x2"]] = 255
        result_composite_ms += int((time.perf_counter() - composite_started) * 1000)
        single_debug.update({
            **chromatic_retry_debug,
            "roiIndex": index + 1,
            "roiBox": {
                "x": spec["x1"],
                "y": spec["y1"],
                "width": spec["x2"] - spec["x1"],
                "height": spec["y2"] - spec["y1"],
            },
            "roiPadding": spec["padding"],
            "roiMaskRatio": round(
                cv2.countNonZero(roi_mask_engine) / float(max(1, roi_mask_engine.size)), 6
            ),
            "textureComplexity": spec["textureComplexity"],
            "roiReflectBorder": borders,
        })
        inner_debugs.append(single_debug)

    _safe_progress(progress_callback, "compositing", requestId=request_id)
    outside = roi_union == 0
    outside_changed = int(np.count_nonzero(np.any(output[outside] != image[outside], axis=1)))
    result_encode_started = time.perf_counter()
    output_bytes = _encode_png(output)
    result_encode_ms = int((time.perf_counter() - result_encode_started) * 1000)
    total_ms = int((time.perf_counter() - started) * 1000)
    first = inner_debugs[0]
    sum_keys = (
        "lamaCallCount", "firstLamaMs", "retryLamaMs", "lamaMs", "lamaInferenceMs",
        "iopaintConnectMs", "iopaintRequestEncodeMs", "iopaintHttpMs",
        "iopaintResponseDecodeMs", "iopaintOutputEncodeMs", "iopaintTotalMs",
    )
    debug = {
        "engine": first.get("engine", "lama"),
        "actualEngine": first.get("engine", "lama"),
        "fallbackUsed": False,
        "iopaintAvailable": True,
        "imageWidth": image_width,
        "imageHeight": image_height,
        "imageSize": f"{image_width}x{image_height}",
        "maskSize": f"{mask_bin.shape[1]}x{mask_bin.shape[0]}",
        "maskResized": mask_resized,
        "maskNonZeroPixels": mask_pixels,
        "maskRatio": round(mask_pixels / float(image_width * image_height), 6),
        "inputMaskNonZeroPixels": input_mask_pixels,
        "inputMaskRatio": round(input_mask_pixels / float(image_width * image_height), 6),
        "processingMaskNonZeroPixels": mask_pixels,
        "processingMaskRatio": round(mask_pixels / float(image_width * image_height), 6),
        **chromatic_debug,
        **component_debug,
        "eachRoiBox": [item["roiBox"] for item in inner_debugs],
        "eachRoiMaskRatio": [item["roiMaskRatio"] for item in inner_debugs],
        "eachRoiPadding": [item["roiPadding"] for item in inner_debugs],
        "roiOriginalSizes": [item.get("roiOriginalSize", "") for item in inner_debugs],
        "roiInferenceSizes": [item.get("roiInferenceSize", "") for item in inner_debugs],
        "roiScales": [item.get("roiScale", 1.0) for item in inner_debugs],
        "roiDetails": inner_debugs,
        "chromaticResidualDetected": any(bool(item.get("chromaticResidualDetected")) for item in inner_debugs),
        "chromaticResidualPixels": sum(int(item.get("chromaticResidualPixels") or 0) for item in inner_debugs),
        "chromaticResidualMaskPixels": sum(
            int(item.get("chromaticResidualMaskPixels") or 0) for item in inner_debugs
        ),
        "chromaticRetryApplied": any(bool(item.get("chromaticRetryApplied")) for item in inner_debugs),
        "chromaticLuminanceCleanupApplied": any(
            bool(item.get("chromaticLuminanceCleanupApplied")) for item in inner_debugs
        ),
        "chromaticLuminanceCleanupPixels": sum(
            int(item.get("chromaticLuminanceCleanupPixels") or 0) for item in inner_debugs
        ),
        "imageDecodeMs": image_decode_ms,
        "maskDecodeMs": mask_decode_ms,
        "roiBuildMs": roi_build_ms,
        "resultResizeMs": result_resize_ms,
        "resultCompositeMs": result_composite_ms,
        "resultEncodeMs": result_encode_ms,
        "retryReason": [item.get("retryReason") for item in inner_debugs if item.get("retryReason")],
        "outputSize": f"{image_width}x{image_height}",
        "outputBytes": len(output_bytes),
        "outsideRoiChangedPixels": outside_changed,
        "durationMs": total_ms,
        "totalDurationMs": total_ms,
        "modelLoaded": all(bool(item.get("modelLoaded", True)) for item in inner_debugs),
        "modelWarm": all(bool(item.get("modelWarm", False)) for item in inner_debugs),
        "processUptimeSeconds": max(int(item.get("processUptimeSeconds") or 0) for item in inner_debugs),
        "modelLoadMs": max(int(item.get("modelLoadMs") or 0) for item in inner_debugs),
        "torchThreads": first.get("torchThreads", 0),
        "interopThreads": first.get("interopThreads", 0),
    }
    for key in sum_keys:
        debug[key] = sum(int(item.get(key) or 0) for item in inner_debugs)
    debug["lamaCallCount"] = min(2, debug["lamaCallCount"])
    diff_mean, diff_max = _diff_debug(image, output, mask_bin)
    debug["diffMean"] = round(diff_mean, 6)
    debug["diffMax"] = diff_max
    if diff_max <= 0:
        raise HdInpaintError("高清修复未产生有效变化，请调整涂抹区域后重试。", debug=debug, status_code=422)
    _safe_progress(progress_callback, "encoding", requestId=request_id)
    return {
        "bytes": output_bytes,
        "suffix": ".png",
        "backendMode": "LaMa/IOPaint 高清修复",
        "mode": "hd",
        "engine": debug["engine"],
        "fallbackUsed": False,
        "message": "处理成功",
        "debug": debug,
    }
