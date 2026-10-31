@echo off
REM Stable Elysia Windows release launcher for desktop shortcut "elysia1".
REM Defaults to operational data root via pilot_paths.py (Elysia-Windows-Integration-Data).
REM Does not modify the separate Verified Pilot installation.
setlocal
cd /d "%~dp0.."
call "%~dp0START_ELYSIA_VERIFIED_PILOT.bat"
exit /b %ERRORLEVEL%
