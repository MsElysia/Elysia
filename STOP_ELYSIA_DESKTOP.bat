@echo off
REM Graceful shutdown only: POST /shutdown if backend is up. Does NOT start Elysia if off.
cd /d "%~dp0"
title Elysia stop
where python >nul 2>&1
if errorlevel 1 (
  py -3 "%~dp0toggle_elysia_desktop.py" --stop-only
) else (
  python "%~dp0toggle_elysia_desktop.py" --stop-only
)
set EC=%errorlevel%
if %EC% neq 0 pause
exit /b %EC%
