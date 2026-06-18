# Analysis Report: Legacy Isolation & Input Validation (Milestone 2)

This report outlines the technical investigation and implementation plans for Milestone 2: Legacy Isolation, Input Validation (`validation.py`), and Matting Adapter (`matting.py`) for the ID Photo Generator rebuilding project.

---

## 1. Legacy Isolation

### 1.1. Identification of Legacy Files
The following files under `server/services/` belong to the old local ID-photo processing chain:
1. `server/services/id_photo_v2.py` (Main prepare/compose coordinator)
2. `server/services/portrait_matting.py` (Old matting pipeline invoking `rembg` fallback and GrabCut post-processing)
3. `server/services/id_photo_composer.py` (Old composition logic)
4. `server/services/id_photo_quality.py` (Old quality metrics/reporting)

### 1.2. Movement and Target Paths
These four files will be moved to the legacy isolation directory:
- `server/id_photo_engine_legacy/`
  - `__init__.py` (To be created)
  - `id_photo_v2.py`
  - `portrait_matting.py`
  - `id_photo_composer.py`
  - `id_photo_quality.py`

### 1.3. Safety & Compatibility Strategy (Stub Redirection)
To prevent runtime breaks in any older test scripts or external endpoints, we will apply a **stub redirection** strategy:
- Leave placeholder scripts in `server/services/` with the original names.
- Each placeholder will import everything from its isolated legacy counterpart. E.g., `server/services/portrait_matting.py` will contain:
  ```python
  from id_photo_engine_legacy.portrait_matting import *
  ```
- This guarantees backward compatibility and prevents import errors during testing.

### 1.4. Reference Updates in Server Modules
The following active modules need to be updated to import directly from the new legacy package:
1. **`server/main.py`**:
   - Change `from services.id_photo_v2 import ...` to `from id_photo_engine_legacy.id_photo_v2 import ...`
   - Change `from services.portrait_matting import matting_status` to `from id_photo_engine_legacy.portrait_matting import matting_status`
2. **`server/id_photo_engines/engine_manager.py`**:
   - Update `_runtime_files()` diagnostic mapping to load modules from `id_photo_engine_legacy`:
     ```python
     import id_photo_engine_legacy.id_photo_v2 as id_photo_v2
     import id_photo_engine_legacy.portrait_matting as portrait_matting
     import id_photo_engine_legacy.id_photo_composer as id_photo_composer
     import id_photo_engine_legacy.id_photo_quality as id_photo_quality
     ```
3. **`server/id_photo_engines/rembg/adapter.py`**:
   - Change `from services.portrait_matting import matting_status` to `from id_photo_engine_legacy.portrait_matting import matting_status`

---

## 2. Input Validation (`validation.py`)

The new input validation will reside in `server/id_photo_engine_minimal/validation.py`. It provides four primary checks on the user-uploaded image.

### 2.1. ValidationError Structure
A clean custom validation exception will be raised for any failure:
```python
class ValidationError(ValueError):
    def __init__(self, error_code: str, message: str, details: dict = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}
```

### 2.2. Validation Checks & Core Logic

1. **Face Detection (Exact 1 Face)**
   - **Mechanism**: Use MediaPipe Face Detection when available (`blaze_face_short_range.tflite` via `mediapipe.tasks.python.vision.FaceDetector`), with OpenCV Haar cascades (`haarcascade_frontalface_default.xml`, `haarcascade_frontalface_alt2.xml`) as a robust local fallback.
   - **Rules**:
     - If `face_count == 0`: Raise `ValidationError("NO_FACE_DETECTED", "未检测到人脸，请上传正面半身照。")`
     - If `face_count > 1`: Raise `ValidationError("MULTIPLE_FACES_DETECTED", "检测到多个人脸，请上传单人照片。")`
     - Else: Return the bounding box `{"x": x, "y": y, "width": w, "height": h}`.

2. **Blur Detection (Laplacian Variance Check)**
   - **Mechanism**: Convert the BGR image to grayscale. Compute the variance of the Laplacian:
     ```python
     gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
     blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
     ```
   - **Rule**: If `blur_score < 18.0`, raise `ValidationError("IMAGE_TOO_BLURRY", "图片清晰度较低，建议更换更清晰的正面照片。", {"blurScore": blur_score})`.

3. **Cartoon/Illustration Detection**
   - **Mechanism**: A composite statistical heuristic on flat regions, edge density, and saturation:
     - Resize the sample to max 320px width/height.
     - Convert to HSV, compute mean saturation `sat_mean`.
     - Convert to gray, run Canny edge detection (thresholds 60, 140) to compute `edge_density`.
     - Compute local standard deviation `_local_std(gray)`. Flat area ratio `flat_ratio` is the fraction of pixels where standard deviation < 5.5.
     - Illustration conditions:
       - `(flat_ratio > 0.70 and sat_mean > 35 and edge_density > 0.01) or (flat_ratio > 0.62 and sat_mean > 42 and edge_density > 0.035)`
   - **Rule**: If illustration conditions are met, raise `ValidationError("INVALID_INPUT_ANIME_OR_CARTOON", "当前图片不适合生成证件照/职业形象照，请上传单人正面真人照片。")`.

4. **Shoulder Detection**
   - **Mechanism**: Validate if enough space exists below the face box and on the sides to ensure shoulders are visible in the crop area.
   - **Formula**:
     - `below_face_ratio = (H - (y + h)) / float(h)`
     - `side_room_ratio = min(x, W - (x + w)) / float(w)`
   - **Rules**:
     - For `task == "professional"` (职业形象照/半身照): Ensure `below_face_ratio >= 1.45` and `side_room_ratio >= 0.18`.
     - For standard `task == "changeBg"` (普通证件照): Ensure `below_face_ratio >= 0.55` and `side_room_ratio >= 0.08`.
     - If validation fails, raise `ValidationError("SHOULDER_MISSING", "照片肩部区域不足，建议上传包含头部和双肩的半身照。")`.

---

## 3. Matting Adapter (`matting.py`)

The new matting adapter will reside in `server/id_photo_engine_minimal/matting.py` and run Hivision matting.

### 3.1. Reusing Alpha Channels for Transparent PNGs
To maximize efficiency and preserve pre-matted uploads:
- Pre-convert any input PIL image to RGBA: `rgba_img = img.convert("RGBA")`.
- Get the extrema of the alpha channel: `extrema = rgba_img.getchannel("A").getextrema()`.
- If `extrema` shows transparent pixels (i.e. `extrema[0] < 255`):
  - Skip ONNX execution entirely.
  - Return `rgba_img` and its alpha channel `rgba_img.getchannel("A")` directly.

### 3.2. Hivision ONNX Runtime Matting Plan
If the input is opaque (RGB or full alpha), the adapter runs in-process ONNX inference.

- **ONNX Session Caching**:
  - Keep a global dictionary `_SESSIONS` mapping model paths to `onnxruntime.InferenceSession`.
  - Dynamically load model weights from:
    - `third_party/HivisionIDPhotos/hivision/creator/weights/rmbg-1.4.onnx`
    - `third_party/HivisionIDPhotos/hivision/creator/weights/birefnet-v1-lite.onnx`
  - Auto-select `CUDAExecutionProvider` if GPU is available, else default to `CPUExecutionProvider`.

- **ONNX Inference Preprocessing**:
  - Resize image to `1024x1024` pixels.
  - Convert PIL image to `float32` numpy array and transpose to CxHxW format.
  - Normalize:
    - **`rmbg-1.4`**: `(im / 255.0 - 0.5) / 0.5`
    - **`birefnet-v1-lite`**: `(im / 255.0 - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]`

- **ONNX Inference Execution**:
  - Run the session with the preprocessed tensor:
    ```python
    output = session.run(None, {session.get_inputs()[0].name: input_tensor})[0]
    ```

- **ONNX Inference Postprocessing**:
  - Squeeze the batch dimension.
  - Apply scaling:
    - **`rmbg-1.4`**: Normalize output using min-max scaling: `(out - min) / (max - min)`.
    - **`birefnet-v1-lite`**: Apply sigmoid activation: `1 / (1 + np.exp(-out))`.
  - Convert the mask array back to a PIL `L` mode (grayscale) image.
  - Resize the mask back to the original image dimensions using bilinear interpolation.
  - Compose the final RGBA image:
    ```python
    rgba_cutout = Image.new("RGBA", original_size, (0, 0, 0, 0))
    rgba_cutout.paste(original_img, mask=alpha_mask)
    ```
  - Return `(rgba_cutout, alpha_mask)`.
