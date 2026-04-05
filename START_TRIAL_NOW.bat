@echo off
cd /d "%~dp0"
echo ========================================
echo Starting Elysia Trial Run Until 7am
echo ========================================
echo.
echo This window will show the trial run progress.
echo The system will run until 7am and then shut down.
echo.
echo Press Ctrl+C to stop early.
echo.
echo ========================================
echo.

python run_elysia_trial_until_7am.py

pause

