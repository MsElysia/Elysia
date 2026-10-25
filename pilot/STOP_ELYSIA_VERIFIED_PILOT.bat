@echo off
REM Stop only the Verified Pilot process recorded in the pilot PID file.
setlocal
cd /d "C:\Users\Owner\Elysia-Verified-Pilot"
"C:\Users\Owner\Project guardian\.venv\Scripts\python.exe" "C:\Users\Owner\Elysia-Verified-Pilot\pilot\stop_verified_pilot.py"
set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
  echo.
  echo Stop failed with code %ERR%.
  pause
)
exit /b %ERR%
