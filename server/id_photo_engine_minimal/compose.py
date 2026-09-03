from PIL import Image

def compose_background(rgba: Image.Image, bg_color: str, background_policy: str = "") -> Image.Image:
    # If policy mandates white_only, enforce white background
    if background_policy == "white_only":
        bg_color = "white"

    # Colors standard
    colors = {
        "blue": (67, 142, 219, 255),
        "white": (255, 255, 255, 255),
        "red": (255, 0, 0, 255),
        "lightBlue": (140, 196, 255, 255),
        "gray": (128, 128, 128, 255),
    }

    # Parse color
    if bg_color.startswith("#"):
        bg_color = bg_color.lstrip('#')
        bg_rgb = tuple(int(bg_color[i:i+2], 16) for i in (0, 2, 4)) + (255,)
    else:
        bg_rgb = colors.get(bg_color, (67, 142, 219, 255))

    # Ensure bottom contact before compositing
    import numpy as np
    rgba_arr = np.array(rgba)
    alpha = rgba_arr[:, :, 3]
    y_non_zero = np.where(np.any(alpha > 20, axis=1))[0]
    if y_non_zero.size > 0:
        last_fg_y = int(y_non_zero[-1])
        if last_fg_y < alpha.shape[0] - 1:
            last_row = rgba_arr[last_fg_y:last_fg_y + 1, :, :].copy()
            rgba_arr[last_fg_y + 1:, :, :] = last_row
            rgba = Image.fromarray(rgba_arr, "RGBA")

    bg = Image.new("RGBA", rgba.size, bg_rgb)
    bg.alpha_composite(rgba)
    return bg

