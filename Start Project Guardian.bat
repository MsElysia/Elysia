@echo off
REM Normal Windows quick launch uses the same restricted offline entry point.
if not "%~1"=="" goto explicit_mode
REM Double-click default: one persistent fictional-only application.
call "%~dp0Start_Elysia_Backend.cmd" --interactive --synthetic-store windows-pilot
exit /b %errorlevel%
:explicit_mode
call "%~dp0Start_Elysia_Backend.cmd" %*
exit /b %errorlevel%
