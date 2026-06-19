# Handoff Report: ID Photo Cropping Algorithm Audit

## 1. Observation
The existing cropping algorithm is defined in `server/id_photo_engine_minimal/crop.py` (lines 37-88):
```python
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
```
Key observations regarding constraints and requirements:
1. **Ratio**: The code hardcodes `target_photo_height = head_height * 1.5` which translates to a head ratio of `head_height / target_photo_height = 1 / 1.5 = 66.67%`.
2. **Hair Volume / Top of Head**: The `head_top` is calculated solely using geometric landmarks (`head_top = eye_center_y - 0.45 * head_height`), disregarding the actual foreground mask (alpha channel). For subjects with voluminous hair, this causes the top of their hair to be cut off.
3. **Top Gap**: The top gap is set to `0.10 * target_photo_height` relative to the estimated `head_top`.
4. **Centering**: The crop box is horizontally centered around `face_cx` (the eye midpoint).
5. **Adaptiveness**: The crop box dimensions adapt to the target spec aspect ratio `(width_px / height_px)`, meaning it does not rely on hardcoded pixel sizes.

---

## 2. Logic Chain
To satisfy the five requirements, we propose the following logic and mathematical derivation:

### Step 1: Base Facial Landmark & Face Box Calculations
First, we compute the coordinates in the padded space:
- **With Landmarks**:
  - `face_cx = (left_eye_x + right_eye_x) / 2.0`
  - `eye_center_y = (left_eye_y + right_eye_y) / 2.0`
  - `eye_dist = hypot(left_eye_x - right_eye_x, left_eye_y - right_eye_y)`
  - `landmark_head_height = eye_dist * 3.8` (standard height)
  - `landmark_head_top = eye_center_y - 0.45 * landmark_head_height`
  - `chin_y = eye_center_y + 0.55 * landmark_head_height`
  - `face_w = eye_dist * 2.0`
  - `search_limit_y = int(eye_center_y)`
- **With Face Box**:
  - `face_cx = bx + bw / 2.0`
  - `landmark_head_height = bh * 1.4`
  - `landmark_head_top = by - 0.3 * bh`
  - `chin_y = landmark_head_top + landmark_head_height = by + 1.1 * bh`
  - `face_w = bw`
  - `search_limit_y = int(by + bh / 2)`

### Step 2: Hair Volume Detection (Requirement 2)
We extract the alpha channel of the padded image `padded_alpha`. To find the true head/hair top, we search for the highest non-transparent row `y` within the head's horizontal bounds:
- Horizontal span: `x_min_search = max(0, int(face_cx - 1.0 * face_w))` to `x_max_search = min(padded_alpha.shape[1], int(face_cx + 1.0 * face_w))`
- Threshold for noise robustness: `min_pixels = max(3, int(face_w * 0.05))` pixels in the row having alpha value `> 50`.
- We iterate `y` from `0` to `search_limit_y`. The first row matching the threshold is `mask_head_top`.
- The hair-volume adjusted top of the head is:
  $$\text{head\_top} = \max(\min(\text{mask\_head\_top}, \text{landmark\_head\_top}), \text{landmark\_head\_top} - 0.35 \times \text{landmark\_head\_height})$$
  *(The max bounding prevents background noise above the head from creating an excessively high crop).*
- This gives the true hair-inclusive head height: `H_head = chin_y - head_top`.

### Step 3: Dynamic Head Ratio and Shoulder Visibility (Requirements 1 & 3)
Let $H_{\text{photo}}$ be the crop height and $R$ be the head-to-photo height ratio ($H_{\text{head}} / H_{\text{photo}}$).
- **Target Ratio**: We start with the default $R = 0.70$ (70% head ratio).
- **Initial Crop Height**: $H_{\text{photo}} = H_{\text{head}} / 0.70$.
- **Top Gap Constraint**: The top gap is 10% of the photo height.
  - `crop_top = head_top - 0.10 * H_photo`
  - `crop_bottom = crop_top + H_photo = head_top + 0.90 * H_photo`
- **Shoulder Visibility Constraint**: The shoulders/clavicle must remain visible at the bottom. The clavicle/shoulder line starts around $0.28 \times \text{landmark\_head\_height}$ below the chin:
  - `required_bottom = chin_y + 0.28 * landmark_head_height`
  - If the initial `crop_bottom` is less than `required_bottom`, we increase $H_{\text{photo}}$:
    $$H_{\text{photo, needed}} = \frac{\text{required\_bottom} - \text{head\_top}}{0.90} = \frac{H_{\text{head}} + 0.28 \times \text{landmark\_head\_height}}{0.90}$$
  - The corresponding adjusted ratio is:
    $$R_{\text{needed}} = \frac{H_{\text{head}}}{H_{\text{photo, needed}}}$$
  - We clamp this dynamic ratio to the specified range $[0.65, 0.75]$:
    $$R_{\text{final}} = \text{clamp}(R_{\text{needed}}, 0.65, 0.75)$$
  - The final crop height is $H_{\text{photo}} = H_{\text{head}} / R_{\text{final}}$.

### Step 4: Horizontal Centering & Adaptiveness (Requirements 4 & 5)
- **Centering**: The horizontal coordinates are perfectly centered around `face_cx`:
  - `target_photo_width = H_photo * (width_px / height_px)`
  - `crop_left = face_cx - target_photo_width / 2.0`
  - `crop_right = face_cx + target_photo_width / 2.0`
- **Adaptiveness**: All coordinates are defined relative to the input photo scale and target aspect ratio. No pixel values are hardcoded, making the algorithm fully adaptive to any target specifications (1-inch, 2-inch, ID card, etc.).

---

## 3. Caveats
1. **Alpha Channel Quality**: The hair volume detection assumes the alpha channel has already been cleaned of floating background noise. This is guaranteed by the previous stage (`cleanup_alpha` in `alpha_cleanup.py`).
2. **Exotic Hairstyles/Hats**: Extremely tall hats or massive hairstyles might hit the safety constraint of $0.35 \times \text{landmark\_head\_height}$ above the standard crown. This safety limit is necessary to prevent weird crops on photos with background clutter or objects held above the head.

---

## 4. Conclusion
The proposed cropping algorithm addresses all five requirements:
- Dynamically adjusts the head ratio between 65% and 75% (targeting 70%) to accommodate shoulder visibility.
- Incorporates the alpha channel mask to detect hair volume and prevent top-cutoff.
- Guarantees a 10% top gap and ensures the bottom extends far enough below the chin to capture the clavicle/shoulders.
- Perfectly centers the face horizontally.
- Adapts cleanly to any target specification without hardcoded limits.

The fully integrated code solution is saved in `.agents/explorer_crop_audit_1/proposed_crop.py`.

---

## 5. Verification Method
1. **Source Code Inspections**: Verify that `server/id_photo_engine_minimal/crop.py` is updated with the logic implemented in `.agents/explorer_crop_audit_1/proposed_crop.py`.
2. **Local End-to-End Test**: Run `python server/test_verify.py` or the server main flow script `python server/scripts/verify_main_flow.py` to ensure the server processes image inputs successfully and returns a cropped photo.
3. **Visual Invalidation**: Using sample images with voluminous hair and standard hair:
   - Ensure the top of voluminous hair is NOT cut off (visible hair top should be ~10% from the top border of the photo).
   - Ensure both shoulders are visible at the bottom of the photo.
   - Verify that the horizontal center of the face lies exactly in the middle of the photo.
