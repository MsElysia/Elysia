# Move Memory and Logs to F: Drive
# This script transfers all memory files and logs from Project Guardian to F: drive

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Moving Memory and Logs to F: Drive" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if F: drive exists
if (-not (Test-Path "F:\")) {
    Write-Host "[ERROR] F: drive not found!" -ForegroundColor Red
    Write-Host "Please ensure F: drive is available." -ForegroundColor Yellow
    exit 1
}

$sourceDir = "c:\Users\mrnat\Project guardian"
$targetBase = "F:\Project Guardian"

# Create target directory structure
$targetLogs = "$targetBase\logs"
$targetMemory = "$targetBase\memory"

Write-Host "[1/4] Creating target directories..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $targetBase | Out-Null
New-Item -ItemType Directory -Force -Path $targetLogs | Out-Null
New-Item -ItemType Directory -Force -Path $targetMemory | Out-Null
Write-Host "  [OK] Created: $targetBase" -ForegroundColor Green
Write-Host "  [OK] Created: $targetLogs" -ForegroundColor Green
Write-Host "  [OK] Created: $targetMemory" -ForegroundColor Green
Write-Host ""

# Move all log files
Write-Host "[2/4] Moving log files..." -ForegroundColor Yellow
$logFiles = Get-ChildItem -Path $sourceDir -Filter "*.log" -File -ErrorAction SilentlyContinue
$logCount = 0
$logSize = 0

foreach ($logFile in $logFiles) {
    try {
        $targetPath = Join-Path $targetLogs $logFile.Name
        Move-Item -Path $logFile.FullName -Destination $targetPath -Force
        $logCount++
        $logSize += $logFile.Length
        Write-Host "  [OK] Moved: $($logFile.Name)" -ForegroundColor Green
    } catch {
        Write-Host "  [ERROR] Failed to move $($logFile.Name): $_" -ForegroundColor Red
    }
}

if ($logCount -gt 0) {
    $logSizeMB = [math]::Round($logSize / 1MB, 2)
    Write-Host "  [OK] Moved $logCount log file(s) ($logSizeMB MB)" -ForegroundColor Green
} else {
    Write-Host "  [INFO] No log files found to move" -ForegroundColor Yellow
}
Write-Host ""

# Move memory directory
Write-Host "[3/4] Moving memory directory..." -ForegroundColor Yellow
$memorySource = Join-Path $sourceDir "memory"
if (Test-Path $memorySource) {
    try {
        # Get size before moving
        $memorySize = (Get-ChildItem -Path $memorySource -Recurse -File -ErrorAction SilentlyContinue | 
                      Measure-Object -Property Length -Sum).Sum
        
        # Move the entire memory directory
        Move-Item -Path $memorySource -Destination $targetMemory -Force
        $memorySizeMB = [math]::Round($memorySize / 1MB, 2)
        Write-Host "  [OK] Moved memory directory ($memorySizeMB MB)" -ForegroundColor Green
        
        # List contents
        $memoryFiles = Get-ChildItem -Path $targetMemory -Recurse -File
        foreach ($memFile in $memoryFiles) {
            Write-Host "    - $($memFile.Name) ($([math]::Round($memFile.Length / 1MB, 2)) MB)" -ForegroundColor Gray
        }
    } catch {
        Write-Host "  [ERROR] Failed to move memory directory: $_" -ForegroundColor Red
    }
} else {
    Write-Host "  [INFO] Memory directory not found at: $memorySource" -ForegroundColor Yellow
}
Write-Host ""

# Create symlinks back to original locations (optional - for compatibility)
Write-Host "[4/4] Creating symlinks for compatibility..." -ForegroundColor Yellow
try {
    # Create symlink for memory directory
    if (Test-Path $targetMemory) {
        $symlinkMemory = Join-Path $sourceDir "memory"
        if (-not (Test-Path $symlinkMemory)) {
            New-Item -ItemType SymbolicLink -Path $symlinkMemory -Target $targetMemory -Force | Out-Null
            Write-Host "  [OK] Created symlink: memory -> $targetMemory" -ForegroundColor Green
        }
    }
    
    # Create symlink for logs directory
    $symlinkLogs = Join-Path $sourceDir "logs"
    if (-not (Test-Path $symlinkLogs)) {
        New-Item -ItemType SymbolicLink -Path $symlinkLogs -Target $targetLogs -Force | Out-Null
        Write-Host "  [OK] Created symlink: logs -> $targetLogs" -ForegroundColor Green
    }
} catch {
    Write-Host "  [WARNING] Could not create symlinks (may require admin): $_" -ForegroundColor Yellow
    Write-Host "  [INFO] Files are still accessible at: $targetBase" -ForegroundColor Yellow
}
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Transfer Complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Files moved to F: drive:" -ForegroundColor Green
Write-Host "  Logs:    $targetLogs" -ForegroundColor White
Write-Host "  Memory:  $targetMemory" -ForegroundColor White
Write-Host ""
Write-Host "Total files moved:" -ForegroundColor Green
Write-Host "  Log files: $logCount" -ForegroundColor White
Write-Host "  Memory directory: 1" -ForegroundColor White
Write-Host ""
Write-Host "Symlinks created for compatibility (if admin rights available)" -ForegroundColor Yellow
Write-Host ""
