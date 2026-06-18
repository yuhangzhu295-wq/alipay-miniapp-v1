# Milestone 1: Runtime Audit & Cache Clean (R1) Analysis Report

This report documents the detailed findings of the runtime investigation on port 8000 services, application caches, log directories, and model weight paths, including the plan to generate audit/clean files at the project root.

---

## 1. Active FastAPI/Uvicorn Processes (Port 8000)

### Findings
* **Port 8000 Status**: A single active process is listening on `0.0.0.0:8000`.
* **Process Information**:
  * **Process ID (PID)**: `39008`
  * **Process Name**: `python.exe`
  * **Command Line**: `"C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000`
  * **Configured Directory**: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\server`
* **Startup Chain**:
  * The process is started by `start-hd-watermark-service.bat` (referenced from `start-dev-all.bat` and `start-all-services.bat`).
  * If `iopaint` is available, this bat also spawns an `iopaint` background service on port 8081. However, no active process is currently listening on port 8081.

### Audit & Control Plan
* **Audit Command**: Run `netstat -ano | findstr :8000` in Cmd/PowerShell to find the PID. Run `Get-CimInstance Win32_Process -Filter "ProcessId = <PID>" | Select-Object CommandLine` to verify.
* **Stop Process Command**:
  * **Graceful**: Press `Ctrl+C` in the terminal executing the Uvicorn service.
  * **Force**: Run `Stop-Process -Id <PID> -Force` (PowerShell) or `taskkill /F /PID <PID>` (Command Prompt).

---

## 2. Cache, Uploads, Outputs, Temp, and Logs Directories

Through static analysis of `server/main.py`, `server/services/id_photo_v2.py`, and `server/services/portrait_matting.py`, we identified two main runtime state storage schemes:

### A. Active Runtime Directory (configured by `ID_PHOTO_RUNTIME_DIR` or defaults to `tempfile.gettempdir() + "/id_photo_server"`)
* **Default Path**: `C:\Users\zyu33\AppData\Local\Temp\id_photo_server`
* **Sub-directories & Registry Files**:
  * `outputs`: Contains generated ID photos. Currently holds **89 files**, totaling **~2.65 MB**.
  * `uploads\watermark\hd`: Active uploads directory. Currently **empty**.
  * `asset_registry.json`: Registry mapping file urls to metadata. Size is **52,916 bytes**.
  * `user_photo_registry.json`: User photos mapping. Size is **2 bytes**.

### B. Workspace Static Outputs & Uploads
* **Outputs Path**: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\server\outputs`
  * Contains **30 files** (stale development/test outputs), totaling **~3.59 MB**.
* **Uploads Path**: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\server\uploads`
  * Currently **empty**.

### C. System Temp Matting Files
* **Path**: `C:\Users\zyu33\AppData\Local\Temp`
* **Details**: The portrait matting engine (`server/services/portrait_matting.py`) uses `tempfile.NamedTemporaryFile(suffix=".png", delete=False)` to save foreground and alpha mask images.
* **Orphan Issue**: Because `delete=False` is used and these paths are only held in an in-memory dictionary (`PREPARE_CACHE` in `id_photo_v2.py` with 24h TTL), a server restart or crash will orphan these files, resulting in persistent temp file buildup (`tmp*.png` files).

### D. Workspace Logs
* **Workspace log directory**: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\logs`
  * Contains **18 files** (e.g. `start-watermark-service.out.log`), totaling **~3.65 MB**.
* **Root log files**: `watermark-iopaint-8081.log` (2,158 B) and `watermark-iopaint-8081.err.log` (1,513 B).

### Cleanup Recommendations
1. Clean all generated images in `C:\Users\zyu33\AppData\Local\Temp\id_photo_server\outputs`.
2. Clear registries: reset `asset_registry.json` to `[]` and `user_photo_registry.json` to `{}`.
3. Clean all files inside `server\outputs` in the workspace directory.
4. Clean orphaned matting temp files (`tmp*.png`) in `C:\Users\zyu33\AppData\Local\Temp` that are older than 1 hour.
5. Clean log files: delete or truncate all files inside `logs\` and the root IOPaint log files.

---

## 3. Model Weight Storage & Status

All critical ONNX and TFLite model weights were located and verified to be present with correct file sizes:

1. **`birefnet-v1-lite.onnx`**
   * **Path**: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\weights\birefnet-v1-lite.onnx`
   * **Size**: `224,005,088 bytes` (Present)
2. **`hivision_modnet.onnx`**
   * **Path**: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\weights\hivision_modnet.onnx`
   * **Size**: `25,888,609 bytes` (Present)
3. **`modnet_photographic_portrait_matting.onnx`**
   * **Path**: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\weights\modnet_photographic_portrait_matting.onnx`
   * **Size**: `25,888,640 bytes` (Present)
4. **`rmbg-1.4.onnx`**
   * **Path**: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\weights\rmbg-1.4.onnx`
   * **Size**: `176,153,355 bytes` (Present)
5. **`retinaface-resnet50.onnx`**
   * **Path**: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\retinaface\weights\retinaface-resnet50.onnx`
   * **Size**: `109,458,296 bytes` (Present)
6. **`blaze_face_short_range.tflite`**
   * **Path**: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\server\models\blaze_face_short_range.tflite`
   * **Size**: `229,746 bytes` (Present)
7. **`big-lama.pt` (IOPaint model checkpoint)**
   * **Path**: `C:\Users\zyu33\.cache\torch\hub\checkpoints\big-lama.pt`
   * **Size**: `205,669,692 bytes` (Present)

---

## 4. Plan for Project Root Reports Generation

To maintain the workspace read-only separation of concerns while delivering the files, we have prepared complete drafts in our agent directory. The subsequent Implementer agent can copy them to the project root:

1. **`runtime-chain-audit.md`** -> Draft saved as `proposed_runtime-chain-audit.md` in `.agents/explorer_m1_1/`.
2. **`cache-clean-report.md`** -> Draft saved as `proposed_cache-clean-report.md` in `.agents/explorer_m1_1/`.
3. **Execution Plan**: The Implementer agent will run copy commands to copy these two proposed files to the project root:
   ```powershell
   Copy-Item -Path "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_m1_1\proposed_runtime-chain-audit.md" -Destination "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\runtime-chain-audit.md" -Force
   Copy-Item -Path "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\explorer_m1_1\proposed_cache-clean-report.md" -Destination "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\cache-clean-report.md" -Force
   ```
