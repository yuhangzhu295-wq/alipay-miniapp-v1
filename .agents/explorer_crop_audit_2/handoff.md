# Handoff Report: Cropping Algorithm Audit & Optimization Plan

We have conducted a thorough read-only investigation of the cropping algorithm in `server/id_photo_engine_minimal/crop.py` and proposed a mathematically rigorous, fully relative, and robust cropping algorithm that incorporates hair volume detection, dynamic head ratios, shoulder visibility constraints, and horizontal centering.

---

## 1. Observation

In the current codebase at `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器`:
- The cropping logic is located in `server/id_photo_engine_minimal/crop.py` (lines 1 to 135).
- It relies on `face_res` from `detect_face()` (defined in `server/services/face_detector.py`) to obtain landmarks or face boxes.
- For landmarks (lines 48-65), the head height estimation and cropping coordinates are calculated as follows:
  ```python
  48:         eye_dist = np.hypot(left_eye_x - right_eye_x, left_eye_y - right_eye_y)
  49:         head_height = eye_dist * 3.8
  50:         
  51:         # Eyes are at about 0.55 of head height (chin to crown) from the chin.
  52:         # Crown is at head_top = eye_center_y - 0.45 * head_height.
  53:         head_top = eye_center_y - 0.45 * head_height
  54:         
  55:         # Crop the subject so the face is horizontally centered, and the head height (chin to crown)
  56:         # occupies approximately 2/3 of the total photo height.
  57:         target_photo_height = head_height * 1.5
  58:         
  59:         # We place the crown at 10% from the top of the photo.
  60:         crop_top = head_top - 0.10 * target_photo_height
  61:         crop_bottom = crop_top + target_photo_height
  62:         
  63:         target_photo_width = target_photo_height * (width_px / height_px)
  64:         crop_left = face_cx - target_photo_width / 2.0
  65:         crop_right = face_cx + target_photo_width / 2.0
  ```
- Similarly, for the face box (lines 67-88):
  ```python
  77:         head_height = bh * 1.4
  78:         # Top of the head is about 0.3 * faceBox height above faceBox top
  79:         head_top = by - 0.3 * bh
  80:         
  81:         target_photo_height = head_height * 1.5
  82:         crop_top = head_top - 0.10 * target_photo_height
  83:         crop_bottom = crop_top + target_photo_height
  ...
  ```

---

## 2. Logic Chain

From the observations:
1. **Fixed Head Ratio**: Currently, `target_photo_height = head_height * 1.5` implies a fixed head ratio of $1 / 1.5 \approx 66.7\%$. There is no mechanism to adapt the head ratio to different specifications or body constraints.
2. **Missing Hair Volume Detection**: The head top (crown) is estimated purely statistically (`eye_center_y - 0.45 * head_height` or `by - 0.3 * bh`), which fails for subjects with voluminous hair, leading to chopped hair tops.
3. **No Dynamic Shoulder Constraint**: There is no constraint checking if the bottom crop coordinate (`crop_bottom`) actually extends low enough to include the shoulders/clavicle region.
4. **Aspect Ratio Adaptiveness**: While horizontal scale adapts using the input aspect ratio `(width_px / height_px)`, it operates on a fixed head ratio, meaning tight crops on wide specs (like creative avatars) could cut shoulders excessively.

To resolve these issues, we formulate the following step-by-step math and logic:

### Step 2.1: Landmark / FaceBox Coordinates & Center
Let the padded image coordinates of landmarks be:
$$x'_{\text{eye}} = x_{\text{eye}} + P_x, \quad y'_{\text{eye}} = y_{\text{eye}} + P_y$$
The horizontal face center $CX_{\text{face}}$ is:
$$CX_{\text{face}} = \frac{x'_{\text{leftEye}} + x'_{\text{rightEye}}}{2.0} \quad \text{or} \quad bx + \frac{bw}{2.0}$$

This guarantees perfect horizontal centering by setting:
$$X_{\text{left}} = CX_{\text{face}} - \frac{W_{\text{final}}}{2.0}, \quad X_{\text{right}} = CX_{\text{face}} + \frac{W_{\text{final}}}{2.0}$$

### Step 2.2: Statistical Head Bounds
We compute the estimated head height $H_{\text{head\_est}}$ and landmark scalp coordinate $Y_{\text{crown\_est}}$:
- Landmarks: $H_{\text{head\_est}} = D_{\text{eye}} \times 3.8$, $Y_{\text{crown\_est}} = CY_{\text{eye}} - 0.45 \times H_{\text{head\_est}}$
- FaceBox: $H_{\text{head\_est}} = bh \times 1.4$, $Y_{\text{crown\_est}} = by - 0.3 \times bh$

The chin coordinate is always:
$$Y_{\text{chin}} = Y_{\text{crown\_est}} + H_{\text{head\_est}}$$

### Step 2.3: Hair Volume Detection using Alpha Mask
1. We scan the alpha channel $A(y, x)$ of the original image inside a vertical band centered on the face center:
   $$\text{ScanWidth} = D_{\text{eye}} \times 2.0 \quad \text{or} \quad bw \times 1.2$$
   $$X_{\text{scan\_start}} = \text{clamp}\left(0, W_{\text{orig}}, CX_{\text{face}} - P_x - \frac{\text{ScanWidth}}{2.0}\right)$$
   $$X_{\text{scan\_end}} = \text{clamp}\left(0, W_{\text{orig}}, CX_{\text{face}} - P_x + \frac{\text{ScanWidth}}{2.0}\right)$$
2. Scan from $y=0$ to $y=H_{\text{orig}}-1$. The first row $y_{\text{mask}}$ containing significant alpha density (solid hair/scalp) is defined by:
   $$\sum_{x=X_{\text{scan\_start}}}^{X_{\text{scan\_end}}-1} \mathbb{I}(A(y, x) > 50) \ge \max\left(3, \lfloor 0.05 \times \text{ScanWidth} \rfloor\right)$$
3. Map to padded coordinates: $Y_{\text{crown\_mask}} = y_{\text{mask}} + P_y$.
4. Clamp the mask top to a maximum hair thickness of $25\%$ of head height to avoid noise/background artifacts:
   $$Y_{\text{crown\_clamped}} = \max\left(Y_{\text{crown\_mask}}, Y_{\text{crown\_est}} - 0.25 \times H_{\text{head\_est}}\right)$$
5. Reconcile with landmark top (we take the higher/smaller y-coordinate to prevent clipping the skull):
   $$Y_{\text{crown\_true}} = \min\left(Y_{\text{crown\_est}}, Y_{\text{crown\_clamped}}\right)$$
6. Calculate true head height:
   $$H_{\text{head\_true}} = Y_{\text{chin}} - Y_{\text{crown\_true}}$$

### Step 2.4: Shoulder Visibility & Dynamic Head Ratio
- Clavicle/shoulder line is located at:
  $$Y_{\text{shoulder}} = Y_{\text{chin}} + K_{\text{shoulder}} \times H_{\text{head\_est}} \quad (\text{with } K_{\text{shoulder}} = 0.35)$$
- Enforcing top gap of $10\%$ and $Y_{\text{photo\_bottom}} \ge Y_{\text{shoulder}}$ requires:
  $$H_{\text{photo}} \ge H_{\text{min}} = \frac{H_{\text{head\_true}} + K_{\text{shoulder}} \times H_{\text{head\_est}}}{0.90}$$
- Under target ratio $R_{\text{target}} = 0.70$, the target photo height is:
  $$H_{\text{target}} = \frac{H_{\text{head\_true}}}{0.70}$$
- Candidate photo height: $H_{\text{candidate}} = \max(H_{\text{target}}, H_{\text{min}})$.
- Candidate ratio: $R_{\text{candidate}} = H_{\text{head\_true}} / H_{\text{candidate}}$.
- Clamp to allowed range $[0.65, 0.75]$:
  $$R_{\text{final}} = \max(0.65, \min(0.75, R_{\text{candidate}}))$$
- Final crop height: $H_{\text{final}} = H_{\text{head\_true}} / R_{\text{final}}$.
- Crop vertical bounds:
  $$Y_{\text{top}} = Y_{\text{crown\_true}} - 0.10 \times H_{\text{final}}$$
  $$Y_{\text{bottom}} = Y_{\text{top}} + H_{\text{final}}$$

---

## 3. Caveats

- **Out-of-boundary shoulders**: If the original image is cropped tightly below the chin (i.e. does not contain shoulders), the crop bottom will extend into the padded area, showing a transparent bottom. This is expected behavior for deficient input, and should be captured by the upstream `validate_segmentation_mask` quality check.
- **Scanning Band Width**: The scanning width ($2.0 \times D_{\text{eye}}$ or $1.2 \times bw$) assumes standard head aspect ratio. Exceptionally wide hairstyles might be partially outside the scanning band, but widening the band too much increases the risk of picking up background noise or raised hands.

---

## 4. Conclusion & Proposed Implementation

Replacing the hardcoded cropping logic in `crop.py` with this adaptive formulation will fully satisfy the dynamic 65%–75% head ratio, voluminous hair handling, shoulder inclusion, and horizontal centering across all specifications.

### Proposed Code Replacement for `server/id_photo_engine_minimal/crop.py`

#### Before (Lines 37–88)
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
```

#### After
```python
    # Extract alpha channel to detect hair volume
    alpha_arr = np.array(rgba.getchannel("A"))
    orig_w, orig_h = rgba.size

    if has_landmarks:
        landmarks = face_res["landmarks"]
        left_eye_x = landmarks["leftEye"]["x"] + pad_x
        left_eye_y = landmarks["leftEye"]["y"] + pad_y
        right_eye_x = landmarks["rightEye"]["x"] + pad_x
        right_eye_y = landmarks["rightEye"]["y"] + pad_y
        
        face_cx = (left_eye_x + right_eye_x) / 2.0
        eye_center_y = (left_eye_y + right_eye_y) / 2.0
        
        eye_dist = np.hypot(left_eye_x - right_eye_x, left_eye_y - right_eye_y)
        head_height_est = eye_dist * 3.8
        
        landmark_head_top = eye_center_y - 0.45 * head_height_est
        chin_y = landmark_head_top + head_height_est
        
        # 1. Hair Volume Detection via Alpha Channel
        orig_cx = face_cx - pad_x
        orig_head_w = eye_dist * 2.0
        x_start_orig = max(0, int(orig_cx - orig_head_w / 2.0))
        x_end_orig = min(orig_w, int(orig_cx + orig_head_w / 2.0))
        
        mask_head_top_y = None
        for y in range(orig_h):
            row_pixels = alpha_arr[y, x_start_orig:x_end_orig]
            # Threshold to filter noise: count pixels with alpha > 50
            if np.sum(row_pixels > 50) >= max(3, int(orig_head_w * 0.05)):
                mask_head_top_y = y
                break
                
        if mask_head_top_y is not None:
            mask_head_top = mask_head_top_y + pad_y
            # Clamp mask top to avoid noise: not higher than landmark_head_top - 0.25 * head_height_est
            clamp_mask_top = max(mask_head_top, landmark_head_top - 0.25 * head_height_est)
            # Reconcile: true head top must not cut off skull (so <= landmark_head_top)
            true_head_top = min(landmark_head_top, clamp_mask_top)
        else:
            true_head_top = landmark_head_top
            
        true_head_height = chin_y - true_head_top
        
        # 2. Dynamic Head Ratio & Shoulder Visibility Constraint
        # Target head ratio = 70%. Top gap is 10% of photo height.
        # Bottom of photo should extend at least 0.35 * head_height_est below chin_y
        K_shoulder = 0.35
        min_bottom_y = chin_y + K_shoulder * head_height_est
        H_min = (min_bottom_y - true_head_top) / 0.90
        
        H_target = true_head_height / 0.70
        H_final = max(H_target, H_min)
        
        R_final = true_head_height / H_final
        R_final = max(0.65, min(0.75, R_final))
        
        target_photo_height = true_head_height / R_final
        
        crop_top = true_head_top - 0.10 * target_photo_height
        crop_bottom = crop_top + target_photo_height
        
        target_photo_width = target_photo_height * (width_px / height_px)
        crop_left = face_cx - target_photo_width / 2.0
        crop_right = face_cx + target_photo_width / 2.0
        
    elif has_facebox:
        face_box = face_res["faceBox"]
        bx = face_box["x"] + pad_x
        by = face_box["y"] + pad_y
        bw = face_box["width"]
        bh = face_box["height"]
        
        face_cx = bx + bw / 2.0
        head_height_est = bh * 1.4
        
        landmark_head_top = by - 0.3 * bh
        chin_y = landmark_head_top + head_height_est
        
        # 1. Hair Volume Detection via Alpha Channel
        orig_cx = face_cx - pad_x
        orig_head_w = bw * 1.2
        x_start_orig = max(0, int(orig_cx - orig_head_w / 2.0))
        x_end_orig = min(orig_w, int(orig_cx + orig_head_w / 2.0))
        
        mask_head_top_y = None
        for y in range(orig_h):
            row_pixels = alpha_arr[y, x_start_orig:x_end_orig]
            if np.sum(row_pixels > 50) >= max(3, int(orig_head_w * 0.05)):
                mask_head_top_y = y
                break
                
        if mask_head_top_y is not None:
            mask_head_top = mask_head_top_y + pad_y
            clamp_mask_top = max(mask_head_top, landmark_head_top - 0.25 * head_height_est)
            true_head_top = min(landmark_head_top, clamp_mask_top)
        else:
            true_head_top = landmark_head_top
            
        true_head_height = chin_y - true_head_top
        
        # 2. Dynamic Head Ratio & Shoulder Visibility Constraint
        K_shoulder = 0.35
        min_bottom_y = chin_y + K_shoulder * head_height_est
        H_min = (min_bottom_y - true_head_top) / 0.90
        
        H_target = true_head_height / 0.70
        H_final = max(H_target, H_min)
        
        R_final = true_head_height / H_final
        R_final = max(0.65, min(0.75, R_final))
        
        target_photo_height = true_head_height / R_final
        
        crop_top = true_head_top - 0.10 * target_photo_height
        crop_bottom = crop_top + target_photo_height
        
        target_photo_width = target_photo_height * (width_px / height_px)
        crop_left = face_cx - target_photo_width / 2.0
        crop_right = face_cx + target_photo_width / 2.0
```

---

## 5. Verification Method

To independently verify this implementation:
1. **Unit Test Formulation**:
   Run a Python test script targeting `crop_id_photo` directly. We can construct a mock `RGBA` image containing a white circle/square representing the head, and a mock `face_res` dictionary:
   ```python
   # Mock face_res structure:
   face_res = {
       "success": True,
       "landmarks": {
           "leftEye": {"x": 100, "y": 120},
           "rightEye": {"x": 150, "y": 120}
       }
   }
   ```
   We can assert that:
   - The returned crop box has a height `H` where `head_height_est / H` is within $[0.65, 0.75]$.
   - If we add mock white pixels in the alpha channel above `landmark_head_top` (representing voluminous hair), the crop box `crop_top` coordinate shifts upwards accordingly, and the output `cropBox` adapts correctly.
   - The crop box horizontal center `(crop_left + crop_right) / 2.0` matches the face center `125` perfectly.
2. **Integration Verification Command**:
   Start the backend services:
   ```powershell
   cd server
   $env:PYTHONIOENCODING="utf-8"
   python main.py
   ```
   And then run the verification script using:
   ```powershell
   python server/test_server.py
   ```
3. **Invalidation Conditions**:
   - If `R_final` falls outside $[0.65, 0.75]$ for any valid input image.
   - If the hair top is clipped when processing a portrait with high hair volume.
   - If the horizontal midpoint of the crop box does not align with the midpoint of the eye coordinates.
