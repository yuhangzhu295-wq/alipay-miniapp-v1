# Handoff Report: ID Photo Cropping Algorithm Audit

## 1. Observation
In `server/id_photo_engine_minimal/crop.py`, the cropping algorithm is defined as:
```python
def crop_id_photo(rgba: Image.Image, width_px: int, height_px: int, face_res: dict = None):
```

### Landmark-based Crop (Lines 48-65):
```python
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

### FaceBox-based Fallback Crop (Lines 75-88):
```python
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

From `server/services/face_detector.py` (Lines 256-267), `detect_face` returns landmarks and faceBox:
```python
    return {
        "success": True,
        "faceBox": face,
        ...
        "landmarks": main.get("landmarks", {}),
        ...
    }
```
where landmarks may include `"leftEye"`, `"rightEye"`, `"nose"`, and `"mouth"`.

## 2. Logic Chain
Based on the observations:
1. **Dynamic Head Ratio**:
   - The current code computes `target_photo_height = head_height * 1.5`, yielding a fixed head ratio of $1 / 1.5 = 2/3 \approx 66.67\%$.
   - To achieve a dynamic $70\%$ head ratio ($R \in [0.65, 0.75]$), we can parameterize $R$ and dynamically compute:
     $$H = \frac{H_{\text{true\_head}}}{R}$$
     where $H$ is the target photo height and $H_{\text{true\_head}}$ is the height of the head.
2. **Hair Volume Detection**:
   - The current code estimates the crown position (`head_top`) solely based on landmarks or `faceBox` heights. It does not look at the alpha channel (foreground mask) and will cut off voluminous hair.
   - The `rgba` parameter has an alpha channel that separates the subject from the background. We can scan the alpha channel in the horizontal region of the head to find the highest pixel where $\alpha > 50$. This gives the true hair top $y_{\text{mask\_top}}$. We can combine it with the landmark crown $y_{\text{landmark\_top}}$ to find the true top of the head:
     $$y_{\text{true\_top}} = \min(y_{\text{landmark\_top}}, y_{\text{mask\_top}})$$
3. **Top Gap and Shoulder Visibility Constraints**:
   - The current code places the crown at $10\%$ from the top of the photo (`crop_top = head_top - 0.10 * target_photo_height`), and hopes that the remaining $90\%$ of height includes the shoulders.
   - If we define a required bottom crop level $y_{\text{shoulder\_min}}$ (either by scanning the alpha channel width below the chin to detect the neck-shoulder transition or using landmark-based heuristics), we must satisfy:
     $$y_{\text{crop\_bottom}} \ge y_{\text{shoulder\_min}}$$
     Given $y_{\text{crop\_bottom}} = y_{\text{true\_top}} + (1 - g) \times H$, where $g \in [0.08, 0.12]$ is the top gap ratio and $H = H_{\text{true\_head}} / R$ is the photo height, we can dynamically search for a valid $(R, g)$ combination starting from the target $(0.70, 0.10)$. If the shoulder is cut off, we can decrease $R$ down to $0.65$ and decrease $g$ down to $0.08$.
4. **Horizontal Centering**:
   - The current code centers on `face_cx`, which is the eye center. This is stable, but we can make it even more robust against tilt and asymmetric eye placement by using a weighted average of eye center, nose, and mouth x-coordinates:
     $$x_{\text{face\_cx}} = 0.5 \times x_{\text{eyes}} + 0.3 \times x_{\text{nose}} + 0.2 \times x_{\text{mouth}}$$
5. **Adaptive to Specifications**:
   - The current crop calculations are scale-invariant since all bounds are calculated as proportions of $H$ in the image's coordinate space, and then the cropped portion is resized to `(width_px, height_px)` using `Image.Resampling.LANCZOS`.
   - By avoiding hardcoded pixel metrics (like absolute offsets) and computing everything relative to $H_{\text{true\_head}}$ and aspect ratio, the algorithm dynamically and perfectly scales to any specification.

## 3. Caveats
- If the original image does not have enough resolution or is too cropped, padding with transparent pixels is already performed:
  `padded_rgba = Image.new("RGBA", (orig_w + 2 * pad_x, orig_h + 2 * pad_y), (0, 0, 0, 0))`
  This is a safe operation.
- In case the input image does not have any face detected (the `else` block), we fallback to the bounding box aspect ratio crop.
- For hair detection, a noise threshold is necessary to prevent single stray pixels (matting artifacts) from altering the crown detection.

## 4. Conclusion & Proposed Implementation
To implement these improvements, the `crop_id_photo` function can be updated with the following logic:

### Math Formulation
1. **Face Center and Landmark Coordinates**:
   - $x_{\text{eyes}} = (x_{\text{left\_eye}} + x_{\text{right\_eye}}) / 2$
   - $y_{\text{eye\_center}} = (y_{\text{left\_eye}} + y_{\text{right\_eye}}) / 2$
   - $x_{\text{face\_cx}} = 0.5 \times x_{\text{eyes}} + 0.3 \times x_{\text{nose}} + 0.2 \times x_{\text{mouth}}$ (fallback to $x_{\text{eyes}}$ if nose/mouth are missing)
   - $d_{\text{eye}} = \text{Euclidean distance between eyes}$
   - $H_{\text{head}} = 3.8 \times d_{\text{eye}}$
   - $y_{\text{landmark\_top}} = y_{\text{eye\_center}} - 0.45 \times H_{\text{head}}$
   - $y_{\text{chin}} = y_{\text{eye\_center}} + 0.55 \times H_{\text{head}}$

2. **Hair Top Detection**:
   - Scan alpha channel columns within $[x_{\text{face\_cx}} - 1.2 \times d_{\text{eye}}, x_{\text{face\_cx}} + 1.2 \times d_{\text{eye}}]$.
   - Let $y_{\text{mask\_top}}$ be the first row with $\ge \max(3, 0.02 \times \text{Search Width})$ pixels where $\alpha > 50$.
   - $y_{\text{true\_top}} = \max(\min(y_{\text{landmark\_top}}, y_{\text{mask\_top}}), y_{\text{landmark\_top}} - 0.4 \times H_{\text{head}})$
   - $H_{\text{true\_head}} = y_{\text{chin}} - y_{\text{true\_top}}$

3. **Shoulder Detection**:
   - Scan alpha channel rows $y > y_{\text{chin}}$ to find foreground width $W(y) = \sum [ \alpha(y, x) > 50 ]$.
   - Find neck width $W_{\text{neck}} = \min_{y \in [y_{\text{chin}}, y_{\text{chin}} + 0.2 H_{\text{head}}]} W(y)$.
   - Find $y_{\text{shoulder\_start}}$ where $W(y) \ge 1.4 \times W_{\text{neck}}$.
   - $y_{\text{shoulder\_min}} = y_{\text{shoulder\_start}} + 0.15 \times H_{\text{head}}$ (fallback: $y_{\text{chin}} + 0.40 \times H_{\text{head}}$).

4. **Dynamic Adjustment of $R$ and $g$**:
   - Start with $R = 0.70$ and $g = 0.10$.
   - Let $S_{\text{req}} = (y_{\text{shoulder\_min}} - y_{\text{true\_top}}) / H_{\text{true\_head}}$.
   - If $(1 - g) / R < S_{\text{req}}$:
     - Solve for $R$ using $g = 0.10$: $R = 0.90 / S_{\text{req}}$.
     - If $R < 0.65$:
       - Set $R = 0.65$.
       - Solve for $g$: $g = 1.0 - 0.65 \times S_{\text{req}}$.
       - Clip $g = \max(0.08, g)$.

5. **Crop Boundaries**:
   - $H = H_{\text{true\_head}} / R$
   - $W = H \times (\text{width\_px} / \text{height\_px})$
   - $y_{\text{crop\_top}} = y_{\text{true\_top}} - g \times H$
   - $y_{\text{crop\_bottom}} = y_{\text{crop\_top}} + H$
   - $x_{\text{crop\_left}} = x_{\text{face\_cx}} - W / 2$
   - $x_{\text{crop\_right}} = x_{\text{face\_cx}} + W / 2$

## 5. Verification Method
To verify this algorithm once implemented:
1. **Local Test Run**: Run pytest (or specific script testing cropping accuracy).
2. **Visual Inspection**: Process input photos with voluminous hair and check if the hair is preserved (compared to the original algorithm).
3. **Specification Check**: Verify that the cropped image contains the shoulders/clavicle and that the head ratio is between 65% and 75% for different output aspect ratios.
