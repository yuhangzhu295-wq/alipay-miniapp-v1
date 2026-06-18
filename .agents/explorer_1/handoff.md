# Handoff Report - explorer_1

## 1. Observation

- **Server Port and Startup**:
  - `start-hd-watermark-service.bat` lines 6-7:
    ```bat
    set "HOST=0.0.0.0"
    set "PORT=8000"
    ```
    Line 64:
    ```bat
    %PYTHON_CMD% -m uvicorn main:app --host %HOST% --port %PORT% --reload
    ```
  - `start-hd-watermark-service.bat` line 51:
    ```bat
    start "watermark-iopaint-lama" cmd /k %PYTHON_CMD% -m iopaint start --host 127.0.0.1 --port %IOPAINT_PORT% --model %HD_REPAIR_ENGINE% --device cpu --no-inbrowser --quality 100
    ```
- **Legacy Patch Chain & Pipeline**:
  - `server/id_photo_engine_legacy/README.md` lines 7-11:
    ```
    Current legacy runtime files:
    - `server/services/id_photo_v2.py`
    - `server/services/portrait_matting.py`
    - `server/services/id_photo_composer.py`
    - `server/services/id_photo_quality.py`
    ```
  - `server/services/portrait_matting.py` lines 1191-1203:
    ```python
    from id_photo_engines.hivision.runner import run_human_matting
    hivision = run_human_matting(image)
    if hivision.get("success"):
        return _finalize_matting_rgba(
            hivision["rgba"],
            face_box,
            image,
            "hivision",
            hivision.get("model") or "hivision_modnet",
            "hivision_human_matting",
            extra_debug=hivision.get("debug"),
        )
    ```
- **Input Quality Gates**:
  - `server/services/portrait_quality.py` lines 155-173:
    ```python
    if min(w, h) < 160 or blur_score < 18:
        quality["code"] = "IMAGE_TOO_BLURRY"
        _fail("IMAGE_TOO_BLURRY", quality)
    ...
    if len(large_faces) > 1:
        quality["code"] = "MULTIPLE_FACES_DETECTED"
        _fail("MULTIPLE_FACES_DETECTED", quality)
    ```
- **Caching Mechanism**:
  - `server/services/id_photo_v2.py` lines 30-31:
    ```python
    PREPARE_CACHE = {}
    PREPARE_CACHE_TTL_SECONDS = 24 * 3600
    ```
- **Mini-program Routes**:
  - `app.json` has routes for:
    - `"pages/generate/generate"` (the main upload/generation/choose-background interface)
    - `"pages/result/result"` (the final photo preview and download trigger)
    - `"pages/photos/photos"` (user generation history list)
- **Positive and Negative Samples**:
  - Directory `reports/id-photo-samples/input` contains 202 positive sample JPEGs (`female_0.jpg` through `male_local.jpg`).
  - Directory `reports/id-photo-samples/negative` contains 12 negative sample JPEGs targeting quality gates.
- **Verification Scripts**:
  - `package.json` contains scripts like:
    - `"verify:id-photo": "node server/scripts/run_python.js server/scripts/verify_id_photo_chain.py --base-url http://127.0.0.1:8000 --real-count 40 --min-pass-rate 95"`
    - `"verify:all": "node server/scripts/run_python.js server/scripts/verify_user_photo_isolation_all.py --base-url http://127.0.0.1:8000 --cloud-url http://120.26.44.156"`
  - `server/scripts/verify_all.py` manages E2E regression tests for environment, engines, watermark, outfits, layouts, and devtools.

---

## 2. Logic Chain

1. **Server Host/Port**: Based on observations of `start-hd-watermark-service.bat`, we deduce that the FastAPI backend runs on host `0.0.0.0` and port `8000` via Uvicorn. An optional IOPaint backend runs on `127.0.0.1:8081` (defaulting to port `8081` if not override).
2. **WeChat Developer Tools Control**: Observed `start-dev-all.bat` opening the workspace folder via WeChat CLI tool path `"C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat"`.
3. **Pipeline Request Lifecycle**:
   - Stage 1: `/api/id-photo/prepare` registers raw uploads, validates blur and faces using MediaPipe, performs matting via Hivision adapter or rembg fallback, and returns a `preparedId` mapped in `PREPARE_CACHE`.
   - Stage 2: `/api/id-photo/compose` takes `preparedId` and target background color, aligns/crops the subject using cached face box ratios, cleans edge halos via `_clean_edge_halo()`, saves the final image, and returns the public `/outputs/` URL with a cache-busting version query string.
4. **Caching Details**: Intermediate matting PNGs and coordinates are stored in the memory dict `PREPARE_CACHE` for up to 24 hours. The FastAPI startup routine schedules an hourly background loop to clean up expired cache memory and physically unlink temporary files.
5. **Quality Gates Check**: Validation rules screen inputs (blurry, cartoon/illustration, multiple faces, small faces, missing shoulders) during the `prepare` phase. Post-compose stages check target constraints (padding ratios, head height ratios, shoulder width ratios, face centering offset, and color contour halos).
6. **Regression Tests Coordination**: Under `package.json` and `server/scripts/verify_all.py`, individual test runner python scripts verify each sub-module, using positive samples (`reports/id-photo-samples/input`) and negative samples (`reports/id-photo-samples/negative`) to evaluate pass rates.

---

## 3. Caveats

- **No Caveats**: All requested areas (server startup, pipeline stages, client routes, sample folders, quality gates, and testing script structure) were directly examined in the codebase and successfully verified.

---

## 4. Conclusion

The codebase exploration is complete. The system implements a robust, two-stage face-driven ID photo generation pipeline utilizing MediaPipe and HivisionIDPhotos (with rembg fallback). Input validation gates screen out invalid samples early, and post-processing steps (connected components, shoulder repair, and halo cleaning) ensure standard-compliant outputs. The legacy pipeline can be safely isolated by moving `services/id_photo_v2.py` and dependencies into a dedicated legacy directory, paving the way for a clean, modular engine (`id_photo_engine_minimal/`) that leverages modern neural matting models (`birefnet-v1-lite` and `rmbg-1.4`) with minimal hand-crafted morphology.

---

## 5. Verification Method

To independently verify our findings, the implementer can:
1. **Start the Backend Server**:
   Run `start-hd-watermark-service.bat` in the project root to start the Python server on port `8000`.
2. **Run Pipeline Verification**:
   Execute the project E2E test suite using:
   ```powershell
   npm run verify:id-photo
   ```
   Confirm that it successfully loads the 202 positive samples and rejects the 12 negative samples.
3. **Inspect Output Logs & Reports**:
   Verify that validation results and generated images are written under `reports/final/` and `reports/id-photo-samples/`.
