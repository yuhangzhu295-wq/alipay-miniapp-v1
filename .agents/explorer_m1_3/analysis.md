# Milestone 1: Runtime Audit & Cache Clean (R1) — Investigation Report

This report documents the findings from the investigation of the `证件照生成器` (ID Photo Generator) workspace for Milestone 1.

---

## 1. Port & Runtime Process Audit

### 1.1 Port 8000 (FastAPI/Uvicorn Backend)
- **Status**: **Active (Listening)**
- **Process ID (PID)**: `39008`
- **Process Name**: `python.exe`
- **Executable Path**: `C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe`
- **Launch Command Line**:
  `"C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000`
- **Health Check Status**: Healthy
  - URL: `http://127.0.0.1:8000/api/health` and `http://127.0.0.1:8000/health`
  - Engine Type: `hivision` (defaulting to `rmbg-1.4`)
  - Standalone verification passed: Yes (using marker file `reports/id-photo-multi-engine-reset/hivision-standalone-ready.json`)

### 1.2 Port 8081 (IOPaint HD Inpaint Service)
- **Status**: **Inactive (Not Listening)**
- **Configured Engine**: `lama` (Big-LaMa)
- **Service Address**: `http://127.0.0.1:8081`
- **Current Status**: Not started. The main FastAPI backend reports `hdAvailable: false` and `hdEngine: not_ready` as a result.

### 1.3 How to Audit & Stop Processes (Windows)
To inspect and stop the processes running on these ports, the following commands can be executed:
- **Audit Listening Port**:
  - CMD/PowerShell: `netstat -ano | findstr :8000` or `netstat -ano | findstr :8081`
- **Audit Process Details**:
  - PowerShell: `Get-CimInstance Win32_Process -Filter "ProcessId = <PID>" | Select-Object CommandLine, Name, Path`
  - CMD: `tasklist /FI "PID eq <PID>"`
- **Stop Process Safely**:
  - PowerShell: `Stop-Process -Id <PID> -Force`
  - CMD: `taskkill /F /PID <PID>`

---

## 2. Cache & Temporary Directories Audit

We calculated the footprints of all directories associated with the application's runtime cache, temporary storage, logs, and outputs:

| Directory Path | Description | File Count | Total Size (MB) | Recommended Action |
| --- | --- | --- | --- | --- |
| `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\runtime` | Hivision input/output temporary image files. | 3,568 | 1342.89 MB | **Clean completely** (safe to delete). |
| `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\standalone-output` | Standalone engine validation outputs. | 4 | 1.20 MB | **Clean completely** (safe to delete). |
| `C:\Users\zyu33\AppData\Local\Temp\id_photo_server` | Active server outputs and upload directories. | 91 | 2.54 MB | **Purge entirely** (safe to reset). |
| `server/outputs` | Local test outputs in workspace. | 30 | 4.53 MB | **Clean completely** (safe to delete). |
| `server/uploads` | Local upload directory in workspace. | 0 | 0.00 MB | Keep empty. |
| `logs` | Workspace process log outputs. | 18 | 3.48 MB | **Clean/Truncate** (safe to clear). |
| Project Root logs (`watermark-iopaint-8081.*.log`) | Root logs for watermark service. | 2 | 0.004 MB (~3.6 KB) | **Clean/Delete** (safe to clear). |
| `server` logs (`uvicorn.*.log`) | Uvicorn stdout/stderr logs. | 2 | 1.39 MB | **Clean/Delete** (safe to clear). |

### 2.1 Accumulation Root Cause
The `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\runtime` folder accumulates 1.34 GB of PNG images (`request-*-input.png` and `request-*-<model>.png`) because `HivisionIDPhotos` executes matting in a standalone Python subprocess that saves intermediate files to disk but does not run an automatic cleanup routine.

---

## 3. Models & Weights Audit

All critical neural network model weights were successfully located and verified for existence and exact sizing:

| Model Filename | Architecture / Use Case | File Size | Storage Path | Status |
| --- | --- | --- | --- | --- |
| `birefnet-v1-lite.onnx` | BiRefNet Lite Matting Engine | 224,005,088 bytes | `third_party/HivisionIDPhotos/hivision/creator/weights/` | **Verified Present** |
| `rmbg-1.4.onnx` | RMBG-1.4 Matting Engine | 176,153,355 bytes | `third_party/HivisionIDPhotos/hivision/creator/weights/` | **Verified Present** |
| `hivision_modnet.onnx` | Hivision MODNet Engine | 25,888,609 bytes | `third_party/HivisionIDPhotos/hivision/creator/weights/` | **Verified Present** |
| `modnet_photographic_portrait_matting.onnx` | Standard MODNet Engine | 25,888,640 bytes | `third_party/HivisionIDPhotos/hivision/creator/weights/` | **Verified Present** |
| `retinaface-resnet50.onnx` | RetinaFace Face Detector | 109,458,296 bytes | `third_party/HivisionIDPhotos/hivision/creator/retinaface/weights/` | **Verified Present** |
| `blaze_face_short_range.tflite` | MediaPipe Face Detector | 229,746 bytes | `server/models/` | **Verified Present** |
| `big-lama.pt` | IOPaint Inpaint Model | 205,669,692 bytes | `C:\Users\zyu33\.cache\torch\hub\checkpoints\` | **Verified Present** |

---

## 4. Documentation Strategy & Generation Plan

### 4.1 Plan for `runtime-chain-audit.md` (Project Root)
This document will establish the operational baseline for auditing execution processes:
1. **Current Port 8000 Process details**: PID `39008`, python command line, host binding, health check result.
2. **Current Port 8081 Process details**: Inactive state, configuration URL.
3. **Execution Command Reference**: Script endpoints (`start-hd-watermark-service.bat`, `start-watermark-service.bat`).
4. **Engine Diagnostic Status**: Matting models list, engine selection priorities.
5. **Auditing & Control instructions**: Step-by-step PowerShell and CMD commands to query and terminate port 8000 and 8081 processes.

### 4.2 Plan for `cache-clean-report.md` (Project Root)
This document will map the exact temporary storage landscape and describe the clean reset workflow:
1. **Cache Footprint Summary**: Table of all audited directories, file counts, and sizes in MB.
2. **Analysis of Accumulation**: Detail why the Hivision sub-process directory accumulates files and how to prevent it.
3. **Concrete Cleanup commands**: Copy-pasteable PowerShell/CMD commands to clean each cache folder safely.
4. **Post-Cleanup validation checks**: Scripted commands to verify size reclamation.
