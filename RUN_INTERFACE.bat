@echo off
cd /d "%~dp0"
echo ========================================
echo ELYSIA UNIFIED INTERFACE
echo ========================================
echo.
echo Starting...
echo.

python elysia_interface.py

if errorlevel 1 (
    echo.
    echo ========================================
    echo ERROR OCCURRED
    echo ========================================
    echo.
    echo Please check the error message above.
    echo.
    pause
)

