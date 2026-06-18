# Milestone 1 Validation Report

## 1. Port 8000 Availability Check

We executed the command `netstat -ano | findstr :8000` to verify whether port 8000 is free.

### Observation:
Port 8000 is **NOT** free. There is a process listening on port 8000:
- **Protocol**: TCP
- **Local Address**: `0.0.0.0:8000`
- **Status**: `LISTENING`
- **Process ID (PID)**: `3932`
- **Process Executable**: `C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe`
- **Command Line**: `C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload` (or similar)

There are also established connections and TIME_WAIT sockets associated with this port.

---

## 2. Model Weights Verification

We verified the existence and exact sizes of all 7 requested model weights:

| Model Name | Path | Size (Bytes) | Status |
|---|---|---|---|
| **birefnet-v1-lite.onnx** | `third_party\HivisionIDPhotos\hivision\creator\weights\birefnet-v1-lite.onnx` | 224,005,088 | **PRESENT** |
| **rmbg-1.4.onnx** | `third_party\HivisionIDPhotos\hivision\creator\weights\rmbg-1.4.onnx` | 176,153,355 | **PRESENT** |
| **hivision_modnet.onnx** | `third_party\HivisionIDPhotos\hivision\creator\weights\hivision_modnet.onnx` | 25,888,609 | **PRESENT** |
| **modnet_photographic_portrait_matting.onnx** | `third_party\HivisionIDPhotos\hivision\creator\weights\modnet_photographic_portrait_matting.onnx` | 25,888,640 | **PRESENT** |
| **retinaface-resnet50.onnx** | `third_party\HivisionIDPhotos\hivision\creator\retinaface\weights\retinaface-resnet50.onnx` | 109,458,296 | **PRESENT** |
| **blaze_face_short_range.tflite** | `server\models\blaze_face_short_range.tflite` | 229,746 | **PRESENT** |
| **big-lama.pt** | `C:\Users\zyu33\.cache\torch\hub\checkpoints\big-lama.pt` | 205,669,692 | **PRESENT** |

All 7 models are present on the disk with correct sizes.
