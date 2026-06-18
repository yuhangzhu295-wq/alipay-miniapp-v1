from PIL import Image

def compose_background(rgba: Image.Image, bg_color: str) -> Image.Image:
    # Colors standard
    colors = {
        "blue": (67, 142, 219, 255),
        "white": (255, 255, 255, 255),
        "red": (255, 0, 0, 255),
        "lightBlue": (140, 196, 255, 255),
        "gray": (128, 128, 128, 255)
    }
    
    # Parse color
    if bg_color.startswith("#"):
        bg_color = bg_color.lstrip('#')
        bg_rgb = tuple(int(bg_color[i:i+2], 16) for i in (0, 2, 4)) + (255,)
    else:
        bg_rgb = colors.get(bg_color, (67, 142, 219, 255))
        
    bg = Image.new("RGBA", rgba.size, bg_rgb)
    bg.alpha_composite(rgba)
    return bg
