<#
.SYNOPSIS
  Start the local RAG API on loopback (127.0.0.1). Written in Phase 7; NOT executed during Phase 7.

.DESCRIPTION
  * Checks prerequisites only; it never installs packages and never edits your environment.
  * Never contains or prints secrets. The API token lives in your user profile
    (see: .venv\Scripts\python.exe run_api.py --show-token-path).
  * Always binds to 127.0.0.1; it has no option to expose the API to the network.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start_api.ps1
  powershell -ExecutionPolicy Bypass -File scripts\start_api.ps1 -Port 9000
#>
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Virtual environment not found at .venv. Create it and install requirements first (see docs/remediation/PHASE7_SECURITY_LOCAL_DEPLOYMENT.md)."
}
if (-not (Test-Path (Join-Path $Root ".env"))) {
    Write-Error ".env not found. Copy .env.example to .env and fill in your own values."
}

& $Python -c "import fastapi, uvicorn, multipart" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "API packages missing. Install them yourself: & '$Python' -m pip install -r backend\requirements-api.txt"
}

Write-Host "Starting RAG API on http://127.0.0.1:$Port/api/v1 (Ctrl+C to stop)"
Write-Host "Token file: run '& $Python run_api.py --show-token-path' (the token itself is never printed)."
Set-Location $Root
& $Python run_api.py --host 127.0.0.1 --port $Port
