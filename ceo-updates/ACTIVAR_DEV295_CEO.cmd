@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - Activar actualización DEV295

set "PYEXE=%LOCALAPPDATA%\Programs\CEO de IAs\runtime\python.exe"
set "HELPER=%TEMP%\CEO_DEV295_SIGN_AND_PUBLISH.py"
set "HELPER_URL=https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/DEV295_SIGN_AND_PUBLISH.py"
set "SIGNED=%LOCALAPPDATA%\CEO de IAs\updates\outbox\DEV295_MANIFEST_SIGNED.json"

cls
echo ============================================================
echo   CEO de IAs - puente unico de actualizacion DEV295
echo ============================================================
echo.
echo Este lanzador NO crea ni rota claves y NO instala nada por si solo.
echo Usa la autoridad de firma que ya existe en este Windows.
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
  echo [BLOQUEADO] No se pudo descargar el puente firmado desde el canal CEO.
  echo No se ha modificado ninguna clave ni version instalada.
  echo.
  pause
  exit /b 7
)

echo [1/3] Verificando paquete y autoridad local...
echo [2/3] Firmando DEV295...
echo [3/3] Intentando publicacion automatica segura...
echo.

"%PYEXE%" -u "%HELPER%"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" goto PUBLISHED
if "%RC%"=="10" goto SIGNED_ONLY

echo [BLOQUEADO] El puente no pudo completarse. Codigo %RC%.
echo No se ha creado ni rotado ninguna clave y no se ha instalado ninguna version.
echo.
pause
exit /b %RC%

:PUBLISHED
echo ============================================================
echo   DEV295 FIRMADA, PUBLICADA Y VERIFICADA
echo ============================================================
echo.
echo Ya puedes abrir CEO y usar: Actualizar CEO - Confirmar.
echo.
if exist "%LOCALAPPDATA%\Programs\CEO de IAs\ABRIR_CEO.cmd" (
  start "" "%LOCALAPPDATA%\Programs\CEO de IAs\ABRIR_CEO.cmd"
)
pause
exit /b 0

:SIGNED_ONLY
echo ============================================================
echo   DEV295 FIRMADA CORRECTAMENTE
echo ============================================================
echo.
echo Git no pudo publicar de forma no interactiva.
echo El archivo firmado esta listo y NO contiene la clave privada:
echo.
echo %SIGNED%
echo.
echo Se abrira la carpeta. Adjunta DEV295_MANIFEST_SIGNED.json en este chat.
echo Yo completare la publicacion en el canal y despues solo tendras que usar
echo Actualizar CEO - Confirmar.
echo.
if exist "%SIGNED%" explorer.exe /select,"%SIGNED%"
pause
exit /b 10
