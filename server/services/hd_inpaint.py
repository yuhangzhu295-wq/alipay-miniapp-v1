"""高清去水印修复服务。

通过 IOPaint / LaMa 本地服务处理原图 + 黑白 mask，并只把 mask 区域合成回原图。
"""
import os
import time
import base64

import cv2
import numpy as np

from services.manual_inpaint import _decode_image, _diff_debug, _mask_to_binary


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


def check_hd_available(timeout=1.5):
    config = get_hd_config()
    if not config["enabled"]:
        return False
    if not config["url"]:
        return False
    try:
        import requests

        response = requests.get(config["url"] + "/api/v1/model", timeout=timeout)
        if response.status_code == 200:
            model = response.json()
            name = str(model.get("name", "")).lower()
            return (not config["engine"]) or config["engine"].lower() in name or bool(name)

        legacy_response = requests.get(config["url"] + "/inpaint", timeout=timeout)
        return legacy_response.status_code in (200, 204, 405)
    except Exception:
        return False


def get_hd_status():
    config = get_hd_config()
    iopaint_available = check_hd_available()
    available = bool(config["enabled"] and iopaint_available)
    engine = config["engine"] if available else "not_ready"
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


def _call_iopaint(image, mask_bin, feather=False, timeout=180):
    config = get_hd_config()
    if not check_hd_available():
        raise HdInpaintError(
            "高清修复服务暂不可用，请使用快速模式或稍后重试",
            debug={"engine": config["engine"], "hdAvailable": False},
            status_code=503,
        )

    try:
        import requests
    except Exception as exc:
        raise HdInpaintError(
            "高清修复服务暂不可用，请使用快速模式或稍后重试",
            debug={"engine": config["engine"], "error": str(exc)},
            status_code=503,
        )

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
            "prompt": "",
            "negative_prompt": "",
        }
        response = requests.post(config["url"] + "/api/v1/inpaint", json=payload, timeout=timeout)

        if response.status_code in (404, 405):
            files = {
                "image": ("image.png", image_png, "image/png"),
                "mask": ("mask.png", mask_png, "image/png"),
            }
            data = {
                "model": config["engine"],
                "sizeLimit": "0",
            }
            response = requests.post(config["url"] + "/inpaint", files=files, data=data, timeout=timeout)
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

    result_arr = np.frombuffer(response.content, dtype=np.uint8)
    result = cv2.imdecode(result_arr, cv2.IMREAD_COLOR)
    if result is None:
        raise HdInpaintError(
            "高清修复模型未返回有效图片",
            debug={"engine": config["engine"], "response": response.text[:300]},
            status_code=502,
        )
    return result


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
    return bool(
        after["mean"] > max(1.8, before["mean"] * 0.30)
        or after["p90"] > max(5.0, before["p90"] * 0.30)
        or after["darkRatio"] > max(0.075, before["darkRatio"] * 0.34)
    )


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


def do_hd_inpaint(img_bytes: bytes, mask_bytes: bytes, strength="medium", preserve_detail=True) -> dict:
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
        repaired = _call_iopaint(image, hd_mask, feather=feather)
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
    residual_detected = _residual_needs_retry(before_quality, after_quality)
    while residual_detected and auto_retry_count < 2:
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
        retry_repaired = _call_iopaint(result, residual_mask, feather=False)
        result = _composite_mask_area(result, retry_repaired, residual_mask, True, sigma=0.35)
        auto_retry_count += 1
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
    })

    diff_mean, diff_max = _diff_debug(image, result, mask_bin)
    debug["diffMean"] = round(diff_mean, 6)
    debug["diffMax"] = diff_max
    debug["durationMs"] = int((time.time() - started_at) * 1000)

    if diff_max <= 0:
        raise HdInpaintError("高清修复未产生有效变化，请调整涂抹区域后重试。", debug=debug, status_code=422)

    ok, encoded = cv2.imencode(".jpg", result, [int(cv2.IMWRITE_JPEG_QUALITY), 96])
    if not ok:
        raise HdInpaintError("高清修复结果编码失败", debug=debug, status_code=500)

    return {
        "bytes": encoded.tobytes(),
        "backendMode": "LaMa/IOPaint 高清修复" if iopaint_available else "OpenCV 高清修复",
        "mode": "hd",
        "engine": debug["engine"],
        "fallbackUsed": not iopaint_available,
        "message": "处理成功",
        "debug": debug,
    }
