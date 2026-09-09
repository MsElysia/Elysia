@echo off
REM Dev-only: minimal OpenClaw-compatible HTTP worker on port 8765 (see scripts/openclaw_stub_worker.py).
REM Start this before (or alongside) Elysia if config/openclaw.json has enabled:true — then openclaw_available can go true.
cd /d "%~dp0"
title OpenClaw stub worker
where python >nul 2>&1
if errorlevel 1 (
  py -3 "%~dp0scripts\openclaw_stub_worker.py" %*
) else (
  python "%~dp0scripts\openclaw_stub_worker.py" %*
)
pause
