# Handoff Report - Explorer 1 (Milestone 2)

## 1. Observation

During read-only investigation, the following files, configurations, and paths were observed:

1. **Legacy Files**: In `server/id_photo_engine_legacy/README.md`, lines 7-11 list the legacy files:
   ```
   Current legacy runtime files:
   - `server/services/id_photo_v2.py`
   - `server/services/portrait_matting.py`
   - `server/services/id_photo_composer.py`
   - `server/services/id_photo_quality.py`
   ```
2. **Legacy Imports**:
   - In `server/main.py`, lines 34-41 import functions from `services.id_photo_v2`.
   - In `server/id_photo_engines/engine_manager.py`, lines 38-41 dynamically import:
     ```python
     import services.id_photo_v2 as id_photo_v2
     import services.portrait_matting as portrait_matting
     import services.id_photo_composer as id_photo_composer
     import services.id_photo_quality as id_photo_quality
     ```
   - In `server/id_photo_engines/rembg/adapter.py`, line 1 imports `matting_status` from `services.portrait_matting`.
3. **ONNX Weights**: Running the search tool found Hivision ONNX weights at:
   - `third_party/HivisionIDPhotos/hivision/creator/weights/rmbg-1.4.onnx`
   - `third_party/HivisionIDPhotos/hivision/creator/weights/birefnet-v1-lite.onnx`
4. **Hivision creator implementations**: `third_party/HivisionIDPhotos/hivision/creator/human_matting.py` contains:
   - `get_rmbg_matting(...)` (lines 265-315) running ONNX `rmbg-1.4.onnx`.
   - `get_birefnet_portrait_matting(...)` (lines 354-428) running ONNX `birefnet-v1-lite.onnx` with sigmoid output normalization.
5. **Existing Validation Logic**: `server/services/portrait_quality.py` contains `validate_portrait_input(...)` (lines 135-210) implementing:
   - Laplacian variance check (`cv2.Laplacian(gray, cv2.CV_64F).var()`).
   - Face count checking (Haar Cascades face detection).
   - Illustration detection (`_looks_like_illustration(...)`).
   - Shoulder checking (`below_face_ratio` and `side_room_ratio` checks).

---

## 2. Logic Chain

1. **Legacy Isolation**: Since the old local ID-photo chain needs to be isolated (**Observation 1**), the four files under `services/` must be moved to `server/id_photo_engine_legacy/`. To prevent breaking any third-party scripts or older tests, stubs must be left under `services/` forwarding imports to the new location. Active imports in `main.py` and `id_photo_engines` (**Observation 2**) must be updated to target `id_photo_engine_legacy` directly.
2. **Input Validation**: Rebuilding the input validation in `validation.py` inside `id_photo_engine_minimal` can leverage the existing proven logic in `portrait_quality.py` (**Observation 5**). Refactoring it into a clean, modern validation module with a custom `ValidationError` ensures clean separation of concerns and robust error reporting.
3. **Matting Adapter**: Running matting via Hivision weights (`rmbg-1.4.onnx` or `birefnet-v1-lite.onnx`) (**Observation 3**) is best done in-process using `onnxruntime` to avoid process-spawning overhead. The preprocessing and postprocessing logic can be adapted from Hivision's own implementation (**Observation 4**).
4. **Transparent PNG Handling**: Direct handling of transparent PNGs can be achieved by checking the alpha channel's extrema. If any transparency exists, we can return the input image and alpha mask directly, bypassing ONNX inference entirely and increasing efficiency.

---

## 3. Caveats

1. **ONNX Runtime Performance**: We assume `onnxruntime` is installed and functioning correctly in the Python environment, utilizing CUDA execution providers if available.
2. **MediaPipe Model Presence**: Face detection assumes `models/blaze_face_short_range.tflite` is present. If missing, it will gracefully fallback to Haar Cascades.
3. **No Code Modifications**: As a read-only Explorer, no source code was modified. The plans must be executed by the Implementer in the next step.

---

## 4. Conclusion

The investigation of Milestone 2 is complete. An actionable, safe execution plan has been written to `server/id_photo_engine_legacy/` and `server/id_photo_engine_minimal/` designs. 
Next step: The Implementer should execute the file movements, create `validation.py` and `matting.py` under `server/id_photo_engine_minimal/`, and update reference imports.

---

## 5. Verification Method

To verify the planned implementation independently:
1. Inspect the written analysis at: `server/.agents/explorer_m2_1/analysis.md`
2. Once implemented, verify code behavior by running standard diagnostic scripts:
   - `python server/scripts/verify_environment.py`
   - `python server/scripts/verify_all.py`
3. Check that transparent PNGs bypass ONNX runtime processing by logging the execution path during a prepare request.
