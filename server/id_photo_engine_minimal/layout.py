from PIL import Image, ImageDraw

def generate_layout_photo(single_img: Image.Image, dpi: int = 300) -> Image.Image:
    """
    Generate a 6-inch layout photo (排版照) from a single ID photo.
    Standard 6-inch photo paper size: 102mm x 152mm.
    At 300 DPI, this is approx 1205 x 1795 pixels.
    """
    # Dimensions of a 6-inch photo paper at given DPI
    paper_w_mm = 152
    paper_h_mm = 102
    
    # Paper size in pixels
    paper_w_px = int(paper_w_mm / 25.4 * dpi)
    paper_h_px = int(paper_h_mm / 25.4 * dpi)
    
    # We will try both portrait and landscape orientation for the paper
    # and see which one fits more photos.
    img_w, img_h = single_img.size
    
    # Minimum gap between photos (mm)
    gap_mm = 2.0
    gap_px = int(gap_mm / 25.4 * dpi)
    
    # Margin from the edge of the paper (mm)
    margin_mm = 4.0
    margin_px = int(margin_mm / 25.4 * dpi)
    
    def calculate_grid(pw, ph):
        # Calculate how many photos can fit in columns and rows
        avail_w = pw - 2 * margin_px
        avail_h = ph - 2 * margin_px
        
        cols = (avail_w + gap_px) // (img_w + gap_px)
        rows = (avail_h + gap_px) // (img_h + gap_px)
        return cols, rows
        
    cols_landscape, rows_landscape = calculate_grid(paper_w_px, paper_h_px)
    cols_portrait, rows_portrait = calculate_grid(paper_h_px, paper_w_px)
    
    # Choose the orientation that fits the most photos
    if cols_landscape * rows_landscape >= cols_portrait * rows_portrait:
        cols, rows = cols_landscape, rows_landscape
        pw, ph = paper_w_px, paper_h_px
    else:
        cols, rows = cols_portrait, rows_portrait
        pw, ph = paper_h_px, paper_w_px
        
    if cols == 0 or rows == 0:
        # Fallback if image is too large: scale it down to fit at least 1
        return single_img
        
    # Create the paper canvas
    canvas = Image.new("RGB", (pw, ph), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    
    # Calculate centering offsets
    total_content_w = cols * img_w + (cols - 1) * gap_px
    total_content_h = rows * img_h + (rows - 1) * gap_px
    
    start_x = (pw - total_content_w) // 2
    start_y = (ph - total_content_h) // 2
    
    # Paste photos and draw crop marks
    for r in range(rows):
        for c in range(cols):
            x = start_x + c * (img_w + gap_px)
            y = start_y + r * (img_h + gap_px)
            canvas.paste(single_img, (x, y))
            
            # Draw subtle crop lines (cut lines)
            # Top-Left corner
            draw.line([(x, y - 10), (x, y)], fill=(200, 200, 200), width=1)
            draw.line([(x - 10, y), (x, y)], fill=(200, 200, 200), width=1)
            # Top-Right corner
            draw.line([(x + img_w, y - 10), (x + img_w, y)], fill=(200, 200, 200), width=1)
            draw.line([(x + img_w, y), (x + img_w + 10, y)], fill=(200, 200, 200), width=1)
            # Bottom-Left corner
            draw.line([(x, y + img_h), (x, y + img_h + 10)], fill=(200, 200, 200), width=1)
            draw.line([(x - 10, y + img_h), (x, y + img_h)], fill=(200, 200, 200), width=1)
            # Bottom-Right corner
            draw.line([(x + img_w, y + img_h), (x + img_w, y + img_h + 10)], fill=(200, 200, 200), width=1)
            draw.line([(x + img_w, y + img_h), (x + img_w + 10, y + img_h)], fill=(200, 200, 200), width=1)

    return canvas
