from PIL import Image
import numpy as np

def crop_id_photo(rgba: Image.Image, width_px: int, height_px: int, face_res: dict = None):
    # If no target width/height, return original
    if not width_px or not height_px:
        return rgba, {}
        
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
                
    if has_landmarks or has_facebox:
        # Extract base coordinates and sizes in padded coordinate space
        if has_landmarks:
            landmarks = face_res["landmarks"]
            left_eye_x = landmarks["leftEye"]["x"] + pad_x
            left_eye_y = landmarks["leftEye"]["y"] + pad_y
            right_eye_x = landmarks["rightEye"]["x"] + pad_x
            right_eye_y = landmarks["rightEye"]["y"] + pad_y
            
            face_cx = (left_eye_x + right_eye_x) / 2.0
            eye_center_y = (left_eye_y + right_eye_y) / 2.0
            eye_dist = np.hypot(left_eye_x - right_eye_x, left_eye_y - right_eye_y)
            
            landmark_head_height = eye_dist * 3.8
            landmark_head_top = eye_center_y - 0.45 * landmark_head_height
            chin_y = eye_center_y + 0.55 * landmark_head_height
            face_w = eye_dist * 2.0
            search_limit_y = int(eye_center_y)
        else:
            face_box = face_res["faceBox"]
            bx = face_box["x"] + pad_x
            by = face_box["y"] + pad_y
            bw = face_box["width"]
            bh = face_box["height"]
            
            face_cx = bx + bw / 2.0
            landmark_head_height = bh * 1.4
            landmark_head_top = by - 0.3 * bh
            chin_y = landmark_head_top + landmark_head_height
            face_w = bw
            search_limit_y = int(by + bh / 2)
            
        # 1. Hair Volume Detection using Foreground Mask (alpha channel)
        # Convert the alpha channel of the padded image to numpy array
        padded_alpha = np.array(padded_rgba.getchannel("A"))
        
        # Define search boundaries horizontally centered around face_cx
        x_min_search = max(0, int(face_cx - 1.0 * face_w))
        x_max_search = min(padded_alpha.shape[1], int(face_cx + 1.0 * face_w))
        
        mask_head_top = None
        min_pixels = max(3, int(face_w * 0.05)) # Avoid noise / single hair strands
        
        # Scan from top of the image to search_limit_y to find the true top of hair/head
        search_limit_y = min(padded_alpha.shape[0], max(0, int(search_limit_y)))
        for y in range(0, search_limit_y):
            row_alpha = padded_alpha[y, x_min_search:x_max_search]
            if np.sum(row_alpha > 50) >= min_pixels:
                mask_head_top = y
                break
                
        # Determine the final true head top using mask and landmark estimates
        if mask_head_top is not None:
            # Prefer the mask top, but bound it to prevent noise from taking over
            head_top = min(mask_head_top, landmark_head_top)
            # Limit the deviation to 35% of the standard head height above standard crown
            head_top = max(head_top, landmark_head_top - 0.35 * landmark_head_height)
        else:
            head_top = landmark_head_top
            
        # Physical head height including voluminous hair
        H_head = chin_y - head_top
        
        # 2. Dynamic 66.7% (2/3) Head Ratio and Shoulder Visibility Constraints
        # Let ratio = H_head / H_photo
        # Starting with the target 66.7% head ratio
        ratio = 0.667
        H_photo = H_head / ratio
        
        # Ensure shoulders/clavicle are visible by enforcing a minimum bottom crop
        # Clavicle/shoulders line starts around 0.28 * landmark_head_height below the chin
        min_shoulder_space = 0.28 * landmark_head_height
        required_bottom = chin_y + min_shoulder_space
        
        # We need crop_bottom = head_top + 0.90 * H_photo >= required_bottom
        # So: H_photo >= (required_bottom - head_top) / 0.90
        current_bottom = head_top + 0.90 * H_photo
        if current_bottom < required_bottom:
            needed_H_photo = (required_bottom - head_top) / 0.90
            needed_ratio = H_head / needed_H_photo
            # Limit the ratio dynamically to the [0.60, 0.70] range (around 0.667)
            ratio = np.clip(needed_ratio, 0.60, 0.70)
            H_photo = H_head / ratio
            
        # 3. Calculate Crop Box Coordinates
        # Top gap is exactly 10% of the photo height (0.10 * H_photo)
        crop_top = head_top - 0.10 * H_photo
        crop_bottom = crop_top + H_photo
        
        # Centering horizontally perfectly
        target_photo_width = H_photo * (width_px / height_px)
        crop_left = face_cx - target_photo_width / 2.0
        crop_right = face_cx + target_photo_width / 2.0
        
    else:
        # Fall back to standard bounding box cropping if no face is detected
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
        sub_aspect = sub_w / max(1, sub_h)
        
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
    
    # Crop from padded image and resize to specifications
    cropped = padded_rgba.crop((crop_left, crop_top, crop_right, crop_bottom))
    final_img = cropped.resize((width_px, height_px), Image.Resampling.LANCZOS)
    
    return final_img, {"cropBox": [int(crop_left - pad_x), int(crop_top - pad_y), int(crop_right - pad_x), int(crop_bottom - pad_y)]}


