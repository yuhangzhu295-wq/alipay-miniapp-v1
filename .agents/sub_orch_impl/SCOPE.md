# Scope: Rebuild Implementation Track

## Architecture
- Legacy code will be isolated under `server/id_photo_engine_legacy/`.
- New clean, minimal pipeline will be implemented under `server/id_photo_engine_minimal/`.
- The new pipeline will handle validation, matting, alpha cleanup, cropping/composition, and post-processing quality checks.
- Integrate back into the FastAPI backend (main.py, etc.) to expose APIs.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Runtime Audit & Cache Clean | Stop backend on 8000, audit runtime, clean cache dirs, verify engines/models, write reports | None | DONE |
| 2 | Legacy Isolation & Input Validation | Isolate legacy files to `server/id_photo_engine_legacy/`, implement input validation checks and matting adapter in `server/id_photo_engine_minimal/` | M1 | PLANNED |
| 3 | Cleanup, Cropping & Composition | Implement alpha cleanup, 1-inch crop, color composition, and quality checks in `server/id_photo_engine_minimal/` | M2 | PLANNED |
| 4 | E2E WeChat & Regression | Poll for `TEST_READY.md`, run Tier 1-4 tests, verify WeChat Developer Tools UI via Browser Agent, run Tier 5 adversarial hardening, verify npm scripts | M3 | PLANNED |

## Interface Contracts
### `validation.py` API
- `validate_input_image(image_bytes: bytes) -> Tuple[bool, str]`: returns (is_valid, reason_if_invalid). Validates face detection, no multiple faces, cartoon/illustration check, blur check, shoulders check.

### `matting.py` API
- `perform_matting(image: np.ndarray, model_name: str) -> np.ndarray`: performs matting and returns RGBA image with transparent background. Handles transparent PNG directly.

### `cleanup.py` API
- `clean_alpha_noise(rgba_image: np.ndarray) -> np.ndarray`: removes fine alpha noise from transparent mask edges.

### `composer.py` API
- `crop_and_composite(rgba_image: np.ndarray, bg_color: str, size_type: str = "1-inch") -> np.ndarray`: Crops according to standard constraints (head ratio, face centering, shoulders visible) and composits with background color.

### `quality.py` API
- `verify_output_quality(rgba_image: np.ndarray) -> Tuple[bool, str]`: verifies output image quality (no dark borders, complete alpha, no weird edge lines).
