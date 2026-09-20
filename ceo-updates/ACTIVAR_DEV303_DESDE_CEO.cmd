@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - Activar candidata interna 1.5.79

set "MANIFEST_URL=https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/DEV303_MANIFEST_UNSIGNED.json"

echo ============================================================
echo   CEO de IAs - puente interno de release 1.5.79
echo ============================================================
echo.
echo Este archivo NO firma, NO instala y NO modifica claves.
echo Solo pide al CEO 1.5.78 que active su PreparedReleaseBridge.
echo CEO verificara, firmara y publicara la candidata internamente.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$expected='1.5.78-rc1-reliable-update-handoff';" ^
  "$port=$null;" ^
  "foreach($p in 8765..8780){try{$h=Invoke-RestMethod -Uri ('http://127.0.0.1:'+$p+'/api/health') -TimeoutSec 2;if([string]$h.version -eq $expected){$port=$p;break}}catch{}};" ^
  "if($null -eq $port){Write-Host '[BLOQUEADO] No se encontro una instancia sana de CEO 1.5.78.';exit 6};" ^
  "Write-Host ('[OK] CEO 1.5.78 localizado en puerto '+$port);" ^
  "$body=@{manifest_url='%MANIFEST_URL%'}|ConvertTo-Json -Compress;" ^
  "Write-Host '[1/3] CEO descarga y verifica la candidata preparada...';" ^
  "Write-Host '[2/3] CEO usa su autoridad local para firmar/publicar...';" ^
  "$r=Invoke-RestMethod -Method Post -Uri ('http://127.0.0.1:'+$port+'/api/internal-release/activate-prepared') -ContentType 'application/json' -Body $body -TimeoutSec 300;" ^
  "$r|ConvertTo-Json -Depth 8;" ^
  "if(-not $r.ok){Write-Host ('[BLOQUEADO] '+[string]$r.status+' '+[string]$r.detail);exit 10};" ^
  "if([string]$r.status -ne 'PUBLISHED'){Write-Host ('[BLOQUEADO] Publicacion no confirmada: '+[string]$r.status);exit 11};" ^
  "Write-Host '[3/3] Release firmada, publicada y verificada por CEO.';" ^
  "if($env:CEO_TRIGGER_NO_BROWSER -ne '1'){Start-Process ('http://127.0.0.1:'+$port+'/')};" ^
  "exit 0"

set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" goto OK
echo ============================================================
echo   ACTIVACION INTERNA BLOQUEADA DE FORMA SEGURA
echo ============================================================
echo Codigo: %RC%
echo CEO 1.5.78 sigue siendo la version activa.
echo No se ha instalado ninguna version.
pause
exit /b %RC%

:OK
echo ============================================================
echo   1.5.79 FIRMADA Y PUBLICADA POR EL PROPIO CEO
echo ============================================================
echo.
echo En CEO pulsa Comprobar ahora.
echo Debe aparecer 1.5.79 disponible.
echo Despues usa Actualizar CEO / Instalar y reiniciar y Confirmar.
echo.
pause
exit /b 0
