@echo off
setlocal

cd /d "%~dp0"

set "ELYSIA_OLLAMA_MODEL=mistral:7b"
set "ELYSIA_FORCE_FULL_BACKEND=1"

echo [Elysia Launcher] Using local Ollama model: %ELYSIA_OLLAMA_MODEL%
echo [Elysia Launcher] Forcing full backend boot.
if exist "%~dp0ensure_ollama_running.ps1" (
  echo [Elysia Launcher] Checking Ollama local API...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ensure_ollama_running.ps1"
  if errorlevel 1 (
    echo [Elysia Launcher] WARN: Ollama autostart check did not confirm readiness.
  )
)
python elysia.py

endlocal
