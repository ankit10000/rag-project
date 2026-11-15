<#
.SYNOPSIS
  Start the local RAG API on loopback (127.0.0.1).

.DESCRIPTION
  * Checks prerequisites only; it never installs packages and never edits your environment.
  * Uses the project virtual environment's python.exe directly (equivalent to activating
    .venv; no Activate.ps1 / execution-policy change is needed).
  * Validates configuration first (run_api.py --check-config: .env is loaded, only
    variable NAMES are reported, never secret values).
  * Never contains or prints secrets. The API token lives in your user profile
    (see: .venv\Scripts\python.exe run_api.py --show-token-path).
  * Always binds to 127.0.0.1; it has no option to expose the API to the network.
  * Exit code: 0 only after a clean server shutdown; 1 for a failed prerequisite or
    configuration check; otherwise the server process's own exit code.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start_api.ps1
  powershell -ExecutionPolicy Bypass -File scripts\start_api.ps1 -Port 9000
#>
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8765
)

# "Continue": native-command stderr must not be turned into terminating errors
# (Windows PowerShell 5.1 wraps it in NativeCommandError); exit codes are checked explicitly.
$ErrorActionPreference = "Continue"

function Fail([string]$Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Fail "Virtual environment not found at $Root\.venv. Create it and install requirements first (see docs/remediation/PHASE7_SECURITY_LOCAL_DEPLOYMENT.md)."
}
if (-not (Test-Path (Join-Path $Root ".env"))) {
    Fail ".env not found in $Root. Copy .env.example to .env and fill in your own values."
}

Set-Location $Root

& $Python -c "import fastapi, starlette, uvicorn, multipart" *> $null
if ($LASTEXITCODE -ne 0) {
    Fail "API packages missing. Install them yourself: & '$Python' -m pip install -r requirements.txt -r backend\requirements-api.txt"
}

& $Python run_api.py --check-config
if ($LASTEXITCODE -ne 0) {
    Fail "Configuration check failed (see the messages above)."
}

Write-Host "Starting RAG API on http://127.0.0.1:$Port/api/v1 (Ctrl+C to stop)"
Write-Host "Token file: run '& $Python run_api.py --show-token-path' (the token itself is never printed)."
& $Python run_api.py --host 127.0.0.1 --port $Port
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-Host "ERROR: the API exited with code $code (see the log above)." -ForegroundColor Red
}
exit $code
