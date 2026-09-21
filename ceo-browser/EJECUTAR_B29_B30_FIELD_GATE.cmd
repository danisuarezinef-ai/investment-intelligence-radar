@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_b29_b30_full_field_gate.ps1"
if errorlevel 1 (
  echo.
  echo [ERROR] B29-B30 no se completo.
  pause
  exit /b 1
)
echo.
echo [OK] B29-B30 completado. BROWSER_FIELD_VERIFIED=true
pause
