param(
  [Parameter(Mandatory = $true)][string]$RunId,
  [Parameter(Mandatory = $true)][string]$PackagePath
)

$ErrorActionPreference = "Stop"
$Base = "C:\apps\id-photo"
$Shared = Join-Path $Base "shared"
$Runtime = Join-Path $Shared "runtime"
$Downloads = Join-Path $Runtime "downloads"
$Logs = Join-Path $Shared "logs"
$Release = Join-Path $Base "releases\$RunId"
$InstallLog = Join-Path $Logs "install-$RunId.log"

function Log($Message) {
  New-Item -ItemType Directory -Force -Path $Logs | Out-Null
  Add-Content -Path $InstallLog -Encoding UTF8 -Value ("{0} {1}" -f (Get-Date).ToString("o"), $Message)
}

function Download-File($Url, $Target) {
  if (Test-Path $Target) { return }
  Log "download $Url"
  Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Target
}

function Ensure-Python() {
  $PythonRoot = Join-Path $Runtime "Python311"
  $Python = Join-Path $PythonRoot "python.exe"
  if (Test-Path $Python) { return $Python }
  $Installer = Join-Path $Downloads "python-3.11.9-amd64.exe"
  Download-File "https://npmmirror.com/mirrors/python/3.11.9/python-3.11.9-amd64.exe" $Installer
  Log "install python"
  $Args = "/quiet InstallAllUsers=1 TargetDir=`"$PythonRoot`" Include_pip=1 Include_launcher=0 Include_test=0 PrependPath=0"
  $p = Start-Process -FilePath $Installer -ArgumentList $Args -Wait -PassThru
  if ($p.ExitCode -ne 0) { throw "Python installer exit code $($p.ExitCode)" }
  return $Python
}

function Ensure-Node() {
  $NodeRoot = Join-Path $Runtime "node-v20.12.2-win-x64"
  $Node = Join-Path $NodeRoot "node.exe"
  if (Test-Path $Node) { return $NodeRoot }
  $Zip = Join-Path $Downloads "node-v20.12.2-win-x64.zip"
  Download-File "https://npmmirror.com/mirrors/node/v20.12.2/node-v20.12.2-win-x64.zip" $Zip
  Expand-Archive -LiteralPath $Zip -DestinationPath $Runtime -Force
  return $NodeRoot
}

function Ensure-Nginx() {
  $NginxRoot = Join-Path $Runtime "nginx-1.26.2"
  $Nginx = Join-Path $NginxRoot "nginx.exe"
  if (-not (Test-Path $Nginx)) {
    $Zip = Join-Path $Downloads "nginx-1.26.2.zip"
    Download-File "https://nginx.org/download/nginx-1.26.2.zip" $Zip
    Expand-Archive -LiteralPath $Zip -DestinationPath $Runtime -Force
  }
  $Conf = Join-Path $NginxRoot "conf\nginx.conf"
  @"
worker_processes  1;
events { worker_connections  1024; }
http {
  include       mime.types;
  default_type  application/octet-stream;
  sendfile        on;
  keepalive_timeout  65;
  client_max_body_size 32m;
  server {
    listen 80;
    server_name _;
    location / {
      proxy_pass http://127.0.0.1:8000;
      proxy_set_header Host `$host;
      proxy_set_header X-Real-IP `$remote_addr;
      proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
      proxy_read_timeout 180s;
    }
  }
}
"@ | Set-Content -Path $Conf -Encoding ASCII
  return $NginxRoot
}

function Try-Ensure-Git() {
  $GitRoot = Join-Path $Runtime "mingit"
  $Git = Join-Path $GitRoot "cmd\git.exe"
  if (Test-Path $Git) { return $Git }
  try {
    $Zip = Join-Path $Downloads "MinGit-2.45.2-64-bit.zip"
    Download-File "https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/MinGit-2.45.2-64-bit.zip" $Zip
    New-Item -ItemType Directory -Force -Path $GitRoot | Out-Null
    Expand-Archive -LiteralPath $Zip -DestinationPath $GitRoot -Force
    return $Git
  } catch {
    Log ("git install skipped: " + $_.Exception.Message)
    return $null
  }
}

New-Item -ItemType Directory -Force -Path `
  $Base,
  (Join-Path $Base "releases"),
  $Shared,
  (Join-Path $Shared "config"),
  (Join-Path $Shared "data"),
  (Join-Path $Shared "uploads"),
  (Join-Path $Shared "outputs"),
  (Join-Path $Shared "temp"),
  (Join-Path $Shared "logs"),
  (Join-Path $Shared "reports"),
  (Join-Path $Base "backups"),
  $Runtime,
  $Downloads | Out-Null

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like "*$Release*" } |
  ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate | Out-Null }
Start-Sleep -Seconds 2
if (Test-Path $Release) { Remove-Item -LiteralPath $Release -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Release | Out-Null
Log "expand package $PackagePath to $Release"
Expand-Archive -LiteralPath $PackagePath -DestinationPath $Release -Force

$Python = Ensure-Python
$NodeRoot = Ensure-Node
$NginxRoot = Ensure-Nginx
$Git = Try-Ensure-Git

$env:Path = "$NodeRoot;$NodeRoot\node_modules\npm\bin;$Runtime\mingit\cmd;$env:Path"
$Venv = Join-Path $Release ".venv"
Log "create venv"
& $Python -m venv $Venv
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"
$PipMirror = @("--index-url", "https://mirrors.aliyun.com/pypi/simple/", "--trusted-host", "mirrors.aliyun.com", "--timeout", "120")
Log "upgrade pip"
& $VenvPython -m pip install @PipMirror --upgrade pip setuptools wheel
Log "install server requirements"
& $Pip install @PipMirror -r (Join-Path $Release "server\requirements.txt")
Log "install iopaint"
& $Pip install @PipMirror iopaint

$HealthScript = Join-Path $Release "deploy\cloud\health-check.ps1"
if (-not (Test-Path $HealthScript)) { throw "deployment scripts missing from release" }

$Summary = [ordered]@{
  runId = $RunId
  release = $Release
  python = (& $VenvPython --version)
  pip = (& $Pip --version)
  node = (& (Join-Path $NodeRoot "node.exe") --version)
  npm = (& (Join-Path $NodeRoot "npm.cmd") --version)
  git = if ($Git) { (& $Git --version) } else { $null }
  nginxRoot = $NginxRoot
  installedAt = (Get-Date).ToString("o")
}
$Summary | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $Logs "install-$RunId.json") -Encoding UTF8
$Summary | ConvertTo-Json -Depth 6
