# Handoff Report — Explorer 2 for Milestone 2

## 1. Observation
* **Legacy Files**: `server/id_photo_engine_legacy/README.md` lines 7-11 explicitly lists the legacy files:
  ```markdown
  Current legacy runtime files:
  - `server/services/id_photo_v2.py`
  - `server/services/portrait_matting.py`
  - `server/services/id_photo_composer.py`
  - `server/services/id_photo_quality.py`
  ```
* **Imports in main.py**: `server/main.py` lines 34-41 imports legacy modules from `services`:
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
* **Imports in engine_manager.py**: `server/id_photo_engines/engine_manager.py` lines 38-41 imports them for path diagnostics in `_runtime_files()`:
  ```python
  import services.id_photo_v2 as id_photo_v2
  import services.portrait_matting as portrait_matting
  import services.id_photo_composer as id_photo_composer
  import services.id_photo_quality as id_photo_quality
  ```
* **ONNX Weights Availability**: Listing of `third_party/HivisionIDPhotos/hivision/creator/weights/` confirmed presence of:
  * `rmbg-1.4.onnx` (176,153,355 bytes)
  * `birefnet-v1-lite.onnx` (224,005,088 bytes)
* **Quality/Validation Heuristics**: `server/services/portrait_quality.py` implements:
  * Laplacian variance blur check: `cv2.Laplacian(gray, cv2.CV_64F).var()` (line 139).
  * Illustration classification `_looks_like_illustration` (lines 101-132) utilizing saturation mean (`sat_mean`), flatness ratio (`flat_ratio`), and edge density (`edge_density`).
  * Face detection via Haar cascades (lines 66-91) and MediaPipe (in `services/face_detector.py`).
  * Shoulder detection via space ratios (lines 192-205): `below_face_ratio = (h - (y + fh)) / float(fh)` (threshold 0.55/1.45) and `side_room_ratio = min(x, w - (x + fw)) / float(fw)` (threshold 0.08/0.18).

## 2. Logic Chain
1. Since the 4 legacy files are identified as legacy runtimes in the legacy README and contain the old generation logic, they must be moved to `server/id_photo_engine_legacy/`.
2. Because `main.py`, `engine_manager.py`, and multiple `scripts/` import these files via the `services` namespace, their import paths must be rewritten to the `id_photo_engine_legacy` namespace. Shims can be used to keep script backward compatibility during migration.
3. Because the new minimal engine needs input verification (R3) before matting, a new `validation.py` should implement checks derived from `portrait_quality.py` and `face_detector.py`: exact 1 face count, Laplacian variance threshold (< 18 is blur), saturation-flatness-edge constraints for cartoon detection, and vertical/horizontal margins around the face bounding box to ensure shoulders will not be cut off in the cropped canvas.
4. Since loading ONNX models takes considerable time and resources (as shown in Hivision's `human_matting.py`), if the input image is an RGBA file with transparent pixels (alpha extrema has min < 255 and max > 20), `matting.py` can optimize performance by bypassing model inference and directly reusing the original alpha channel.
5. If the image needs processing, `matting.py` can load `rmbg-1.4.onnx` or `birefnet-v1-lite.onnx` using `onnxruntime` and execute preprocessing, inference, and mask resizing to generate the cutout.

## 3. Caveats
No caveats. All areas described in the task request were thoroughly investigated.

## 4. Conclusion
Milestone 2 Legacy Isolation, Input Validation, and Matting Adapter designs are completely planned and documented in `analysis.md`. The design is fully compatible with existing project constraints and provides a clear blueprint for implementation.

## 5. Verification Method
1. Inspect the generated report at `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_m2_2\analysis.md`.
2. Once implementation starts, verify that:
   * Moving legacy files does not break the server startup: `uvicorn main:app --host 0.0.0.0 --port 8000` (run from `server/`).
   * Running legacy matting tests passes: `python server/scripts/verify_id_photo_matting.py`.
