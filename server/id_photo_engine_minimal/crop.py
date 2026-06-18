from PIL import Image
import numpy as np

def crop_id_photo(rgba: Image.Image, width_px: int, height_px: int, face_res: dict = None):
    # If no target width/height, return original
    if not width_px or not height_px:
        return rgba, {}
        
    # We must ensure we don't chop off clothes arbitrarily.
    # Rule 11: Base crop on face box and shoulder width.
    
    # Handle border conditions safely by padding the image with transparent pixels prior to cropping,
    # ensuring no awkward cuts of shoulders or head.
    orig_w, orig_h = rgba.size
    pad_x = orig_w
    pad_y = orig_h
    
    padded_rgba = Image.new("RGBA", (orig_w + 2 * pad_x, orig_h + 2 * pad_y), (0, 0, 0, 0))
    padded_rgba.paste(rgba, (pad_x, pad_y))
    
    has_landmarks = False
    has_facebox = False
    
    if face_res and face_res.get("success"):
        landmarks = face_res.get("landmarks")
        face_box = face_res.get("faceBox")
        if landmarks and "leftEye" in landmarks and "rightEye" in landmarks:
            le = landmarks["leftEye"]
            re = landmarks["rightEye"]
            if le and re and "x" in le and "y" in le and "x" in re and "y" in re:
                if le["x"] is not None and le["y"] is not None and re["x"] is not None and re["y"] is not None:
                    has_landmarks = True
        if not has_landmarks and face_box and "x" in face_box and "y" in face_box and "width" in face_box and "height" in face_box:
            if face_box["x"] is not None and face_box["y"] is not None and face_box["width"] is not None and face_box["height"] is not None:
                has_facebox = True
                
    if has_landmarks:
        # If landmarks (leftEye, rightEye) are available, calculate face center and estimate head scale.
        landmarks = face_res["landmarks"]
        left_eye_x = landmarks["leftEye"]["x"] + pad_x
        left_eye_y = landmarks["leftEye"]["y"] + pad_y
        right_eye_x = landmarks["rightEye"]["x"] + pad_x
        right_eye_y = landmarks["rightEye"]["y"] + pad_y
        
        face_cx = (left_eye_x + right_eye_x) / 2.0
        eye_center_y = (left_eye_y + right_eye_y) / 2.0
        
        eye_dist = np.hypot(left_eye_x - right_eye_x, left_eye_y - right_eye_y)
        head_height = eye_dist * 3.8
        
        # Eyes are at about 0.55 of head height (chin to crown) from the chin.
        # Crown is at head_top = eye_center_y - 0.45 * head_height.
        head_top = eye_center_y - 0.45 * head_height
        
        # Crop the subject so the face is horizontally centered, and the head height (chin to crown)
        # occupies approximately 2/3 of the total photo height.
        target_photo_height = head_height * 1.5
        
        # We place the crown at 10% from the top of the photo.
        crop_top = head_top - 0.10 * target_photo_height
        crop_bottom = crop_top + target_photo_height
        
        target_photo_width = target_photo_height * (width_px / height_px)
        crop_left = face_cx - target_photo_width / 2.0
        crop_right = face_cx + target_photo_width / 2.0
        
    elif has_facebox:
        # Else if only faceBox is available, calculate based on faceBox center and scale.
        face_box = face_res["faceBox"]
        bx = face_box["x"] + pad_x
        by = face_box["y"] + pad_y
        bw = face_box["width"]
        bh = face_box["height"]
        
        face_cx = bx + bw / 2.0
        # Head height is approximately 1.4 * faceBox height
        head_height = bh * 1.4
        # Top of the head is about 0.3 * faceBox height above faceBox top
        head_top = by - 0.3 * bh
        
        target_photo_height = head_height * 1.5
        crop_top = head_top - 0.10 * target_photo_height
        crop_bottom = crop_top + target_photo_height
        
        target_photo_width = target_photo_height * (width_px / height_px)
        crop_left = face_cx - target_photo_width / 2.0
        crop_right = face_cx + target_photo_width / 2.0
        
    else:
        # Else fall back to standard bounding box cropping.
        arr = np.array(rgba)
        alpha = arr[:, :, 3]
        y_indices, x_indices = np.where(alpha > 0)
        
        if len(y_indices) == 0:
            # Empty image, just resize
            return rgba.resize((width_px, height_px)), {}
            
        ymin, ymax = y_indices.min() + pad_y, y_indices.max() + pad_y
        xmin, xmax = x_indices.min() + pad_x, x_indices.max() + pad_x
        
        sub_w = xmax - xmin
        sub_h = ymax - ymin
        
        target_aspect = width_px / height_px
        sub_aspect = sub_w / sub_h
        
        if sub_aspect > target_aspect:
            new_h = int(sub_w / target_aspect)
            new_w = sub_w
            pad_top = new_h - sub_h
            ymin = ymin - pad_top
        else:
            new_w = int(sub_h * target_aspect)
            new_h = sub_h
            pad_split = new_w - sub_w
            xmin = xmin - pad_split // 2
            xmax = xmin + new_w
            
        crop_left = xmin
        crop_top = ymin
        crop_right = xmin + new_w
        crop_bottom = ymin + new_h
        
    crop_left = int(round(crop_left))
    crop_top = int(round(crop_top))
    crop_right = int(round(crop_right))
    crop_bottom = int(round(crop_bottom))
    
    cropped = padded_rgba.crop((crop_left, crop_top, crop_right, crop_bottom))
    final_img = cropped.resize((width_px, height_px), Image.Resampling.LANCZOS)
    
    return final_img, {"cropBox": [int(crop_left - pad_x), int(crop_top - pad_y), int(crop_right - pad_x), int(crop_bottom - pad_y)]}

