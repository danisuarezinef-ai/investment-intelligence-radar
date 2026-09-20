@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - Completar actualizacion mayor 1.5.78

set "PYEXE=%LOCALAPPDATA%\Programs\CEO de IAs\runtime\python.exe"
set "HELPER=%TEMP%\CEO_DEV302_COMPLETE_TRANSITION.py"
set "HELPER_URL=https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/DEV302_COMPLETE_TRANSITION.py"
set "SIGNED=%LOCALAPPDATA%\CEO de IAs\updates\outbox\DEV302_MANIFEST_SIGNED.json"

cls
echo ============================================================
echo   CEO de IAs - completar actualizacion mayor 1.5.78
echo ============================================================
echo.
echo Este activador corrige el bloqueo detectado en 72%%:
echo   - verifica la revision final 1.5.78
echo   - firma y publica usando la autoridad persistente
echo   - reintenta de forma acotada bloqueos transitorios de Windows
echo   - deja 1.5.78 preparada para instalar
echo   - NO instala sin tu confirmacion
echo   - NO crea, rota ni exporta claves privadas
echo.

if not exist "%PYEXE%" (
  echo [BLOQUEADO] No se encontro el runtime privado de CEO:
  echo %PYEXE%
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
  echo [BLOQUEADO] No se pudo descargar el puente DEV302.
  echo No se ha modificado la version activa.
  pause
  exit /b 7
)

echo [1/5] Verificando paquete 1.5.78...
echo [2/5] Comprobando autoridad de firma...
echo [3/5] Firmando y publicando DEV302...
echo [4/5] Preparando la version con recuperacion robusta...
echo [5/5] Verificando estado LISTA PARA INSTALAR...
echo.

"%PYEXE%" -u "%HELPER%"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" goto READY
if "%RC%"=="10" goto SIGNED_ONLY

echo ============================================================
echo   TRANSICION BLOQUEADA DE FORMA SEGURA
echo ============================================================
echo.
echo Codigo: %RC%
echo CEO actual permanece intacto.
echo No se ha instalado ninguna version.
echo.
pause
exit /b %RC%

:READY
echo ============================================================
echo   1.5.78 PUBLICADA Y PREPARADA PARA INSTALAR
echo ============================================================
echo.
echo Vuelve a la interfaz de CEO y recarga la pagina una vez.
echo Debe aparecer:
echo.
echo       Actualizacion lista para instalar
echo       Instalar y reiniciar
echo.
echo Pulsa Instalar y reiniciar y despues Confirmar.
echo.
start "" "http://127.0.0.1:8772/"
pause
exit /b 0

:SIGNED_ONLY
echo ============================================================
echo   1.5.78 FIRMADA, PUBLICACION LOCAL PENDIENTE
echo ============================================================
echo.
echo Adjunta este archivo en el chat:
echo %SIGNED%
echo.
if exist "%SIGNED%" explorer.exe /select,"%SIGNED%"
pause
exit /b 10
