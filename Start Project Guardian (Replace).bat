@echo off
title Project Guardian (Replace)
color 0E

echo.
echo ========================================
echo    PROJECT GUARDIAN - REPLACE RUNNING
echo    (stops prior backend ^& starts fresh)
echo ========================================
echo.

cd /d "%~dp0"
set "PROJECT_ROOT=%~dp0"

if exist "%PROJECT_ROOT%elysia.py" (
    cd /d "%PROJECT_ROOT%"
    python elysia.py --takeover
    if errorlevel 1 (
        echo.
        echo Replace/takeover or start failed. Check messages above.
        pause
    )
) else (
    echo ERROR: elysia.py not found in %PROJECT_ROOT%
    pause
)
