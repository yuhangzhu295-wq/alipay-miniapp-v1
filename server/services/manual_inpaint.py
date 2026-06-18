"""手动擦除去水印服务。"""
import cv2
import numpy as np


class ManualInpaintError(ValueError):
    def __init__(self, message, debug=None):
        super().__init__(message)
        self.debug = debug or {}


def _decode_image(image_bytes, flags, label):
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, flags)
    if image is None:
        raise ManualInpaintError(f"{label}读取失败，请重新上传图片")
    return image


def _resolve_strength(strength):
    if isinstance(strength, bytes):
      strength = strength.decode("utf-8", errors="ignore")
    value = str(strength or "medium").lower()
    if value in ("low", "轻度"):
        return 2, 1, "low"
    if value in ("high", "强力"):
        return 5, 2, "high"
    if value in ("medium", "standard", "标准"):
        return 3, 1, "medium"
    try:
        radius = int(float(value))
    except Exception:
        radius = 3
    radius = max(2, min(radius, 5))
    return radius, 1 if radius <= 3 else 2, "custom"


def _mask_to_binary(mask_raw):
    if len(mask_raw.shape) == 2:
        mask_gray = mask_raw
    elif mask_raw.shape[2] == 4:
        bgr = mask_raw[:, :, :3]
        alpha = mask_raw[:, :, 3]
        rgb_gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        alpha_bin = cv2.threshold(alpha, 10, 255, cv2.THRESH_BINARY)[1]
        rgb_bin = cv2.threshold(rgb_gray, 10, 255, cv2.THRESH_BINARY)[1]

        alpha_non_zero = cv2.countNonZero(alpha_bin)
        total = alpha.shape[0] * alpha.shape[1]
        rgb_non_zero = cv2.countNonZero(rgb_bin)

        if 0 < alpha_non_zero < total * 0.95 and rgb_non_zero == 0:
            mask_gray = alpha
        else:
            mask_gray = rgb_gray
    else:
        mask_gray = cv2.cvtColor(mask_raw, cv2.COLOR_BGR2GRAY)

    return cv2.threshold(mask_gray, 10, 255, cv2.THRESH_BINARY)[1]


def _diff_debug(image, result, mask_bin):
    mask_pixels = mask_bin > 0
    if not np.any(mask_pixels):
        return 0.0, 0
    masked_original = image[mask_pixels].astype(np.int16)
    masked_result = result[mask_pixels].astype(np.int16)
    diff = np.abs(masked_original - masked_result)
    return float(np.mean(diff)), int(np.max(diff))


def do_manual_inpaint(img_bytes: bytes, mask_bytes: bytes, strength="medium") -> dict:
    if not img_bytes:
        raise ManualInpaintError("原图数据为空")
    if not mask_bytes:
        raise ManualInpaintError("Mask 数据为空")

    image = _decode_image(img_bytes, cv2.IMREAD_COLOR, "原图")
    mask_raw = _decode_image(mask_bytes, cv2.IMREAD_UNCHANGED, "遮罩")

    image_h, image_w = image.shape[:2]
    mask_h, mask_w = mask_raw.shape[:2]
    radius, dilation_iterations, strength_mode = _resolve_strength(strength)

    debug = {
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
        "inpaintRadius": radius,
        "strength": strength_mode,
        "diffMean": 0,
        "diffMax": 0,
        "algorithm": "TELEA",
        "resultUrl": "",
    }

    mask_bin = _mask_to_binary(mask_raw)
    if (mask_w, mask_h) != (image_w, image_h):
        print(
            "[watermark] mask size mismatch:",
            f"image={image_w}x{image_h}",
            f"mask={mask_w}x{mask_h}",
        )
        mask_bin = cv2.resize(mask_bin, (image_w, image_h), interpolation=cv2.INTER_NEAREST)
        debug["maskResized"] = True
        debug["maskWidth"] = image_w
        debug["maskHeight"] = image_h
        debug["maskSize"] = f"{image_w}x{image_h}"

    non_zero = int(cv2.countNonZero(mask_bin))
    debug["maskNonZeroPixels"] = non_zero
    debug["maskRatio"] = round(non_zero / float(image_w * image_h), 6)

    print("[watermark] imageSize:", debug["imageSize"])
    print("[watermark] maskSize:", debug["maskSize"])
    print("[watermark] maskNonZeroPixels:", debug["maskNonZeroPixels"])
    print("[watermark] maskRatio:", debug["maskRatio"])

    if non_zero == 0:
        raise ManualInpaintError("遮罩为空，请重新涂抹水印区域。", debug)

    kernel = np.ones((3, 3), np.uint8)
    inpaint_mask = cv2.dilate(mask_bin, kernel, iterations=dilation_iterations)

    result = cv2.inpaint(image, inpaint_mask, radius, cv2.INPAINT_TELEA)
    diff_mean, diff_max = _diff_debug(image, result, mask_bin)
    debug["diffMean"] = round(diff_mean, 6)
    debug["diffMax"] = diff_max

    if diff_max <= 0:
        result_ns = cv2.inpaint(image, inpaint_mask, radius, cv2.INPAINT_NS)
        diff_mean, diff_max = _diff_debug(image, result_ns, mask_bin)
        debug["algorithm"] = "NS"
        debug["diffMean"] = round(diff_mean, 6)
        debug["diffMax"] = diff_max
        result = result_ns

    print("[watermark] dilationIterations:", debug["dilationIterations"])
    print("[watermark] inpaintRadius:", debug["inpaintRadius"])
    print("[watermark] diffMean:", debug["diffMean"])
    print("[watermark] diffMax:", debug["diffMax"])

    if diff_max <= 0:
        raise ManualInpaintError("OpenCV 修复未产生有效变化，请检查遮罩是否覆盖水印区域。", debug)

    ok, encoded = cv2.imencode(".jpg", result, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        raise ManualInpaintError("修复结果编码失败", debug)

    return {
        "bytes": encoded.tobytes(),
        "backendMode": "OpenCV inpaint " + debug["algorithm"],
        "mode": "manual",
        "engine": "opencv_manual",
        "message": "使用 OpenCV 图像修复完成。",
        "debug": debug,
    }


def do_quick_inpaint(img_bytes: bytes, mask_bytes: bytes, strength="medium") -> dict:
    if not img_bytes:
        raise ManualInpaintError("原图数据为空")
    if not mask_bytes:
        raise ManualInpaintError("Mask 数据为空")

    image = _decode_image(img_bytes, cv2.IMREAD_COLOR, "原图")
    mask_raw = _decode_image(mask_bytes, cv2.IMREAD_UNCHANGED, "遮罩")

    image_h, image_w = image.shape[:2]
    mask_h, mask_w = mask_raw.shape[:2]
    debug = {
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
        "dilationIterations": 0,
        "inpaintRadius": 2,
        "strength": "quick",
        "diffMean": 0,
        "diffMax": 0,
        "algorithm": "TELEA_QUICK",
        "resultUrl": "",
    }

    mask_bin = _mask_to_binary(mask_raw)
    if (mask_w, mask_h) != (image_w, image_h):
        mask_bin = cv2.resize(mask_bin, (image_w, image_h), interpolation=cv2.INTER_NEAREST)
        debug["maskResized"] = True
        debug["maskWidth"] = image_w
        debug["maskHeight"] = image_h
        debug["maskSize"] = f"{image_w}x{image_h}"

    non_zero = int(cv2.countNonZero(mask_bin))
    debug["maskNonZeroPixels"] = non_zero
    debug["maskRatio"] = round(non_zero / float(image_w * image_h), 6)
    if non_zero == 0:
        raise ManualInpaintError("遮罩为空，请重新涂抹水印区域。", debug)

    inpaint_mask = cv2.morphologyEx(mask_bin, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    result = cv2.inpaint(image, inpaint_mask, 2, cv2.INPAINT_TELEA)
    diff_mean, diff_max = _diff_debug(image, result, mask_bin)
    debug["diffMean"] = round(diff_mean, 6)
    debug["diffMax"] = diff_max
    if diff_max <= 0:
        raise ManualInpaintError("OpenCV quick 修复未产生有效变化，请检查遮罩区域。", debug)

    ok, encoded = cv2.imencode(".jpg", result, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:
        raise ManualInpaintError("快速修复结果编码失败", debug)

    return {
        "bytes": encoded.tobytes(),
        "backendMode": "OpenCV quick inpaint TELEA",
        "mode": "quick",
        "engine": "opencv_quick",
        "message": "快速去水印完成。",
        "debug": debug,
    }
