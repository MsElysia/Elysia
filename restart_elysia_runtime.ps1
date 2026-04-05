# Quick script to restart Elysia runtime
Write-Host "Stopping existing Elysia runtime..."
Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like '*elysia*' -or $_.MainWindowTitle -like '*elysia*'
} | Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 2

Write-Host "Starting Elysia runtime..."
Start-Process python -ArgumentList "-m", "elysia", "run", "--mode=all" -WindowStyle Minimized

Write-Host "Runtime restarted. Waiting for API to be ready..."
Start-Sleep -Seconds 3

# Test if API is responding
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8123/api/ping" -TimeoutSec 2 -UseBasicParsing
    Write-Host "✓ API is responding!" -ForegroundColor Green
} catch {
    Write-Host "✗ API not responding yet. Wait a few more seconds." -ForegroundColor Yellow
}

