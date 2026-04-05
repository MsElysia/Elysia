@echo off
title Project Guardian
color 0A

echo.
echo ========================================
echo    PROJECT GUARDIAN - QUICK LAUNCH
echo ========================================
echo.

cd /d "%~dp0"
set "PROJECT_ROOT=%~dp0"
set "LAUNCH_DIR=%PROJECT_ROOT%organized_project"

if exist "%PROJECT_ROOT%elysia.py" (
    echo Starting Project Guardian via elysia.py...
    cd /d "%PROJECT_ROOT%"
    python elysia.py
    if errorlevel 2 (
        echo.
        echo Another instance is already running. Use the dashboard above or close it first.
        pause
    ) else if errorlevel 1 (
        echo.
        echo Failed to start. Make sure Python is installed and in PATH.
        pause
    )
) else if exist "%LAUNCH_DIR%\launch_guardian.bat" (
    echo Using organized_project launcher...
    cd /d "%LAUNCH_DIR%"
    call launch_guardian.bat
) else if exist "%LAUNCH_DIR%\launch_project_guardian.bat" (
    echo Using organized_project launcher...
    cd /d "%LAUNCH_DIR%"
    call launch_project_guardian.bat
) else (
    echo ERROR: Could not find elysia.py or organized_project launcher
    echo Please check the installation.
    pause
)
