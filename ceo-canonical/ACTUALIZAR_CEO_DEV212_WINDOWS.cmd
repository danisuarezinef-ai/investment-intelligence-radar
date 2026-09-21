@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CEO de IAs - Actualizacion DEV212
set "EXPECTED=1.4.89-rc1-continuity-loop-breaker"
set "PY=%LOCALAPPDATA%\Programs\CEO de IAs\runtime\python.exe"

echo ============================================================
echo CEO de IAs - ACTUALIZACION DEV212 SIDE-BY-SIDE
echo Version: %EXPECTED%
echo ============================================================
echo Corrige el bucle cognitive early abort ^<^-> continuity recovery.
echo No reemplaza bootstrap. Conserva datos, runtime y claves DPAPI.
echo.

if not exist "%PY%" (
  echo [BLOCKED] No encuentro el runtime privado de CEO.
  pause
  exit /b 10
)

echo [1/3] Self-test: contrato, runtime proyectado y arranque real...
"%PY%" "scripts\update_dev212_side_by_side.py" --self-test --source "%CD%"
if errorlevel 1 (
  echo [BLOCKED] DEV212 no supera self-test. No se modifica nada.
  pause
  exit /b 11
)

echo.
echo [2/3] Confirmacion humana requerida.
echo CEO debe estar cerrado y el puerto 8765 libre.
echo Escribe ACTUALIZAR para activar DEV212.
set /p "CONFIRM=> "
if /I not "%CONFIRM%"=="ACTUALIZAR" (
  echo Cancelado. No se ha modificado CEO.
  pause
  exit /b 0
)

echo.
echo [3/3] Instalando side-by-side, cambiando puntero y verificando health...
"%PY%" -u "scripts\update_dev212_side_by_side.py" --source "%CD%"
if errorlevel 1 (
  echo [BLOCKED] DEV212 no se activo. El puntero anterior se conserva/restaura.
  pause
  exit /b 20
)

echo.
echo ============================================================
echo DEV212 ACTUALIZADO Y HEALTH CHECK PASS
echo ============================================================
echo CEO queda arrancado con la nueva version.
pause
exit /b 0
