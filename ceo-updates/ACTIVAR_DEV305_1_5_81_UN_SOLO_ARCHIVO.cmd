@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - Activar DEV305 1.5.81

set "PS1_URL=https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/43093902cbdd2a1afe9e0c51ce30ff5d7535239d/ceo-updates/ACTIVAR_DEV305_1_5_81.ps1"
set "PS1_TMP=%TEMP%\CEO_DEV305_1_5_81_%RANDOM%_%RANDOM%.ps1"

echo ============================================================
echo   CEO de IAs - ACTIVADOR UNICO DEV305 / 1.5.81
echo ============================================================
echo.
echo Descargando el activador validado...
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$u='%PS1_URL%'; $o='%PS1_TMP%';" ^
  "Invoke-WebRequest -UseBasicParsing -Uri $u -OutFile $o -TimeoutSec 60;" ^
  "if(-not (Test-Path $o)){throw 'No se creo el script temporal'};" ^
  "if((Get-Item $o).Length -lt 1000){throw 'Script temporal incompleto'}"

if errorlevel 1 (
  echo.
  echo [BLOQUEADO] No se pudo descargar el activador DEV305.
  echo No se ha modificado CEO.
  echo.
  pause
  exit /b 7
)

if not exist "%PS1_TMP%" (
  echo.
  echo [BLOQUEADO] No existe el script temporal descargado.
  echo No se ha modificado CEO.
  echo.
  pause
  exit /b 8
)

echo [OK] Activador descargado.
echo Ejecutando publicacion interna de 1.5.81...
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1_TMP%"
set "RC=%ERRORLEVEL%"

del /q "%PS1_TMP%" >nul 2>nul

echo.
echo ============================================================
if "%RC%"=="0" (
  echo   ACTIVACION DEV305 COMPLETADA
) else (
  echo   ACTIVACION DEV305 BLOQUEADA DE FORMA SEGURA
  echo   Codigo: %RC%
  echo   CEO 1.5.80 sigue activo. No se ha instalado nada.
)
echo ============================================================
echo.
echo Log:
echo %LOCALAPPDATA%\CEO de IAs\diagnostics\DEV305_ACTIVACION_1_5_81.log
echo.

if not "%CEO_ACTIVATOR_NO_PAUSE%"=="1" pause
exit /b %RC%
