@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title CEO de IAs - Preparar campaña DEV271

echo ================================================================
echo CEO DEV271 - PREPARACION FINAL DE CAMPANA WINDOWS
echo ================================================================
echo.
echo Este paso NO instala ni activa ninguna version.
echo Comprueba la candidata exacta, la instalacion actual, staging aislado,
echo preflight y capacidad de rollback antes de una futura activacion humana.
echo.

set "PY=%LOCALAPPDATA%\Programs\CEO de IAs\runtime\python.exe"
set "ROOT=%~dp0"
set "ZIP=%ROOT%CEO_1.5.48-rc1-terminal-local-campaign-gate.zip"
set "OUT=%LOCALAPPDATA%\CEO de IAs\updates\DEV271_WINDOWS_CAMPAIGN_READINESS.json"

if not exist "%PY%" (
  echo [ERROR] No encuentro el runtime privado de CEO: %PY%
  pause
  exit /b 7
)
if not exist "%ZIP%" (
  echo [ERROR] No encuentro la candidata exacta junto a este script: %ZIP%
  pause
  exit /b 7
)

"%PY%" -u "%ROOT%scripts\dev271_windows_campaign.py" --candidate-root "%ROOT%" --candidate-zip "%ZIP%" --output "%OUT%"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo [PASS] Preflight DEV271 completo. NO se ha instalado nada.
  echo Informe: %OUT%
) else (
  echo [BLOCKED] DEV271 no autoriza una campana fisica todavia.
  echo Informe: %OUT%
)
echo.
pause
exit /b %RC%
