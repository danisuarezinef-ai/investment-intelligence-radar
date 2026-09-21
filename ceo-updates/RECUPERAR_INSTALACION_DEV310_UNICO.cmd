@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - Recuperar instalacion DEV310

set "PS1_URL=https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/e3c96b8ead6f3f7faf48f386dfb5d35f94e6cbd5/ceo-updates/RECUPERAR_INSTALACION_DEV310.ps1"
set "PS1_TMP=%TEMP%\CEO_RECUPERAR_DEV310_%RANDOM%_%RANDOM%.ps1"

echo ============================================================
echo   CEO de IAs - Recuperar instalacion DEV310
echo ============================================================
echo.
echo Este archivo NO vuelve a descargar DEV310.
echo Solo continua una instalacion 1.5.86 que ya este preparada.
echo Pedira confirmacion antes de instalar.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; Invoke-WebRequest -UseBasicParsing -Uri '%PS1_URL%' -OutFile '%PS1_TMP%' -TimeoutSec 60; if(-not (Test-Path '%PS1_TMP%')){throw 'No se creo el recuperador temporal'}"

if errorlevel 1 (
  echo [ERROR] No se pudo obtener el recuperador.
  pause
  exit /b 7
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1_TMP%"
set "RC=%ERRORLEVEL%"
del /q "%PS1_TMP%" >nul 2>nul

echo.
echo Codigo final: %RC%
if not "%CEO_RECOVERY_NO_PAUSE%"=="1" pause
exit /b %RC%
