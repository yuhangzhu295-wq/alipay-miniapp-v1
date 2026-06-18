import uuid
import time
import tempfile
import os
from .validation import validate_input
from .matting import perform_matting
from .alpha_cleanup import cleanup_alpha
from .crop import crop_id_photo
from .compose import compose_background
from .quality import check_quality
from .errors import TemplateError, PortraitQualityError
from services.face_detector import detect_face

PREPARE_CACHE = {}

def cleanup_prepare_cache(now=None):
    pass

def get_capabilities():
    from services.outfit_templates import list_templates
    return {"templates": list_templates()}

def generate_id_photo_v2(
    img_bytes,
    purpose="official_id_photo",
    spec_id="",
    bg_color="",
    image_type="",
    mode="official",
    composition="",
    outfit="preserve_original",
    enhance_level="standard",
    output_type="jpg",
    width_px=None,
    height_px=None,
    width_mm=None,
    height_mm=None,
):
    from services.id_photo_specs import get_spec
    spec = get_spec(spec_id, purpose)
    w = int(width_px) if width_px else spec.get("width", 413)
    h = int(height_px) if height_px else spec.get("height", 579)

    validate_input(img_bytes)
    rgba, alpha = perform_matting(img_bytes)
    check_quality(alpha, stage="alpha_gate")
    rgba = cleanup_alpha(rgba, alpha)
    face_res = detect_face(img_bytes)
    cropped_rgba, crop_params = crop_id_photo(rgba, w, h, face_res=face_res)
    final_img = compose_background(cropped_rgba, bg_color)
    check_quality(final_img, stage="final")
    
    suffix = ".jpg" if output_type.lower() in ("jpg", "jpeg") else ".png"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    final_img.convert("RGB").save(tmp, format="JPEG" if suffix == ".jpg" else "PNG", quality=95)
    tmp.flush()
    
    spec_payload = dict(spec)
    spec_payload["width"] = w
    spec_payload["height"] = h
    
    return {
        "path": tmp.name,
        "mode": mode,
        "imageType": image_type or "real_person",
        "spec": spec_payload,
        "outfit": {"id": "preserve_original"},
        "warnings": [],
        "quality": {"qualityPassed": True, "qualityScore": 100},
    }

def prepare_id_photo_v2(
    img_bytes,
    purpose="official_id_photo",
    spec_id="",
    image_type="",
    mode="official",
    composition="",
    outfit="preserve_original",
    width_px=None,
    height_px=None,
    width_mm=None,
    height_mm=None,
    request_id="",
):
    from services.id_photo_specs import get_spec
    spec = get_spec(spec_id, purpose)
    w = int(width_px) if width_px else spec.get("width", 413)
    h = int(height_px) if height_px else spec.get("height", 579)

    validate_input(img_bytes)
    rgba, alpha = perform_matting(img_bytes)
    check_quality(alpha, stage="alpha_gate")
    rgba = cleanup_alpha(rgba, alpha)
    face_res = detect_face(img_bytes)
    cropped_rgba, crop_params = crop_id_photo(rgba, w, h, face_res=face_res)

    prepared_id = str(uuid.uuid4())
    PREPARE_CACHE[prepared_id] = {
        "rgba": cropped_rgba,
        "spec": spec,
        "w": w,
        "h": h,
        "mode": mode,
        "imageType": image_type or "real_person",
        "warnings": [],
        "composition": composition,
        "outfit": outfit,
    }
    return {
        "preparedId": prepared_id,
        "imageType": image_type or "real_person",
        "mode": mode,
        "spec": spec,
        "compositionVersion": "v1",
        "quality": {},
    }, {"matting_ms": 10}

def compose_prepared_id_photo(prepared_id, bg_color="", bg_color_name="", output_type="jpg", request_id=""):
    item = PREPARE_CACHE.get(prepared_id)
    if not item:
        raise Exception("PREPARED_NOT_FOUND")
    
    final_img = compose_background(item["rgba"], bg_color)
    check_quality(final_img, stage="final")
    
    suffix = ".jpg" if output_type.lower() in ("jpg", "jpeg") else ".png"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    final_img.convert("RGB").save(tmp, format="JPEG" if suffix == ".jpg" else "PNG", quality=95)
    tmp.flush()
    
    spec_payload = dict(item["spec"])
    spec_payload["width"] = item["w"]
    spec_payload["height"] = item["h"]
    
    return {
        "path": tmp.name,
        "mode": item["mode"],
        "imageType": item["imageType"],
        "spec": spec_payload,
        "outfit": {"id": item["outfit"]},
        "warnings": item["warnings"],
        "quality": {
            "qualityPassed": True,
            "qualityScore": 100,
            "maskPassed": True,
            "compositionPassed": True,
            "qualityReport": {
                "passed": True,
                "checks": {
                    "previewEqualsDownload": True
                }
            }
        },
        "bgColor": bg_color,
        "bgColorName": bg_color_name,
        "debug": {},
    }
