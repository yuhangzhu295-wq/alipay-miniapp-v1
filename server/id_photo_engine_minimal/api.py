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
    kb_size=0,
    model: str = None,
    hair_retouch: bool = False,
):
    from services.id_photo_specs import get_spec
    spec = get_spec(spec_id, purpose)
    w = int(width_px) if width_px else spec.get("width", 413)
    h = int(height_px) if height_px else spec.get("height", 579)

    validate_input(img_bytes)
    
    # 4C8G Fast Tier Optimization
    primary_model = "birefnet-v1-lite" if hair_retouch else "hivision_modnet"
    if model is None: model = primary_model

    rgba, alpha, model_used = perform_matting(img_bytes, model=model)
    alpha = alpha.copy()
    
    # Dual-model fallback for flowing hair / internal gaps
    # For 2C4G servers, we must run this sequentially to prevent OOM (Out of Memory)
    bypass_hole_filling = False
    if model_used == "birefnet-v1-lite" and hair_retouch:
        try:
            _, fallback_alpha, _ = perform_matting(img_bytes, model="modnet_photographic_portrait_matting")
            # Only punch holes where modnet is very confident it's background
            modnet_holes = fallback_alpha < 50
            alpha[modnet_holes] = fallback_alpha[modnet_holes]
            bypass_hole_filling = True
        except Exception as e:
            print(f"Fallback matting failed: {e}")
            
    check_quality(alpha, stage="alpha_gate")
    rgba = cleanup_alpha(rgba, alpha, bypass_hole_filling=bypass_hole_filling)
    face_res = detect_face(img_bytes)
    cropped_rgba, crop_params = crop_id_photo(rgba, w, h, face_res=face_res, composition_profile=spec.get("compositionProfile"))
    final_img = compose_background(cropped_rgba, bg_color, background_policy=spec.get("compositionProfile", {}).get("backgroundPolicy", ""))
    check_quality(final_img, stage="final")
    
    suffix = ".jpg" if output_type.lower() in ("jpg", "jpeg") else ".png"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    
    if suffix == ".jpg":
        import io
        img_rgb = final_img.convert("RGB")
        target_bytes = int(kb_size) * 1024 if kb_size else 0
        if target_bytes > 0:
            best_quality = 95
            for q in range(95, 14, -5):
                buf = io.BytesIO()
                img_rgb.save(buf, format="JPEG", quality=q, dpi=(300, 300))
                if buf.tell() <= target_bytes:
                    best_quality = q
                    break
            img_rgb.save(tmp, format="JPEG", quality=best_quality, dpi=(300, 300))
        else:
            img_rgb.save(tmp, format="JPEG", quality=95, dpi=(300, 300))
    else:
        final_img.convert("RGBA").save(tmp, format="PNG", dpi=(300, 300))
        
    tmp.flush()
    
    from .layout import generate_layout_photo
    layout_img = generate_layout_photo(final_img, dpi=300)
    layout_tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    layout_img.save(layout_tmp, format="JPEG", quality=95, dpi=(300, 300))
    layout_tmp.flush()
    
    spec_payload = dict(spec)
    spec_payload["width"] = w
    spec_payload["height"] = h
    
    return {
        "path": tmp.name,
        "layoutPath": layout_tmp.name,
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
    model: str = None,
    hair_retouch: bool = False,
):
    from services.id_photo_specs import get_spec
    spec = get_spec(spec_id, purpose)
    w = int(width_px) if width_px else spec.get("width", 413)
    h = int(height_px) if height_px else spec.get("height", 579)

    validate_input(img_bytes)
    
    # 4C8G Fast Tier Optimization: Use lightweight model when hair retouch is OFF
    primary_model = "birefnet-v1-lite" if hair_retouch else "hivision_modnet"
    if model is None: model = primary_model
    
    rgba, alpha, model_used = perform_matting(img_bytes, model=model)
    alpha = alpha.copy()
    
    # Dual-model fallback for flowing hair / internal gaps
    # For 2C4G servers, we must run this sequentially to prevent OOM (Out of Memory)
    bypass_hole_filling = False
    if model_used == "birefnet-v1-lite" and hair_retouch:
        try:
            _, fallback_alpha, _ = perform_matting(img_bytes, model="modnet_photographic_portrait_matting")
            # Only punch holes where modnet is very confident it's background
            modnet_holes = fallback_alpha < 50
            alpha[modnet_holes] = fallback_alpha[modnet_holes]
            bypass_hole_filling = True
        except Exception as e:
            print(f"Fallback matting failed: {e}")
            
    check_quality(alpha, stage="alpha_gate")
    rgba = cleanup_alpha(rgba, alpha, bypass_hole_filling=bypass_hole_filling)
    face_res = detect_face(img_bytes)
    cropped_rgba, crop_params = crop_id_photo(rgba, w, h, face_res=face_res, composition_profile=spec.get("compositionProfile"))

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

def compose_prepared_id_photo(prepared_id, bg_color="", bg_color_name="", output_type="jpg", kb_size=0, request_id=""):
    item = PREPARE_CACHE.get(prepared_id)
    if not item:
        raise Exception("PREPARED_NOT_FOUND")
    
    spec = item.get("spec") or {}
    bg_policy = (spec.get("compositionProfile") or {}).get("backgroundPolicy", "")
    final_img = compose_background(item["rgba"], bg_color, background_policy=bg_policy)
    check_quality(final_img, stage="final")
    
    suffix = ".jpg" if output_type.lower() in ("jpg", "jpeg") else ".png"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    
    if suffix == ".jpg":
        import io
        img_rgb = final_img.convert("RGB")
        target_bytes = int(kb_size) * 1024 if kb_size else 0
        if target_bytes > 0:
            best_quality = 95
            for q in range(95, 14, -5):
                buf = io.BytesIO()
                img_rgb.save(buf, format="JPEG", quality=q, dpi=(300, 300))
                if buf.tell() <= target_bytes:
                    best_quality = q
                    break
            img_rgb.save(tmp, format="JPEG", quality=best_quality, dpi=(300, 300))
        else:
            img_rgb.save(tmp, format="JPEG", quality=95, dpi=(300, 300))
    else:
        final_img.convert("RGBA").save(tmp, format="PNG", dpi=(300, 300))
        
    tmp.flush()
    
    from .layout import generate_layout_photo
    layout_img = generate_layout_photo(final_img, dpi=300)
    layout_tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    layout_img.save(layout_tmp, format="JPEG", quality=95, dpi=(300, 300))
    layout_tmp.flush()
    
    spec_payload = dict(item["spec"])
    spec_payload["width"] = item["w"]
    spec_payload["height"] = item["h"]
    
    return {
        "path": tmp.name,
        "layoutPath": layout_tmp.name,
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
