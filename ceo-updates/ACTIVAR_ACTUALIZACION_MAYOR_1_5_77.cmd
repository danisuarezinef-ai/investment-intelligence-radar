@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - Activar actualizacion mayor 1.5.77

set "PYEXE=%LOCALAPPDATA%\Programs\CEO de IAs\runtime\python.exe"
set "HELPER=%TEMP%\CEO_DEV301_SIGN_AND_ACTIVATE.py"
set "HELPER_URL=https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/DEV301_SIGN_AND_ACTIVATE.py"
set "SIGNED=%LOCALAPPDATA%\CEO de IAs\updates\outbox\DEV301_MANIFEST_SIGNED.json"

cls
echo ============================================================
echo   CEO de IAs - actualizacion mayor de fiabilidad 1.5.77
echo ============================================================
echo.
echo Una sola operacion de transicion:
echo   - verifica el paquete preparado y sus hashes
echo   - usa la autoridad de firma persistente de este Windows
echo   - NO crea ni rota claves
echo   - NO exporta la clave privada
echo   - NO instala sin tu confirmacion en CEO
echo.

if not exist "%PYEXE%" (
  echo [BLOQUEADO] No se encontro el runtime privado de CEO:
  echo %PYEXE%
  echo.
  echo No se ha modificado nada.
  pause
  exit /b 6
)

if exist "%HELPER%" del /q "%HELPER%" >nul 2>nul

where curl.exe >nul 2>nul
if not errorlevel 1 (
  curl.exe -fL --retry 3 --connect-timeout 15 -o "%HELPER%" "%HELPER_URL%" >nul 2>nul
)

if not exist "%HELPER%" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%HELPER_URL%' -OutFile '%HELPER%'; exit 0 } catch { exit 1 }" >nul 2>nul
)

if not exist "%HELPER%" (
  echo [BLOQUEADO] No se pudo descargar el puente DEV301 desde el canal CEO.
  echo No se ha modificado ninguna clave ni version instalada.
  echo.
  pause
  exit /b 7
)

echo [1/4] Verificando candidata 1.5.77 y contrato del paquete...
echo [2/4] Comprobando autoridad de firma persistente...
echo [3/4] Firmando el manifest DEV301...
echo [4/4] Intentando activar el canal de actualizacion...
echo.

"%PYEXE%" -u "%HELPER%"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" goto PUBLISHED
if "%RC%"=="10" goto SIGNED_ONLY

echo ============================================================
echo   TRANSICION BLOQUEADA DE FORMA SEGURA
echo ============================================================
echo.
echo Codigo: %RC%
echo No se ha creado ni rotado ninguna clave.
echo No se ha instalado ninguna version.
echo.
pause
exit /b %RC%

:PUBLISHED
echo ============================================================
echo   1.5.77 FIRMADA, PUBLICADA Y VERIFICADA
echo ============================================================
echo.
echo Ahora abre CEO y utiliza:
echo.
echo            Actualizar CEO  -  Confirmar
echo.
if exist "%LOCALAPPDATA%\Programs\CEO de IAs\ABRIR_CEO.cmd" (
  start "" "%LOCALAPPDATA%\Programs\CEO de IAs\ABRIR_CEO.cmd"
)
pause
exit /b 0

:SIGNED_ONLY
echo ============================================================
echo   1.5.77 FIRMADA CORRECTAMENTE
echo ============================================================
echo.
echo Git no pudo publicar de forma no interactiva.
echo La firma es valida y la clave privada NO sale de Windows.
echo Se abrira la carpeta con:
echo.
echo %SIGNED%
echo.
echo Adjunta DEV301_MANIFEST_SIGNED.json en este chat.
echo Yo activare el manifest firmado en el canal y despues solo
echo tendras que usar Actualizar CEO - Confirmar.
echo.
if exist "%SIGNED%" explorer.exe /select,"%SIGNED%"
pause
exit /b 10
