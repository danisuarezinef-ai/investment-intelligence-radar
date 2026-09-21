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

function Run-Gate([string]$name,[string]$script){
  Write-Host ""
  Write-Host "=== $name ==="
  $args=@(
    "-NoProfile","-ExecutionPolicy","Bypass","-File",(Join-Path $base $script),
    "-ProfileDir",$ProfileDir,
    "-Port",[string]$Port,
    "-TimeoutSeconds",[string]$TimeoutSeconds
  )
  & powershell.exe @args
  if($LASTEXITCODE -ne 0){throw "$name failed"}
}

Run-Gate "B14 conversación real" "run_b09_b14_physical_gate.ps1"
Run-Gate "B18 artefacto real" "run_b15_b18_physical_gate.ps1"
Run-Gate "B20 programación real" "run_b20_code_gate.ps1"

$python=(Get-Command python.exe -ErrorAction SilentlyContinue)
if(-not $python){$python=(Get-Command py.exe -ErrorAction SilentlyContinue)}
if(-not $python){throw "Python no encontrado"}
& $python.Source (Join-Path $base "finalize_browser_field.py")
if($LASTEXITCODE -ne 0){throw "B30 field qualification failed"}

Write-Host ""
Write-Host "[PASS] B29-B30: BROWSER_FIELD_VERIFIED=true"
Write-Host "[PASS] ChatGPT web + artefacto + programación, sin APIs."
Write-Host "[LÍMITE] Esto NO autoriza merge, producción ni compras automáticas."
