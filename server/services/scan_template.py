"""扫描水印服务 (Template Matching 匹配)
"""
import io
import cv2
import numpy as np
from PIL import Image

def do_scan_template(img_bytes: bytes, x: int, y: int, w: int, h: int, threshold: float = 0.7) -> tuple:
    """
    根据用户框选的模版坐标，在全图内寻找相似的水印区域，生成对应的二值化 Mask。
    x, y, w, h 为在原图分辨率下的模版坐标。
    返回: (mask_png_bytes, list_of_matching_rects)
    """
    if not img_bytes:
        raise ValueError("输入图片数据为空")
    
    img_pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img_np = np.array(img_pil)
    img_gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    
    h_img, w_img = img_gray.shape[:2]
    
    # 校验和限制模版框范围
    x1 = max(0, min(w_img - 2, int(x)))
    y1 = max(0, min(h_img - 2, int(y)))
    x2 = max(x1 + 2, min(w_img, int(x + w)))
    y2 = max(y1 + 2, min(h_img, int(y + h)))
    
    tw, th = x2 - x1, y2 - y1
    if tw < 4 or th < 4:
        raise ValueError("框选范围太小，无法作为去水印匹配模版")
        
    template = img_gray[y1:y2, x1:x2]
    
    # 匹配模版
    res = cv2.matchTemplate(img_gray, template, cv2.TM_CCOEFF_NORMED)
    
    # 获取匹配位置
    loc = np.where(res >= threshold)
    
    # 合并相近的匹配区域 (NMS 极简版)
    matches = []
    for pt in zip(*loc[::-1]): # pt 是 (x, y)
        score = res[pt[1], pt[0]]
        matches.append((pt[0], pt[1], score))
        
    # 按得分从大到小排序
    matches = sorted(matches, key=lambda val: val[2], reverse=True)
    
    # 过滤相近点
    filtered_matches = []
    for m in matches:
        mx, my, ms = m
        # 检查是否和已过滤的点靠得太近 (比如距离小于模版宽高的 50%)
        too_close = False
        for fm in filtered_matches:
            fmx, fmy, _ = fm
            if abs(mx - fmx) < tw * 0.5 and abs(my - fmy) < th * 0.5:
                too_close = True
                break
        if not too_close:
            filtered_matches.append(m)

    # Template matching cannot return a match that extends outside the image,
    # so repeated edge tiles used to leave half-visible text at the right and
    # bottom borders. When matches form a stable two-dimensional lattice,
    # extrapolate the lattice and include clipped edge tiles in the mask.
    if len(filtered_matches) >= 6:
        unique_x = sorted(set(int(m[0]) for m in filtered_matches))
        unique_y = sorted(set(int(m[1]) for m in filtered_matches))

        def _stable_period(values, template_size):
            diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
            diffs = [d for d in diffs if d >= max(8, int(template_size * 0.55))]
            if not diffs:
                return 0
            period = int(round(float(np.median(diffs))))
            support = sum(1 for d in diffs if abs(d - period) <= max(4, int(period * 0.05)))
            return period if support >= 2 else 0

        period_x = _stable_period(unique_x, tw)
        period_y = _stable_period(unique_y, th)
        periods_match = (
            period_x > 0
            and period_y > 0
            and abs(period_x - period_y) <= max(6, int(max(period_x, period_y) * 0.06))
        )
        if periods_match:
            anchor_x = unique_x[0]
            anchor_y = unique_y[0]
            lattice_matches = []
            start_x = anchor_x
            start_y = anchor_y
            while start_x - period_x + tw > 0:
                start_x -= period_x
            while start_y - period_y + th > 0:
                start_y -= period_y
            y_pos = start_y
            while y_pos < h_img:
                x_pos = start_x
                while x_pos < w_img:
                    lattice_matches.append((x_pos, y_pos, 1.0))
                    x_pos += period_x
                y_pos += period_y
            filtered_matches = lattice_matches
            
    # 创建 Mask，底色为黑色(0)，匹配出的水印区为白色(255)
    mask = np.zeros_like(img_gray)
    
    rects_list = []
    # 在 Mask 上画白色矩形并记录坐标
    for m in filtered_matches:
        mx, my, _ = m
        draw_x1 = max(0, int(mx))
        draw_y1 = max(0, int(my))
        draw_x2 = min(w_img, int(mx + tw))
        draw_y2 = min(h_img, int(my + th))
        if draw_x2 <= draw_x1 or draw_y2 <= draw_y1:
            continue
        cv2.rectangle(mask, (draw_x1, draw_y1), (draw_x2, draw_y2), 255, -1)
        rects_list.append({
            "x": draw_x1,
            "y": draw_y1,
            "w": draw_x2 - draw_x1,
            "h": draw_y2 - draw_y1
        })
        
    # 保存 Mask 为 PNG 并返回字节
    mask_pil = Image.fromarray(mask)
    buf = io.BytesIO()
    mask_pil.save(buf, format="PNG")
    return buf.getvalue(), rects_list
