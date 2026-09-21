param(
  [string]$ProfileDir = "",
  [int]$Port = 9227,
  [int]$TimeoutSeconds = 180,
  [string]$ResultPath = ""
)
$ErrorActionPreference="Stop"
$base=Split-Path -Parent $MyInvocation.MyCommand.Path
$driver=Join-Path $base "windows_chatgpt_cdp_driver.ps1"
$recipe=Join-Path $base "recipes\chatgpt_web.json"
$login=Join-Path $base "open_chatgpt_profile.ps1"

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
  $ResultPath=Join-Path $evidence "BROWSER_RESTART_GATE.json"
}

$loginArgs=@(
  "-NoProfile","-ExecutionPolicy","Bypass","-File",$login,
  "-ProfileDir",$ProfileDir,
  "-Port",[string]$Port,
  "-TimeoutSeconds","300",
  "-RecipePath",$recipe,
  "-DriverPath",$driver
)
& powershell.exe @loginArgs
if($LASTEXITCODE -ne 0){throw "No se pudo preparar la sesión persistente"}

function Invoke-Turn(
  [string]$Prompt,
  [string]$ConversationUrl = "",
  [switch]$CloseAfter
){
  $args=@(
    "-NoProfile","-ExecutionPolicy","Bypass","-File",$driver,
    "-RecipePath",$recipe,
    "-Prompt",$Prompt,
    "-ProfileDir",$ProfileDir,
    "-Port",[string]$Port,
    "-TimeoutSeconds",[string]$TimeoutSeconds
  )
  if($ConversationUrl){
    # Intentionally no -NoLaunch: B26 must be able to relaunch Chrome.
    $args+=@("-ConversationUrl",$ConversationUrl)
  }
  if($CloseAfter){$args+=@("-CloseBrowserAfter")}
  $raw=& powershell.exe @args
  $code=$LASTEXITCODE
  if(-not $raw){throw "Browser driver returned no output"}
  $row=$raw | ConvertFrom-Json
  if($code -ne 0 -or -not $row.ok){
    throw (($row.status | Out-String).Trim() + ": " + (($row.detail | Out-String).Trim()))
  }
  return $row
}

$stage="START"
try {
  $token1="CEO_BROWSER_RESTART_TURN_1_OK"
  $token2="CEO_BROWSER_RESTART_TURN_2_OK"

  $stage="TURN_1"
  $t1=Invoke-Turn -Prompt "Responde únicamente con $token1" -CloseAfter
  if(([string]$t1.response) -notmatch [regex]::Escape($token1)){throw "Turno 1 incorrecto"}
  $conversation=[string]$t1.conversation_url
  if(-not $conversation){throw "No se obtuvo URL de conversación"}
  Start-Sleep -Seconds 2

  $stage="TURN_2_RELAUNCH"
  $t2=Invoke-Turn -Prompt "Continúa en esta misma conversación y responde únicamente con $token2" -ConversationUrl $conversation -CloseAfter
  if(([string]$t2.response) -notmatch [regex]::Escape($token2)){throw "Turno 2 incorrecto"}

  $stage="SAME_CONVERSATION_CHECK"
  $same=([string]$t2.conversation_url -eq $conversation)
  if(-not $same){throw "La conversación cambió tras relanzar Chrome"}

  $result=[ordered]@{
    schema_version=2
    generated_at=(Get-Date).ToString("s")
    ok=$true
    status="BROWSER_RESTART_SAME_CONVERSATION_PASS"
    stage="COMPLETE"
    provider="chatgpt-web"
    api_calls=0
    paid_api_calls=0
    profile_dir=$ProfileDir
    port=$Port
    browser_closed_between_turns=$true
    browser_relaunched=$true
    same_conversation=$same
    conversation_url=[string]$t2.conversation_url
    turn_1_response=[string]$t1.response
    turn_2_response=[string]$t2.response
    detail=""
  }
  $result | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $ResultPath
  Write-Host "[PASS] Chrome cerrado y relanzado entre turnos conservando conversación."
  Write-Host "[EVIDENCIA] $ResultPath"
  exit 0
}
catch {
  $detail=($_.Exception.Message | Out-String).Trim()
  if(-not $detail){$detail=($_ | Out-String).Trim()}
  $result=[ordered]@{
    schema_version=2
    generated_at=(Get-Date).ToString("s")
    ok=$false
    status="BROWSER_RESTART_RESILIENCE_DEGRADED"
    stage=$stage
    provider="chatgpt-web"
    api_calls=0
    paid_api_calls=0
    profile_dir=$ProfileDir
    port=$Port
    browser_closed_between_turns=($stage -ne "START" -and $stage -ne "TURN_1")
    browser_relaunched=($stage -eq "SAME_CONVERSATION_CHECK")
    same_conversation=$false
    conversation_url=""
    detail=$detail
  }
  $result | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $ResultPath
  Write-Host "[WARN] Reinicio de navegador no verificado."
  Write-Host ("[ETAPA] " + $stage)
  Write-Host ("[DETALLE] " + $detail)
  Write-Host ("[EVIDENCIA] " + $ResultPath)
  exit 5
}
