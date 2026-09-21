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

$token1="CEO_BROWSER_RESTART_TURN_1_OK"
$token2="CEO_BROWSER_RESTART_TURN_2_OK"
$t1=Invoke-Turn -Prompt "Responde únicamente con $token1" -CloseAfter
if(([string]$t1.response) -notmatch [regex]::Escape($token1)){throw "Turno 1 incorrecto"}
$conversation=[string]$t1.conversation_url
if(-not $conversation){throw "No se obtuvo URL de conversación"}
Start-Sleep -Seconds 2

$t2=Invoke-Turn -Prompt "Continúa en esta misma conversación y responde únicamente con $token2" -ConversationUrl $conversation -CloseAfter
if(([string]$t2.response) -notmatch [regex]::Escape($token2)){throw "Turno 2 incorrecto"}
$same=([string]$t2.conversation_url -eq $conversation)
if(-not $same){throw "La conversación cambió tras relanzar Chrome"}

$result=[ordered]@{
  schema_version=1
  generated_at=(Get-Date).ToString("s")
  ok=$true
  status="BROWSER_RESTART_SAME_CONVERSATION_PASS"
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
}
$result | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $ResultPath
Write-Host "[PASS] Chrome cerrado y relanzado entre turnos conservando conversación."
Write-Host "[EVIDENCIA] $ResultPath"
