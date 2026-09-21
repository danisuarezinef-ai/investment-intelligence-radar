@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - DEV309 Closure Convergence 1.5.85

set "PS1_URL=https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/6a349d3d7b0617678043e4b2fc156874524f3f01/ceo-updates/DEV309_CLOSURE_CONVERGENCE_ACTIVAR.ps1"
set "PS1_TMP=%TEMP%\CEO_DEV309_%RANDOM%_%RANDOM%.ps1"

echo ============================================================
echo   CEO de IAs - DEV309 / 1.5.85
echo   CLOSURE CONVERGENCE
echo ============================================================
echo.
echo Activador unico. No necesita ZIP ni archivos auxiliares.
echo CEO 1.5.84 debe estar abierto.
echo.
echo Esta operacion publica la candidata validada.
echo La instalacion seguira requiriendo tu confirmacion dentro de CEO.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$u='%PS1_URL%'; $o='%PS1_TMP%';" ^
  "Invoke-WebRequest -UseBasicParsing -Uri $u -OutFile $o -TimeoutSec 60;" ^
  "if(-not (Test-Path $o)){throw 'No se creo el script temporal'};" ^
  "if((Get-Item $o).Length -lt 1000){throw 'Script temporal incompleto'}"

if errorlevel 1 (
  echo.
  echo [BLOQUEADO] No se pudo descargar el activador DEV309.
  echo CEO no ha sido modificado.
  echo.
  if not "%CEO_ACTIVATOR_NO_PAUSE%"=="1" pause
  exit /b 7
)

echo [OK] Activador validado descargado.
echo Solicitando publicacion interna de 1.5.85...
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1_TMP%"
set "RC=%ERRORLEVEL%"

del /q "%PS1_TMP%" >nul 2>nul

echo.
echo ============================================================
if "%RC%"=="0" (
  echo   DEV309 PUBLICADO
) else (
  echo   DEV309 BLOQUEADO DE FORMA SEGURA
  echo   Codigo: %RC%
  echo   La instalacion 1.5.84 sigue intacta.
)
echo ============================================================
echo.
echo Log:
echo %LOCALAPPDATA%\CEO de IAs\diagnostics\DEV309_CLOSURE_CONVERGENCE_ACTIVACION.log
echo.

if not "%CEO_ACTIVATOR_NO_PAUSE%"=="1" pause
exit /b %RC%
