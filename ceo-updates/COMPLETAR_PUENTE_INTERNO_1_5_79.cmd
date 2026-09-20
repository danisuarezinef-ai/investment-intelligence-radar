@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - Completar puente interno 1.5.79

set "PYEXE=%LOCALAPPDATA%\Programs\CEO de IAs\runtime\python.exe"
set "HELPER=%TEMP%\CEO_DEV303_BRIDGE_REPAIR.py"
set "HELPER_URL=https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/DEV303_BRIDGE_REPAIR_IN_MEMORY.py"

cls
echo ============================================================
echo   CEO de IAs - puente interno corregido 1.5.79
echo ============================================================
echo.
echo Se ha detectado el fallo exacto del bridge de 1.5.78:
echo UpdateChannelIdentity no contiene el atributo branch.
echo.
echo Esta transicion:
echo   - NO modifica los archivos instalados de 1.5.78
echo   - corrige el bridge solo en memoria durante esta ejecucion
echo   - usa la autoridad de firma persistente de CEO
echo   - deja a CEO firmar/publicar 1.5.79
echo   - NO instala sin tu confirmacion
echo.

if not exist "%PYEXE%" (
  echo [BLOQUEADO] No se encontro el runtime privado de CEO.
  pause
  exit /b 6
)

if exist "%HELPER%" del /q "%HELPER%" >nul 2>nul
where curl.exe >nul 2>nul
if not errorlevel 1 curl.exe -fL --retry 3 --connect-timeout 15 -o "%HELPER%" "%HELPER_URL%" >nul 2>nul

if not exist "%HELPER%" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%HELPER_URL%' -OutFile '%HELPER%'; exit 0 } catch { exit 1 }" >nul 2>nul
)

if not exist "%HELPER%" (
  echo [BLOQUEADO] No se pudo descargar el reparador temporal del bridge.
  pause
  exit /b 7
)

echo [1/3] Verificando CEO activo y candidata DEV303...
echo [2/3] Corrigiendo branch del bridge solo en memoria...
echo [3/3] CEO firma y publica la candidata...
echo.

"%PYEXE%" -u "%HELPER%"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" goto OK

echo ============================================================
echo   PUBLICACION BLOQUEADA DE FORMA SEGURA
echo ============================================================
echo Codigo: %RC%
echo CEO 1.5.78 sigue activo y no se ha instalado nada.
pause
exit /b %RC%

:OK
echo ============================================================
echo   1.5.79 PUBLICADA POR EL NUCLEO DE CEO
echo ============================================================
echo.
echo Vuelve a CEO y pulsa Comprobar ahora.
echo Despues: Actualizar / Instalar y reiniciar - Confirmar.
echo.
start "" "http://127.0.0.1:8772/"
pause
exit /b 0
