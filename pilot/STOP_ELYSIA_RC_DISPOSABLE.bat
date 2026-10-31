@echo off
REM Stop only the RC disposable pilot whose data root was recorded at start.
setlocal EnableExtensions
cd /d "%~dp0.."

if not defined ELYSIA_PILOT_DATA_ROOT (
  if exist "%TEMP%\elysia-rc-active-root.txt" (
    set /p ELYSIA_PILOT_DATA_ROOT=<"%TEMP%\elysia-rc-active-root.txt"
  )
)
if not defined ELYSIA_PILOT_MARKER set "ELYSIA_PILOT_MARKER=elysia-rc-disposable"

if not defined ELYSIA_PILOT_DATA_ROOT (
  echo ERROR: ELYSIA_PILOT_DATA_ROOT not set and no active RC root file found.
  exit /b 2
)

echo Stopping RC disposable pilot at %ELYSIA_PILOT_DATA_ROOT%
"C:\Users\Owner\Project guardian\.venv\Scripts\python.exe" "%~dp0stop_verified_pilot.py"
set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
  echo.
  echo RC disposable stop failed with code %ERR%.
  pause
)
exit /b %ERR%
