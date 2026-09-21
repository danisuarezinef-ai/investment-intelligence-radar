@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "PY=%LOCALAPPDATA%\Programs\CEO de IAs\runtime\python.exe"
if not exist "%PY%" (
  echo [BLOQUEADO] No encuentro el runtime privado instalado de CEO.
  pause
  exit /b 7
)
echo CEO de IAs - DEV261 preflight fisico seguro
echo.
echo Este paso NO instala ni activa ninguna version.
echo Solo comprueba la instalacion actual y esta candidata.
echo.
"%PY%" "%~dp0scripts\dev261_windows_preflight.py" --candidate-root "%~dp0"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo [PASS] Candidata preparada para el gate humano de cutover.
) else (
  echo [BLOCKED] No se debe activar esta candidata. Revise DEV261_WINDOWS_PREFLIGHT.json.
)
pause
exit /b %RC%
