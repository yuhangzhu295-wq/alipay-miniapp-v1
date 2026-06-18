# Handoff Report — Explorer 1

## 1. Observation
1. Port 8000 process active listening check command:
   * Command: `cmd /c "netstat -ano | findstr 8000"`
   * Result:
     ```
     TCP    0.0.0.0:8000           0.0.0.0:0              LISTENING       39008
     ```
2. Process command line query command:
   * Command: `Get-CimInstance Win32_Process -Filter "ProcessId = 39008" | Select-Object CommandLine | Format-List`
   * Result:
     ```
     CommandLine : "C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
     ```
3. Port 8081 check command:
   * Command: `cmd /c "netstat -ano | findstr 8081"`
   * Result: Failed with exit code 1 (no active listening process).
4. `server/main.py` lines 49-54:
   ```python
   BASE_RUNTIME_DIR = os.environ.get(
       "ID_PHOTO_RUNTIME_DIR",
       os.path.join(tempfile.gettempdir(), "id_photo_server")
   )
   OUTPUTS_DIR = os.path.join(BASE_RUNTIME_DIR, "outputs")
   UPLOADS_DIR = os.path.join(BASE_RUNTIME_DIR, "uploads")
   ```
5. `C:\Users\zyu33\AppData\Local\Temp\id_photo_server` directory contents:
   * `outputs`: 89 files, total size ~2.65 MB.
   * `uploads`: 1 folder (watermark/hd), empty.
   * `asset_registry.json`: 52,916 bytes.
   * `user_photo_registry.json`: 2 bytes.
6. `server/outputs` directory contents:
   * 30 files, total size ~3.59 MB.
7. `logs` directory contents:
   * 18 log files, total size ~3.65 MB.
8. System temporary matting files observation (`server/services/portrait_matting.py` lines 1171-1172):
   ```python
   foreground_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
   mask_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
   ```
9. Model weights verification:
   * `third_party/HivisionIDPhotos/hivision/creator/weights/birefnet-v1-lite.onnx` (224,005,088 bytes) - Present.
   * `third_party/HivisionIDPhotos/hivision/creator/weights/hivision_modnet.onnx` (25,888,609 bytes) - Present.
   * `third_party/HivisionIDPhotos/hivision/creator/weights/modnet_photographic_portrait_matting.onnx` (25,888,640 bytes) - Present.
   * `third_party/HivisionIDPhotos/hivision/creator/weights/rmbg-1.4.onnx` (176,153,355 bytes) - Present.
   * `third_party/HivisionIDPhotos/hivision/creator/retinaface/weights/retinaface-resnet50.onnx` (109,458,296 bytes) - Present.
   * `server/models/blaze_face_short_range.tflite` (229,746 bytes) - Present.
   * `C:\Users\zyu33\.cache\torch\hub\checkpoints\big-lama.pt` (205,669,692 bytes) - Present.

---

## 2. Logic Chain
1. From Observation 1 and 2, PID 39008 runs the FastAPI app on port 8000. It is bound to `0.0.0.0`.
2. From Observation 3 and batch script analysis, the bat file starts IOPaint on port 8081, but it is currently inactive.
3. From Observation 4, the active runtime directory defaults to `C:\Users\zyu33\AppData\Local\Temp\id_photo_server`.
4. Observation 5, 6, and 7 identify active and workspace cache/log targets. Cleaning these will not break core model weights.
5. From Observation 8, `delete=False` is used for matting temporary files. Since `PREPARE_CACHE` is an in-memory dictionary, these files become orphaned after a server restart/crash and remain in the system temp directory, requiring periodic cleanup.
6. From Observation 9, all required model weight files are present in the specified locations and have valid sizes, meaning no model downloads are needed.

---

## 3. Caveats
* We assumed that the server is run using the default configuration without `ID_PHOTO_RUNTIME_DIR` set in the environment variables, which we verified since the active temp files are located in `C:\Users\zyu33\AppData\Local\Temp\id_photo_server`. If a custom path is set in the environment, the cleanup script must clean that custom path instead.
* The system temp directory `C:\Users\zyu33\AppData\Local\Temp` contains other processes' temp files. The cleanup plan specifies cleaning only `tmp*.png` files created by the application process or matching the pattern and timestamp threshold to prevent deleting unrelated system files.

---

## 4. Conclusion
* The FastAPI backend is running on PID 39008 on port 8000. It can be audited via `netstat` and stopped using PowerShell's `Stop-Process`.
* Cache/temp files are split between the active temp directory (`C:\Users\zyu33\AppData\Local\Temp\id_photo_server`), workspace directories (`server/outputs`, `logs`), and the system temp directory (orphaned matting `tmp*.png` files). A total of ~10 MB of cache and logs can be cleaned.
* All model weight files are present and verified.
* Drafts for root files `runtime-chain-audit.md` and `cache-clean-report.md` have been generated as proposed files inside `.agents/explorer_m1_1/` for the Implementer to copy to the root.

---

## 5. Verification Method
* **Process audit verification**: Run `netstat -ano | findstr 8000` to verify port 8000 state.
* **Weights verification**: Run `Get-ChildItem -Recurse -Filter *.onnx` to inspect all ONNX model weight files.
* **Cache verification**: Check the size and existence of `C:\Users\zyu33\AppData\Local\Temp\id_photo_server` and `server/outputs` before and after running the implementer's cleanup script.
