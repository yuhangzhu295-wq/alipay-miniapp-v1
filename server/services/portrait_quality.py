"""真人证件照 / 职业形象照质量校验与人像 mask 后处理。"""
import io
import math

import cv2
import numpy as np
from PIL import Image, ImageFilter


MESSAGES = {
    "INVALID_INPUT_NOT_REAL_PERSON": "当前图片不适合生成证件照/职业形象照，请上传单人正面真人照片。",
    "INVALID_INPUT_ANIME_OR_CARTOON": "当前图片不适合生成证件照/职业形象照，请上传单人正面真人照片。",
    "NO_FACE_DETECTED": "未检测到清晰人脸，请上传正面半身照。",
    "MULTIPLE_FACES_DETECTED": "检测到多个人脸，请上传单人照片。",
    "LOW_FACE_CONFIDENCE": "未检测到清晰人脸，请上传正面半身照。",
    "SHOULDER_MISSING": "照片肩部区域不足，建议上传包含头部和双肩的半身照。",
    "SEGMENTATION_INCOMPLETE": "主体识别不完整，请上传清晰的单人正面半身照后重试。",
    "MASK_TOO_SMALL": "主体识别不完整，请上传清晰的单人正面半身照后重试。",
    "MASK_FACE_MISSING": "主体识别不完整，请上传清晰的单人正面半身照后重试。",
    "IMAGE_TOO_BLURRY": "图片清晰度较低，建议更换更清晰的照片。",
    "HEADSHOT_LAYOUT_INVALID": "当前照片构图不适合生成标准头肩证件照，请上传更清晰的正面半身照片后重试。",
}


class PortraitQualityError(ValueError):
    def __init__(self, code, quality=None, status_code=400):
        super().__init__(MESSAGES.get(code, "生成失败，请重新上传符合要求的照片。"))
        self.code = code
        self.quality = quality or {}
        self.status_code = status_code


def _fail(code, quality=None, status_code=400):
    raise PortraitQualityError(code, quality, status_code)


def _decode_bgr(img_bytes):
    arr = np.frombuffer(img_bytes, np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        _fail("NO_FACE_DETECTED")
    return image


def _merge_faces(faces):
    merged = []
    for face in faces:
        x, y, w, h = [int(v) for v in face]
        keep = True
        for existing in merged:
            ex, ey, ew, eh = existing
            ix1, iy1 = max(x, ex), max(y, ey)
            ix2, iy2 = min(x + w, ex + ew), min(y + h, ey + eh)
            inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            union = w * h + ew * eh - inter
            if union and inter / union > 0.35:
                keep = False
                if w * h > ew * eh:
                    existing[:] = [x, y, w, h]
                break
        if keep:
            merged.append([x, y, w, h])
    return merged


def _detect_faces(bgr):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray_eq = cv2.equalizeHist(gray)
    min_side = min(gray.shape[:2])
    min_size = max(32, int(min_side * 0.08))
    cascades = [
        "haarcascade_frontalface_default.xml",
        "haarcascade_frontalface_alt2.xml",
    ]
    faces = []
    for name in cascades:
        path = cv2.data.haarcascades + name
        detector = cv2.CascadeClassifier(path)
        if detector.empty():
            continue
        detected = detector.detectMultiScale(
            gray_eq,
            scaleFactor=1.08,
            minNeighbors=5,
            minSize=(min_size, min_size),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )
        faces.extend(detected)
    faces = _merge_faces(faces)
    faces.sort(key=lambda item: item[2] * item[3], reverse=True)
    return faces


def _local_std(gray):
    gray_f = gray.astype(np.float32)
    mean = cv2.blur(gray_f, (7, 7))
    sq_mean = cv2.blur(gray_f * gray_f, (7, 7))
    return np.sqrt(np.maximum(sq_mean - mean * mean, 0))


def _looks_like_illustration(bgr, face_box=None):
    h, w = bgr.shape[:2]
    scale = min(1.0, 320.0 / max(w, h))
    sample = cv2.resize(bgr, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(sample, cv2.COLOR_BGR2HSV)
    sat_mean = float(np.mean(hsv[:, :, 1]))
    gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 140)
    edge_density = float(np.mean(edges > 0))
    flat_ratio = float(np.mean(_local_std(gray) < 5.5))

    if face_box is not None:
        x, y, fw, fh = face_box
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w, x + fw), min(h, y + fh)
        if x2 > x1 and y2 > y1:
            patch = bgr[y1:y2, x1:x2]
            patch_gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
            patch_local_std = _local_std(patch_gray)
            patch_flat = float(np.mean(patch_local_std < 5.5))
            patch_texture = float(np.mean(patch_local_std))
            patch_gray_std = float(np.std(patch_gray))
            patch_hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
            patch_sat = float(np.mean(patch_hsv[:, :, 1]))
            if patch_flat < 0.66 and patch_texture > 5.8 and patch_gray_std > 32:
                return False
            if patch_flat > 0.72 and patch_sat > 34 and edge_density > 0.035:
                return True

    return (flat_ratio > 0.70 and sat_mean > 35 and edge_density > 0.01) or (
        flat_ratio > 0.62 and sat_mean > 42 and edge_density > 0.035
    )


def validate_portrait_input(img_bytes, task="changeBg"):
    bgr = _decode_bgr(img_bytes)
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    faces = _detect_faces(bgr)

    quality = {
        "realPerson": False,
        "faceDetected": False,
        "singlePerson": False,
        "faceConfidence": 0,
        "faceCount": len(faces),
        "imageSize": f"{w}x{h}",
        "blurScore": round(blur_score, 2),
        "shoulderAreaPresent": False,
        "headAreaPresent": False,
        "inputType": "unknown",
    }

    if min(w, h) < 160 or blur_score < 18:
        quality["code"] = "IMAGE_TOO_BLURRY"
        _fail("IMAGE_TOO_BLURRY", quality)

    if not faces:
        if _looks_like_illustration(bgr):
            quality["inputType"] = "illustration"
            quality["code"] = "INVALID_INPUT_ANIME_OR_CARTOON"
            _fail("INVALID_INPUT_ANIME_OR_CARTOON", quality)
        quality["code"] = "NO_FACE_DETECTED"
        _fail("NO_FACE_DETECTED", quality)

    main = faces[0]
    x, y, fw, fh = main
    main_area = fw * fh
    large_faces = [f for f in faces if f[2] * f[3] > main_area * 0.38]
    if len(large_faces) > 1:
        quality["code"] = "MULTIPLE_FACES_DETECTED"
        _fail("MULTIPLE_FACES_DETECTED", quality)

    face_area_ratio = main_area / float(w * h)
    quality.update({
        "faceDetected": True,
        "singlePerson": True,
        "faceBox": {"x": x, "y": y, "width": fw, "height": fh},
        "faceConfidence": round(min(0.99, 0.45 + face_area_ratio * 12), 3),
    })

    if face_area_ratio < 0.012:
        quality["code"] = "LOW_FACE_CONFIDENCE"
        _fail("LOW_FACE_CONFIDENCE", quality)

    if _looks_like_illustration(bgr, main):
        quality["inputType"] = "illustration"
        quality["code"] = "INVALID_INPUT_ANIME_OR_CARTOON"
        _fail("INVALID_INPUT_ANIME_OR_CARTOON", quality)

    below_face_ratio = (h - (y + fh)) / float(fh)
    side_room_ratio = min(x, w - (x + fw)) / float(fw)
    quality["belowFaceRatio"] = round(below_face_ratio, 3)
    quality["sideRoomRatio"] = round(side_room_ratio, 3)
    quality["headAreaPresent"] = y > fh * 0.08

    if task == "professional":
        shoulder_ok = below_face_ratio >= 1.45 and side_room_ratio >= 0.18
    else:
        shoulder_ok = below_face_ratio >= 0.55 and side_room_ratio >= 0.08
    quality["shoulderAreaPresent"] = shoulder_ok
    if not shoulder_ok:
        quality["code"] = "SHOULDER_MISSING"
        _fail("SHOULDER_MISSING", quality)

    quality["realPerson"] = True
    quality["inputType"] = "real_person"
    quality["code"] = "OK"
    return quality


def classify_image_type(img_bytes):
    """只识别图片类型，不把二次元/插画直接当成失败输入。"""
    bgr = _decode_bgr(img_bytes)
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    faces = _detect_faces(bgr)
    main_face = faces[0] if faces else None
    illustration_like = _looks_like_illustration(bgr, main_face)

    image_type = "unknown"
    if illustration_like:
        image_type = "anime" if main_face is not None else "illustration"
    elif faces:
        image_type = "real_person"
    else:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        sat_mean = float(np.mean(hsv[:, :, 1]))
        edge_density = float(np.mean(cv2.Canny(gray, 60, 140) > 0))
        image_type = "landscape" if edge_density < 0.018 and sat_mean < 55 else "object"

    result = {
        "imageType": image_type,
        "realPerson": image_type == "real_person",
        "faceDetected": bool(faces),
        "singlePerson": len(faces) == 1,
        "faceCount": len(faces),
        "imageSize": f"{w}x{h}",
        "blurScore": round(blur_score, 2),
        "inputType": image_type,
    }
    if main_face is not None:
        x, y, fw, fh = [int(v) for v in main_face]
        result["faceBox"] = {"x": x, "y": y, "width": fw, "height": fh}
    return result


def is_illustration_like(img_bytes, face_box=None):
    bgr = _decode_bgr(img_bytes)
    box = None
    if isinstance(face_box, dict):
        try:
            box = (
                int(face_box.get("x")),
                int(face_box.get("y")),
                int(face_box.get("width")),
                int(face_box.get("height")),
            )
        except Exception:
            box = None
    elif isinstance(face_box, (list, tuple)) and len(face_box) >= 4:
        try:
            box = tuple(int(v) for v in face_box[:4])
        except Exception:
            box = None
    return _looks_like_illustration(bgr, box)


def _component_stats(mask):
    labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    components = []
    for idx in range(1, labels_count):
        x, y, w, h, area = stats[idx]
        components.append({"label": idx, "x": int(x), "y": int(y), "w": int(w), "h": int(h), "area": int(area)})
    components.sort(key=lambda item: item["area"], reverse=True)
    return labels, components


def refine_alpha(alpha, face_box):
    alpha = np.asarray(alpha).astype(np.uint8)
    binary = (alpha > 8).astype(np.uint8)
    labels, components = _component_stats(binary)
    if not components:
        return alpha, binary

    h, w = alpha.shape[:2]
    min_keep = max(64, int(w * h * 0.0012))
    fx, fy, fw, fh = face_box
    face_rect = (max(0, fx), max(0, fy), min(w, fx + fw), min(h, fy + fh))
    keep = np.zeros_like(binary)
    for comp in components:
        cx1, cy1 = comp["x"], comp["y"]
        cx2, cy2 = cx1 + comp["w"], cy1 + comp["h"]
        ix1, iy1 = max(cx1, face_rect[0]), max(cy1, face_rect[1])
        ix2, iy2 = min(cx2, face_rect[2]), min(cy2, face_rect[3])
        intersects_face = ix2 > ix1 and iy2 > iy1
        if comp["area"] >= min_keep or intersects_face:
            keep[labels == comp["label"]] = 1

    kernel = np.ones((3, 3), np.uint8)
    keep = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, kernel, iterations=1)
    refined = (alpha.astype(np.float32) * keep).astype(np.uint8)
    refined_img = Image.fromarray(refined, "L").filter(ImageFilter.GaussianBlur(radius=0.6))
    refined = np.asarray(refined_img).astype(np.uint8)
    return refined, (refined > 8).astype(np.uint8)


def validate_segmentation_mask(alpha, input_quality, task="changeBg"):
    face = input_quality.get("faceBox") or {}
    face_box = (
        int(face.get("x", 0)),
        int(face.get("y", 0)),
        int(face.get("width", 1)),
        int(face.get("height", 1)),
    )
    refined_alpha, binary = refine_alpha(alpha, face_box)
    h, w = binary.shape[:2]
    foreground = int(np.count_nonzero(binary))
    area_ratio = foreground / float(w * h)

    quality = dict(input_quality)
    quality.update({
        "foregroundAreaRatio": round(area_ratio, 6),
        "foregroundBoundingBox": None,
        "bboxWidthRatio": 0,
        "bboxHeightRatio": 0,
        "connectedComponents": 0,
        "largestComponentRatio": 0,
        "faceInsideMask": False,
        "maskValid": False,
    })

    min_area = 0.07 if task == "professional" else 0.035
    if area_ratio < min_area:
        quality["code"] = "MASK_TOO_SMALL"
        _fail("MASK_TOO_SMALL", quality)

    labels, components = _component_stats(binary)
    quality["connectedComponents"] = len(components)
    if not components:
        quality["code"] = "MASK_TOO_SMALL"
        _fail("MASK_TOO_SMALL", quality)

    largest = components[0]
    quality["largestComponentRatio"] = round(largest["area"] / float(max(1, foreground)), 6)
    if quality["largestComponentRatio"] < 0.62:
        quality["code"] = "SEGMENTATION_INCOMPLETE"
        _fail("SEGMENTATION_INCOMPLETE", quality)

    ys, xs = np.where(binary > 0)
    x1, x2 = int(xs.min()), int(xs.max()) + 1
    y1, y2 = int(ys.min()), int(ys.max()) + 1
    bbox_w, bbox_h = x2 - x1, y2 - y1
    bbox_w_ratio = bbox_w / float(w)
    bbox_h_ratio = bbox_h / float(h)
    quality["foregroundBoundingBox"] = {"x": x1, "y": y1, "width": bbox_w, "height": bbox_h}
    quality["bboxWidthRatio"] = round(bbox_w_ratio, 6)
    quality["bboxHeightRatio"] = round(bbox_h_ratio, 6)

    min_bbox_h = 0.45 if task == "professional" else 0.22
    min_bbox_w = 0.22 if task == "professional" else 0.12
    if bbox_h_ratio < min_bbox_h or bbox_w_ratio < min_bbox_w:
        quality["code"] = "SEGMENTATION_INCOMPLETE"
        _fail("SEGMENTATION_INCOMPLETE", quality)

    fx, fy, fw, fh = face_box
    fx1, fy1 = max(0, fx), max(0, fy)
    fx2, fy2 = min(w, fx + fw), min(h, fy + fh)
    face_mask_ratio = 0
    if fx2 > fx1 and fy2 > fy1:
        face_crop = binary[fy1:fy2, fx1:fx2]
        face_mask_ratio = float(np.mean(face_crop > 0))
    quality["faceMaskRatio"] = round(face_mask_ratio, 6)
    quality["faceInsideMask"] = face_mask_ratio >= 0.52
    if not quality["faceInsideMask"]:
        quality["code"] = "MASK_FACE_MISSING"
        _fail("MASK_FACE_MISSING", quality)

    quality["headAreaPresent"] = y1 <= fy + fh * 0.2
    if not quality["headAreaPresent"]:
        quality["code"] = "SEGMENTATION_INCOMPLETE"
        _fail("SEGMENTATION_INCOMPLETE", quality)

    below_face_pixels = max(0, y2 - (fy + fh))
    torso_height_ratio = below_face_pixels / float(fh)
    shoulder_band_y1 = int(min(h, fy + fh * 1.05))
    shoulder_band_y2 = int(min(h, fy + fh * 2.55))
    shoulder_present = False
    if shoulder_band_y2 > shoulder_band_y1:
        band = binary[shoulder_band_y1:shoulder_band_y2, :]
        row_widths = np.sum(band > 0, axis=1)
        shoulder_present = bool(row_widths.size and np.percentile(row_widths, 75) >= fw * 1.18)
    quality["torsoHeightRatio"] = round(torso_height_ratio, 6)
    quality["shoulderAreaPresent"] = shoulder_present

    if task == "professional" and (not shoulder_present or torso_height_ratio < 1.35):
        quality["code"] = "SHOULDER_MISSING"
        _fail("SHOULDER_MISSING", quality)

    if task == "changeBg" and torso_height_ratio < 0.42:
        quality["code"] = "SEGMENTATION_INCOMPLETE"
        _fail("SEGMENTATION_INCOMPLETE", quality)

    quality["maskValid"] = True
    quality["code"] = "OK"
    return refined_alpha, quality


def segment_human_rgba(img_bytes, model_name="u2net_human_seg"):
    from rembg import remove
    from services.remove_bg import get_rembg_session

    input_image = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    session = get_rembg_session(model_name or "u2net_human_seg")
    output = remove(input_image, session=session)
    return output.convert("RGBA")


def _clamp_int(value, low, high):
    return int(max(low, min(high, value)))


def get_headshot_crop_box(image_size, face_box):
    """根据人脸框生成标准头肩照裁切框，不保留过多胸口/身体。"""
    image_w, image_h = image_size
    fx = int(face_box["x"])
    fy = int(face_box["y"])
    fw = int(face_box["width"])
    fh = int(face_box["height"])
    face_center_x = fx + fw / 2.0

    left = face_center_x - fw * 1.65
    right = face_center_x + fw * 1.65
    top = fy - fh * 1.15
    bottom = fy + fh * 2.75

    left = _clamp_int(left, 0, image_w - 1)
    right = _clamp_int(right, left + 1, image_w)
    top = _clamp_int(top, 0, image_h - 1)
    bottom = _clamp_int(bottom, top + 1, image_h)
    return (left, top, right, bottom)


def get_portrait_crop_box(image_size, face_box, composition="head_shoulder"):
    if composition == "half_body":
        image_w, image_h = image_size
        fx = int(face_box["x"])
        fy = int(face_box["y"])
        fw = int(face_box["width"])
        fh = int(face_box["height"])
        face_center_x = fx + fw / 2.0
        left = face_center_x - fw * 1.85
        right = face_center_x + fw * 1.85
        top = fy - fh * 0.68
        bottom = fy + fh * 3.45
        return (
            _clamp_int(left, 0, image_w - 1),
            _clamp_int(top, 0, image_h - 1),
            _clamp_int(right, _clamp_int(left, 0, image_w - 1) + 1, image_w),
            _clamp_int(bottom, _clamp_int(top, 0, image_h - 1) + 1, image_h),
        )
    if composition == "square_avatar":
        image_w, image_h = image_size
        fx = int(face_box["x"])
        fy = int(face_box["y"])
        fw = int(face_box["width"])
        fh = int(face_box["height"])
        face_center_x = fx + fw / 2.0
        left = face_center_x - fw * 1.34
        right = face_center_x + fw * 1.34
        top = fy - fh * 0.72
        bottom = fy + fh * 2.05
        return (
            _clamp_int(left, 0, image_w - 1),
            _clamp_int(top, 0, image_h - 1),
            _clamp_int(right, _clamp_int(left, 0, image_w - 1) + 1, image_w),
            _clamp_int(bottom, _clamp_int(top, 0, image_h - 1) + 1, image_h),
        )
    return get_headshot_crop_box(image_size, face_box)


def verify_document_standard_compliance(metrics, spec, composition):
    """Verify headshot alignment against standard document profile.
    Returns (True, None) if valid, or (False, reason) if invalid.
    """
    profile = spec.get("compositionProfile") if spec else None
    
    if not profile:
        # Default fallback bounds
        min_head_ratio = 0.36 if composition == "half_body" else 0.42
        if metrics.get("headRatio", 1) < min_head_ratio:
            return False, "HEADSHOT_LAYOUT_INVALID"
        if metrics.get("topPaddingRatio", 0) > 0.16:
            return False, "HEADSHOT_LAYOUT_INVALID"
        if metrics.get("faceCenterOffset", 0) > 0.12:
            return False, "HEADSHOT_LAYOUT_INVALID"
        if composition != "half_body" and metrics.get("bodyHeightBelowShoulder", 0) > 0.30:
            return False, "HEADSHOT_LAYOUT_INVALID"
        return True, None
        
    # Standard document profile checks
    head_ratio = metrics.get("headRatio", 0)
    face_h_ratio = metrics.get("faceHeightRatio", 0)
    top_padding = metrics.get("topPaddingRatio", 0)
    face_offset = metrics.get("faceCenterOffset", 0)
    
    if face_offset > 0.15:
        return False, "FACE_OFF_CENTER"
        
    head_h_min = profile.get("headHeightRatioMin")
    head_h_max = profile.get("headHeightRatioMax")
    op_head_max = profile.get("operationalHeadHeightRatioMax")
    
    if head_h_min and head_ratio < head_h_min * 0.95:  # 5% tolerance
        return False, "HEAD_TOO_SMALL"
    
    if op_head_max and head_ratio > op_head_max:
        return False, "HEAD_TOO_LARGE"
    elif head_h_max and head_ratio > head_h_max * 1.05:
        return False, "HEAD_TOO_LARGE"
        
    chin_min = profile.get("chinBottomRatioMin")
    if chin_min:
        # Distance from chin to bottom = 1.0 - (top_padding + face_h_ratio)
        chin_to_bottom = max(0, 1.0 - (top_padding + face_h_ratio))
        if chin_to_bottom < chin_min * 0.9:
            return False, "CHIN_TOO_LOW"
            
    return True, None


def compose_headshot(
    cutout: Image.Image,
    quality: dict,
    background: Image.Image,
    target_size=(413, 579),
    face_height_ratio=0.36,
    composition="head_shoulder",
    spec=None,
):
    """
    将 RGBA 人像合成为标准头肩证件照/职业头像照。

    目标构图：
    - 头顶留白约 8%~12%
    - 估算头部高度约 45%~60%
    - 只保留头部、脖子、双肩和少量上胸
    """
    target_w, target_h = target_size
    if background.size != target_size:
        background = background.resize(target_size, Image.LANCZOS)

    face = quality["faceBox"]
    fx = int(face["x"])
    fy = int(face["y"])
    fw = int(face["width"])
    fh = int(face["height"])
    if composition == "half_body" and face_height_ratio == 0.34:
        face_height_ratio = 0.26
    if composition == "square_avatar" and face_height_ratio == 0.34:
        face_height_ratio = 0.40
    crop_box = get_portrait_crop_box(cutout.size, face, composition)
    crop_left, crop_top, crop_right, crop_bottom = crop_box
    person = cutout.crop(crop_box)
    crop_w, crop_h = person.size

    person_bbox = person.getbbox()
    hairTopY_in_crop = person_bbox[1] if person_bbox else 0
    chinY_in_crop = (fy + fh) - crop_top
    detectedHeadHeight = max(1, chinY_in_crop - hairTopY_in_crop)

    profile = spec.get("compositionProfile") if spec else None
    
    if profile and profile.get("headHeightRatioTarget"):
        targetHeadHeight = target_h * profile.get("headHeightRatioTarget")
        scale = targetHeadHeight / float(detectedHeadHeight)
    else:
        target_face_h = target_h * face_height_ratio
        scale_by_face = target_face_h / max(1, fh)
        # 头肩照允许肩线自然贴近画布边缘，宽度不再把人像压得过小。
        width_factor = 1.12 if composition == "half_body" else (1.34 if composition == "square_avatar" else 1.45)
        scale_by_width = target_w * width_factor / max(1, crop_w)
        scale_by_height = target_h * 1.06 / max(1, crop_h)
        scale = min(scale_by_face, scale_by_width, scale_by_height)

    new_w = max(1, int(crop_w * scale))
    new_h = max(1, int(crop_h * scale))
    person_resized = person.resize((new_w, new_h), Image.LANCZOS)

    face_center_x_in_crop = (fx + fw / 2.0 - crop_left) * scale
    face_top_in_crop = (fy - crop_top) * scale
    face_h_out = fh * scale
    foreground_top_in_crop = hairTopY_in_crop * scale

    if profile and profile.get("topGapRatioTarget"):
        targetTopGap = target_h * profile.get("topGapRatioTarget")
        py = int(targetTopGap - foreground_top_in_crop)
    else:
        target_top_padding = target_h * (0.07 if composition == "half_body" else 0.09)
        py = int(target_top_padding - foreground_top_in_crop)

    face_px = int(target_w / 2.0 - face_center_x_in_crop)
    
    if person_bbox:
        person_left = person_bbox[0] * scale
        person_right = person_bbox[2] * scale
        person_w = person_right - person_left
        if person_w >= target_w:
            px = _clamp_int(face_px, int(target_w - person_right), int(-person_left))
        else:
            body_px = int(target_w / 2.0 - (person_left + person_right) / 2.0)
            px = int(face_px * 0.6 + body_px * 0.4)
    else:
        px = face_px
    px = _clamp_int(px, target_w - new_w, 0)
    py = _clamp_int(py, int(target_h * 0.02) - new_h, int(target_h * 0.10))

    layer = Image.new("RGBA", target_size, (0, 0, 0, 0))
    layer.paste(person_resized, (px, py), person_resized)
    result = Image.alpha_composite(background.convert("RGBA"), layer)

    alpha = np.asarray(layer.getchannel("A"))
    bbox = layer.getbbox()
    top_padding_ratio = 0
    shoulder_width_ratio = 0
    body_height_below_shoulder = 0
    if bbox:
        top_padding_ratio = bbox[1] / float(target_h)
        face_top_out = py + face_top_in_crop
        shoulder_y1 = _clamp_int(face_top_out + face_h_out * 1.35, 0, target_h - 1)
        shoulder_y2 = _clamp_int(face_top_out + face_h_out * 2.05, shoulder_y1 + 1, target_h)
        band = alpha[shoulder_y1:shoulder_y2, :]
        if band.size:
            shoulder_width_ratio = float(np.percentile(np.sum(band > 8, axis=1), 75)) / float(target_w)
        shoulder_line = face_top_out + face_h_out * 2.05
        body_height_below_shoulder = max(0, bbox[3] - shoulder_line) / float(target_h)

    face_center_out = px + face_center_x_in_crop
    face_left_out = px + (fx - crop_left) * scale
    face_top_out = py + face_top_in_crop
    
    head_height_actual = max(1, (chinY_in_crop - hairTopY_in_crop) * scale)
    top_gap_actual = py + hairTopY_in_crop * scale
    chin_y_actual = py + chinY_in_crop * scale

    metrics = {
        "headRatio": round((face_h_out * 1.55) / float(target_h), 6),
        "faceHeightRatio": round(face_h_out / float(target_h), 6),
        "shoulderWidthRatio": round(shoulder_width_ratio, 6),
        "bodyHeightBelowShoulder": round(body_height_below_shoulder, 6),
        "topPaddingRatio": round(top_padding_ratio, 6),
        "faceCenterOffset": round(abs(face_center_out - target_w / 2.0) / float(target_w), 6),
        "headHeightRatioActual": round(head_height_actual / float(target_h), 6),
        "topGapRatioActual": round(top_gap_actual / float(target_h), 6),
        "chinYRatioActual": round(chin_y_actual / float(target_h), 6),
        "shoulderSpanRatioActual": round(shoulder_width_ratio, 6),
        "outputFaceBox": {
            "x": round(face_left_out, 3),
            "y": round(face_top_out, 3),
            "width": round(fw * scale, 3),
            "height": round(face_h_out, 3),
        },
        "outputForegroundBox": {
            "x": bbox[0] if bbox else 0,
            "y": bbox[1] if bbox else 0,
            "width": (bbox[2] - bbox[0]) if bbox else 0,
            "height": (bbox[3] - bbox[1]) if bbox else 0,
        },
        "headshotCropBox": {
            "x": crop_left,
            "y": crop_top,
            "width": crop_right - crop_left,
            "height": crop_bottom - crop_top,
        },
    }

    quality.update(metrics)
    is_compliant, fail_reason = verify_document_standard_compliance(metrics, spec, composition)
    if not is_compliant:
        quality["code"] = fail_reason
        raise PortraitQualityError(fail_reason, quality)

    return result.convert("RGB"), quality
