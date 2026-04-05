@echo off
cd /d "%~dp0"
python elysia_health_check.py
exit /b %ERRORLEVEL%
