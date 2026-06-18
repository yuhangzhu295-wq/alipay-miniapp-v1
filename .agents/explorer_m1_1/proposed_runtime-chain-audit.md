# Runtime Chain Audit Report

This report outlines the active processes and network services associated with the ID Photo Generator application.

## 1. Active Services and Port Usage

### Port 8000 (FastAPI Backend)
* **Status**: Active (LISTENING)
* **Process ID (PID)**: 39008
* **Process Name**: `python.exe`
* **Command Line**: `"C:\Users\zyu33\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000`
* **Start Path**: Started via `start-hd-watermark-service.bat` (or `start-watermark-service.bat` / `start-dev-all.bat`)
* **Bind Address**: `0.0.0.0:8000`

### Port 8081 (IOPaint Service)
* **Status**: Inactive (Not running)
* **Start Command (in bat)**: `%PYTHON_CMD% -m iopaint start --host 127.0.0.1 --port 8081 --model lama --device cpu --no-inbrowser --quality 100`
* **Log Files**: `watermark-iopaint-8081.log`, `watermark-iopaint-8081.err.log`

---

## 2. Service Startup Chain Analysis

The application services are initiated through a chain of Windows batch files:
1. **`start-all-services.bat`**: Entry point that invokes `start-dev-all.bat`.
2. **`start-dev-all.bat`**: Sets up WeChat Developer Tools path and calls `start-hd-watermark-service.bat` in a new window.
3. **`start-hd-watermark-service.bat`**:
   - Spawns IOPaint on port 8081 (if installed).
   - Starts the main FastAPI application using Uvicorn on port 8000:
     `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

---

## 3. Auditing & Process Control Instructions

### Port Audit Command (Windows PowerShell)
To identify which process is currently holding port 8000 or 8081, run:
```powershell
netstat -ano | findstr :8000
netstat -ano | findstr :8081
```

To fetch detailed information of the process using PowerShell:
```powershell
Get-Process -Id <PID>
Get-CimInstance Win32_Process -Filter "ProcessId = <PID>" | Select-Object CommandLine | Format-List
```

### Stop Service Commands (Windows PowerShell)
* **Graceful termination**: Locate the terminal window executing the service (named "watermark-opencv-hd-service" or "watermark-iopaint-lama") and press `Ctrl+C`.
* **Forced CLI termination**:
  ```powershell
  Stop-Process -Id <PID> -Force
  ```
* **Interactive termination**: Open Windows Task Manager, find the `python` process corresponding to `<PID>` under the "Details" tab, and select "End Process".
