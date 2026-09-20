@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - Activar DEV305 1.5.81

echo ============================================================
echo   CEO de IAs - ACTIVADOR UNICO DEV305 / 1.5.81
echo ============================================================
echo.
echo Este archivo funciona por si solo. No necesita extraer un ZIP
echo ni tener ningun .ps1 a su lado.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$expected='1.5.80-rc1-provider-resilience';" ^
  "$manifest='https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/DEV305_MANIFEST_UNSIGNED.json';" ^
  "$logDir=Join-Path $env:LOCALAPPDATA 'CEO de IAs\diagnostics'; New-Item -ItemType Directory -Force -Path $logDir ^| Out-Null;" ^
  "$log=Join-Path $logDir 'DEV305_ACTIVACION_1_5_81.log';" ^
  "function L([string]$m){$x=('['+(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')+'] '+$m); Write-Host $x; Add-Content -Path $log -Value $x -Encoding UTF8};" ^
  "try {" ^
  "  L 'Inicio activacion DEV305';" ^
  "  $port=$null;" ^
  "  foreach($p in 8765..8780){try{$h=Invoke-RestMethod -Uri ('http://127.0.0.1:'+$p+'/api/health') -TimeoutSec 2; L ('Puerto '+$p+' version '+[string]$h.version); if([string]$h.version -eq $expected){$port=$p;break}}catch{}};" ^
  "  if($null -eq $port){L 'ERROR: no se encontro CEO 1.5.80 activo'; exit 6};" ^
  "  L ('CEO 1.5.80 localizado en puerto '+$port);" ^
  "  $body=@{manifest_url=$manifest}^|ConvertTo-Json -Compress;" ^
  "  $uri='http://127.0.0.1:'+$port+'/api/internal-release/activate-prepared';" ^
  "  L 'Solicitando verificacion, firma y publicacion interna de 1.5.81';" ^
  "  $r=Invoke-RestMethod -Method Post -Uri $uri -ContentType 'application/json' -Body $body -TimeoutSec 300;" ^
  "  L ('Respuesta: '+($r^|ConvertTo-Json -Depth 8 -Compress));" ^
  "  if(-not $r.ok){L ('ERROR: ok=false status='+[string]$r.status+' detail='+[string]$r.detail); exit 10};" ^
  "  if([string]$r.status -ne 'PUBLISHED'){L ('ERROR: publicacion no confirmada: '+[string]$r.status); exit 11};" ^
  "  L 'DEV305 publicada y verificada por CEO';" ^
  "  Write-Host ''; Write-Host '1.5.81 FIRMADA Y PUBLICADA POR EL PROPIO CEO';" ^
  "  Write-Host 'Ahora: Comprobar ahora - Actualizar / Instalar y reiniciar - Confirmar';" ^
  "  if($env:CEO_ACTIVATOR_NO_BROWSER -ne '1'){try{Start-Process ('http://127.0.0.1:'+$port+'/')}catch{}};" ^
  "  exit 0" ^
  "} catch { L ('ERROR NO CONTROLADO: '+$_.Exception.Message); if($_.ErrorDetails -and $_.ErrorDetails.Message){L ('Detalle: '+$_.ErrorDetails.Message)}; exit 99 }"

set "RC=%ERRORLEVEL%"
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
pause
exit /b %RC%
