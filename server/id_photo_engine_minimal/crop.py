from PIL import Image
import numpy as np

from PIL import Image
import numpy as np

def crop_id_photo(
    rgba: Image.Image,
    width_px: int,
    height_px: int,
    face_res: dict = None,
    composition_profile: dict = None,
):
    # If no target width/height, return original
    if not width_px or not height_px:
        return rgba, {}

    profile = dict(composition_profile or {})
    head_height_min = float(profile.get("headHeightRatioMin") or 0.58)
    head_height_max = float(
        profile.get("headHeightRatioMax")
        or profile.get("operationalHeadHeightRatioMax")
        or 0.70
    )
    top_min = float(profile.get("topMarginRatioMin") or 0.066)
    top_max = float(profile.get("topMarginRatioMax") or 0.123)
    target_head_ratio = float(
        profile.get("headHeightRatioTarget") or ((head_height_min + head_height_max) / 2.0)
    )
    target_head_ratio = min(head_height_max, max(head_height_min, target_head_ratio))
    target_top_ratio = float(
        profile.get("topMarginRatioTarget") or ((top_min + top_max) / 2.0)
    )
    target_top_ratio = min(top_max, max(top_min, target_top_ratio))

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
                if (
                    le["x"] is not None
                    and le["y"] is not None
                    and re["x"] is not None
                    and re["y"] is not None
                ):
                    has_landmarks = True
        if not has_landmarks and face_box and "x" in face_box and "y" in face_box and "width" in face_box and "height" in face_box:
            if (
                face_box["x"] is not None
                and face_box["y"] is not None
                and face_box["width"] is not None
                and face_box["height"] is not None
            ):
                has_facebox = True

    if has_landmarks or has_facebox:
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

        # 1. Hair Volume Detection from Foreground Alpha Mask
        padded_alpha = np.array(padded_rgba.getchannel("A"))
        x_min_search = max(0, int(face_cx - 1.0 * face_w))
        x_max_search = min(padded_alpha.shape[1], int(face_cx + 1.0 * face_w))

        mask_head_top = None
        min_pixels = max(3, int(face_w * 0.05))
        search_limit_y = min(padded_alpha.shape[0], max(0, int(search_limit_y)))

        for y in range(0, search_limit_y):
            row_alpha = padded_alpha[y, x_min_search:x_max_search]
            if np.sum(row_alpha > 50) >= min_pixels:
                mask_head_top = y
                break

        # Anatomical skull head height vs hair envelope top
        anatomical_head_height = landmark_head_height
        if mask_head_top is not None:
            hair_head_top = min(mask_head_top, landmark_head_top)
            # Bound hair top offset to prevent hair volume from shrinking anatomical face size
            hair_head_top = max(hair_head_top, landmark_head_top - 0.20 * landmark_head_height)
        else:
            hair_head_top = landmark_head_top

        # Base photo height on anatomical face height scale
        H_photo = anatomical_head_height / target_head_ratio

        # Calculate crop top with target top margin
        crop_top = hair_head_top - target_top_ratio * H_photo
        # Ensure hair top is inside photo and does not touch top boundary
        if mask_head_top is not None and crop_top > mask_head_top - top_min * H_photo:
            crop_top = mask_head_top - top_min * H_photo

        crop_bottom = crop_top + H_photo

        # 2. Torso Center of Mass & Shoulder Symmetry Balance
        # Scan lower body alpha to find shoulder and torso center
        lower_y1 = int(min(padded_alpha.shape[0] - 1, chin_y + 0.1 * landmark_head_height))
        lower_y2 = int(min(padded_alpha.shape[0], crop_bottom))

        torso_cx = face_cx
        lower_alpha = padded_alpha[lower_y1:lower_y2, :]
        l_ys, l_xs = np.where(lower_alpha > 30)
        if l_xs.size > 0:
            torso_cx = float(np.mean(l_xs))
            shoulder_left = float(np.percentile(l_xs, 5))
            shoulder_right = float(np.percentile(l_xs, 95))
            shoulder_cx = (shoulder_left + shoulder_right) / 2.0
            # Balanced visual center
            visual_cx = 0.55 * face_cx + 0.30 * shoulder_cx + 0.15 * torso_cx
        else:
            visual_cx = face_cx

        # Limit deviation of visual center from face_cx to prevent excessive shift
        target_photo_width = H_photo * (width_px / height_px)
        max_shift = 0.015 * target_photo_width
        visual_cx = min(face_cx + max_shift, max(face_cx - max_shift, visual_cx))

        crop_left = visual_cx - target_photo_width / 2.0
        crop_right = crop_left + target_photo_width

    else:
        arr = np.array(rgba)
        alpha = arr[:, :, 3]
        y_indices, x_indices = np.where(alpha > 0)

        if len(y_indices) == 0:
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

    # 3. Bottom Contact & Lower Torso Mask Extension (Prevent foregroundBottomGapPx > 0)
    # Extract crop area from padded_rgba
    cropped = padded_rgba.crop((crop_left, crop_top, crop_right, crop_bottom))
    crop_arr = np.array(cropped)
    c_alpha = crop_arr[:, :, 3]

    # Find the lowest row with non-zero alpha in cropped RGBA
    y_non_zero = np.where(np.any(c_alpha > 20, axis=1))[0]
    if y_non_zero.size > 0:
        last_fg_y = int(y_non_zero[-1])
        # If the torso alpha ends before the bottom row, duplicate the bottom non-zero torso row down
        if last_fg_y < c_alpha.shape[0] - 1:
            last_row = crop_arr[last_fg_y:last_fg_y + 1, :, :].copy()
            crop_arr[last_fg_y + 1:, :, :] = last_row
            cropped = Image.fromarray(crop_arr, "RGBA")

    final_img = cropped.resize((width_px, height_px), Image.Resampling.LANCZOS)

    return final_img, {
        "cropBox": [
            int(crop_left - pad_x),
            int(crop_top - pad_y),
            int(crop_right - pad_x),
            int(crop_bottom - pad_y),
        ]
    }



