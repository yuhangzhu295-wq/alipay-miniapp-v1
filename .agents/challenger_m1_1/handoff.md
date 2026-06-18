# Handoff Report - Milestone 1 Validation Checks

## 1. Observation

We executed verification tools and terminal commands to assess port 8000 and the presence/sizes of the model weights:

- **Port 8000 Check**:
  Command executed: `netstat -ano | findstr :8000`
  Verbatim output:
  ```text
    TCP    0.0.0.0:8000           0.0.0.0:0              LISTENING       3932
    TCP    127.0.0.1:8000         127.0.0.1:57345        ESTABLISHED     3932
    ... (several sockets in TIME_WAIT status) ...
  ```
  Process details lookup: `Get-CimInstance Win32_Process -Filter "ProcessId = 3932" | Select-Object CommandLine`
  Verbatim output:
  ```text
  CommandLine
  -----------
  C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
  ```

- **Matting Weights (Hivision Creator)**:
  `list_dir` on `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\weights`
  Verbatim output:
  ```json
  {"name":"birefnet-v1-lite.onnx", "sizeBytes":"224005088"}
  {"name":"hivision_modnet.onnx", "sizeBytes":"25888609"}
  {"name":"modnet_photographic_portrait_matting.onnx", "sizeBytes":"25888640"}
  {"name":"rmbg-1.4.onnx", "sizeBytes":"176153355"}
  ```

- **Retinaface Weights**:
  `list_dir` on `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\retinaface\weights`
  Verbatim output:
  ```json
  {"name":"retinaface-resnet50.onnx", "sizeBytes":"109458296"}
  ```

- **Blaze Face Weights**:
  `list_dir` on `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\server\models`
  Verbatim output:
  ```json
  {"name":"blaze_face_short_range.tflite", "sizeBytes":"229746"}
  ```

- **Big-Lama Weights**:
  PowerShell command executed: `Get-Item C:\Users\zyu33\.cache\torch\hub\checkpoints\big-lama.pt | Select-Object Name, Length`
  Verbatim output:
  ```text
  Name           Length
  ----           ------
  big-lama.pt 205669692
  ```

---

## 2. Logic Chain

1. **Port 8000 Status**:
   - Observation shows PID `3932` holds a `LISTENING` socket on `0.0.0.0:8000` and has active connections (ESTABLISHED/TIME_WAIT).
   - PID `3932` is identified as a Python process running uvicorn on port 8000.
   - Therefore, port 8000 is **not completely free**; it is currently occupied by the backend FastAPI/uvicorn server.

2. **Model Weights presence and sizes**:
   - The files `birefnet-v1-lite.onnx`, `rmbg-1.4.onnx`, `hivision_modnet.onnx`, and `modnet_photographic_portrait_matting.onnx` exist in `third_party\HivisionIDPhotos\hivision\creator\weights\` with sizes `224005088`, `176153355`, `25888609`, and `25888640` bytes respectively.
   - The file `retinaface-resnet50.onnx` exists in `third_party\HivisionIDPhotos\hivision\creator\retinaface\weights\` with size `109458296` bytes.
   - The file `blaze_face_short_range.tflite` exists in `server\models\` with size `229746` bytes.
   - The file `big-lama.pt` exists in `C:\Users\zyu33\.cache\torch\hub\checkpoints\` with size `205669692` bytes.
   - All 7 expected files exist, match their respective name constraints, and display correct storage footprints.

---

## 3. Caveats

- We assume the uvicorn process running on port 8000 is the expected project backend server.
- The `big-lama.pt` model is stored in the user's global torch cache directory (`C:\Users\zyu33\.cache\torch\hub\checkpoints\big-lama.pt`) rather than inside the project directory itself, which is normal for PyTorch hub downloads.

---

## 4. Conclusion

- **Port 8000**: Currently occupied by uvicorn backend server (PID 3932). It is NOT completely free.
- **Model weights**: All 7 model weights are present with their expected sizes.

---

## 5. Verification Method

To independently verify these checks:

1. **Port 8000**:
   Run the following PowerShell command to identify any listening processes on port 8000:
   ```powershell
   Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, State, OwningProcess
   ```
2. **Model Weights presence and sizes**:
   Run the following PowerShell script to print file locations and sizes:
   ```powershell
   $paths = @(
       "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\weights\birefnet-v1-lite.onnx",
       "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\weights\rmbg-1.4.onnx",
       "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\weights\hivision_modnet.onnx",
       "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\weights\modnet_photographic_portrait_matting.onnx",
       "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\third_party\HivisionIDPhotos\hivision\creator\retinaface\weights\retinaface-resnet50.onnx",
       "C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\server\models\blaze_face_short_range.tflite",
       "C:\Users\zyu33\.cache\torch\hub\checkpoints\big-lama.pt"
   )
   foreach ($p in $paths) {
       if (Test-Path $p) {
           $item = Get-Item $p
           Write-Host "$($item.Name) exists, size: $($item.Length) bytes"
       } else {
           Write-Warning "$p DOES NOT exist"
       }
   }
   ```
