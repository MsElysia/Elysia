@echo off
title Elysia - Mark drive for memory
setlocal
echo.
echo ========================================
echo   Mark a drive for Elysia memory
echo ========================================
echo.
echo Creates the file ELYSIA_MEMORY on the root of the chosen drive
echo so Elysia can find this thumb drive on any PC.
echo.
set /p DRIVE="Enter drive letter (e.g. F, no colon): "
if "%DRIVE%"=="" goto :eof
set "ROOT=%DRIVE%:\"
if not exist "%ROOT%" (
    echo Drive %DRIVE%: not found.
    pause
    exit /b 1
)
echo. > "%ROOT%ELYSIA_MEMORY"
if exist "%ROOT%ELYSIA_MEMORY" (
    echo [OK] Created %ROOT%ELYSIA_MEMORY
    echo This drive will be used for Elysia memory when plugged in.
) else (
    echo Failed to create marker. Try running as Administrator.
)
echo.
pause
