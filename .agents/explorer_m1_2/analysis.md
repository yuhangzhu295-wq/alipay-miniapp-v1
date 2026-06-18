# Milestone 1 Investigation: Runtime Audit & Cache Clean (R1)

This report summarizes the findings of the runtime process audit, cache directories localization, and model weight verification for the ID Photo Generator project.

---

## 1. Active Process Analysis (Port 8000)

We audited the local network ports to find any running FastAPI/Uvicorn services.

### Directly Observed Process:
- **Port**: `8000` (FastAPI backend port)
- **Protocol**: TCP
- **Status**: LISTENING
- **PID**: `39008`
- **Process Name**: `python.exe`
- **Command Line**: `"C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000`

### Auditing Commands (Windows Powershell / CMD):
1. **Find PID on Port 8000**:
   ```cmd
   netstat -ano | findstr :8000
   ```
2. **Find Process Details by PID**:
   ```powershell
   Get-Process -Id 39008 | Select-Object Id, ProcessName, Path
   ```
   Or via `tasklist`:
   ```cmd
   tasklist | findstr 39008
   ```
3. **Query Running Command Line**:
   ```powershell
   powershell -Command "Get-CimInstance Win32_Process -Filter 'ProcessId = 39008' | Select-Object CommandLine"
   ```

### Termination Command:
To stop the process safely and free up port 8000:
```cmd
taskkill /F /PID 39008
```

---

## 2. Cache, Uploads, Outputs, and Temp Directories

We inspected the server codebase (`server/main.py`, `portrait_matting.py`, `runner.py`) and located several temporary/cache directory chains.

### Cache Directory Inventory & Size Analysis:

| Directory Path / Name | Purpose | File Patterns | File Count | Total Size |
|---|---|---|---|---|
| **Hivision Engine Runtime**<br>`C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\runtime` | Hivision matting process intermediate temp inputs/outputs | `request-*-input.png`, `request-*-<model>.png` | 3,568 files | **1.41 GB** |
| **System Temp Files**<br>`C:\Users\zyu33\AppData\Local\Temp` | Temporary foreground cutout & alpha mask images from matting | `tmp*.png`, `tmp*.jpg` | 12,347 files | **1.79 GB** |
| **App Static Outputs**<br>`C:\Users\zyu33\AppData\Local\Temp\id_photo_server\outputs` | Final cropped and composed ID photos served at `/outputs` | `*.jpg` | 89 files | **2.61 MB** |
| **App Static Uploads**<br>`C:\Users\zyu33\AppData\Local\Temp\id_photo_server\uploads` | Uploaded raw photos and watermark workspace files | Subdirectories (`watermark/hd`) | 0 files | **0 Bytes** |
| **Hivision Standalone Output**<br>`C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\standalone-output` | Output files from verification run | `test_*.png`, `test_*.jpg` | 4 files | **1.25 MB** |
| **Registries (App Meta)**<br>`C:\Users\zyu33\AppData\Local\Temp\id_photo_server` | Asset and user photo tracking databases | `asset_registry.json`, `user_photo_registry.json` | 2 files | **53 KB** |
| **Project Logs**<br>`C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\logs` | Historical background service logs | `*.log` | 18 files | **3.6 MB** |
| **Project Root logs**<br>`C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器` | Old watermark service logs | `watermark-iopaint-8081*.log` | 2 files | **3.6 KB** |
| **Project Legacy Reports**<br>`C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\reports` | Diagnostic validation reports and release zip backups | `*.json`, `*.zip`, `*.log` | Multiple | **~5.9 MB** (Zip) |

### Cleaning Reclaimed Space Assessment:
- **Total Reclaimed Space**: **~3.21 GB**
- **Total Files to Delete**: **> 16,000 files**

### Cleaning Strategy & Constraints:
- **What can be cleaned**:
  - All files in `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\runtime` and `standalone-output`.
  - All files matching `tmp*.png` or `tmp*.jpg` in `C:\Users\zyu33\AppData\Local\Temp`.
  - All files in `C:\Users\zyu33\AppData\Local\Temp\id_photo_server\outputs` (ensure active client sessions are closed first).
  - Clear the content of `asset_registry.json` to `[]` and `user_photo_registry.json` to `[]`.
  - All project log files (`logs/*.log`, root `*.log`).
- **What MUST NOT be cleaned / deleted**:
  - The model weights ONNX files.
  - The Directory Junction `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\HivisionIDPhotos` (deleting the link directory incorrectly could delete the physical third_party source directory!).

---

## 3. Model Weights Verification

We verified the local presence of all deep learning model weight files on the filesystem.

### 1. Hivision ONNX Models:
Stored in `third_party/HivisionIDPhotos/hivision/creator/weights/` and `third_party/HivisionIDPhotos/hivision/creator/retinaface/weights/`.
- `rmbg-1.4.onnx`: 176,153,355 bytes (Verified)
- `birefnet-v1-lite.onnx`: 224,005,088 bytes (Verified)
- `hivision_modnet.onnx`: 25,888,609 bytes (Verified)
- `modnet_photographic_portrait_matting.onnx`: 25,888,640 bytes (Verified)
- `retinaface-resnet50.onnx`: 109,458,296 bytes (Verified)

### 2. Rembg Fallback Models:
Stored in the user directory `C:\Users\zyu33\.u2net\`.
- `u2net.onnx`: 175,997,641 bytes (Verified)
- `u2net_human_seg.onnx`: 175,997,641 bytes (Verified)
- `isnet-general-use.onnx`: 178,648,008 bytes (Verified)
- `isnet-anime.onnx`: 176,069,933 bytes (Verified)

### 3. LaMa Inpainting Model:
Stored in the PyTorch Hub directory `C:\Users\zyu33\.cache\torch\hub\checkpoints\`.
- `big-lama.pt`: Present (Verified)

---

## 4. Templates for Milestone 1 Outputs (Project Root)

These templates are designed to be generated at the project root by the Implementer during Milestone 1.

### Plan/Template for `runtime-chain-audit.md`
```markdown
# Runtime Chain Audit Report

This report documents the active background processes and network ports utilized by the ID Photo Generator application.

## 1. Port Allocation Table
| Port | Service Name | Protocol | Active PID | Process Name | Path |
|---|---|---|---|---|---|
| **8000** | FastAPI/Uvicorn API Gateway | TCP | 39008 | python.exe | `C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe` |
| **8081** | LaMa / IOPaint HD Repair (Optional) | TCP | None | - | - |

## 2. Process Command Lines
- **Port 8000 Process**:
  `"C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000`

## 3. Port Conflict Audit and Cleanup Script
To audit and terminate any conflicting processes:
1. Find PID on port 8000:
   ```cmd
   netstat -ano | findstr :8000
   ```
2. Kill conflicting process:
   ```cmd
   taskkill /F /PID <PID>
   ```

## 4. Hot Reload & hot-linking configuration
The application creates directory junctions in the temp folder to bridge relative path execution:
- **Junction**: `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\HivisionIDPhotos` -> `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos`
- **Caution**: Do NOT delete this junction directory recursively; use `rmdir` (not deleting contents) to safely remove the link.
```

### Plan/Template for `cache-clean-report.md`
```markdown
# Cache Clean Report

This report details the execution and results of the cache cleaning procedure for the ID Photo Generator application.

## 1. Cache Locations and Sizes Before Clean

| Directory Path | Description | Files Count | Size Before | Size After | Reclaimed |
|---|---|---|---|---|---|
| `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\runtime` | Hivision Intermediate Cutouts | 3,568 | 1.41 GB | 0 Bytes | 1.41 GB |
| `C:\Users\zyu33\AppData\Local\Temp` (`tmp*.png` / `tmp*.jpg`) | System Temp Cutouts | 12,347 | 1.79 GB | 0 Bytes | 1.79 GB |
| `C:\Users\zyu33\AppData\Local\Temp\id_photo_server\outputs` | FastAPI Composed Outputs | 89 | 2.61 MB | 0 Bytes | 2.61 MB |
| `C:\Users\zyu33\AppData\Local\Temp\id_photo_server\uploads` | User uploads | 0 | 0 Bytes | 0 Bytes | 0 Bytes |
| `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\standalone-output` | Standalone verification outputs | 4 | 1.25 MB | 0 Bytes | 1.25 MB |
| `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\logs` | Project Service Logs | 18 | 3.6 MB | 0 Bytes | 3.6 MB |
| `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器` (`*.log`) | Project Root Logs | 2 | 3.6 KB | 0 Bytes | 3.6 KB |
| **TOTAL** | | **~16,028** | **~3.21 GB** | **0 Bytes** | **~3.21 GB** |

## 2. Cleaning Commands (Powershell)
The following script was used to safely clean all temporary files without touching weights or active code junctions:

```powershell
# 1. Stop FastAPI Port 8000 process if active
# 2. Clean Hivision Runtime files
Remove-Item -Path "C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\runtime\*" -Force -Recurse -ErrorAction SilentlyContinue
Remove-Item -Path "C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\standalone-output\*" -Force -Recurse -ErrorAction SilentlyContinue

# 3. Clean tmp png/jpg in system temp
Remove-Item -Path "C:\Users\zyu33\AppData\Local\Temp\tmp*.png" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "C:\Users\zyu33\AppData\Local\Temp\tmp*.jpg" -Force -ErrorAction SilentlyContinue

# 4. Clean app-specific outputs and reset registries
Remove-Item -Path "C:\Users\zyu33\AppData\Local\Temp\id_photo_server\outputs\*" -Force -Recurse -ErrorAction SilentlyContinue
Set-Content -Path "C:\Users\zyu33\AppData\Local\Temp\id_photo_server\asset_registry.json" -Value "[]" -Encoding utf8
Set-Content -Path "C:\Users\zyu33\AppData\Local\Temp\id_photo_server\user_photo_registry.json" -Value "[]" -Encoding utf8

# 5. Clean logs
Remove-Item -Path "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\logs\*.log" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\watermark-iopaint-8081*.log" -Force -ErrorAction SilentlyContinue
```

## 3. Preserved Assets (MUST NOT BE DELETED)
- **Model weights directories**:
  - `third_party/HivisionIDPhotos/hivision/creator/weights/`
  - `C:\Users\zyu33\.u2net/`
  - `C:\Users\zyu33\.cache/torch/hub/checkpoints/`
- **Code Junction Links**:
  - `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\HivisionIDPhotos`
```
