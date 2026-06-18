## 2026-06-18T01:44:45Z
Implement the tasks for Milestone 2: Legacy Isolation & Input Validation (R2, R3, R4) in the workspace C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器.
Your identity:
- Role: Worker for Milestone 2
- Working directory: C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\worker_m2
- Parent/Orchestrator: Implementation Sub-Orchestrator (this conversation)

Tasks to perform:
1. Legacy Isolation:
   - Create directory `server/id_photo_engine_legacy/` with a blank `__init__.py`.
   - Move files `server/services/id_photo_v2.py`, `server/services/portrait_matting.py`, `server/services/id_photo_composer.py`, and `server/services/id_photo_quality.py` into `server/id_photo_engine_legacy/`.
   - Create placeholder compatibility stubs in the original `server/services/` folder (e.g. `server/services/portrait_matting.py` contains `from id_photo_engine_legacy.portrait_matting import *`) to avoid breaking existing imports.
   - Update direct import references in `server/main.py`, `server/id_photo_engines/engine_manager.py`, and `server/id_photo_engines/rembg/adapter.py`.

2. Rebuild Input Validation (`server/id_photo_engine_minimal/validation.py`):
   - Define a custom `ValidationError(ValueError)` with `error_code` and `details`.
   - Implement `validate_input_image(image_bytes: bytes, task: str = "changeBg") -> Tuple[bool, dict]`:
     - Face count check: exact 1 face using MediaPipe face detector (`server/models/blaze_face_short_range.tflite`). Fallback to OpenCV Haar Cascades if MediaPipe is not ready. If face count is 0, raise ValidationError with error_code "NO_FACE_DETECTED". If face count > 1, raise ValidationError with error_code "MULTIPLE_FACES_DETECTED".
     - Blur check: Convert to grayscale and check Laplacian variance. If blur score < 18.0, raise ValidationError with error_code "IMAGE_TOO_BLURRY".
     - Cartoon/Illustration check: HSV mean saturation and Canny edge density + local standard deviation check. If illustration conditions are met, raise ValidationError with error_code "INVALID_INPUT_ANIME_OR_CARTOON".
     - Shoulder visibility check: Verify sufficient space below and to the sides of the face bounding box. For professional task: below_face_ratio >= 1.45, side_room_ratio >= 0.18. For changeBg task: below_face_ratio >= 0.55, side_room_ratio >= 0.08. If check fails, raise ValidationError with error_code "SHOULDER_MISSING".

3. Rebuild Matting Adapter (`server/id_photo_engine_minimal/matting.py`):
   - Implement PIL transparent PNG check: if input image is already a transparent PNG, extract the alpha channel and return the RGBA image directly, bypassing ONNX inference.
   - Run Hivision matting in-process: Load `rmbg-1.4.onnx` or `birefnet-v1-lite.onnx` via `onnxruntime.InferenceSession` (caching sessions globally, auto-selecting CUDA provider if GPU is available).
   - Implement preprocessing (resize to 1024x1024, normalize accordingly) and postprocessing (sigmoid for birefnet, min-max scale for rmbg, bilinear resize mask back to original, paste original image onto a transparent canvas using the mask).

4. Run local builds/tests to verify compilation, import sanity, and tests passing.
5. Write your implementation report to `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\worker_m2\handoff.md`.
