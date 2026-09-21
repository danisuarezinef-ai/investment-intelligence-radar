param(
  [string]$ProfileDir = "",
  [int]$Port = 9227,
  [int]$TimeoutSeconds = 180,
  [string]$ResultPath = ""
)

$ErrorActionPreference="Stop"
$baseDir=Split-Path -Parent $MyInvocation.MyCommand.Path
$driver=Join-Path $baseDir "windows_chatgpt_cdp_driver.ps1"
$recipe=Join-Path $baseDir "recipes\chatgpt_web.json"
$loginHelper=Join-Path $baseDir "open_chatgpt_profile.ps1"

if(-not $ProfileDir){
  $local=$env:LOCALAPPDATA
  if(-not $local){$local=$env:TEMP}
  $ProfileDir=Join-Path $local "CEO de IAs\browser-profile"
}
if(-not $ResultPath){
  $local=$env:LOCALAPPDATA
  if(-not $local){$local=$env:TEMP}
  $evidenceDir=Join-Path $local "CEO de IAs\evidence"
  New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
  $ResultPath=Join-Path $evidenceDir "B09_B14_PHYSICAL_GATE.json"
}

function Invoke-Driver([string]$prompt,[string]$conversationUrl=""){
  $args=@(
    "-NoProfile","-ExecutionPolicy","Bypass","-File",$driver,
    "-RecipePath",$recipe,
    "-Prompt",$prompt,
    "-ProfileDir",$ProfileDir,
    "-Port",[string]$Port,
    "-TimeoutSeconds",[string]$TimeoutSeconds
  )
  if($conversationUrl){
    $args+=@("-ConversationUrl",$conversationUrl,"-NoLaunch")
  }
  $raw=& powershell.exe @args
  $code=$LASTEXITCODE
  if(-not $raw){throw "Browser driver returned no output"}
  try{$row=$raw | ConvertFrom-Json}catch{throw "Browser driver returned invalid JSON: $raw"}
  if($code -ne 0 -or -not $row.ok){
    $status=if($row.status){$row.status}else{"ERROR"}
    $detail=if($row.detail){$row.detail}else{$raw}
    throw ($status + ": " + $detail)
  }
  return $row
}

Write-Host ""
Write-Host "=== CEO B09-B14: gate físico ChatGPT web, 0 APIs ==="
Write-Host "Se usará el perfil persistente exclusivo de CEO."
Write-Host "Si ChatGPT pide acceso, inicia sesión manualmente una sola vez."
Write-Host ""

$loginArgs=@(
  "-NoProfile","-ExecutionPolicy","Bypass","-File",$loginHelper,
  "-ProfileDir",$ProfileDir,
  "-Port",[string]$Port,
  "-TimeoutSeconds","300",
  "-RecipePath",$recipe,
  "-DriverPath",$driver
)
& powershell.exe @loginArgs
if($LASTEXITCODE -ne 0){throw "La sesión web de CEO no quedó preparada"}

$turn1Token="CEO_BROWSER_TURN_1_OK"
$turn2Token="CEO_BROWSER_TURN_2_OK"
$prompt1="Responde únicamente con el texto $turn1Token"
$prompt2="Sin cambiar de conversación, responde únicamente con el texto $turn2Token"

$t1=Invoke-Driver $prompt1
if(([string]$t1.response) -notmatch [regex]::Escape($turn1Token)){
  throw "B14 turno 1 no devolvió el token esperado"
}
if(-not $t1.submission_verified -or -not $t1.generation_started -or -not $t1.conversation_stable){
  throw "B14 turno 1 carece de evidencia B10/B11/B13"
}
$conversation=[string]$t1.conversation_url
if(-not $conversation){throw "B13 no devolvió URL de conversación"}

$t2=Invoke-Driver $prompt2 $conversation
if(([string]$t2.response) -notmatch [regex]::Escape($turn2Token)){
  throw "B14 turno 2 no devolvió el token esperado"
}
if(-not $t2.submission_verified -or -not $t2.generation_started -or -not $t2.conversation_stable){
  throw "B14 turno 2 carece de evidencia B10/B11/B13"
}

$result=[ordered]@{
  schema_version=1
  phase="B09-B14"
  generated_at=(Get-Date).ToString("s")
  ok=$true
  status="B14_REAL_CHATGPT_TWO_TURN_PASS"
  provider="chatgpt-web"
  api_calls=0
  paid_api_calls=0
  profile_dir=$ProfileDir
  conversation_url=[string]$t2.conversation_url
  same_conversation=([string]$t2.conversation_url -eq $conversation)
  turn_1=[ordered]@{
    response=[string]$t1.response
    response_chars=[int]$t1.response_chars
    typed_chars=[int]$t1.typed_chars
    send_method=[string]$t1.send_method
    completion_reason=[string]$t1.completion_reason
  }
  turn_2=[ordered]@{
    response=[string]$t2.response
    response_chars=[int]$t2.response_chars
    typed_chars=[int]$t2.typed_chars
    send_method=[string]$t2.send_method
    completion_reason=[string]$t2.completion_reason
  }
}
$result | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $ResultPath

Write-Host ""
Write-Host "[PASS] B09-B14 superado en ChatGPT web real."
Write-Host "[PASS] Dos turnos, misma conversación, 0 llamadas API."
Write-Host "[EVIDENCIA] $ResultPath"
