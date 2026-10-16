@echo off
REM Backward-compatible name: same as START_ELYSIA_UNIFIED.bat (docs / old shortcuts).
cd /d "%~dp0"
call "%~dp0START_ELYSIA_UNIFIED.bat" %*
exit /b %errorlevel%
