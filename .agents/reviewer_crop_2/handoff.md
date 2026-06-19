# Handoff Report - Crop Implementation Review

## 1. Observation

Direct observations and quotes from `server/id_photo_engine_minimal/crop.py` and test commands.

### File and Code Observations:
- **Path**: `server/id_photo_engine_minimal/crop.py`
- **Dynamic 70% Head Ratio & Bottom Margin (Lines 96-116)**:
  ```python
        # 2. Dynamic 70% Head Ratio and Shoulder Visibility Constraints
        # Let ratio = H_head / H_photo
        # Starting with the target 70% head ratio
        ratio = 0.70
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
            # Limit the ratio dynamically to the [0.65, 0.75] range
            ratio = np.clip(needed_ratio, 0.65, 0.75)
            H_photo = H_head / ratio
  ```
- **Hair Volume Mask Detection (Lines 66-94)**:
  ```python
        # 1. Hair Volume Detection using Foreground Mask (alpha channel)
        # Convert the alpha channel of the padded image to numpy array
        padded_alpha = np.array(padded_rgba.getchannel("A"))
        
        # Define search boundaries horizontally centered around face_cx
        x_min_search = max(0, int(face_cx - 1.0 * face_w))
        x_max_search = min(padded_alpha.shape[1], int(face_cx + 1.0 * face_w))
        
        mask_head_top = None
        min_pixels = max(3, int(face_w * 0.05)) # Avoid noise / single hair strands
        
        # Scan from top of the image to search_limit_y to find the true top of hair/head
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
  ```
- **Top Margin & Centering (Lines 119-125)**:
  ```python
        # 3. Calculate Crop Box Coordinates
        # Top gap is exactly 10% of the photo height (0.10 * H_photo)
        crop_top = head_top - 0.10 * H_photo
        crop_bottom = crop_top + H_photo
        
        # Centering horizontally perfectly
        target_photo_width = H_photo * (width_px / height_px)
        crop_left = face_cx - target_photo_width / 2.0
        crop_right = face_cx + target_photo_width / 2.0
  ```
- **Robustness and Fallback (Lines 21-34, 127-162)**:
  Guarantees safe parsing of landmarks and fallback to `faceBox` if landmarks are missing, and fallback to alpha bounding box calculation if both are missing.
  Handles empty images gracefully without crashes (Lines 133-135).

---

## 2. Logic Chain

1. **Dynamic 70% head ratio constraint**: From line 96, the algorithm starts at `ratio = 0.70` (70%) and adjusts `H_photo` depending on shoulder visibility. If adjustment is required, the new ratio is clipped to `[0.65, 0.75]` using `np.clip(needed_ratio, 0.65, 0.75)`. Therefore, the output head ratio is mathematically constrained strictly within 65% to 75%.
2. **Hair volume mask detection**: Lines 66-94 extract the alpha channel of the padded image, scan top-to-bottom within the horizontal boundaries `[face_cx - face_w, face_cx + face_w]` to find `mask_head_top`, and then combine this with `landmark_head_top` under a max deviation boundary (`max(head_top, landmark_head_top - 0.35 * landmark_head_height)`). This correctly handles hair volume while preventing upper-bound noise.
3. **Proper top margin and shoulder bottom margins**: Line 119 sets `crop_top` to exactly `0.10 * H_photo` above `head_top` (10% top margin). The bottom constraint uses `min_shoulder_space = 0.28 * landmark_head_height` to ensure the shoulders/clavicle are visible.
4. **Perfect horizontal centering**: Lines 123-125 center the photo perfectly around `face_cx` (the eye center x-coordinate or face box center), while calculating `target_photo_width` based on the target aspect ratio (`width_px / height_px`).
5. **Adaptive sizing**: No hardcoded pixel coordinates or sizes are used for margins or crops. The algorithm scales entirely based on face/head dimensions (`landmark_head_height`, `face_cx`, `H_photo`).
6. **Missing landmarks & Edge conditions**: The code handles missing landmarks by falling back to `faceBox` (Lines 53-64) and falling back to alpha bounding box cropping (Lines 127-162) if no face features exist, and gracefully resizes empty images without failing.

---

## 3. Caveats

- **Computational Complexity**: While correct, the foreground mask scanning runs a Python loop (`for y in range(0, search_limit_y)`) over rows of a numpy array. For very high-resolution images, this row-by-row scanning could add minor latency, though in practice it is bound by `search_limit_y`.
- **Rembg Performance**: Performance of the overall API relies heavily on the background removal step, which takes ~4-12 seconds on CPU depending on system load. This is outside the crop logic itself but limits test execution speed.

---

## 4. Conclusion

The cropping implementation in `server/id_photo_engine_minimal/crop.py` is **correct, complete, safe, and robust**. It satisfies all functional requirements and handles edge cases/fallbacks correctly without introducing any integrity violations.

**Verdict**: **APPROVE**

---

## 5. Verification Method

To verify the cropping logic independently, you can run the following test commands:

```bash
# 1. Run the targeted unit test script (which was created and verified to run successfully)
python server/test_crop_units.py

# 2. Run the server's quality regression script to verify against real samples
npm run verify:id-photo-quality
```

### Invalidation Conditions:
- If `H_photo` calculation is changed such that `head_ratio` can exceed `[0.65, 0.75]`.
- If the `np.sum(row_alpha > 50)` scanning logic is broken or does not correctly identify the hair top.

---

## Quality Review Report

**Verdict**: **APPROVE**

### Verified Claims
- **Dynamic 70% (strictly 65% to 75%) head ratio** → verified via unit test Case 1 & Case 2 → **PASS**
- **Hair volume mask detection** → verified via unit test Case 1 & Case 2 → **PASS**
- **Proper margins (10% top, shoulder bottom)** → verified via unit test Case 1 → **PASS**
- **Perfect horizontal centering** → verified via unit test Case 1 & Case 2 → **PASS**
- **Adaptive sizing** → verified via unit test Case 1, 2, 3 → **PASS**
- **Fallback logic (faceBox, bounding box, empty)** → verified via unit test Case 2, 3, 4 → **PASS**

---

## Challenge Report (Adversarial Critic)

**Overall risk assessment**: **LOW**

### Challenges
- **Challenge**: Out-of-bounds crop coordinate vulnerability.
- **Scenario**: If `crop_left` or `crop_top` goes negative or exceeds the padded image dimensions due to extreme aspect ratios or face alignments.
- **Assessment**: PIL's `Image.crop` handles out-of-bounds coordinates gracefully by filling them with the background color (`(0, 0, 0, 0)` transparent). Additionally, the padding size (`pad_x = orig_w`, `pad_y = orig_h`) is extremely generous (tripling the image canvas size), making out-of-bounds occurrences practically impossible for normal inputs.
