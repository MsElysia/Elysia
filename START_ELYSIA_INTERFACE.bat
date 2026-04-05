@echo off
title Elysia Interface
cd /d "%~dp0"
echo.
echo ========================================
echo   ELYSIA INTERFACE (Attach Mode)
echo ========================================
echo.
echo Connecting to backend at http://127.0.0.1:8888
echo Make sure elysia.py is already running.
echo.
python elysia_interface.py --attach-only
echo.
if errorlevel 1 pause
