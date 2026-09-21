@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - DEV314 Native Transport Integrity 1.5.90

set "PS1_URL=https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/6ac6039d01aeb2f2861cc4da3eab6d244a644edb/ceo-updates/DEV314_NATIVE_TRANSPORT_INTEGRITY_ACTIVAR.ps1"
set "PS1_TMP=%TEMP%\CEO_DEV314_%RANDOM%_%RANDOM%.ps1"

echo ============================================================
echo   CEO de IAs - DEV314 / 1.5.90
echo   NATIVE TRANSPORT INTEGRITY
echo ============================================================
echo.
echo Actualizacion directa desde 1.5.86.
echo Incluye DEV311 + DEV312 + cierre determinista DEV313.
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
  echo [BLOQUEADO] No se pudo descargar el activador DEV314.
  echo CEO no ha sido modificado.
  echo.
  if not "%CEO_ACTIVATOR_NO_PAUSE%"=="1" pause
  exit /b 7
)

echo [OK] Activador validado descargado.
echo Solicitando publicacion interna de 1.5.90...
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1_TMP%"
set "RC=%ERRORLEVEL%"

del /q "%PS1_TMP%" >nul 2>nul

echo.
echo ============================================================
if "%RC%"=="0" (
  echo   DEV314 PUBLICADO
) else (
  echo   DEV314 BLOQUEADO DE FORMA SEGURA
  echo   Codigo: %RC%
  echo   La instalacion 1.5.86 sigue intacta.
)
echo ============================================================
echo.
echo Log:
echo %LOCALAPPDATA%\CEO de IAs\diagnostics\DEV314_NATIVE_TRANSPORT_INTEGRITY_ACTIVACION.log
echo.

if not "%CEO_ACTIVATOR_NO_PAUSE%"=="1" pause
exit /b %RC%
