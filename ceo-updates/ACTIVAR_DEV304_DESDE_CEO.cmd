@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - Activar DEV304 1.5.80

set "MANIFEST_URL=https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/DEV304_MANIFEST_UNSIGNED.json"

echo ============================================================
echo   CEO de IAs - activacion interna DEV304 / 1.5.80
echo ============================================================
echo.
echo Este archivo NO firma, NO instala y NO modifica claves.
echo Solo solicita a CEO 1.5.79 que:
echo   - descargue y verifique la candidata preparada
echo   - la firme con su autoridad local
echo   - la publique en el canal interno
echo La instalacion sigue requiriendo tu confirmacion.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$expected='1.5.79-rc1-productive-resume-gate';" ^
  "$port=$null;" ^
  "foreach($p in 8765..8785){try{$h=Invoke-RestMethod -Uri ('http://127.0.0.1:'+$p+'/api/health') -TimeoutSec 2;if([string]$h.version -eq $expected){$port=$p;break}}catch{}};" ^
  "if($null -eq $port){Write-Host '[BLOQUEADO] No se encontro CEO 1.5.79 activo.';exit 6};" ^
  "Write-Host ('[OK] CEO 1.5.79 localizado en puerto '+$port);" ^
  "$body=@{manifest_url='%MANIFEST_URL%'}|ConvertTo-Json -Compress;" ^
  "Write-Host '[1/3] CEO verifica DEV304...';" ^
  "Write-Host '[2/3] CEO firma y publica 1.5.80...';" ^
  "$r=Invoke-RestMethod -Method Post -Uri ('http://127.0.0.1:'+$port+'/api/internal-release/activate-prepared') -ContentType 'application/json' -Body $body -TimeoutSec 300;" ^
  "$r|ConvertTo-Json -Depth 10;" ^
  "if(-not $r.ok){Write-Host ('[BLOQUEADO] '+[string]$r.status+' '+[string]$r.detail);exit 10};" ^
  "if(([string]$r.status -ne 'PUBLISHED') -and ([string]$r.status -ne 'ALREADY_PUBLISHED')){Write-Host ('[BLOQUEADO] Publicacion no confirmada: '+[string]$r.status);exit 11};" ^
  "Write-Host '[3/3] DEV304 firmada y publicada por CEO.';" ^
  "if($env:CEO_TRIGGER_NO_BROWSER -ne '1'){Start-Process ('http://127.0.0.1:'+$port+'/')};" ^
  "exit 0"

set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" goto OK
echo ============================================================
echo   ACTIVACION DEV304 BLOQUEADA DE FORMA SEGURA
echo ============================================================
echo Codigo: %RC%
echo CEO 1.5.79 sigue activo. No se ha instalado 1.5.80.
pause
exit /b %RC%

:OK
echo ============================================================
echo   DEV304 / 1.5.80 PUBLICADA POR CEO
echo ============================================================
echo.
echo En CEO pulsa Comprobar ahora.
echo Cuando aparezca 1.5.80:
echo   Actualizar / Instalar y reiniciar - Confirmar
echo.
pause
exit /b 0
