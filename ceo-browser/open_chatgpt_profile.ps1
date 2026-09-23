param(
  [string]$ProfileDir = "",
  [int]$Port = 9227,
  [int]$TimeoutSeconds = 300,
  [string]$RecipePath = "",
  [string]$DriverPath = "",
  [string]$TargetUrl = "",
  [switch]$CloseBrowserAfter
)
$ErrorActionPreference="Stop"

if(-not $ProfileDir){
  $base=$env:LOCALAPPDATA
  if(-not $base){$base=$env:TEMP}
  $ProfileDir=Join-Path $base "CEO de IAs\browser-profile"
}
New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

$marker=Join-Path $ProfileDir "CEO_BROWSER_PROFILE.json"
$createdAt=(Get-Date).ToString("s")
if(Test-Path $marker){
  try{
    $existingMarker=Get-Content -Raw -Encoding UTF8 $marker | ConvertFrom-Json
    if($existingMarker.created_at){$createdAt=[string]$existingMarker.created_at}
  }catch{}
}
# W14-A: the marker is a contract, not user-editable truth. Reassert the
# invariants every time so a stale/corrupt marker cannot silently downgrade
# profile exclusivity or redirect CEO to a different browser profile.
$profile=[ordered]@{
  schema_version=1
  owner="CEO de IAs"
  exclusive_profile=$true
  provider_surface="chatgpt-web"
  profile_dir=$ProfileDir
  created_at=$createdAt
  validated_at=(Get-Date).ToString("s")
  no_api_required=$true
}
$profile | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $marker

$baseDir=Split-Path -Parent $MyInvocation.MyCommand.Path
if(-not $DriverPath){$DriverPath=Join-Path $baseDir "windows_chatgpt_cdp_driver.ps1"}
if(-not $RecipePath){$RecipePath=Join-Path $baseDir "recipes\chatgpt_web.json"}
if(-not (Test-Path $DriverPath)){throw "Browser driver not found: $DriverPath"}
if(-not (Test-Path $RecipePath)){throw "ChatGPT recipe not found: $RecipePath"}

$statusPath=Join-Path $ProfileDir "CEO_BROWSER_SESSION.json"
Write-Host "CEO abrirá la IA web con su perfil exclusivo."
Write-Host "Si aparece la pantalla de acceso, inicia sesión manualmente. CEO no intenta saltarse CAPTCHA ni 2FA."

$args=@(
  "-NoProfile","-ExecutionPolicy","Bypass","-File",$DriverPath,
  "-RecipePath",$RecipePath,
  "-ProfileDir",$ProfileDir,
  "-Port",[string]$Port,
  "-TimeoutSeconds",[string]$TimeoutSeconds,
  "-SessionProbeOnly",
  "-AllowManualLogin"
)
if($TargetUrl){$args+=@("-ConversationUrl",$TargetUrl)}
if($CloseBrowserAfter){$args+=@("-CloseBrowserAfter")}

$raw=& powershell.exe @args
$exit=$LASTEXITCODE
try{$row=$raw | ConvertFrom-Json}catch{$row=$null}

if($row){
  $out=[ordered]@{
    generated_at=(Get-Date).ToString("s")
    ok=[bool]$row.ok
    status=[string]$row.status
    session_state=[string]$row.session_state
    logged_in_evidence=[bool]$row.logged_in_evidence
    profile_dir=$ProfileDir
    provider=[string]$row.provider
    no_api_required=$true
    input_strategy=[string]$row.input_strategy
  }
  $out | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $statusPath
}

if($exit -ne 0 -or -not $row -or -not $row.ok){
  $detail=if($row){$row.detail}else{"No structured session result returned"}
  throw "Web AI session not ready: $detail"
}

Write-Host "[OK] Perfil persistente preparado: $ProfileDir"
Write-Host "[OK] Estado de sesión: $($row.session_state)"
Write-Host "[OK] API requerida: NO"
