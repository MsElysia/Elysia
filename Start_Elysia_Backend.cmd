@echo off
REM Always full backend boot - see ELYSIA_FORCE_FULL_BACKEND in elysia.py main().
set ELYSIA_FORCE_FULL_BACKEND=1
if "%ELYSIA_OLLAMA_MODEL%"=="" set ELYSIA_OLLAMA_MODEL=mistral:7b
cd /d "%~dp0"
title Elysia Backend Server
echo [Elysia Backend] Working directory: %CD%
echo [Elysia Backend] ELYSIA_FORCE_FULL_BACKEND=%ELYSIA_FORCE_FULL_BACKEND% (full boot, not attach-only probe^)
echo [Elysia Backend] ELYSIA_OLLAMA_MODEL=%ELYSIA_OLLAMA_MODEL%
if exist "%~dp0ensure_ollama_running.ps1" (
  echo [Elysia Backend] Checking Ollama local API...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ensure_ollama_running.ps1"
  if errorlevel 1 (
    echo [Elysia Backend] WARN: Ollama autostart check did not confirm readiness. Elysia will continue and may use degraded autonomy.
  )
)
if exist "%~dp0ensure_openclaw_running.ps1" (
  echo [Elysia Backend] Checking OpenClaw execution worker ^(optional autostart^)...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ensure_openclaw_running.ps1" -ProjectRoot "%CD%"
  if errorlevel 1 (
    echo [Elysia Backend] WARN: OpenClaw autostart did not confirm readiness. Elysia will continue; set autostart in config\openclaw.json or start the worker manually.
  )
)
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
