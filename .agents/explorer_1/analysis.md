# Codebase Exploration and Pipeline Analysis Report

This analysis document outlines the structure, workflow, and caching mechanisms of the ID photo generator project, detailing recommendations for isolating the legacy patch chain and building a new minimal generation engine.

---

## 1. Key Codebase Components and File Paths

### 1.1 Server & Core Pipeline Modules
- **Server Entrypoint**: `server/main.py`
  - Defines the FastAPI endpoints, handles static directory mounting, CORS configuration, token authentication, and request routing.
- **Engine Manager**: `server/id_photo_engines/engine_manager.py`
  - Dynamically detects and registers available matting engines (`hivision`, `rembg`, `modnet`, `birefnet`) and routes requests.
- **Legacy Pipeline Modules**:
  - `server/services/id_photo_v2.py`: Coordinates the two-step E2E generation flow (`prepare` -> `compose`).
  - `server/services/portrait_matting.py`: Core human matting logic including complex morphological repairs and rembg fallback.
  - `server/services/id_photo_composer.py`: Handles face-driven scaling, alignment, centering, and edge halo cleaning.
  - `server/services/portrait_quality.py` / `server/services/id_photo_quality.py`: Input pre-validation and final image metrics checking (quality gates).
- **Hivision Engine Adapter**:
  - `server/id_photo_engines/hivision/adapter.py`: Checks for existence of Hivision code and environment.
  - `server/id_photo_engines/hivision/runner.py`: Launches standalone `inference.py` in Hivision's virtual environment (`.venv`) via subprocess.

### 1.2 Directories & Registries
- **Runtime Temporary Directory**: `tempfile.gettempdir()/id_photo_server` (typically `C:\Users\zyu33\AppData\Local\Temp\id_photo_server` on Windows). Note: Storing uploads and outputs in a temporary system folder prevents WeChat Developer Tools from triggering hot reloads when images are written.
- **Uploads Directory**: `BASE_RUNTIME_DIR/uploads` (mapped to `/uploads` endpoint).
- **Outputs Directory**: `BASE_RUNTIME_DIR/outputs` (mapped to `/outputs` endpoint).
- **Asset Registry**: `BASE_RUNTIME_DIR/asset_registry.json` (registers storage paths, public URLs, expirations, and metadata).
- **User Photo Registry**: `BASE_RUNTIME_DIR/user_photo_registry.json` (stores generated photo records mapped to specific user IDs for isolation).

### 1.3 Client (WeChat Mini-program) Pages
- **Specification Picker**: `pages/specs/specs.js` (allows picking photo size categories and searching specs).
- **Photo Upload/Adjust/Generate**: `pages/generate/generate.js` (renders the cropper, captures the upload, calls `/api/id-photo/prepare` and `/api/id-photo/compose`).
- **Preview and Download**: `pages/result/result.js` (binds the generated `resultImage` URL, triggers download/save after checking `canDownload` permission).
- **History List**: `pages/photos/photos.js` (retrieves and displays history photos isolated by user ID).
- **Toolkit Menu**: `pages/tools/tools.js` (the toolkit catalog; outfits and career templates have been removed).
- **General Image Editing Details**: `pages/tool-detail/tool-detail.js` (manages watermark removal, background change, and format conversions).

### 1.4 Test Files & Test Runner
- **Test Runner (Final regression verifier)**: `server/scripts/verify_all.py` (executes all validation scripts and writes consolidated reports in `reports/final/`).
- **Core Pipeline E2E Verifier**: `server/scripts/verify_id_photo_chain.py` (scans mini-program pages, checks server health, validates negative cases, and benchmarks positive samples).
- **Positive Samples Pool**: `reports/id-photo-samples/input` (contains 202 JPEG portraits of males and females).
- **Negative Samples Pool**: `reports/id-photo-samples/negative` (contains 12 test cases for animal faces, anime, cartoons, blurry inputs, multiple faces, document text, and landscape photos).

---

## 2. Server Startup and Request Lifecycle Workflow

### 2.1 Server Startup and Service Management
1. **FastAPI Server (Port 8000)**:
   - Command: `python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
   - Started via: `start-hd-watermark-service.bat`.
2. **IOPaint HD Repair Service (Port 8081)**:
   - Command: `python -m iopaint start --host 127.0.0.1 --port 8081 --model lama --device cpu --no-inbrowser --quality 100` (started in parallel by the batch file if the `iopaint` package is detected).
3. **WeChat Developer Tools CLI**:
   - Command: `"%WECHAT_CLI%" open --project "%ROOT%"` (triggered via `start-dev-all.bat` which launches both the Python server and the editor workspace).

### 2.2 E2E Request Lifecycle (The Two-Stage Generation Flow)
```
[User Photo] ---> POST /api/id-photo/prepare ---> [Generate request_id]
                                                               |
                                                 Validate Input (Blur / Illustration)
                                                               |
                                                   Face Detection (MediaPipe)
                                                               |
                                                   Matting Engine (Hivision)
                                                               |
                                                  Postprocessing & Mask Refine
                                                               |
                                                   Save Temp PNG & Mask
                                                               |
                                                  Cache in PREPARE_CACHE
                                                               |
[Success Response] <--------------------------------- Return preparedId
        |
        +-------> POST /api/id-photo/compose ---> Retrieve preparedId
                                                               |
                                                  Align & Center Face (Pillow)
                                                               |
                                                  Edge Halo Cleanup (OpenCV)
                                                               |
                                                   Composite on bg_color
                                                               |
                                                  Save final JPG with cacheBust
                                                               |
[Success Response] <--------------------------------- Return finalImageUrl
```

1. **Phase 1: Prepare (`/api/id-photo/prepare`)**:
   - The frontend uploads a raw photo.
   - The backend generates a 10-character `request_id` (e.g. `uuid.uuid4().hex[:10]`) to track trace outputs.
   - **Quality Gate**: Runs `validate_portrait_input()` which screens out too blurry images (`blurScore < 18`), cartoons/illustrations (`_looks_like_illustration`), multiple faces, or missing/small faces. Raises `PortraitQualityError` on failure.
   - **Face Detection**: Runs MediaPipe face detection to get face box coordinate ratios.
   - **Matting**: Calls `matte_person()`. It attempts Hivision first (spawning a subprocess with `rmbg-1.4.onnx` or `birefnet-v1-lite.onnx` weights). If Hivision fails, it falls back to the local `rembg` library (`u2net_human_seg` or `isnet-general-use`).
   - **Mask Post-processing**: The legacy pipeline runs complex morphology passes to fill holes, trim side neutral sheets, delete row artifacts, and remove clothing watermarks.
   - **Temporary Storage**: Saves the refined foreground (RGBA PNG) and the alpha mask (L grayscale PNG) to unique paths in the system temp directory.
   - **PREPARE_CACHE Registration**: Registers an entry in an in-memory dict `PREPARE_CACHE` with a generated `preparedId` containing the asset paths, face boxes, quality metrics, and requested specification details.
   - **Response**: Sends the `preparedId`, input classification type, and quality markers back to the client.

2. **Phase 2: Compose (`/api/id-photo/compose`)**:
   - Client requests composition by submitting the `preparedId` and target `bgColor` (e.g., `blue`, `white`, `red`, `lightBlue`, `gray`).
   - **Cache Check**: Retrieves the record from `PREPARE_CACHE`. If missing or expired, raises `PortraitQualityError` (code `PREPARED_NOT_FOUND`).
   - **Composition**: Crops, centers, and resizes the foreground image based on the cached face box ratios. The target outputs align to reference dimensions (e.g., 295x413 px, head height ratio 58%-70%, top padding 7%-12%, centered horizontal alignment).
   - **Edge Halo Gate**: Runs `_clean_edge_halo()` to decontaminate transition pixels and remove white background bleed (which would otherwise look like halo lines on colored backgrounds).
   - **Saving & Cache-busting**: Saves the output to `OUTPUTS_DIR` and returns a cache-busted path containing version details: `/outputs/xxxx.jpg?v=requestId-modifiedEpochMs-sha256Hash`.

### 2.3 Caching Mechanism
- **PREPARE_CACHE**:
  - In-memory dictionary mapped in `services/id_photo_v2.py`.
  - Cache TTL is 24 hours (`PREPARE_CACHE_TTL_SECONDS = 86400`).
  - Active cleanup is managed by a background async task running every hour (`cleanup_expired_assets()`). It removes expired keys from the dictionary and deletes the corresponding physical PNGs from the filesystem.
- **Outfit Asset Cache**:
  - Outfits (e.g., suits, shirts) are cached in `OUTFIT_ASSET_CACHE` in memory to prevent repeated disk I/O when generating multiple photos.

---

## 3. Detailed Structure of Quality Gates and Checks

The project enforces strict quality checks at both input and output stages:

| Quality Gate | Checked Stage | Module & Functions | Rules / Thresholds |
|---|---|---|---|
| **Blur Check** | Input Pre-validation | `portrait_quality.py` / `_reject_if_too_blurry()` | Laplacian variance must be $\ge 18$. Minimum image dimension $\ge 160$ px. |
| **Real Person Check** | Input Pre-validation | `portrait_quality.py` / `_looks_like_illustration()` | HSV saturation mean and Canny edge density checks to intercept anime, cartoons, animals, and text. |
| **Face Count** | Input Pre-validation | `portrait_quality.py` / `_detect_faces()` | Exactly 1 face is allowed. Multiple large faces trigger `MULTIPLE_FACES_DETECTED`. |
| **Face Area Ratio** | Input Pre-validation | `portrait_quality.py` / `validate_portrait_input()` | Main face area must occupy $\ge 1.2\%$ of the image canvas. |
| **Shoulder Check** | Input Pre-validation | `portrait_quality.py` / `validate_portrait_input()` | Below-face ratio $\ge 0.55$ and side room ratio $\ge 0.08$ (higher for career templates). |
| **Mask Leak Gates** | Matting Output | `portrait_matting.py` / `_matting_leak_metrics()` | Ensures the background is fully removed and hair details are preserved. E.g. background leak ratio, mask overflow, edge leak score. |
| **Composition Check** | Final Output | `id_photo_quality.py` / `validate_composition_metrics()` | Target crop check: top padding 7%-12%, head height 58%-70%, shoulder width 75%-100%, and face center offset $< 4\%$. |
| **Edge Halo Check** | Final Output | `id_photo_quality.py` / `validate_final_output()` | White/light/gray contour halo ratios check. |

---

## 4. Recommendations for Isolating and Refactoring the Pipeline

### 4.1 Isolating the Legacy Patch Chain
The "legacy patch chain" consists of hand-crafted OpenCV heuristic code in:
- `server/services/id_photo_v2.py`
- `server/services/portrait_matting.py`
- `server/services/id_photo_composer.py`
- `server/services/id_photo_quality.py`

This chain is fragile and heavily patched to correct deficiencies in older models. To isolate it:
1. **Archive to Legacy Directory**: Move these files directly into the `server/id_photo_engine_legacy/` package, renaming them or exposing them through a legacy route adapter to preserve backwards compatibility.
2. **Abstract Core Interfaces**:
   Define abstract base classes for the new engine structure:
   ```python
   class BaseMattingEngine(abc.ABC):
       @abc.abstractmethod
       def matte(self, image: Image.Image, face_box: dict) -> Tuple[Image.Image, dict]:
           """Returns the transparent foreground RGBA image and diagnostic metadata."""
           pass
           
   class BaseComposer(abc.ABC):
       @abc.abstractmethod
       def compose(self, foreground: Image.Image, face_box: dict, target_size: tuple, bg_color: str) -> Tuple[Image.Image, dict]:
           """Aligns, crops, and composites the foreground on the background."""
           pass
   ```

### 4.2 Building the Minimal Chain (`server/id_photo_engine_minimal/`)
Modern models like `birefnet-v1-lite` and `rmbg-1.4` produce incredibly clean alpha boundaries directly. By adopting a modern deep learning stack, we can eliminate approximately 80% of the morphological heuristics:
1. **Create the Package**: Establish `server/id_photo_engine_minimal/` with clean, modular adapters for `engines`, `composer`, and `quality_checker`.
2. **Bypass Connected Component and Morphological Hacks**:
   - Remove complex operations like `_remove_background_sheets()`, `_remove_detached_row_artifacts()`, and `_grabcut_subject_mask()`.
   - Directly use the raw alpha mask returned by the neural network, applying only a mild Gaussian Blur for anti-aliasing edges.
3. **Deep Learning Driven Quality Gates**:
   - Replace Haar Cascade face classifiers with a lightweight, robust neural detector (e.g. MediaPipe Face Mesh or RetinaFace) to extract accurate landmarks (eyes, nose, mouth) for rotation correction and composition positioning.
   - Use the computed landmarks to calculate top padding and head heights mathematically, rather than relying on OpenCV contour bounding boxes.
4. **Standard Model Selection Recommendations**:
   - **Hivision + RMBG-1.4 (ONNX)**: Great balance of size (~176MB) and hairline definition. Suitable as the default general-purpose engine.
   - **Hivision + BiRefNet-v1-lite (ONNX)**: Exceptionally clean edge quality (~224MB) for complex clothing borders and varied hairstyles. Highly recommended for premium servers.
   - **MediaPipe Face Landmarker**: The ideal input validator for face orientation, facial expression, and obstruction checks.
