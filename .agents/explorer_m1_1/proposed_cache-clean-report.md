# Cache Clean Report

This report identifies all cache, uploads, outputs, temp, and logs directories used by the application, detailing their sizes and the cleaning plan.

## 1. Directory Catalog & Current Status

| Target Directory / File | Description | Location / Path | File Count | Total Size | Cleaning Priority |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **Active Runtime Temp** | Active FastAPI backend output store | `C:\Users\zyu33\AppData\Local\Temp\id_photo_server\outputs` | 89 files | ~2.65 MB | **High** (Stale production outputs) |
| **Active Runtime Uploads** | Active FastAPI backend upload store | `C:\Users\zyu33\AppData\Local\Temp\id_photo_server\uploads` | 0 files (1 empty folder) | 0 B | **Medium** (Stale uploads) |
| **Active Registry (Assets)** | Database of assets metadata | `C:\Users\zyu33\AppData\Local\Temp\id_photo_server\asset_registry.json` | 1 file | 52,916 B | **High** (Out of sync with files) |
| **Active Registry (Users)** | Database of user photos metadata | `C:\Users\zyu33\AppData\Local\Temp\id_photo_server\user_photo_registry.json` | 1 file | 2 B | **High** (Out of sync with files) |
| **Workspace Outputs** | Development/Test outputs | `server\outputs` | 30 files | ~3.59 MB | **High** (Stale development files) |
| **Workspace Uploads** | Development/Test uploads | `server\uploads` | 0 files | 0 B | **Low** (Already empty) |
| **Orphaned Matting Temp** | Leftover temporary files from ModNet/BirefNet | `C:\Users\zyu33\AppData\Local\Temp\tmp*.png` | Varies | Varies | **High** (Not deleted on server crash) |
| **Workspace Log Files** | Log files from various runs | `logs\` | 18 files | ~3.65 MB | **Medium** (Historical log data) |
| **IOPaint Logs (Root)** | IOPaint service stdout/stderr logs | `watermark-iopaint-8081*.log` | 2 files | ~3.67 KB | **Medium** (Historical logs) |

---

## 2. Model & Weight Files (DO NOT CLEAN)

The following weights files are critical to the runtime. **Do not clean, delete, or modify these paths:**
* **BirefNet V1 Lite**: `third_party/HivisionIDPhotos/hivision/creator/weights/birefnet-v1-lite.onnx` (224,005,088 bytes)
* **Hivision MODNet**: `third_party/HivisionIDPhotos/hivision/creator/weights/hivision_modnet.onnx` (25,888,609 bytes)
* **MODNet Photographic Portrait Matting**: `third_party/HivisionIDPhotos/hivision/creator/weights/modnet_photographic_portrait_matting.onnx` (25,888,640 bytes)
* **RMBG-1.4 ONNX**: `third_party/HivisionIDPhotos/hivision/creator/weights/rmbg-1.4.onnx` (176,153,355 bytes)
* **RetinaFace ResNet50**: `third_party/HivisionIDPhotos/hivision/creator/retinaface/weights/retinaface-resnet50.onnx` (109,458,296 bytes)
* **BlazeFace Short Range**: `server/models/blaze_face_short_range.tflite` (229,746 bytes)
* **External Torch Checkpoint (LaMa)**: `C:\Users\zyu33\.cache\torch\hub\checkpoints\big-lama.pt` (205,669,692 bytes)

---

## 3. Recommended Cleaning Actions

To perform a clean reset of the runtime cache, execute the following steps:
1. **Stop the active FastAPI server** (PID 39008) to release locks on registry and output files.
2. **Clean Active Temp files**:
   - Delete all files inside `C:\Users\zyu33\AppData\Local\Temp\id_photo_server\outputs`.
   - Reset `C:\Users\zyu33\AppData\Local\Temp\id_photo_server\asset_registry.json` content to `[]`.
   - Reset `C:\Users\zyu33\AppData\Local\Temp\id_photo_server\user_photo_registry.json` content to `{}`.
3. **Clean Workspace outputs**:
   - Delete all files in `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\server\outputs` (excluding `.gitkeep` if present).
4. **Clean System Temp Matting remnants**:
   - Delete all `tmp*.png` files in `C:\Users\zyu33\AppData\Local\Temp` that were created by the user process or are older than 1 hour.
5. **Clean Log directories**:
   - Delete or truncate all `.log` files in `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\logs\`.
   - Delete `watermark-iopaint-8081.log` and `watermark-iopaint-8081.err.log` at the project root.
