@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 (
    py -3 tools\wachterfeder\gui_compat.py
    if errorlevel 1 pause
    exit /b
)

where python >nul 2>&1
if not errorlevel 1 (
    python tools\wachterfeder\gui_compat.py
    if errorlevel 1 pause
    exit /b
)

echo Python wurde nicht gefunden.
echo Bitte installiere Python 3.10 oder neuer und aktiviere "Add Python to PATH".
pause
