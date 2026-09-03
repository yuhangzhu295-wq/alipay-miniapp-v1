"""Create synthetic watermark fixtures from an already-downloaded public asset.

This is test-only image processing. It never reads or writes files in alipay/.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "reports" / "alipay-final-validation" / "assets"
GENERATED = ASSETS / "generated"


def font(size):
    for candidate in (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def stamp(image, text, x, y, size):
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    fnt = font(size)
    draw.rounded_rectangle((x - 24, y - 20, x + size * len(text) + 28, y + size + 20), radius=18, fill=(255, 255, 255, 190))
    draw.text((x, y), text, font=fnt, fill=(225, 40, 40, 235), stroke_width=1, stroke_fill=(255, 255, 255, 220))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def main():
    GENERATED.mkdir(parents=True, exist_ok=True)
    source = Image.open(ASSETS / "watermark_source.jpg").convert("RGB")
    normal = stamp(source, "VALIDATION WATERMARK", max(20, source.width - 620), max(20, source.height - 120), 38)
    normal.save(GENERATED / "watermark_normal.jpg", quality=95, subsampling=0)

    # A deliberately tall derivative lets the runtime test verify that controls
    # stay reachable while only a small lower ROI is submitted for repair.
    target_width = min(900, source.width)
    scale = target_width / source.width
    panel = source.resize((target_width, max(1, int(source.height * scale))))
    gap = 16
    long_image = Image.new("RGB", (target_width, panel.height * 4 + gap * 3), "#f4f6f8")
    for index in range(4):
        long_image.paste(panel, (0, index * (panel.height + gap)))
    long_image = stamp(long_image, "LOCAL ROI TEST", target_width - 360, long_image.height - 110, 36)
    long_image.save(GENERATED / "watermark_long.jpg", quality=95, subsampling=0)

    png = source.convert("RGBA")
    png.save(GENERATED / "format_source.png")
    print("generated", GENERATED)


if __name__ == "__main__":
    main()
