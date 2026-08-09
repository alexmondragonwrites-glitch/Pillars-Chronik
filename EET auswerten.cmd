@echo off
setlocal
cd /d "%~dp0"

python tools\wachterfeder\eet_session.py inspect
set EXITCODE=%ERRORLEVEL%

echo.
if not "%EXITCODE%"=="0" (
  echo Beim ersten Start bitte einmal den EET-Spielordner konfigurieren:
  echo python tools\wachterfeder\eet_session.py configure "DEIN_EET_SPIELORDNER"
  echo.
)
pause
exit /b %EXITCODE%
