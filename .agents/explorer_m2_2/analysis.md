# Milestone 2: Legacy Isolation & Input Validation (R2, R3, R4) - Analysis Report

This report outlines the technical analysis and implementation plan for Milestone 2: Legacy Isolation, Input Validation, and Matting Adapter for the ID Photo Generator project.

---

## 1. Legacy Isolation (R2)

### 1.1 Target Files for Isolation
The legacy local ID-photo generation chain consists of the following 4 files located in `server/services/`. These must be isolated by moving them to the `server/id_photo_engine_legacy/` directory:
1. `server/services/id_photo_v2.py` -> `server/id_photo_engine_legacy/id_photo_v2.py`
2. `server/services/portrait_matting.py` -> `server/id_photo_engine_legacy/portrait_matting.py`
3. `server/services/id_photo_composer.py` -> `server/id_photo_engine_legacy/id_photo_composer.py`
4. `server/services/id_photo_quality.py` -> `server/id_photo_engine_legacy/id_photo_quality.py`

*Note: Shared services that are still used by other endpoints (such as `/api/change-bg` or `/api/professional-photo`), including `services/portrait_quality.py` and `services/face_detector.py`, will remain in `server/services/` to prevent regressions.*

### 1.2 Import Path Adjustments
When the 4 files are moved into the `id_photo_engine_legacy` package, their mutual import statements must be updated.
* **Internal Imports in `server/id_photo_engine_legacy/id_photo_v2.py`**:
  * Before:
    ```python
    from services.id_photo_composer import compose_id_photo
    from services.id_photo_quality import build_quality_report, validate_composition_metrics, validate_final_output
    from services.portrait_matting import matte_person, matting_status
    ```
  * After (relative package imports):
    ```python
    from .id_photo_composer import compose_id_photo
    from .id_photo_quality import build_quality_report, validate_composition_metrics, validate_final_output
    from .portrait_matting import matte_person, matting_status
    ```
  * Imports from `services.face_detector` and `services.portrait_quality` remain unchanged, as `server/` is on the Python path.

* **External Imports in `server/main.py`**:
  * Before:
    ```python
    from services.id_photo_v2 import (
        TemplateError,
        compose_prepared_id_photo,
        cleanup_prepare_cache,
        generate_id_photo_v2,
        get_capabilities,
        prepare_id_photo_v2,
    )
    from services.portrait_matting import matting_status
    ```
  * After:
    ```python
    from id_photo_engine_legacy.id_photo_v2 import (
        TemplateError,
        compose_prepared_id_photo,
        cleanup_prepare_cache,
        generate_id_photo_v2,
        get_capabilities,
        prepare_id_photo_v2,
    )
    from id_photo_engine_legacy.portrait_matting import matting_status
    ```

* **Dynamic Imports in `server/id_photo_engines/engine_manager.py`**:
  * The `_runtime_files()` function maps files for diagnostics. It must be updated:
    ```python
    def _runtime_files() -> dict[str, str]:
        import id_photo_engine_legacy.id_photo_v2 as id_photo_v2
        import id_photo_engine_legacy.portrait_matting as portrait_matting
        import id_photo_engine_legacy.id_photo_composer as id_photo_composer
        import id_photo_engine_legacy.id_photo_quality as id_photo_quality
        ...
        return {
            "manager": str(Path(__file__).resolve()),
            "hivisionAdapter": module_path(hivision_adapter),
            "hivisionRunner": module_path(hivision_runner),
            "legacyPrepareCompose": module_path(id_photo_v2),
            "matting": module_path(portrait_matting),
            "compose": module_path(id_photo_composer),
            "quality": module_path(id_photo_quality),
        }
    ```

### 1.3 Transition and Compatibility Safety Plan
To ensure zero-downtime and safe transition:
1. **Shims (Optional but recommended)**: Maintain deprecated shim files in `server/services/` (e.g., `services/id_photo_v2.py`) containing only wildcard imports from `id_photo_engine_legacy` to prevent breakage of untracked test scripts.
2. **Script Updates**: Scan and update import paths in all validation scripts under `server/scripts/`.
3. **Validation Run**: Run the verification scripts (e.g., `python server/scripts/verify_id_photo_matting.py`) before and after the move to verify the behavior remains completely unchanged.

---

## 2. Input Validation (`validation.py`) (R3)

A new `validation.py` will be created under `server/id_photo_engine_minimal/` to validate input images before matting.

### 2.1 Technical Specifications

#### A. Face Detection (Exact 1 Face)
* **Goal**: Reject images that have no face or multiple faces, or where the face is too small.
* **Mechanism**:
  1. Detect faces using MediaPipe `blaze_face_short_range.tflite` model (located at `server/models/blaze_face_short_range.tflite`).
  2. Fall back to OpenCV Haar Cascades (`haarcascade_frontalface_default.xml` and `haarcascade_frontalface_alt2.xml`) if MediaPipe is unavailable.
  3. Merge duplicate overlapping bounding boxes using Intersect-over-Union (IoU > 0.35).
  4. Ensure `len(faces) == 1`.
  5. Check face height ratio relative to the image height: `fh / h >= 0.055` (reject if too small).
  6. Return coordinates of the main face box `(fx, fy, fw, fh)` and the face center.

#### B. Blur Detection (Laplacian Variance Check)
* **Goal**: Reject blurry images.
* **Mechanism**:
  1. Convert the input image to grayscale.
  2. Compute the Laplacian variance:
     ```python
     blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
     ```
  3. Compare `blur_score` against the threshold of `18.0`. Reject if `blur_score < 18.0`.

#### C. Cartoon/Illustration Detection
* **Goal**: Reject non-photorealistic illustrations or anime images.
* **Mechanism**:
  Adapt the robust heuristic logic from `services/portrait_quality.py`:
  1. Resize image to maximum 320px for fast color/edge statistics.
  2. Extract saturation mean in HSV space: `sat_mean = np.mean(hsv[:, :, 1])`.
  3. Extract edge density using Canny edge detection: `edge_density = np.mean(cv2.Canny(gray, 60, 140) > 0)`.
  4. Compute flat area ratio (local standard deviation of gray < 5.5):
     ```python
     gray_f = gray.astype(np.float32)
     mean = cv2.blur(gray_f, (7, 7))
     sq_mean = cv2.blur(gray_f * gray_f, (7, 7))
     local_std = np.sqrt(np.maximum(sq_mean - mean * mean, 0))
     flat_ratio = np.mean(local_std < 5.5)
     ```
  5. Reject as illustration if:
     * `(flat_ratio > 0.70 and sat_mean > 35 and edge_density > 0.01)` OR
     * `(flat_ratio > 0.62 and sat_mean > 42 and edge_density > 0.035)`.
     *(Optional: Exclude real humans with flat background/clothing by validating a smaller face patch).*

#### D. Shoulder Detection (Visibility in Crop Area)
* **Goal**: Verify that shoulders are present and will be visible inside the target crop area.
* **Mechanism**:
  1. The target crop area is determined by the composition type (`head_shoulder` or `half_body`) and the face bounding box:
     * Vertical crop bottom: `crop_bottom = min(h, fy + fh * 2.30)` (standard) or `fy + fh * 4.2` (half-body).
     * Horizontal crop left/right: expand face box by `1.28 * fw` on each side (standard) or `1.7 * fw` (half-body).
  2. Ensure that the original image contains the shoulder region by checking:
     * **Below Face Space**: `below_face_ratio = (h - (fy + fh)) / fh`.
       * Must be `>= 0.55` for standard `head_shoulder` layout.
       * Must be `>= 1.45` for `professional` / `half_body` layouts.
     * **Side Margin Space**: `side_room_ratio = min(fx, w - (fx + fw)) / fw`.
       * Must be `>= 0.08` for standard layout.
       * Must be `>= 0.18` for professional layout.
  3. If these space checks fail, reject with `SHOULDER_MISSING`.

---

## 3. Matting Adapter (`matting.py`) (R4)

A new `matting.py` will be created under `server/id_photo_engine_minimal/` to run Hivision matting.

### 3.1 Transparent PNG Direct Reuse (Performance Optimization)
If the input image is already an RGBA image containing transparent background pixels, we bypass the heavy ONNX model inference entirely:
1. Check if the image mode is `RGBA`.
2. Extract the alpha channel and check its extrema (minimum and maximum alpha values):
   ```python
   alpha = image.getchannel("A")
   min_val, max_val = alpha.getextrema()
   ```
3. If `min_val < 255` (indicating transparency exists) and `max_val > 20` (ensuring it's not a completely empty image), reuse the original alpha channel directly as the matting mask and return the image.

### 3.2 Running Hivision Matting via ONNX Runtime
If the image is not a transparent PNG, load and run one of the Hivision ONNX models:
* **Models path**: `third_party/HivisionIDPhotos/hivision/creator/weights/`
  * `rmbg-1.4.onnx` (176MB)
  * `birefnet-v1-lite.onnx` (224MB)

#### A. Preprocessing & Inference for `rmbg-1.4`
1. Convert the image to `RGB` and resize to `(1024, 1024)` using bilinear interpolation.
2. Convert to numpy float32, transpose to shape `(3, 1024, 1024)`.
3. Add batch dimension: shape `(1, 3, 1024, 1024)`.
4. Normalize pixels to `[-1.0, 1.0]`: `(img / 255.0 - 0.5) / 0.5`.
5. Run ONNX Session inference.
6. Post-process the output output mask: normalize to `[0.0, 1.0]`, scale to `[0, 255]` uint8, resize back to original image size, and paste the mask onto the original image as the alpha channel.

#### B. Preprocessing & Inference for `birefnet-v1-lite`
1. Convert the image to `RGB` and resize to `(1024, 1024)`.
2. Normalize using ImageNet statistics:
   * Subtract mean: `[0.485, 0.456, 0.406]`
   * Divide by std: `[0.229, 0.224, 0.225]`
3. Transpose to `(1, 3, 1024, 1024)`.
4. Run ONNX Session inference.
5. Apply Sigmoid to the output logits: `result = 1 / (1 + np.exp(-pred))`.
6. Scale to `[0, 255]` uint8, resize back to original image size, and paste as the alpha channel.
