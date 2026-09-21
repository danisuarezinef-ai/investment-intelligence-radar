@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_b09_b14_physical_gate.ps1"
if errorlevel 1 (
  echo.
  echo [ERROR] El gate B09-B14 no se completo.
  pause
  exit /b 1
)
echo.
echo [OK] Gate B09-B14 completado.
pause
