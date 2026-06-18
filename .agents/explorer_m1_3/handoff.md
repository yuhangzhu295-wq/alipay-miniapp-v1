# Handoff Report — Explorer 3 (Milestone 1)

## 1. Observation

- **Port 8000 Activity**: Hitting `http://127.0.0.1:8000/health` or `http://127.0.0.1:8000/api/id-photo/health` succeeds. Specifically, the engine-info endpoint returned:
  ```json
  {"success": True, "engine": "hivision", "engineVersion": "id-photo-final-fix-source-bg-residue-v42-20260617", "selectedModel": "rmbg-1.4", "loaded": True, "selectionReason": "standalone verification marker found..."}
  ```
- **Process running on Port 8000**:
  - Found PID `39008` using `netstat -ano | findstr 8000`:
    ```
    TCP    0.0.0.0:8000           0.0.0.0:0              LISTENING       39008
    ```
  - Identified process command line using `Get-CimInstance Win32_Process -Filter "ProcessId = 39008"`:
    ```
    CommandLine: "C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
    ```
- **Port 8081 Activity**: Running `netstat -ano | findstr 8081` failed with exit code 1 (no active listening port).
- **Hivision Weights**: Running `find_by_name` for `*.onnx` within `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器` returned:
  - `third_party/HivisionIDPhotos/hivision/creator/weights/birefnet-v1-lite.onnx` (224,005,088 bytes)
  - `third_party/HivisionIDPhotos/hivision/creator/weights/rmbg-1.4.onnx` (176,153,355 bytes)
  - `third_party/HivisionIDPhotos/hivision/creator/weights/hivision_modnet.onnx` (25,888,609 bytes)
  - `third_party/HivisionIDPhotos/hivision/creator/weights/modnet_photographic_portrait_matting.onnx` (25,888,640 bytes)
  - `third_party/HivisionIDPhotos/hivision/creator/retinaface/weights/retinaface-resnet50.onnx` (109,458,296 bytes)
- **Local Face Detector Weight**:
  - `server/models/blaze_face_short_range.tflite` (229,746 bytes)
- **Torch Cache Inpaint Weight**:
  - Found `C:\Users\zyu33\.cache\torch\hub\checkpoints\big-lama.pt` (205,669,692 bytes) using directory search.
- **Cache Footprints**: Running a Python analysis script returned:
  - `C:\Users\zyu33\AppData\Local\Temp\id_photo_server` : 91 files, 2.54 MB
  - `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\runtime` : 3568 files, 1342.89 MB
  - `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\standalone-output` : 4 files, 1.20 MB
  - `server/outputs` : 30 files, 4.53 MB
  - `logs` : 18 files, 3.48 MB

---

## 2. Logic Chain

1. **Port 8000 Process Identification**: The success of the local HTTP health checks combined with `netstat -ano` shows that the port is bound. Querying WMI with PID 39008 retrieves the exact uvicorn command line.
2. **Port 8081 Inactivity**: The netstat failure demonstrates that IOPaint is not running, explaining why the health check lists `hdAvailable: false` and `hdEngine: not_ready`.
3. **Weight Location Verification**: Finding the `.onnx` files in the `third_party/HivisionIDPhotos` path confirms Hivision creator is pre-installed with its dependencies. Finding `big-lama.pt` in `C:\Users\zyu33\.cache\torch` confirms the offline model for IOPaint is available.
4. **Cache Directory Identification**: Examining `server/main.py` and `server/id_photo_engines/hivision/runner.py` shows:
   - `BASE_RUNTIME_DIR` defaults to the OS temp folder (`C:\Users\zyu33\AppData\Local\Temp\id_photo_server`).
   - Hivision runner uses an ASCII mapping in `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\runtime` to run subprocesses.
5. **Accumulation Cause**: Python `subprocess.run` executions of `inference.py` in Hivision write to `idphoto_hivision_ascii/runtime` but do not clear them afterward, leading to 1.34 GB of accumulated file assets.

---

## 3. Caveats

- We assumed that `tempfile.gettempdir()` resolves to `C:\Users\zyu33\AppData\Local\Temp` for all executing environments under this user.
- We did not manually stop the port 8000 process or delete any cache folders because we are constrained to a read-only investigation.

---

## 4. Conclusion

- **Audit**: Port 8000 is running FastAPI/Uvicorn under PID `39008`. Port 8081 is inactive.
- **Cache**: 1.34 GB of runtime files exist in `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\runtime` and should be targeted for cleanup alongside local `server/outputs` and `logs`.
- **Weights**: All necessary weights (`rmbg-1.4.onnx`, `birefnet-v1-lite.onnx`, `big-lama.pt`, etc.) are present and fully verified.
- **Planning**: We have defined the scope and structure for `runtime-chain-audit.md` and `cache-clean-report.md`.

---

## 5. Verification Method

- **Command to Verify Process**:
  `Get-CimInstance Win32_Process -Filter "ProcessId = 39008" | Select-Object CommandLine`
- **Command to Verify Weights presence**:
  `Test-Path "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\weights\rmbg-1.4.onnx"`
- **Command to Verify Cache Size**:
  `Get-ChildItem -Path C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\runtime -Recurse | Measure-Object -Property Length -Sum`
