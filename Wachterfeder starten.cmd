@echo off
setlocal
cd /d "%~dp0"

where pyw >nul 2>nul
if %errorlevel%==0 (
  start "Wächterfeder" pyw -3 tools\wachterfeder\gui_compat.py
  exit /b 0
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 tools\wachterfeder\gui_compat.py
  exit /b %errorlevel%
)

echo Python wurde nicht gefunden.
echo Bitte Python 3 installieren und dabei "Add Python to PATH" aktivieren.
pause
exit /b 1
