param()

$ErrorActionPreference = "Stop"
$Base = "C:\apps\id-photo"
$Shared = Join-Path $Base "shared"
$Runtime = Join-Path $Shared "runtime"
$NginxRoot = Get-ChildItem -Directory -Path $Runtime -Filter "nginx-*" -ErrorAction SilentlyContinue |
  Sort-Object Name -Descending |
  Select-Object -First 1
if (-not $NginxRoot) { throw "Nginx runtime not found in $Runtime" }

$NginxExe = Join-Path $NginxRoot.FullName "nginx.exe"
Set-Location $NginxRoot.FullName
& $NginxExe -p $NginxRoot.FullName -c "conf\nginx.conf"
