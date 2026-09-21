@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0recover_first_trial.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo [ERROR] La recuperacion no pudo completarse.
pause
exit /b %RC%
