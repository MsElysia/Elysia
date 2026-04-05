@echo off
echo ========================================
echo VIEWING ELYSIA LOGS
echo ========================================
echo.
echo Choose log to view:
echo.
echo 1. Main log (elysia_unified.log) - Recent activity
echo 2. Unified log (unified_autonomous_system.log) - Full history
echo 3. View last 50 lines of unified log
echo 4. Exit
echo.
set /p choice="Enter choice (1-4): "

if "%choice%"=="1" (
    echo.
    echo Opening elysia_unified.log...
    if exist elysia_unified.log (
        powershell Get-Content elysia_unified.log -Tail 50
    ) else (
        echo Log file not found. System may not have been started yet.
    )
    pause
)

if "%choice%"=="2" (
    echo.
    echo Opening unified_autonomous_system.log...
    echo WARNING: This file is very large (400,000+ lines)
    echo Opening last 100 lines...
    powershell Get-Content "organized_project\data\logs\unified_autonomous_system.log" -Tail 100
    pause
)

if "%choice%"=="3" (
    echo.
    echo Last 50 lines of unified log:
    echo ========================================
    powershell Get-Content "organized_project\data\logs\unified_autonomous_system.log" -Tail 50
    pause
)

if "%choice%"=="4" (
    exit
)

