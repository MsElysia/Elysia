@echo off
REM Single-file launcher: backend (new window) + wait for status API + attach-mode UI.
REM Does not depend on START_ELYSIA_FULL.bat.
cd /d "%~dp0"
REM Optional: reduce resource warning frequency (default 10 min)
REM set ELYSIA_RESOURCE_COOLDOWN=600
REM Optional: raise memory limit if system runs near 80%% baseline
REM set ELYSIA_MEMORY_LIMIT=0.95
REM Health: CHECK_ELYSIA_HEALTH.bat | Watchdog: python elysia_watchdog.py --daemon --restart
echo ========================================
echo ELYSIA UNIFIED - Backend + Interface
echo ========================================
echo.
echo Project: %CD%
echo.
echo Backend window: ELYSIA_FORCE_FULL_BACKEND=1 + elysia.py from:
echo   %~dp0
echo Starting backend (elysia.py) in new window...
REM start /D + explicit script path avoids cwd/space issues (e.g. "Project guardian")
start "Elysia Backend" /D "%~dp0" cmd /k call "%~dp0Start_Elysia_Backend.cmd"
echo.
echo Waiting for backend status API (polls http://127.0.0.1:8888/status, max 300s by default^)...
echo Set ELYSIA_STARTUP_WAIT_SEC to change the cap.
where python >nul 2>&1
if errorlevel 1 (
  py -3 wait_for_elysia_backend.py
) else (
  python wait_for_elysia_backend.py
)
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
where python >nul 2>&1
if errorlevel 1 (
  py -3 elysia_interface.py --attach-only
) else (
  python elysia_interface.py --attach-only
)
if errorlevel 1 pause
