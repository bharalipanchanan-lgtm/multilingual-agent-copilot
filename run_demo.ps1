# Windows launcher for Claviq Agent Copilot
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
  throw "Missing .venv. Run: py -3 -m venv .venv && .\.venv\Scripts\pip install -r requirements.txt"
}

if (-not $env:COPILOT_BACKEND) {
  $env:COPILOT_BACKEND = "ollama"
}
$env:HF_HUB_DISABLE_XET = "1"

Write-Host "Starting server on http://127.0.0.1:8000 (backend=$env:COPILOT_BACKEND)"
& $venvPython server.py
