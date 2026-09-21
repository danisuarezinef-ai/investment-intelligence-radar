@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_b20_code_gate.ps1"
if errorlevel 1 (
  echo.
  echo [ERROR] B19-B20 no se completo.
  pause
  exit /b 1
)
echo.
echo [OK] B19-B20 completado.
pause
