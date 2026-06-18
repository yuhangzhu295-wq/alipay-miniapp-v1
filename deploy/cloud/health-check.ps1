param(
  [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
function Get-Json($Url) {
  try {
    $r = Invoke-RestMethod -Uri $Url -TimeoutSec 10
    return [ordered]@{ url = $Url; passed = $true; data = $r }
  } catch {
    return [ordered]@{ url = $Url; passed = $false; error = $_.Exception.Message }
  }
}

$Payload = [ordered]@{
  generatedAt = (Get-Date).ToString("o")
  baseUrl = $BaseUrl
  api = Get-Json ($BaseUrl.TrimEnd("/") + "/api/health")
  watermark = Get-Json ($BaseUrl.TrimEnd("/") + "/api/watermark/health")
  retention = Get-Json ($BaseUrl.TrimEnd("/") + "/api/assets/retention-policy")
  capabilities = Get-Json ($BaseUrl.TrimEnd("/") + "/api/id-photo/capabilities")
}
$Payload.passed = ($Payload.api.passed -and $Payload.watermark.passed -and $Payload.retention.passed -and $Payload.capabilities.passed)
$Payload | ConvertTo-Json -Depth 10
if (-not $Payload.passed) { exit 1 }
