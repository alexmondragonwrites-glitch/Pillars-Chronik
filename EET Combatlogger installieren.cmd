@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 (
    py -3 tools\wachterfeder\eet_combat_setup.py install
    pause
    exit /b
)

where python >nul 2>&1
if not errorlevel 1 (
    python tools\wachterfeder\eet_combat_setup.py install
    pause
    exit /b
)

echo Python wurde nicht gefunden.
pause
