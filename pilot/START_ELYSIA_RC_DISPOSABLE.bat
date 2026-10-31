@echo off
REM Isolated release-candidate launch using the SAME launch_verified_pilot.py path.
REM Does not touch C:\Users\Owner\Elysia-Windows-Integration-Data or port 5065 by default.
REM Sets ELYSIA_PILOT_DATA_ROOT + preferred unused port, then runs the normal launcher.
setlocal EnableExtensions
cd /d "%~dp0.."

if not defined ELYSIA_PILOT_DATA_ROOT (
  set "ELYSIA_PILOT_DATA_ROOT=%TEMP%\elysia-rc-disposable-%RANDOM%%RANDOM%"
)
if not defined ELYSIA_PREFERRED_UI_PORT set "ELYSIA_PREFERRED_UI_PORT=5086"
if not defined ELYSIA_PILOT_MARKER set "ELYSIA_PILOT_MARKER=elysia-rc-disposable"
if not defined ELYSIA_LOCAL_MODEL set "ELYSIA_LOCAL_MODEL=llama3.2:3b"

mkdir "%ELYSIA_PILOT_DATA_ROOT%" 2>nul
mkdir "%ELYSIA_PILOT_DATA_ROOT%\logs" 2>nul
mkdir "%ELYSIA_PILOT_DATA_ROOT%\runtime" 2>nul
mkdir "%ELYSIA_PILOT_DATA_ROOT%\temp" 2>nul
mkdir "%ELYSIA_PILOT_DATA_ROOT%\memory" 2>nul
mkdir "%ELYSIA_PILOT_DATA_ROOT%\inbox" 2>nul

REM Persist active RC root so STOP_ELYSIA_RC_DISPOSABLE.bat targets the same store.
> "%TEMP%\elysia-rc-active-root.txt" echo %ELYSIA_PILOT_DATA_ROOT%
> "%TEMP%\elysia-rc-active-port.txt" echo %ELYSIA_PREFERRED_UI_PORT%

echo RC disposable data root: %ELYSIA_PILOT_DATA_ROOT%
echo Preferred UI port: %ELYSIA_PREFERRED_UI_PORT%
echo Using normal launcher entry via launch_verified_pilot.py

"C:\Users\Owner\Project guardian\.venv\Scripts\python.exe" "%~dp0launch_verified_pilot.py"
set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
  echo.
  echo RC disposable launch failed with code %ERR%.
  pause
)
exit /b %ERR%
