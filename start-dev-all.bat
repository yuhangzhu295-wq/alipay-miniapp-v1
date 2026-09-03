@echo off
setlocal

set "ROOT=%~dp0"
set "WECHAT_CLI=C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat"

echo [watermark] Starting OpenCV + HD repair service in a new terminal...
start "watermark-opencv-hd-service" cmd /k call "%ROOT%start-hd-watermark-service.bat"

if exist "%WECHAT_CLI%" (
  echo [watermark] Opening WeChat Developer Tools project...
  "%WECHAT_CLI%" open --project "%ROOT%"
) else (
  echo [watermark] WeChat Developer Tools CLI not found.
  echo [watermark] Please open this project manually: %ROOT%
)

endlocal
