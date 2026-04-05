@echo off
cd /d "%~dp0"
REM Optional: reduce resource warning frequency (default 10 min)
REM set ELYSIA_RESOURCE_COOLDOWN=600
REM Optional: raise memory limit if system runs near 80%% baseline
REM set ELYSIA_MEMORY_LIMIT=0.95
REM Health: CHECK_ELYSIA_HEALTH.bat | Watchdog: python elysia_watchdog.py --daemon --restart
echo ========================================
echo ELYSIA FULL - Backend + Interface
echo ========================================
echo.
echo Starting backend (elysia.py) in new window...
start "Elysia Backend" cmd /k "cd /d "%~dp0" && python elysia.py"
echo.
echo Waiting for backend status API (polls http://127.0.0.1:8888/status, max 300s by default^)...
echo Set ELYSIA_STARTUP_WAIT_SEC to change the cap.
python wait_for_elysia_backend.py
if errorlevel 2 (
  echo.
  echo Backend process appears to have exited — see the Elysia Backend window.
  pause
  exit /b 2
)
if errorlevel 3 (
  echo.
  echo Timed out waiting for /status. Backend may still be loading — check backend window or logs.
  pause
  exit /b 3
)
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo Starting interface (attach mode)...
python elysia_interface.py --attach-only
if errorlevel 1 pause
