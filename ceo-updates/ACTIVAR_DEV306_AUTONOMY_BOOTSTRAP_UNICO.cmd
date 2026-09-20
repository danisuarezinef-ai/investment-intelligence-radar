@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - Autonomy Bootstrap 1.5.82

set "PS1_URL=https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/6a190ac9c73c81e661362374b33c93334c7a9ab4/ceo-updates/DEV306_AUTONOMY_BOOTSTRAP_ACTIVAR.ps1"
set "PS1_TMP=%TEMP%\CEO_DEV306_%RANDOM%_%RANDOM%.ps1"

echo ============================================================
echo   CEO de IAs - AUTONOMY BOOTSTRAP 1.5.82
echo ============================================================
echo.
echo Activador unico. No necesita ZIP ni archivos auxiliares.
echo CEO 1.5.80 debe estar abierto.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$u='%PS1_URL%'; $o='%PS1_TMP%';" ^
  "Invoke-WebRequest -UseBasicParsing -Uri $u -OutFile $o -TimeoutSec 60;" ^
  "if(-not (Test-Path $o)){throw 'No se creo el script temporal'};" ^
  "if((Get-Item $o).Length -lt 1000){throw 'Script temporal incompleto'}"

if errorlevel 1 (
  echo.
  echo [BLOQUEADO] No se pudo descargar el activador DEV306.
  echo CEO no ha sido modificado.
  echo.
  if not "%CEO_ACTIVATOR_NO_PAUSE%"=="1" pause
  exit /b 7
)

echo [OK] Activador validado descargado.
echo Solicitando publicacion interna de 1.5.82...
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1_TMP%"
set "RC=%ERRORLEVEL%"

del /q "%PS1_TMP%" >nul 2>nul

echo.
echo ============================================================
if "%RC%"=="0" (
  echo   DEV306 AUTONOMY BOOTSTRAP PUBLICADO
) else (
  echo   ACTIVACION DEV306 BLOQUEADA DE FORMA SEGURA
  echo   Codigo: %RC%
  echo   La instalacion actual sigue sin cambios.
)
echo ============================================================
echo.
echo Log:
echo %LOCALAPPDATA%\CEO de IAs\diagnostics\DEV306_AUTONOMY_BOOTSTRAP_ACTIVACION.log
echo.

if not "%CEO_ACTIVATOR_NO_PAUSE%"=="1" pause
exit /b %RC%
