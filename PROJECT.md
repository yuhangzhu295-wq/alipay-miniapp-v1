# Project: ID Photo Generator Rebuilding (证件照生成器)

## Architecture
The system consists of:
1. **Frontend (WeChat Mini-program)**: Captures user photo, handles image cropping UI, sends requests to the backend, displays preview images, and triggers downloads.
2. **Backend (FastAPI, Python)**: Runs on port `8000`. Exposes APIs for preparing (validation + matting) and composing (alignment + cropping + background synthesis) ID photos.
3. **Matting Engines**:
   - Primary: HivisionIDPhotos (supporting `rmbg-1.4.onnx` and `birefnet-v1-lite.onnx` weights).
   - Fallback: Local `rembg` library.

### Data Flow
```
[User Upload] -> POST /api/id-photo/prepare -> Validation -> Matting -> Alpha Check -> Cache RGBA & Mask
                                                                                        |
[Result Image] <- POST /api/id-photo/compose <- Cropping & Layout <- Background Synth <-+
```

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Runtime Audit & Cache Clean | Stop/audit port 8000, ensure correct models loaded, clean all cached directories. Generate `runtime-chain-audit.md` and `cache-clean-report.md`. | None | PLANNED |
| M2 | Legacy Isolation & Input Validation | Move legacy services to `server/id_photo_engine_legacy/`. Rebuild input validation (face count, blur, orientation) and matting adapter for Hivision (`server/id_photo_engine_minimal/`). | M1 | PLANNED |
| M3 | Cleanup, Cropping & Composition | Implement lightweight alpha cleanup, 1-inch crop (face, eyes, head top, chin, shoulders), five-color background compositing, and quality checks. | M2 | PLANNED |
| M4 | E2E WeChat & Regression | Coordinate with Browser Agent for WeChat devtools verification, generate validation reports, and ensure all npm regression verify scripts pass. | M3, TEST_READY.md | PLANNED |

## Interface Contracts

### Client ↔ Server APIs
#### 1. Prepare Request (`POST /api/id-photo/prepare`)
- **Headers**: `Content-Type: multipart/form-data`
- **Body**:
  - `file`: Raw image file
  - `spec_id`: Target size ID (e.g. `1inch`)
- **Response (Success)**:
  ```json
  {
    "success": true,
    "preparedId": "unique_prepared_uuid",
    "requestId": "unique_10char_request_id",
    "quality": {
      "passed": true,
      "blurScore": 24.5,
      "faceCount": 1
    }
  }
  ```
- **Response (Failure)**:
  ```json
  {
    "success": false,
    "error_code": "IMAGE_TOO_BLURRY",
    "message": "The uploaded photo is too blurry."
  }
  ```

#### 2. Compose Request (`POST /api/id-photo/compose`)
- **Headers**: `Content-Type: application/json`
- **Body**:
  ```json
  {
    "preparedId": "unique_prepared_uuid",
    "bgColor": "white"
  }
  ```
- **Response (Success)**:
  ```json
  {
    "success": true,
    "finalImageUrl": "/outputs/unique_10char_request_id.jpg?v=version_hash"
  }
  ```

## Code Layout
- `server/main.py`: Backend entrypoint
- `server/id_photo_engine_minimal/`: Package for the new minimal pipeline
  - `__init__.py`
  - `validation.py`: Input validation logic (R3)
  - `matting.py`: Matting engine adapter layer (R4)
  - `cleanup.py`: Lightweight alpha purification (R5)
  - `composer.py`: Cropping, composition, and background colors (R5)
  - `quality.py`: Post-composition quality gates (R6)
- `server/id_photo_engine_legacy/`: Isolated legacy patch chain code (R2)
- `pages/generate/`: WeChat Mini-program generation page (R7)
- `pages/result/`: WeChat Mini-program preview/download page (R7)
- `server/scripts/`: Verification and testing scripts
- `reports/final/`: Test outputs and markdown reports
