@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_b15_b18_physical_gate.ps1"
if errorlevel 1 (
  echo.
  echo [ERROR] B15-B18 no se completo.
  pause
  exit /b 1
)
echo.
echo [OK] B15-B18 completado.
pause
