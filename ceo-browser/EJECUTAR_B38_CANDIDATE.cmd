@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_b38_real_ceo_candidate.ps1"
if errorlevel 1 (
  echo.
  echo [ERROR] B38 no se completo.
  pause
  exit /b 1
)
echo.
echo [OK] B38 completado. Candidato preparado para revision humana.
pause
