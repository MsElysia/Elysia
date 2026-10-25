@echo off
REM Elysia Verified Pilot — separate contained installation launcher
REM Does not modify or replace the original Elysia desktop shortcut.
setlocal
cd /d "C:\Users\Owner\Elysia-Verified-Pilot"
"C:\Users\Owner\Project guardian\.venv\Scripts\python.exe" "C:\Users\Owner\Elysia-Verified-Pilot\pilot\launch_verified_pilot.py"
set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
  echo.
  echo Launch failed with code %ERR%. See C:\Users\Owner\Elysia-Verified-Pilot-Data\logs\pilot-launch.log
  pause
)
exit /b %ERR%
