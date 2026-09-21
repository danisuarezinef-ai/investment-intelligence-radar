param(
  [string]$ProfileDir = "",
  [int]$PreferredPort = 9227,
  [int]$TimeoutSeconds = 180
)
$ErrorActionPreference="Stop"
$base=Split-Path -Parent $MyInvocation.MyCommand.Path
if(-not $ProfileDir){
  $local=$env:LOCALAPPDATA
  if(-not $local){$local=$env:TEMP}
  $ProfileDir=Join-Path $local "CEO de IAs\browser-profile"
}
$python=(Get-Command python.exe -ErrorAction SilentlyContinue)
if(-not $python){$python=(Get-Command py.exe -ErrorAction SilentlyContinue)}
if(-not $python){throw "Python no encontrado"}

Write-Host "=========================================================="
Write-Host " CEO DE IAs - PRIMERA CAMPANA FUNCIONAL B29-B30"
Write-Host "=========================================================="
Write-Host "Este lanzador abre una sola sesion de navegador y NO ejecuta B38 automaticamente."
Write-Host "No actualiza CEO estable, no hace merge y no usa APIs."

$args=@(
  (Join-Path $base "first_trial_orchestrator.py"),
  "--profile-dir",$ProfileDir,
  "--preferred-port",[string]$PreferredPort,
  "--timeout",[string]$TimeoutSeconds
)
& $python.Source @args
if($LASTEXITCODE -ne 0){
  Write-Host ""
  Write-Host "[NO-GO] La primera prueba de autodesarrollo sigue bloqueada."
  exit $LASTEXITCODE
}
Write-Host ""
Write-Host "[GO] Preflight y B29-B30 superados."
Write-Host "[SEPARACION] B38 NO se ha iniciado."
Write-Host "Cuando quieras lanzar la primera prueba real, ejecuta EJECUTAR_B38_CANDIDATE.cmd."
