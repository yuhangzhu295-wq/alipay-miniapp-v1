"""图片去水印 / Inpainting 服务

当前使用 OpenCV inpaint (Telea 算法) — 基础修复，适合简单水印。
如需高质量 AI 级去水印，请部署 IOPaint (https://github.com/Sanster/IOPaint)。
"""
import io
import tempfile

import cv2
import numpy as np
from PIL import Image


def do_inpaint(img_bytes: bytes, x: int, y: int, w: int, h: int) -> str:
    """
    使用 OpenCV inpaint（Telea 算法）修复指定区域
    x, y, w, h 为水印区域的像素坐标
    返回修复后的 JPEG 临时文件路径
    """
    if not img_bytes:
        raise ValueError("输入图片数据为空")

    img_raw = Image.open(io.BytesIO(img_bytes))
    
    # 优雅处理透明 PNG
    if img_raw.mode in ("RGBA", "LA") or (img_raw.mode == "P" and "transparency" in img_raw.info):
        img = Image.new("RGB", img_raw.size, (255, 255, 255))
        img.paste(img_raw, mask=img_raw.convert("RGBA").split()[3])
    else:
        img = img_raw.convert("RGB")

    img_np = np.array(img)
    h_img, w_img = img_np.shape[:2]

    # Bounding box bounds checking
    x1 = max(0, min(w_img - 1, int(x)))
    y1 = max(0, min(h_img - 1, int(y)))
    x2 = max(0, min(w_img, int(x + w)))
    y2 = max(0, min(h_img, int(y + h)))

    # If the repair box is zero-sized or completely invalid, return original image converted to JPEG
    if x1 >= x2 or y1 >= y2:
        out_img = img
    else:
        # Build mask: white on repair region
        mask = np.zeros(img_np.shape[:2], dtype=np.uint8)
        mask[y1:y2, x1:x2] = 255

        # Expand mask slightly for blending
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=1)

        result = cv2.inpaint(img_np, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
        out_img = Image.fromarray(result)

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    out_img.save(tmp, format="JPEG", quality=95)
    tmp.flush()
    return tmp.name

