@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - DEV312 Provider Trust Integrity 1.5.88

set "PS1_URL=https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/05bcb73e4a16b5071535b6e556d428b9fd1f6d40/ceo-updates/DEV312_PROVIDER_TRUST_INTEGRITY_ACTIVAR.ps1"
set "PS1_TMP=%TEMP%\CEO_DEV312_%RANDOM%_%RANDOM%.ps1"

echo ============================================================
echo   CEO de IAs - DEV312 / 1.5.88
echo   PROVIDER TRUST INTEGRITY
echo ============================================================
echo.
echo Actualizacion directa desde 1.5.86.
echo Incluye tambien los arreglos DEV311 del updater y modo app.
echo NO necesitas generar otra clave Gemini.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$u='%PS1_URL%'; $o='%PS1_TMP%';" ^
  "Invoke-WebRequest -UseBasicParsing -Uri $u -OutFile $o -TimeoutSec 60;" ^
  "if(-not (Test-Path $o)){throw 'No se creo el script temporal'};" ^
  "if((Get-Item $o).Length -lt 1000){throw 'Script temporal incompleto'}"

if errorlevel 1 (
  echo.
  echo [BLOQUEADO] No se pudo descargar el activador DEV312.
  echo CEO no ha sido modificado.
  echo.
  if not "%CEO_ACTIVATOR_NO_PAUSE%"=="1" pause
  exit /b 7
)

echo [OK] Activador validado descargado.
echo Solicitando publicacion interna de 1.5.88...
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1_TMP%"
set "RC=%ERRORLEVEL%"

del /q "%PS1_TMP%" >nul 2>nul

echo.
echo ============================================================
if "%RC%"=="0" (
  echo   DEV312 PUBLICADO
) else (
  echo   DEV312 BLOQUEADO DE FORMA SEGURA
  echo   Codigo: %RC%
  echo   La instalacion 1.5.86 sigue intacta.
)
echo ============================================================
echo.
echo Log:
echo %LOCALAPPDATA%\CEO de IAs\diagnostics\DEV312_PROVIDER_TRUST_INTEGRITY_ACTIVACION.log
echo.

if not "%CEO_ACTIVATOR_NO_PAUSE%"=="1" pause
exit /b %RC%
