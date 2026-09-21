@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_first_trial_gate.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo [NO-GO] Revisa PRIMERA_PRUEBA_CEO_RESULTADO.json en evidencias.
  pause
  exit /b %RC%
)
echo [GO] Ensayo general superado. B38 sigue separado.
pause
