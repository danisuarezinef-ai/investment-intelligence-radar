@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul
title CEO de IAs - Diagnostico ATASCADO 1.5.79

set "OUTDIR=%LOCALAPPDATA%\CEO de IAs\diagnostics"
set "OUTFILE=%OUTDIR%\CEO_DIAGNOSTICO_ATASCADO_1_5_79.json"

if not exist "%OUTDIR%" mkdir "%OUTDIR%" >nul 2>nul

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$port=$null;$health=$null;" ^
  "foreach($p in 8765..8780){try{$h=Invoke-RestMethod -Uri ('http://127.0.0.1:'+$p+'/api/health') -TimeoutSec 2;if([string]$h.version -eq '1.5.79-rc1-productive-resume-gate'){$port=$p;$health=$h;break}}catch{}};" ^
  "if($null -eq $port){Write-Host '[BLOQUEADO] No se encontro CEO 1.5.79 activo.';exit 6};" ^
  "Write-Host ('[OK] CEO 1.5.79 localizado en puerto '+$port);" ^
  "$base='http://127.0.0.1:'+$port;" ^
  "$endpoints=@{'state'='/api/state';'operations'='/api/operations';'queue'='/api/work-queue';'attention'='/api/attention';'executive_summary'='/api/executive-summary';'internal_release'='/api/internal-release/status';'update_status'='/api/update/status'};" ^
  "$result=[ordered]@{captured_at=(Get-Date).ToString('o');port=$port;health=$health;read_only=$true};" ^
  "foreach($k in $endpoints.Keys){try{$result[$k]=Invoke-RestMethod -Uri ($base+$endpoints[$k]) -TimeoutSec 15}catch{$result[$k]=@{error=$_.Exception.Message}}};" ^
  "$json=$result|ConvertTo-Json -Depth 30;" ^
  "[System.IO.File]::WriteAllText('%OUTFILE%',$json,[System.Text.UTF8Encoding]::new($false));" ^
  "Write-Host '[OK] Diagnostico guardado:';" ^
  "Write-Host '%OUTFILE%';" ^
  "exit 0"

set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo No se ha modificado nada.
  pause
  exit /b %RC%
)

echo ============================================================
echo   DIAGNOSTICO SOLO LECTURA COMPLETADO
echo ============================================================
echo.
echo Adjunta en este chat el archivo:
echo %OUTFILE%
echo.
explorer.exe /select,"%OUTFILE%"
pause
exit /b 0
