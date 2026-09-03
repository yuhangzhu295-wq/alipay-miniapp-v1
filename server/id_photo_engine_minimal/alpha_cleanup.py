import cv2
import numpy as np
from PIL import Image

def cleanup_alpha(rgba: Image.Image, alpha: np.ndarray, bypass_hole_filling: bool = False) -> Image.Image:
    # Rule 10: Lightweight cleanup (remove isolated noise, separate background pieces, light feathering)
    binary = (alpha > 127).astype(np.uint8) * 255
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, 8)
    
    if num_labels <= 1:
        final_alpha = alpha.copy()
    else:
        # Keep the largest component (excluding background at index 0)
        max_label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        clean_mask = np.zeros_like(binary)
        clean_mask[labels == max_label] = 255
        
        if not bypass_hole_filling:
            # Safe hole filling: only fill holes that are < 0.5% of image area
            h, w = clean_mask.shape
            floodfilled = clean_mask.copy()
            mask = np.zeros((h+2, w+2), np.uint8)
            for pt in [(0,0), (w-1,0), (0,h-1), (w-1,h-1)]:
                if floodfilled[pt[1], pt[0]] == 0:
                    cv2.floodFill(floodfilled, mask, pt, 255)
            holes = cv2.bitwise_not(floodfilled)
            
            # Filter holes by size
            num_holes, hole_labels, hole_stats, _ = cv2.connectedComponentsWithStats(holes, 8)
            max_hole_size = max(100, int(h * w * 0.05))
            safe_holes = np.zeros_like(holes)
            for i in range(1, num_holes):
                if hole_stats[i, cv2.CC_STAT_AREA] < max_hole_size:
                    safe_holes[hole_labels == i] = 255
                    
            clean_mask = cv2.bitwise_or(clean_mask, safe_holes)
        
        # Light feathering
        clean_mask = cv2.GaussianBlur(clean_mask, (3, 3), 0)
        
        # Preserve soft alpha transitions by utilizing the connected components mask as a mask
        alpha_normalized = clean_mask.astype(np.float32) / 255.0
        final_alpha = np.clip(alpha.astype(np.float32) * alpha_normalized, 0, 255).astype(np.uint8)

    # Color purification to prevent halo bleeding
    arr = np.array(rgba)
    arr_f32 = arr.astype(np.float32)
    rgb = arr_f32[:, :, :3]
    
    opaque = (final_alpha > 202).astype(np.float32)
    denom = cv2.GaussianBlur(opaque, (11, 11), 0)
    weighted = cv2.GaussianBlur(rgb * opaque[:, :, None], (11, 11), 0)
    
    near = np.zeros_like(rgb)
    valid = denom > 0.01
    near[valid] = weighted[valid] / denom[valid, None]
    near[~valid] = rgb[~valid]
    
    fg = final_alpha > 2
    if np.any(fg):
        kernel = np.ones((3, 3), np.uint8)
        near_background = cv2.dilate((~fg).astype("uint8"), kernel, iterations=3) > 0
        edge = fg & near_background
        transition = edge & (final_alpha > 2) & (final_alpha < 235)
        
        cleaned = int(np.count_nonzero(transition & valid))
        if cleaned > 0:
            strength = np.zeros_like(final_alpha, dtype=np.float32)
            strength[transition & valid] = np.clip((235.0 - final_alpha[transition & valid]) / 235.0, 0.18, 0.72)
            rgb[:] = rgb * (1.0 - strength[:, :, None]) + near * strength[:, :, None]
            
    arr_f32[:, :, :3] = np.clip(rgb, 0, 255)
    arr_f32[:, :, 3] = final_alpha
    return Image.fromarray(arr_f32.astype(np.uint8), "RGBA")

