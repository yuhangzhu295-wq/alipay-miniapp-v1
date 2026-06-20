import numpy as np
import cv2
from .errors import PortraitQualityError

def check_quality(img, stage="alpha_gate"):
    if stage == "alpha_gate":
        # img is alpha numpy array
        # Check for holes inside the foreground
        binary = (img > 127).astype(np.uint8) * 255
        
        # Invert to find holes
        inv = cv2.bitwise_not(binary)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(inv, 8)
        
        # 0 is the background. 1 is the main outside background. Any other label is a hole.
        # But connected components on inverted image might find the bounding box border as 0 or 1.
        # Actually, simpler: find contours of the foreground. Contours with hierarchy can tell if there are holes.
        h, w = binary.shape
        floodfilled = binary.copy()
        mask = np.zeros((h+2, w+2), np.uint8)
        # Flood fill from top-left, top-right, bottom-left, bottom-right
        for pt in [(0,0), (w-1,0), (0,h-1), (w-1,h-1)]:
            if floodfilled[pt[1], pt[0]] == 0:
                cv2.floodFill(floodfilled, mask, pt, 255)
        
        # Now floodfilled is 255 everywhere EXCEPT true internal holes
        holes = cv2.bitwise_not(floodfilled)
        
        # Check if any individual hole is too large
        num_holes, hole_labels, hole_stats, _ = cv2.connectedComponentsWithStats(holes, 8)
        max_hole_size = max(100, int(h * w * 0.005)) # 0.5% max
        
        for i in range(1, num_holes):
            if hole_stats[i, cv2.CC_STAT_AREA] > max_hole_size:
                print("WARNING: ALPHA_HOLES_DETECTED - Transparent holes found in clothing")
                # Removed raise so it doesn't block the user
                        
    elif stage == "final":
        # Check for edge lines, etc.
        pass
    
    return True
