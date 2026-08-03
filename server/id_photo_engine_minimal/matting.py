from io import BytesIO
import numpy as np
from PIL import Image, ImageOps
from id_photo_engines.hivision.runner import run_human_matting
from .errors import PortraitQualityError

def perform_matting(img_bytes, model=None):
    image = ImageOps.exif_transpose(Image.open(BytesIO(img_bytes))).convert("RGB")
    hivision = run_human_matting(image, model=model)
    if not hivision.get("success"):
        print("MATTING DEBUG:", hivision.get("debug"))
        raise PortraitQualityError("MATTING_FAILED", {"message": f"抠图引擎失败: {hivision.get('message')}"})
    
    rgba = hivision.get("rgba") or hivision.get("image")
    alpha = np.asarray(rgba)[:, :, 3]
    model_used = hivision.get("model")
    return rgba, alpha, model_used
