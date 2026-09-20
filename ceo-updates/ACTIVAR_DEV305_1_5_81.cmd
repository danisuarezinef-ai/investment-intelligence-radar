@echo off
setlocal
chcp 65001 >nul 2>nul
title CEO de IAs - Activar DEV305 1.5.81
echo.
echo Lanzando activador robusto DEV305...
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0ACTIVAR_DEV305_1_5_81.ps1"
set "RC=%ERRORLEVEL%"
echo.
echo El activador termino con codigo %RC%.
echo.
pause
exit /b %RC%
