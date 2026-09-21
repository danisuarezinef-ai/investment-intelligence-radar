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
$driver=Join-Path $base "windows_chatgpt_cdp_driver.ps1"
$recipe=Join-Path $base "recipes\chatgpt_web.json"
$login=Join-Path $base "open_chatgpt_profile.ps1"

Write-Host "=== B19-B20: gate de programación por ChatGPT web ==="
Write-Host "Se creará un repositorio sandbox desechable con un bug intencional."

$loginArgs=@(
  "-NoProfile","-ExecutionPolicy","Bypass","-File",$login,
  "-ProfileDir",$ProfileDir,"-Port",[string]$Port,
  "-TimeoutSeconds","300","-RecipePath",$recipe,"-DriverPath",$driver
)
& powershell.exe @loginArgs
if($LASTEXITCODE -ne 0){throw "La sesión de ChatGPT web no quedó preparada"}

$python=(Get-Command python.exe -ErrorAction SilentlyContinue)
if(-not $python){$python=(Get-Command py.exe -ErrorAction SilentlyContinue)}
if(-not $python){throw "Python no encontrado"}

$args=@(
  (Join-Path $base "run_b20_code_gate.py"),
  "--profile-dir",$ProfileDir,
  "--port",[string]$Port,
  "--timeout",[string]$TimeoutSeconds
)
& $python.Source @args
if($LASTEXITCODE -ne 0){throw "B20 no superado"}

Write-Host "[PASS] ChatGPT web propuso el cambio, CEO lo aplicó sólo en sandbox y los tests pasaron."
Write-Host "[PASS] No commit, push ni merge del cambio generado."
