param(
  [string]$ProfileDir = "",
  [int]$Port = 9227,
  [int]$TimeoutSeconds = 180
)
$ErrorActionPreference="Stop"
$base=Split-Path -Parent $MyInvocation.MyCommand.Path
if(-not $ProfileDir){
  $local=$env:LOCALAPPDATA
  if(-not $local){$local=$env:TEMP}
  $ProfileDir=Join-Path $local "CEO de IAs\browser-profile"
}

Write-Host "=== B38: primer candidato real de autodesarrollo por ChatGPT web ==="
Write-Host "Requisito: B29-B30 debe haber dejado BROWSER_FIELD_VERIFIED=true."
Write-Host "El código original NO se modifica. El candidato se crea en una copia aislada."

$python=(Get-Command python.exe -ErrorAction SilentlyContinue)
if(-not $python){$python=(Get-Command py.exe -ErrorAction SilentlyContinue)}
if(-not $python){throw "Python no encontrado"}

$args=@(
  (Join-Path $base "run_b38_real_ceo_candidate.py"),
  "--profile-dir",$ProfileDir,
  "--port",[string]$Port,
  "--timeout",[string]$TimeoutSeconds
)
& $python.Source @args
if($LASTEXITCODE -ne 0){throw "B38 no superado"}

Write-Host ""
Write-Host "[PASS] B38: candidato real de CEO generado y verificado en copia aislada."
Write-Host "[LÍMITE] No se ha hecho commit, push, merge ni actualización de CEO."
Write-Host "[SIGUIENTE] El parche queda preparado exclusivamente para revisión humana."
