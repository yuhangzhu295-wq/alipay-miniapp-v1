"""职业形象照：真人校验、完整头肩胸区域校验后合成。"""
import tempfile

from PIL import Image, ImageDraw

from services.portrait_quality import (
    compose_headshot,
    segment_human_rgba,
    validate_portrait_input,
    validate_segmentation_mask,
)


TEMPLATES = {
    "blueSuit": {"bg": (26, 115, 232), "bg2": (21, 87, 176), "name": "商务蓝"},
    "blackSuit": {"bg": (44, 44, 44), "bg2": (26, 26, 26), "name": "西装黑"},
    "whiteShirt": {"bg": (232, 236, 242), "bg2": (213, 219, 227), "name": "白衬衫"},
}


def do_professional_photo(img_bytes: bytes, template_id: str) -> dict:
    """
    合成流程：
    1. 校验真人、单人、正面、头肩胸区域。
    2. 真人分割并校验 mask 完整性。
    3. 基于人脸框向下/左右扩展到肩部和胸口区域。
    4. 将完整人像合成到职业形象照背景。
    """
    tpl = TEMPLATES.get(template_id, TEMPLATES["blueSuit"])
    target_w, target_h = 413, 579

    input_quality = validate_portrait_input(img_bytes, task="professional")
    cutout = segment_human_rgba(img_bytes, "u2net_human_seg")
    refined_alpha, quality = validate_segmentation_mask(
        cutout.getchannel("A"),
        input_quality,
        task="professional",
    )
    cutout.putalpha(Image.fromarray(refined_alpha, "L"))

    bg = Image.new("RGBA", (target_w, target_h), tpl["bg"] + (255,))
    draw = ImageDraw.Draw(bg)
    for y in range(target_h):
        ratio = y / target_h
        r = int(tpl["bg"][0] * (1 - ratio) + tpl["bg2"][0] * ratio)
        g = int(tpl["bg"][1] * (1 - ratio) + tpl["bg2"][1] * ratio)
        b = int(tpl["bg"][2] * (1 - ratio) + tpl["bg2"][2] * ratio)
        draw.line([(0, y), (target_w, y)], fill=(r, g, b))

    result, quality = compose_headshot(
        cutout,
        quality,
        bg,
        target_size=(target_w, target_h),
        face_height_ratio=0.34,
    )

    overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    o_draw = ImageDraw.Draw(overlay)
    for y in range(int(target_h * 0.68), target_h):
        alpha = int(45 * (y - target_h * 0.68) / (target_h * 0.32))
        o_draw.line([(0, y), (target_w, y)], fill=(0, 0, 0, min(55, alpha)))
    result = Image.alpha_composite(result.convert("RGBA"), overlay).convert("RGB")

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    result.save(tmp, format="JPEG", quality=95)
    tmp.flush()
    return {"path": tmp.name, "quality": quality}
