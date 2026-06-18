# Milestone 2 Exploration & Design Analysis

This report outlines the technical design, directory layout, and implementation plans for **Milestone 2: Legacy Isolation & Input Validation** in the ID Photo Generator project.

---

## 1. Legacy Isolation Plan

### Legacy Files Identification
The following files under `server/services/` are identified as part of the legacy image processing and composition chain. They need to be isolated into the dedicated legacy engine folder:
- `server/services/id_photo_v2.py`
- `server/services/portrait_matting.py`
- `server/services/id_photo_composer.py`
- `server/services/id_photo_quality.py`

*Note: Shared services that are used by other endpoints (like face detection helpers, templates, inpainting, and spec configurations) will remain in `server/services/` or `server/id_photo_engines/` and will not be moved.*

### Movement & Safety Steps
To isolate the legacy codebase without breaking existing endpoints and compatibility:
1. **File Relocation**: Move the four files from `server/services/` to `server/id_photo_engine_legacy/`.
2. **Internal Legacy Imports Resolution**:
   In `server/id_photo_engine_legacy/id_photo_v2.py`, modify imports referencing other legacy files:
   - `from services.portrait_matting import matte_person, matting_status` $\rightarrow$ `from id_photo_engine_legacy.portrait_matting import matte_person, matting_status`
   - `from services.id_photo_composer import compose_id_photo` $\rightarrow$ `from id_photo_engine_legacy.id_photo_composer import compose_id_photo`
   - `from services.id_photo_quality import build_quality_report, validate_composition_metrics, validate_final_output` $\rightarrow$ `from id_photo_engine_legacy.id_photo_quality import build_quality_report, validate_composition_metrics, validate_final_output`
3. **Endpoint Integration in `server/main.py`**:
   Update `server/main.py` to reference the relocated legacy services. Specifically, change:
   - `from services.id_photo_v2 import ...` $\rightarrow$ `from id_photo_engine_legacy.id_photo_v2 import ...`
   - `from services.portrait_matting import matting_status` $\rightarrow$ `from id_photo_engine_legacy.portrait_matting import matting_status`
4. **Backward Compatibility**: Ensure that other services, such as `server/services/portrait_quality.py` (which is imported by `main.py` and the legacy code), remain untouched or accessible.

---

## 2. Input Validation Plan (`validation.py`)

The new `server/id_photo_engine_minimal/validation.py` will be a self-contained module containing helper functions and a main validation coordinator `validate_input_image`.

### Core Validation Components

#### A. Face Detection (Exactly 1 Face)
- **Mechanism**: Use OpenCV's Haar Cascades as a robust, light-weight local detector. Optionally fallback or load MediaPipe if dependencies are present.
- **Cascade Classifiers**: Load `haarcascade_frontalface_default.xml` and `haarcascade_frontalface_alt2.xml`.
- **Merging Overlaps**: Implement a standard Intersection-over-Union (IoU) face box merging algorithm with a threshold of `0.35` to avoid double-counting the same face.
- **Constraints**:
  - If detected face count is `0`, raise validation error: `NO_FACE_DETECTED`.
  - If detected face count is `> 1`, raise validation error: `MULTIPLE_FACES_DETECTED`.
  - Check if the main face area is too small relative to the image (e.g., face area ratio `< 0.012` or height ratio `< 0.055`). If so, raise validation error: `LOW_FACE_CONFIDENCE` or `FACE_TOO_SMALL`.

#### B. Blur Detection (Laplacian Variance Check)
- **Mechanism**: Compute the Laplacian variance of the grayscale representation of the input image.
- **Formula**: `blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()`
- **Threshold**: Standard threshold of `18.0`.
- **Constraint**: If `blur_score < 18.0`, raise validation error: `IMAGE_TOO_BLURRY`.

#### C. Cartoon/Illustration Detection
- **Mechanism**: Evaluate edge density, color saturation, and local standard deviation flatness of the resized image (max side 320 px) and face patch (if face box is available).
- **Metrics**:
  - `flat_ratio`: The ratio of pixels with local standard deviation `< 5.5`.
  - `sat_mean`: Average saturation channel in HSV color space.
  - `edge_density`: Percentage of edge pixels from a Canny edge detector (e.g., thresholds `60` and `140`).
- **Logic**:
  - General Illustration Check: `(flat_ratio > 0.70 and sat_mean > 35 and edge_density > 0.01) or (flat_ratio > 0.62 and sat_mean > 42 and edge_density > 0.035)`.
  - Face Patch Check: Extract face patch `img[y:y+fh, x:x+fw]`. If face flat ratio `> 0.72` and saturation `> 34` and edge density `> 0.035` $\rightarrow$ Illustration.
  - Real Person Safeguard: If face flat ratio `< 0.66` and face texture (mean local std) `> 5.8` and gray std `> 32` $\rightarrow$ Real Person.
- **Constraint**: If identified as illustration or anime, raise validation error: `INVALID_INPUT_ANIME_OR_CARTOON` or `INVALID_INPUT_NOT_REAL_PERSON`.

#### D. Shoulder Detection (Visibility in Crop Area)
- **Mechanism**: Analyze spatial margins below and to the sides of the face box relative to the image width `w` and height `h`.
- **Heuristic**:
  - `below_face_ratio = (h - (y + fh)) / float(fh)` (verifies space at bottom)
  - `side_room_ratio = min(x, w - (x + fw)) / float(fw)` (verifies space on left/right)
- **Constraints**:
  - For professional career photos (e.g., `task == "professional"`): Must satisfy `below_face_ratio >= 1.45` and `side_room_ratio >= 0.18`.
  - For standard ID photos: Must satisfy `below_face_ratio >= 0.55` and `side_room_ratio >= 0.08`.
  - If limits are violated, raise validation error: `SHOULDER_MISSING`.

---

## 3. Matting Adapter Plan (`matting.py`)

The module `server/id_photo_engine_minimal/matting.py` will wrap model loading, input pre-processing, ONNX inference, and output post-processing for `rmbg-1.4.onnx` and `birefnet-v1-lite.onnx`.

### Transparent PNG Direct Handling (Alpha Re-use)
Prior to loading or executing any neural network inference, the adapter will examine the input image:
```python
def check_and_reuse_alpha(image: Image.Image) -> Image.Image | None:
    if image.mode == "RGBA":
        alpha = image.getchannel("A")
        extrema = alpha.getextrema()
        # If the minimum alpha value is less than 255, it has transparent pixels
        if extrema[0] < 255:
            print("[matting_minimal] Reusing existing alpha channel from input PNG")
            return image
    return None
```
If `check_and_reuse_alpha` returns a transparent image, it is returned directly, short-circuiting the ONNX model execution entirely.

### ONNX Model Pre-processing & Inference

#### A. RMBG-1.4 Model Execution
1. **Inputs**: Expects `(1, 3, 1024, 1024)` shaped tensor in float32.
2. **Pre-processing**:
   - Resize image to `1024x1024` using bilinear interpolation.
   - Transpose from `HWC` to `CHW` format.
   - Normalize pixel values to `[0, 1]` via division by `255.0`.
   - Scale values to `[-1, 1]` via: `im_np = (im_np - 0.5) / 0.5`.
   - Add batch dimension.
3. **Session Run**: `RMBG_SESS.run(None, {input_name: im_np})[0]`.
4. **Post-processing**:
   - Squeeze output to `(1024, 1024)`.
   - Min-Max normalization: `mask = (out - min) / (max - min)`.
   - Convert to single-channel uint8 mask (`0-255`).
   - Resize mask back to original image dimensions.
   - Paste original image on transparent background using the resized mask as alpha channel.

#### B. BirefNet-v1-Lite Model Execution
1. **Inputs**: Expects `(1, 3, 1024, 1024)` shaped tensor in float32.
2. **Pre-processing**:
   - Resize image to `1024x1024`.
   - Normalize pixel values to `[0, 1]` via division by `255.0`.
   - Standardize using ImageNet statistics:
     - `im_np = (im_np - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]`
   - Transpose from `HWC` to `CHW` format and add batch dimension.
3. **Session Run**: `BIREFNET_V1_LITE_SESS.run(None, {input_name: im_np})[-1]`.
4. **Post-processing**:
   - Squeeze output to `(1024, 1024)`.
   - Apply sigmoid activation: `mask = 1.0 / (1.0 + np.exp(-out))`.
   - Convert to uint8 (`0-255`), resize to original dimensions, and apply as alpha channel.

---

## 4. Proposed Directory Layout

Upon implementing Milestone 2, the `server/` workspace will look as follows:

```
server/
├── id_photo_engine_legacy/               # Isolated legacy engine
│   ├── README.md
│   ├── id_photo_v2.py                    # Moved from services/
│   ├── portrait_matting.py               # Moved from services/
│   ├── id_photo_composer.py              # Moved from services/
│   └── id_photo_quality.py               # Moved from services/
│
├── id_photo_engine_minimal/              # New minimal engine setup
│   ├── __init__.py
│   ├── validation.py                     # Face, blur, illustration, and shoulder validations
│   └── matting.py                        # RMBG-1.4 / BirefNet-v1-lite ONNX & PNG alpha reuse
│
├── services/                             # Core remaining backend services
│   ├── outfit_templates.py
│   ├── face_detector.py                  # Standard MediaPipe/OpenCV detector
│   └── ...
│
└── main.py                               # Uvicorn entry point (updated imports)
```
