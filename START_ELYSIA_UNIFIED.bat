@echo off
REM Draft startup delegates directly; no new windows, live API or attached UI.
call "%~dp0Start_Elysia_Backend.cmd" %*
exit /b %errorlevel%
