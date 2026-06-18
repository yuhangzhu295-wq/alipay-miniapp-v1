param()

$ErrorActionPreference = "Stop"
$Base = "C:\apps\id-photo"
$Current = Join-Path $Base "current"
$Previous = Join-Path $Base "previous"

if (-not (Test-Path $Previous)) {
  throw "No previous release junction exists"
}

Stop-ScheduledTask -TaskName "id-photo-api" -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName "id-photo-iopaint" -ErrorAction SilentlyContinue

if (Test-Path $Current) { Remove-Item -Path $Current -Force -Recurse }
cmd.exe /c mklink /J $Current $Previous | Out-Null

Start-ScheduledTask -TaskName "id-photo-iopaint" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Start-ScheduledTask -TaskName "id-photo-api" -ErrorAction SilentlyContinue
