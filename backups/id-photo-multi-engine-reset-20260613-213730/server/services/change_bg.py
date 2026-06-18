"""证件照更换底色：真人校验、抠图完整性校验后再合成。"""
import tempfile

from PIL import Image

from services.portrait_quality import (
    compose_headshot,
    segment_human_rgba,
    validate_portrait_input,
    validate_segmentation_mask,
)


BG_COLORS = {
    "blue": (26, 115, 232),
    "white": (255, 255, 255),
    "red": (229, 57, 53),
    "lightBlue": (129, 212, 250),
    "gray": (158, 158, 158),
    "darkBlue": (11, 61, 145),
}


def do_change_bg(img_bytes: bytes, bg_color: str, model_name: str = "u2net_human_seg") -> dict:
    """
    1. 校验输入是否为单人正面真人照片。
    2. 使用真人分割模型抠图。
    3. 校验 mask 是否包含完整头部、脸、脖子和肩部。
    4. 通过校验后合成目标底色。
    """
    color = BG_COLORS.get(bg_color, BG_COLORS["blue"])

    input_quality = validate_portrait_input(img_bytes, task="changeBg")
    output = segment_human_rgba(img_bytes, model_name or "u2net_human_seg")
    refined_alpha, quality = validate_segmentation_mask(
        output.getchannel("A"),
        input_quality,
        task="changeBg",
    )
    output.putalpha(Image.fromarray(refined_alpha, "L"))

    bg = Image.new("RGBA", (413, 579), color + (255,))
    composite, quality = compose_headshot(
        output,
        quality,
        bg,
        target_size=(413, 579),
        face_height_ratio=0.34,
    )

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    composite.save(tmp, format="JPEG", quality=95)
    tmp.flush()
    return {"path": tmp.name, "quality": quality}
