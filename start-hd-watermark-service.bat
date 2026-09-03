@echo off
setlocal

set "ROOT=%~dp0"
set "SERVER_DIR=%ROOT%server"
set "HOST=0.0.0.0"
set "PORT=8000"
if "%IOPAINT_PORT%"=="" set "IOPAINT_PORT=8081"
if "%ENABLE_HD_REPAIR%"=="" set "ENABLE_HD_REPAIR=true"
if "%HD_REPAIR_ENGINE%"=="" set "HD_REPAIR_ENGINE=lama"
if "%IOPAINT_URL%"=="" set "IOPAINT_URL=http://127.0.0.1:%IOPAINT_PORT%"

echo [watermark-hd] Starting OpenCV + LaMa/IOPaint service...
echo [watermark-hd] Server dir: %SERVER_DIR%

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PYTHON_CMD=py -3"
) else (
  where python >nul 2>nul
  if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=python"
  ) else (
    echo [watermark-hd] Python was not found. Please install Python 3.10+ and retry.
    pause
    exit /b 1
  )
)

cd /d "%SERVER_DIR%"
if not exist requirements.txt (
  echo [watermark-hd] requirements.txt not found in %SERVER_DIR%.
  pause
  exit /b 1
)

%PYTHON_CMD% -c "import fastapi, uvicorn, cv2, PIL, requests" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  echo [watermark-hd] Installing missing Python dependencies...
  %PYTHON_CMD% -m pip install -r requirements.txt
  if %ERRORLEVEL% NEQ 0 (
    echo [watermark-hd] Failed to install dependencies.
    pause
    exit /b 1
  )
)

%PYTHON_CMD% -c "import iopaint" >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  echo [watermark-hd] Starting IOPaint on %IOPAINT_URL% ...
  start "watermark-iopaint-lama" cmd /k %PYTHON_CMD% -m iopaint start --host 127.0.0.1 --port %IOPAINT_PORT% --model %HD_REPAIR_ENGINE% --device cpu --no-inbrowser --quality 100
) else (
  echo [watermark-hd] IOPaint Python package was not found.
  echo [watermark-hd] HD service will report hdAvailable=false until IOPaint is installed and running.
  echo [watermark-hd] Install manually: %PYTHON_CMD% -m pip install iopaint
)

echo [watermark-hd] Service address: http://127.0.0.1:%PORT%
echo [watermark-hd] Health check: http://127.0.0.1:%PORT%/health
echo [watermark-hd] OpenCV available: yes
echo [watermark-hd] LaMa / IOPaint URL: %IOPAINT_URL%
echo [watermark-hd] Manual remove API: http://127.0.0.1:%PORT%/api/watermark/manual-remove
echo [watermark-hd] HD remove API: http://127.0.0.1:%PORT%/api/watermark/hd-remove
%PYTHON_CMD% -m uvicorn main:app --host %HOST% --port %PORT% --reload

endlocal
