@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CEO de IAs

set "PYEXE="
set "PYARGS="
set "CEO_BUNDLED_PYTHON=%~dp0runtime\python.exe"
if exist "%CEO_BUNDLED_PYTHON%" set "PYEXE=%CEO_BUNDLED_PYTHON%"

if not defined PYEXE (
  if exist "%LOCALAPPDATA%\Programs\CEO de IAs\runtime\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\CEO de IAs\runtime\python.exe"
)
if not defined PYEXE (
  where py.exe >nul 2>nul
  if not errorlevel 1 (
    set "PYEXE=py.exe"
    set "PYARGS=-3"
  )
)
if not defined PYEXE (
  where python.exe >nul 2>nul
  if not errorlevel 1 set "PYEXE=python.exe"
)
if not defined PYEXE (
  echo [BLOCKED] CEO no encontro su runtime privado ni Python 3 de respaldo.
  echo Diagnostico local: "%~dp0CEO_LAUNCHER_STATUS.json"
  echo Diagnostico persistente: "%LOCALAPPDATA%\CEO de IAs\diagnostics\startup-latest.json"
  echo.
  exit /b 6
)

"%PYEXE%" %PYARGS% -u "%~dp0scripts\launch_current.py"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [BLOCKED] CEO no pudo iniciarse. Codigo %RC%.
  echo Diagnostico local: "%~dp0CEO_LAUNCHER_STATUS.json"
  echo Diagnostico persistente: "%LOCALAPPDATA%\CEO de IAs\diagnostics\startup-latest.json"
  echo Error detallado: "%LOCALAPPDATA%\CEO de IAs\diagnostics\startup-latest-error.txt"
)
exit /b %RC%
