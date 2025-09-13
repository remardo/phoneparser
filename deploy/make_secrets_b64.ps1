Param(
  [string]$ServiceAccountPath = "src/service-acount-sheets.json",
  [string]$SessionsPath = "src/sessions.json"
)

function Get-Base64 {
  param([string]$Path)
  if (-not (Test-Path $Path)) { return "" }
  $bytes = [System.IO.File]::ReadAllBytes($Path)
  [System.Convert]::ToBase64String($bytes)
}

$sa = Get-Base64 -Path $ServiceAccountPath
$sess = Get-Base64 -Path $SessionsPath

Write-Host "SA_JSON_B64=$sa"
Write-Host "SESSIONS_JSON_B64=$sess"