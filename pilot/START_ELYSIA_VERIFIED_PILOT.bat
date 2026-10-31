@echo off
REM Elysia Verified Pilot — separate contained installation launcher
REM Does not modify or replace the original Elysia desktop shortcut.
setlocal
cd /d "%~dp0.."
"C:\Users\Owner\Project guardian\.venv\Scripts\python.exe" "%~dp0launch_verified_pilot.py"
set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
  echo.
  echo Launch failed with code %ERR%. See C:\Users\Owner\Elysia-Windows-Integration-Data\logs\pilot-launch.log
  pause
)
exit /b %ERR%
