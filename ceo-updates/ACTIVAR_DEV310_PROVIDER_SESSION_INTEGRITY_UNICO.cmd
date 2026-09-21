@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - DEV310 Provider Session Integrity 1.5.86

set "PS1_URL=https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/b633e491587619ff7c75e8b26a6af38a4de80183/ceo-updates/DEV310_PROVIDER_SESSION_INTEGRITY_ACTIVAR.ps1"
set "PS1_TMP=%TEMP%\CEO_DEV310_%RANDOM%_%RANDOM%.ps1"

echo ============================================================
echo   CEO de IAs - DEV310 / 1.5.86
echo   PROVIDER SESSION INTEGRITY
echo ============================================================
echo.
echo Activador unico. No necesita ZIP ni archivos auxiliares.
echo CEO 1.5.85 debe estar abierto.
echo.
echo Esta operacion publica la candidata validada.
echo La instalacion seguira requiriendo tu confirmacion dentro de CEO.
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
  echo [BLOQUEADO] No se pudo descargar el activador DEV310.
  echo CEO no ha sido modificado.
  echo.
  if not "%CEO_ACTIVATOR_NO_PAUSE%"=="1" pause
  exit /b 7
)

echo [OK] Activador validado descargado.
echo Solicitando publicacion interna de 1.5.86...
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1_TMP%"
set "RC=%ERRORLEVEL%"

del /q "%PS1_TMP%" >nul 2>nul

echo.
echo ============================================================
if "%RC%"=="0" (
  echo   DEV310 PUBLICADO
) else (
  echo   DEV310 BLOQUEADO DE FORMA SEGURA
  echo   Codigo: %RC%
  echo   La instalacion 1.5.85 sigue intacta.
)
echo ============================================================
echo.
echo Log:
echo %LOCALAPPDATA%\CEO de IAs\diagnostics\DEV310_PROVIDER_SESSION_INTEGRITY_ACTIVACION.log
echo.

if not "%CEO_ACTIVATOR_NO_PAUSE%"=="1" pause
exit /b %RC%
