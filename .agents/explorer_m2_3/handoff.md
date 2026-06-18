# Handoff Report — Explorer 3 (Milestone 2)

## 1. Observation
- Legacy files list is defined in `server/id_photo_engine_legacy/README.md`:
  - `server/services/id_photo_v2.py`
  - `server/services/portrait_matting.py`
  - `server/services/id_photo_composer.py`
  - `server/services/id_photo_quality.py`
- In `server/main.py`, these legacy services are imported at lines 34-41 and line 43:
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
- The model weights for ONNX inference are located in `third_party/HivisionIDPhotos/hivision/creator/weights/`:
  - `rmbg-1.4.onnx` (file size is verified in third-party dependencies)
  - `birefnet-v1-lite.onnx`
- In `server/services/portrait_quality.py` (line 139), Laplacian variance is computed as:
  ```python
  blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
  ```
  If `blur_score < 18`, it raises `IMAGE_TOO_BLURRY`.
- Illustration check heuristic in `portrait_quality.py` (lines 101-132) depends on `flat_ratio`, `sat_mean`, and `edge_density` parameters.
- Shoulder presence in `portrait_quality.py` (lines 192-202) checks margins:
  - `below_face_ratio = (h - (y + fh)) / float(fh)`
  - `side_room_ratio = min(x, w - (x + fw)) / float(fw)`
  - Standard check: `below_face_ratio >= 0.55` and `side_room_ratio >= 0.08`
  - Professional check: `below_face_ratio >= 1.45` and `side_room_ratio >= 0.18`

## 2. Logic Chain
1. Moving `services/id_photo_v2.py` and its dependencies (`portrait_matting.py`, `id_photo_composer.py`, `id_photo_quality.py`) to `id_photo_engine_legacy/` requires changing imports inside `id_photo_v2.py` because they will no longer reside in `services/`.
2. By updating `main.py` imports to reference `id_photo_engine_legacy.id_photo_v2`, the endpoints `/api/id-photo/prepare`, `/api/id-photo/compose`, and `/api/id-photo/generate-v2` will continue to work normally (acting as a safety fallback or legacy runner).
3. The validation logic in the new minimal engine must replicate standard error codes (`IMAGE_TOO_BLURRY`, `NO_FACE_DETECTED`, `MULTIPLE_FACES_DETECTED`, `INVALID_INPUT_ANIME_OR_CARTOON`, `SHOULDER_MISSING`) to maintain API contract compatibility with the frontend.
4. If an uploaded image is a PNG with an active alpha channel (`img.mode == "RGBA"` and alpha minimum `< 255`), the pixels are already masked. Processing it through matting ONNX model is redundant. Therefore, directly reusing the alpha channel is computationally optimal.
5. Implementing `matting.py` requires onnxruntime sessions configured to match the input specifications of `rmbg-1.4` and `birefnet-v1-lite` (bilinear resizing to 1024x1024, transpose to CHW, normalization to [-1, 1] for RMBG or ImageNet standardization for BirefNet).

## 3. Caveats
- No actual code changes have been performed (read-only mode).
- Standard MediaPipe model (`blaze_face_short_range.tflite`) is located in `server/models/`. If MediaPipe is not present in the Python environment, validation must fall back to OpenCV Haar Cascades.
- Running ONNX models on CPU vs GPU needs to be robustly handled in the InferenceSession initialization to avoid crash-looping if CUDA is not configured properly.

## 4. Conclusion
The legacy isolation and new engine layouts are fully defined. The implementation of `validation.py` and `matting.py` can proceed in `server/id_photo_engine_minimal/` based on standard OpenCV/ONNX pipelines, and the legacy codebase can be moved safely to `id_photo_engine_legacy` by updating the import statements.

## 5. Verification Method
- Verification of Plan: Run `python -c "import onnxruntime; print(onnxruntime.__version__)"` to ensure local ONNX runtime is available.
- Verification of Model Paths: Verify existence of files:
  - `third_party/HivisionIDPhotos/hivision/creator/weights/rmbg-1.4.onnx`
  - `third_party/HivisionIDPhotos/hivision/creator/weights/birefnet-v1-lite.onnx`
- Verification of Legacy Move: Ensure no imports under `server/` fail after moving. Run `python -m py_compile main.py` to check for compilation or import errors.
