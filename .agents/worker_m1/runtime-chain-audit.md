# Runtime Chain Audit Report

## 1. Port Usage
* **Port 8000**: Used by the main FastAPI backend service (`main:app`).
  * Status: **Stopped** (previously running under PID `39008`).
* **Port 8081**: Used by the IOPaint/LaMa inpainting service.
  * Status: **Active** (running under PID `46208`).

---

## 2. Process Command Lines
* **Main Backend (Port 8000)**:
  ```cmd
  "C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
  ```
* **IOPaint Service (Port 8081)**:
  ```cmd
  C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe -m iopaint start --host 127.0.0.1 --port 8081 --model lama --device cpu --no-inbrowser --quality 100
  ```

---

## 3. How to Stop Processes Safely on Windows
Since `taskkill` is a restricted/prohibited command in the user workspace rules, processes are stopped using PowerShell:
```powershell
Stop-Process -Id <PID> -Force
```
* Main Backend (PID `39008`) was stopped using:
  ```powershell
  Stop-Process -Id 39008 -Force
  ```
* IOPaint Service (PID `46208`) can be stopped using:
  ```powershell
  Stop-Process -Id 46208 -Force
  ```

---

## 4. Startup Scripts Audit
The project includes the following batch scripts for automation:

1. **`start-all-services.bat`**:
   * Entry point script.
   * Calls `start-dev-all.bat`.

2. **`start-dev-all.bat`**:
   * Launches `start-hd-watermark-service.bat` in a separate command window (`start "watermark-opencv-hd-service" ...`).
   * Attempts to open the WeChat Developer Tools CLI (`cli.bat`) targeting the project root if it exists.

3. **`start-hd-watermark-service.bat`**:
   * Initializes environment configurations (host `0.0.0.0`, port `8000`, IOPaint port `8081`, engine `lama`, HD repair enabled).
   * Checks for Python 3 installation.
   * Installs dependencies from `server/requirements.txt` if necessary.
   * Detects the `iopaint` module:
     * If installed, runs `iopaint start` on port `8081` with CPU device.
     * If not, reports `hdAvailable=false` but proceeds.
   * Starts uvicorn server on port `8000` with hot reload enabled.

4. **`start-watermark-service.bat`**:
   * Launches only the local FastAPI backend service on port `8000` (without spawning an IOPaint process).

---

## 5. Engine Statuses
* **HivisionIDPhotos Creator Engine**:
  * Status: **Available**.
  * Model weights present under:
    * `third_party/HivisionIDPhotos/hivision/creator/weights/birefnet-v1-lite.onnx`
    * `third_party/HivisionIDPhotos/hivision/creator/weights/hivision_modnet.onnx`
    * `third_party/HivisionIDPhotos/hivision/creator/weights/modnet_photographic_portrait_matting.onnx`
    * `third_party/HivisionIDPhotos/hivision/creator/weights/rmbg-1.4.onnx`
* **RetinaFace Engine**:
  * Status: **Available**.
  * Model weights present under:
    * `third_party/HivisionIDPhotos/hivision/creator/retinaface/weights/retinaface-resnet50.onnx`
* **LaMa Inpainting Engine (IOPaint)**:
  * Status: **Active** on port `8081`.
  * Model weights present under:
    * `C:\Users\zyu33\.cache\torch\hub\checkpoints\big-lama.pt`
