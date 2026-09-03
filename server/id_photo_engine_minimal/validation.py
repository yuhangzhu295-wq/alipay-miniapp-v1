import cv2
import numpy as np
from io import BytesIO
from PIL import Image, ImageOps
from services.face_detector import detect_face
from .errors import PortraitQualityError

def _blur_score(img_bytes):
    try:
        image = ImageOps.exif_transpose(Image.open(BytesIO(img_bytes))).convert("L")
        gray = np.asarray(image)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise PortraitQualityError("INVALID_IMAGE", {"message": "上传的图片格式不正确或已损坏。"})


def validate_input(img_bytes):
    score = _blur_score(img_bytes)
    if score < 18:
        raise PortraitQualityError("IMAGE_TOO_BLURRY", {"message": "图片清晰度较低，建议更换更清晰的正面照片。", "blurScore": score})
    
    face_res = detect_face(img_bytes)
    if not face_res.get("success"):
        raise PortraitQualityError(face_res.get("code"), face_res)
        
    if face_res.get("faceCount", 1) != 1:
        raise PortraitQualityError("MULTIPLE_FACES", {"message": "检测到多个人脸。请上传单人照片。"})
        
    if face_res.get("confidence", 0) < 0.85:
        raise PortraitQualityError("FACE_NOT_FOUND", {"message": "未检测到合格的真人面部，可能为卡通或异常图片。请上传清晰的真人正面照片。"})
        
    return face_res["faceBox"]
