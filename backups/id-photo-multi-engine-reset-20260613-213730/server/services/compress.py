"""目标 KB 压缩 — 双循环降低 quality + 缩小尺寸"""
import io
import tempfile
from PIL import Image


def do_compress(img_bytes: bytes, target_kb: int) -> tuple:
    """
    循环压缩直到接近 target_kb，返回 (tmp_path, actual_kb)
    策略：
      1. 先降低 JPG quality (92 → 15)。
      2. quality 降到最低仍超出时，缩小图片宽高（每次 ×0.85）。
      3. 返回最接近目标（且不超过目标 + 10%）的图片。
    """
    if not img_bytes:
        raise ValueError("输入图片数据为空")
    if target_kb <= 0:
        target_kb = 100  # 默认目标大小

    img_raw = Image.open(io.BytesIO(img_bytes))
    
    # 优雅处理 PNG/RGBA 透明通道，避免直接转 RGB 导致背景变黑
    if img_raw.mode in ("RGBA", "LA") or (img_raw.mode == "P" and "transparency" in img_raw.info):
        img = Image.new("RGB", img_raw.size, (255, 255, 255))
        img.paste(img_raw, mask=img_raw.convert("RGBA").split()[3])
    else:
        img = img_raw.convert("RGB")

    target_bytes = target_kb * 1024

    quality = 92
    scale = 1.0
    orig_w, orig_h = img.size
    best_result = None
    best_size = float("inf")
    best_quality = 92

    for loop in range(25):
        cw = max(10, int(orig_w * scale))
        ch = max(10, int(orig_h * scale))
        resized = img.resize((cw, ch), Image.LANCZOS)

        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=quality)
        actual_size = buf.tell()

        if actual_size < best_size:
            best_size = actual_size
            best_result = buf.getvalue()
            best_quality = quality

        # Close enough (within 5% of target)
        if target_bytes * 0.95 <= actual_size <= target_bytes * 1.05:
            break

        # Exceeded target - reduce quality first, then scale
        if actual_size > target_bytes:
            if quality > 15:
                quality = max(15, quality - 5)
            else:
                # quality already min, reduce scale
                scale = max(0.15, scale * 0.85)
                quality = 80  # reset quality for new scale
        else:
            # Under target - we're done (or close enough)
            break

    if best_result is None:
        # 兜底：直接输出原图的 JPEG 转换
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        best_result = buf.getvalue()
        best_size = len(best_result)

    # Write the best result to temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.write(best_result)
    tmp.flush()
    return tmp.name, best_size // 1024

