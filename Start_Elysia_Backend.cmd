@echo off
REM No arguments opens the synthetic interactive pilot; explicit modes stay intact.
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" goto local_python
if "%~1"=="" goto global_interactive
python -S -B "%~dp0elysia.py" %*
exit /b %errorlevel%

:local_python
if "%~1"=="" goto local_interactive
"%~dp0.venv\Scripts\python.exe" -S -B "%~dp0elysia.py" %*
exit /b %errorlevel%

:global_interactive
python -S -B "%~dp0elysia.py" --interactive
exit /b %errorlevel%

:local_interactive
"%~dp0.venv\Scripts\python.exe" -S -B "%~dp0elysia.py" --interactive
exit /b %errorlevel%
