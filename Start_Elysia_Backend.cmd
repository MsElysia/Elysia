@echo off
REM Always full backend boot — see ELYSIA_FORCE_FULL_BACKEND in elysia.py main().
set ELYSIA_FORCE_FULL_BACKEND=1
cd /d "%~dp0"
title Elysia Backend Server
echo [Elysia Backend] Working directory: %CD%
echo [Elysia Backend] ELYSIA_FORCE_FULL_BACKEND=%ELYSIA_FORCE_FULL_BACKEND% (full boot, not attach-only probe^)
if not exist "%~dp0elysia.py" (
  echo [Elysia Backend] ERROR: elysia.py not found in %CD%
  echo Fix shortcut "Start in" / Working directory to the Project Guardian folder.
  pause
  exit /b 1
)
echo [Elysia Backend] Starting elysia.py (full server^)...
echo.
where python >nul 2>&1
if errorlevel 1 (
  echo Using Windows Python launcher: py -3
  py -3 elysia.py
) else (
  python elysia.py
)
echo.
echo Backend process ended (exit code %errorlevel%).
pause
