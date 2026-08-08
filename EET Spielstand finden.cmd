@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\wachterfeder\find_eet_saves.ps1"
echo.
pause
