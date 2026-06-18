from io import BytesIO
import numpy as np
from PIL import Image, ImageOps
from id_photo_engines.hivision.runner import run_human_matting
from .errors import PortraitQualityError

def perform_matting(img_bytes):
    image = ImageOps.exif_transpose(Image.open(BytesIO(img_bytes))).convert("RGB")
    hivision = run_human_matting(image)
    if not hivision.get("success"):
        raise PortraitQualityError("MATTING_FAILED", {"message": f"抠图引擎失败: {hivision.get('message')}"})
    
    rgba = hivision["rgba"]
    alpha = np.asarray(rgba)[:, :, 3]
    return rgba, alpha
