param(
  [string]$ProfileDir = "",
  [int]$Port = 9227,
  [int]$TimeoutSeconds = 180,
  [string]$ResultPath = ""
)

$ErrorActionPreference="Stop"
$base=Split-Path -Parent $MyInvocation.MyCommand.Path
$profileHelper=Join-Path $base "open_chatgpt_profile.ps1"
$restartGate=Join-Path $base "run_browser_restart_gate.ps1"
$driver=Join-Path $base "windows_chatgpt_cdp_driver.ps1"
$recipe=Join-Path $base "recipes\chatgpt_web.json"

if(-not $ProfileDir){
  $local=$env:LOCALAPPDATA
  if(-not $local){$local=$env:TEMP}
  $ProfileDir=Join-Path $local "CEO de IAs\browser-profile"
}
if(-not $ResultPath){
  $local=$env:LOCALAPPDATA
  if(-not $local){$local=$env:TEMP}
  $evidence=Join-Path $local "CEO de IAs\evidence"
  New-Item -ItemType Directory -Force -Path $evidence | Out-Null
  $ResultPath=Join-Path $evidence "W14B_REAL_CHATGPT_SESSION.json"
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ResultPath) | Out-Null

function Read-JsonFile([string]$path){
  if(-not (Test-Path $path)){return $null}
  try{return Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json}catch{return $null}
}

function Write-Failure([string]$stage,[string]$detail){
  $row=[ordered]@{
    schema_version=1
    generated_at=(Get-Date).ToString("s")
    ok=$false
    status="W14B_REAL_SESSION_PENDING_OR_FAILED"
    stage=$stage
    provider="chatgpt-web"
    profile_dir=$ProfileDir
    api_calls=0
    paid_api_calls=0
    real_chatgpt_verified=$false
    windows_physical_verified=$false
    detail=$detail
  }
  $row | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $ResultPath
  Write-Host "[NO-GO] W14-B no queda certificado."
  Write-Host ("[ETAPA] " + $stage)
  Write-Host ("[DETALLE] " + $detail)
  Write-Host ("[EVIDENCIA] " + $ResultPath)
}

$stage="START"
try {
  foreach($p in @($profileHelper,$restartGate,$driver,$recipe)){
    if(-not (Test-Path $p)){throw "Falta componente W14-B: $p"}
  }

  Write-Host "==============================================================="
  Write-Host " CEO DE IAs - W14-B SESION REAL CHATGPT / REINICIO / 0 APIs"
  Write-Host "==============================================================="
  Write-Host "Si ChatGPT solicita acceso, inicia sesion manualmente."
  Write-Host "CEO NO intenta saltarse CAPTCHA ni 2FA."
  Write-Host "La prueba cerrara y reabrira el navegador de CEO."
  Write-Host ""

  $stage="SESSION_PREPARE"
  $loginArgs=@(
    "-NoProfile","-ExecutionPolicy","Bypass","-File",$profileHelper,
    "-ProfileDir",$ProfileDir,
    "-Port",[string]$Port,
    "-TimeoutSeconds","300",
    "-RecipePath",$recipe,
    "-DriverPath",$driver,
    "-CloseBrowserAfter"
  )
  & powershell.exe @loginArgs
  if($LASTEXITCODE -ne 0){throw "La sesion real de ChatGPT no quedo preparada"}

  $markerPath=Join-Path $ProfileDir "CEO_BROWSER_PROFILE.json"
  $sessionPath=Join-Path $ProfileDir "CEO_BROWSER_SESSION.json"
  $marker=Read-JsonFile $markerPath
  $sessionBefore=Read-JsonFile $sessionPath
  if(-not $marker -or -not $marker.exclusive_profile){throw "Perfil exclusivo CEO no verificado"}
  if(-not $sessionBefore -or -not $sessionBefore.ok -or $sessionBefore.status -ne "SESSION_READY"){
    throw "SESSION_READY no demostrado antes del reinicio"
  }

  $stage="RESTART_TWO_TURN_GATE"
  $restartResult=Join-Path (Split-Path -Parent $ResultPath) "W14B_BROWSER_RESTART_DETAIL.json"
  $restartArgs=@(
    "-NoProfile","-ExecutionPolicy","Bypass","-File",$restartGate,
    "-ProfileDir",$ProfileDir,
    "-Port",[string]$Port,
    "-TimeoutSeconds",[string]$TimeoutSeconds,
    "-ResultPath",$restartResult
  )
  & powershell.exe @restartArgs
  if($LASTEXITCODE -ne 0){throw "El gate de cierre/reapertura y continuidad fallo"}
  $restart=Read-JsonFile $restartResult
  if(-not $restart -or -not $restart.ok){throw "Evidencia de reinicio ausente o invalida"}
  if($restart.status -ne "BROWSER_RESTART_SAME_CONVERSATION_PASS"){throw "Estado de reinicio inesperado"}
  if(-not $restart.browser_closed_between_turns -or -not $restart.browser_relaunched){throw "No se demostro cierre/reapertura real"}
  if(-not $restart.same_conversation){throw "La conversacion cambio tras relanzar Chrome"}
  if([int]$restart.api_calls -ne 0 -or [int]$restart.paid_api_calls -ne 0){throw "La prueba reporto uso de API"}

  $stage="POST_RESTART_SESSION_PROBE"
  $probeArgs=@(
    "-NoProfile","-ExecutionPolicy","Bypass","-File",$driver,
    "-RecipePath",$recipe,
    "-ProfileDir",$ProfileDir,
    "-Port",[string]$Port,
    "-TimeoutSeconds","45",
    "-SessionProbeOnly",
    "-CloseBrowserAfter"
  )
  $raw=& powershell.exe @probeArgs
  $probeCode=$LASTEXITCODE
  if(-not $raw){throw "Probe final sin salida"}
  $probe=$raw | ConvertFrom-Json
  if($probeCode -ne 0 -or -not $probe.ok -or $probe.status -ne "SESSION_READY"){
    throw "La sesion no siguio lista despues del cierre/reapertura"
  }

  $result=[ordered]@{
    schema_version=1
    generated_at=(Get-Date).ToString("s")
    ok=$true
    status="W14B_REAL_CHATGPT_SESSION_PASS"
    stage="COMPLETE"
    provider="chatgpt-web"
    profile_dir=$ProfileDir
    profile_exclusive=[bool]$marker.exclusive_profile
    pre_restart_session_ready=$true
    browser_closed_between_turns=[bool]$restart.browser_closed_between_turns
    browser_relaunched=[bool]$restart.browser_relaunched
    same_conversation=[bool]$restart.same_conversation
    conversation_url=[string]$restart.conversation_url
    post_restart_session_ready=$true
    api_calls=0
    paid_api_calls=0
    manual_login_only=$true
    captcha_bypass=$false
    two_factor_bypass=$false
    real_chatgpt_verified=$true
    windows_physical_verified=$true
    restart_detail=$restartResult
    detail=""
  }
  $result | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $ResultPath
  Write-Host ""
  Write-Host "[PASS] W14-B: sesion real ChatGPT persistente tras cierre/reapertura."
  Write-Host "[PASS] Misma conversacion y 0 APIs."
  Write-Host "[EVIDENCIA] $ResultPath"
  exit 0
}
catch {
  $detail=($_.Exception.Message | Out-String).Trim()
  if(-not $detail){$detail=($_ | Out-String).Trim()}
  Write-Failure $stage $detail
  exit 7
}
