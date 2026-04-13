@echo off
title Install Elysia desktop shortcuts
cd /d "%~dp0"
echo Installing desktop shortcuts for Elysia...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_elysia_desktop_shortcut.ps1"
if errorlevel 1 (
  echo.
  echo If PowerShell blocked this script, run:
  echo   powershell -ExecutionPolicy Bypass -File "%~dp0create_elysia_desktop_shortcut.ps1"
  pause
  exit /b 1
)
echo.
pause
