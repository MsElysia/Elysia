@echo off
REM Stop only the Verified Pilot process recorded in the pilot PID file.
setlocal
cd /d "%~dp0.."
"C:\Users\Owner\Project guardian\.venv\Scripts\python.exe" "%~dp0stop_verified_pilot.py"
set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
  echo.
  echo Stop failed with code %ERR%.
  pause
)
exit /b %ERR%
