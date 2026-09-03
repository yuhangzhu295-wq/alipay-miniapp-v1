"""AI 抠图 — 使用 rembg 移除图片背景"""
import io
import tempfile
from PIL import Image

_SESSIONS = {}

def get_rembg_session(model_name: str):
    from rembg import new_session
    if model_name not in _SESSIONS:
        try:
            _SESSIONS[model_name] = new_session(model_name)
        except Exception:
            # Fallback to default if download fails
            if model_name != "u2net":
                return get_rembg_session("u2net")
            raise
    return _SESSIONS[model_name]


def detect_segmentation_model(img_bytes: bytes, model_name: str) -> str:
    """
    智能人脸特征与插画判定逻辑：
    若请求默认人像抠图模型，且未在图像中抓取到物理真人脸，自动升级为二次元动漫专精模型 isnet-anime
    """
    if model_name == "u2net_human_seg":
        try:
            import cv2
            import numpy as np
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                face_cascade = cv2.CascadeClassifier(cascade_path)
                faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                if len(faces) == 0:
                    return "isnet-anime"
        except Exception:
            pass
    return model_name


def do_remove_bg(img_bytes: bytes, model_name: str = "u2net_human_seg") -> str:
    """
    使用 rembg 移除背景，返回透明 PNG 临时文件路径
    """
    from rembg import remove

    actual_model = detect_segmentation_model(img_bytes, model_name)
    input_image = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    
    session = get_rembg_session(actual_model)
    output_image = remove(input_image, session=session)

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    output_image.save(tmp, format="PNG")
    tmp.flush()
    return tmp.name
