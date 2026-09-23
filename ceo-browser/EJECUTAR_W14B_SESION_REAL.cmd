@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_w14b_real_session_gate.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo [NO-GO] W14-B no quedo certificado. Revisa W14B_REAL_CHATGPT_SESSION.json en evidencias.
  pause
  exit /b %RC%
)
echo [PASS] W14-B certificado: sesion real persistente, cierre/reapertura y 0 APIs.
pause
exit /b 0
