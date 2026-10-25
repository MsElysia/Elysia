@echo off
REM Startup/manual inbox scan (.txt/.md) into the pilot memory store.
REM Not a watcher. Prefer running while the pilot UI is stopped.
setlocal
cd /d "C:\Users\Owner\Elysia-Verified-Pilot"
"C:\Users\Owner\Project guardian\.venv\Scripts\python.exe" "C:\Users\Owner\Elysia-Verified-Pilot\pilot\inbox_import.py"
set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
  echo.
  echo Inbox scan finished with code %ERR% (unsupported files or refuse-while-running).
  pause
)
exit /b %ERR%
