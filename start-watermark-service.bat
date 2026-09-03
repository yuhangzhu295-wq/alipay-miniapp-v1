@echo off
setlocal

set "ROOT=%~dp0"
set "SERVER_DIR=%ROOT%server"
set "HOST=0.0.0.0"
set "PORT=8000"
if "%ENABLE_HD_REPAIR%"=="" set "ENABLE_HD_REPAIR=true"
if "%HD_REPAIR_ENGINE%"=="" set "HD_REPAIR_ENGINE=lama"
if "%IOPAINT_URL%"=="" set "IOPAINT_URL=http://127.0.0.1:8081"

echo [watermark] Starting local OpenCV service...
echo [watermark] Server dir: %SERVER_DIR%

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PYTHON_CMD=py -3"
) else (
  where python >nul 2>nul
  if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=python"
  ) else (
    echo [watermark] Python was not found. Please install Python 3.10+ and retry.
    pause
    exit /b 1
  )
)

cd /d "%SERVER_DIR%"
if not exist requirements.txt (
  echo [watermark] requirements.txt not found in %SERVER_DIR%.
  pause
  exit /b 1
)

%PYTHON_CMD% -c "import fastapi, uvicorn, cv2, PIL" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  echo [watermark] Installing missing Python dependencies...
  %PYTHON_CMD% -m pip install -r requirements.txt
  if %ERRORLEVEL% NEQ 0 (
    echo [watermark] Failed to install dependencies.
    pause
    exit /b 1
  )
)

echo [watermark] Service address: http://127.0.0.1:%PORT%
echo [watermark] Health check: http://127.0.0.1:%PORT%/health
echo [watermark] OpenCV available: yes
echo [watermark] HD repair enabled: %ENABLE_HD_REPAIR%
echo [watermark] HD repair engine: %HD_REPAIR_ENGINE%
echo [watermark] IOPaint URL: %IOPAINT_URL%
echo [watermark] Manual remove API: http://127.0.0.1:%PORT%/api/watermark/manual-remove
echo [watermark] HD remove API: http://127.0.0.1:%PORT%/api/watermark/hd-remove
%PYTHON_CMD% -m uvicorn main:app --host %HOST% --port %PORT%

endlocal
