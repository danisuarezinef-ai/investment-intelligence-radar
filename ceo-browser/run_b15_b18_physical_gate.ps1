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

Write-Host "=== B15-B18: primera tarea real con artefacto ==="
Write-Host "Se reutilizará la sesión web persistente de CEO."

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
  (Join-Path $base "run_b15_b18_physical_task.py"),
  "--profile-dir",$ProfileDir,
  "--port",[string]$Port,
  "--timeout",[string]$TimeoutSeconds
)
& $python.Source @args
if($LASTEXITCODE -ne 0){throw "B15-B18 no superado"}
Write-Host "[PASS] CEO obtuvo la respuesta web y guardó/verificó el artefacto."
