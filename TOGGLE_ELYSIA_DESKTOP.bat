@echo off
REM One double-click: turn Elysia off (graceful) if running, else start unified launcher.
cd /d "%~dp0"
title Elysia toggle
where python >nul 2>&1
if errorlevel 1 (
  py -3 "%~dp0toggle_elysia_desktop.py"
) else (
  python "%~dp0toggle_elysia_desktop.py"
)
set EC=%errorlevel%
if %EC% neq 0 pause
exit /b %EC%
