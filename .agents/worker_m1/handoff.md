# Handoff Report - Milestone 1: Runtime Audit & Cache Clean (R1)

## 1. Observation
* **Port 8000 Status**: Running command `cmd /c netstat -ano | findstr :8000` initially showed:
  ```
  TCP    0.0.0.0:8000           0.0.0.0:0              LISTENING       39008
  ```
  And running PowerShell command `Get-CimInstance Win32_Process -Filter "ProcessId = 39008" | Select-Object -ExpandProperty CommandLine` returned:
  ```
  "C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
  ```
  After executing `Stop-Process -Id 39008 -Force`, port 8000 no longer lists `LISTENING` status.
* **Port 8081 Status**: Running command `cmd /c netstat -ano | findstr :8081` showed:
  ```
  TCP    127.0.0.1:8081         0.0.0.0:0              LISTENING       46208
  ```
  With command line:
  ```
  C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe -m iopaint start --host 127.0.0.1 --port 8081 --model lama --device cpu --no-inbrowser --quality 100
  ```
* **Cache Footprint**:
  * `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\runtime` contained `1342.89 MB` of request images.
  * `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\standalone-output` contained `1.20 MB` of test images.
  * `C:\Users\zyu33\AppData\Local\Temp\id_photo_server` contained outputs (`2.49 MB`) and registry JSON files (`asset_registry.json` size `52916` bytes, `user_photo_registry.json` size `2` bytes).
  * `server/outputs` contained `4.53 MB` of output files.
  * `logs` contained `3.45 MB` of log files.
  * `watermark-iopaint-8081.err.log` and `watermark-iopaint-8081.log` in the project root contained log content.
* **Model Weights Footprint**:
  * `server/models`: `blaze_face_short_range.tflite` (0.22 MB)
  * `third_party/HivisionIDPhotos/hivision/creator/weights`: `birefnet-v1-lite.onnx` (213.63 MB), `hivision_modnet.onnx` (24.69 MB), `modnet_photographic_portrait_matting.onnx` (24.69 MB), `rmbg-1.4.onnx` (167.99 MB)
  * `third_party/HivisionIDPhotos/hivision/creator/retinaface/weights`: `retinaface-resnet50.onnx` (104.39 MB)
  * `C:\Users\zyu33\.cache\torch\hub\checkpoints`: `big-lama.pt` (196.14 MB)

---

## 2. Logic Chain
1. **PID 39008 Termination**: Based on the observation of PID 39008 holding port 8000 (uvicorn backend), terminating PID 39008 frees port 8000. Under Windows user rules, `taskkill` is prohibited. Thus, the native PowerShell `Stop-Process -Id 39008 -Force` was invoked to terminate it safely.
2. **Safe Cache Cleanup**: Based on the cache directories and size measurements, `Remove-Item` was recursively applied to clear temporary files and logs under:
   * `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\runtime`
   * `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\standalone-output`
   * `C:\Users\zyu33\AppData\Local\Temp\id_photo_server\outputs` and `uploads`
   * `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\server\outputs`
   * `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\logs`
   * Root files: `watermark-iopaint-8081.err.log` and `watermark-iopaint-8081.log`.
   This keeps directory structures intact to avoid potential runtime missing-folder errors.
3. **Registry Reset**: Based on requirements, `Set-Content` was used to overwrite `asset_registry.json` with `[]` and `user_photo_registry.json` with `{}` in the `id_photo_server` AppData path.
4. **Model Weights Preservation**: Confirmed that model weight directories were excluded from deletion paths. Re-checking file structures and sizes after cleanup verified all ONNX, TFLite, and Torch checkpoints remained completely intact.
5. **Reports Generation**: The required `runtime-chain-audit.md` and `cache-clean-report.md` reports were written locally, then copied to the project root path.

---

## 3. Caveats
* **IOPaint Port 8081 Process**: Port 8081 remains active running `iopaint` under PID `46208`. Based on the request, only port 8000 PID 39008 was to be stopped, but IOPaint service statuses are detailed in `runtime-chain-audit.md` as requested.

---

## 4. Conclusion
Milestone 1 tasks are fully completed:
* Port 8000 backend process has been stopped.
* All identified temporary caches and uvicorn/watermark logs have been cleared.
* Registry JSON files are reset to original empty states.
* Model weights have been verified as intact.
* Audit and cleanup reports have been successfully generated at the project root.

---

## 5. Verification Method
* **Port Verification**:
  * Run: `cmd /c netstat -ano | findstr :8000` to confirm port 8000 is free and no process is listening.
* **Cache Clean Verification**:
  * Run: `Get-ChildItem -Path "C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii", "C:\Users\zyu33\AppData\Local\Temp\id_photo_server", "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\server\outputs", "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\logs" -Recurse -File`
  * Verify only `asset_registry.json` (containing `[]`) and `user_photo_registry.json` (containing `{}`) are present under `id_photo_server` and all other folders contain zero files.
* **Model Weight Verification**:
  * Run: `Get-ChildItem -Path "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\server\models", "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\weights", "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\retinaface\weights", "C:\Users\zyu33\.cache\torch\hub\checkpoints" -File` to confirm all weight files are present.
* **Reports Verification**:
  * View: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\runtime-chain-audit.md` and `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\cache-clean-report.md`.
