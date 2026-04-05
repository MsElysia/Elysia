# Start Control Panel
# Runs the FastAPI control panel on 127.0.0.1:8000

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "Starting Project Guardian Control Panel..."
Write-Host ""

# Check if UI dependencies are installed
$uiDepsFile = Join-Path $projectRoot "requirements-ui.txt"
if (Test-Path $uiDepsFile) {
    Write-Host "[INFO] UI dependencies file found: requirements-ui.txt"
    Write-Host "[INFO] If you see import errors, install with: pip install -r requirements-ui.txt"
    Write-Host ""
}

# Check if FastAPI is available
try {
    python -c "import fastapi" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARNING] FastAPI not found. Install UI dependencies:" -ForegroundColor Yellow
        Write-Host "  pip install -r requirements-ui.txt" -ForegroundColor Yellow
        Write-Host ""
    }
} catch {
    Write-Host "[WARNING] Could not check for FastAPI. Install UI dependencies:" -ForegroundColor Yellow
    Write-Host "  pip install -r requirements-ui.txt" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "URL: http://127.0.0.1:8000"
Write-Host ""
Write-Host "[SECURITY] Control panel is bound to 127.0.0.1 (local-only)." -ForegroundColor Green
Write-Host "[SECURITY] Do NOT modify --host parameter. Remote access is blocked by application middleware." -ForegroundColor Yellow
Write-Host ""

python -m uvicorn project_guardian.ui.app:app --host 127.0.0.1 --port 8000
